from __future__ import annotations

from io import BytesIO
import hashlib
import re
from typing import Any

from fastapi import HTTPException
from .inventory_store import import_inventory_rows


MAX_IMPORT_BYTES = 15 * 1024 * 1024
MAX_IMPORT_ROWS = 10000
MAX_PREVIEW_ROWS = 75

_HEADER_ALIASES = {
    "ENV": "environment",
    "ENVIRONMENT": "environment",
    "IP": "ip_address",
    "IPADDRESS": "ip_address",
    "HOSTNAME": "hostname",
    "HOST": "hostname",
    "APPLICATION": "application",
    "APPLICATIONNAME": "application",
    "TYPE": "asset_type",
    "SERVERTYPE": "asset_type",
    "APPNAME": "app_name",
    "APPLICATIONAPPNAME": "app_name",
    "SSHUSERNAME": "ssh_username",
    "SSHUSER": "ssh_username",
    "SSHPASSWORD": "ssh_password",
    "APPLICATIONUSERNAME": "application_username",
    "APPUSERNAME": "application_username",
    "APPLICATIONPASSWORD": "application_password",
    "APPPASSWORD": "application_password",
    "CONSOLEDETAILS": "console_details",
    "CONSOLE": "console_details",
    "NOTES": "notes",
    "COMMENTS": "notes",
}

_REQUIRED_COLUMNS = {"environment", "ip_address", "application"}


def _normalise_header(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]+", "", str(value or "").strip().upper())


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _detect_header_row(sheet) -> tuple[int, dict[int, str]]:
    best_row = 0
    best_mapping: dict[int, str] = {}
    best_score = 0

    for row_number, row in enumerate(sheet.iter_rows(min_row=1, max_row=min(sheet.max_row, 20), values_only=True), start=1):
        mapping: dict[int, str] = {}
        for index, value in enumerate(row):
            normalised = _normalise_header(value)
            field = _HEADER_ALIASES.get(normalised)
            if field:
                mapping[index] = field

        score = len(set(mapping.values()))
        if score > best_score:
            best_row = row_number
            best_mapping = mapping
            best_score = score

    missing = _REQUIRED_COLUMNS - set(best_mapping.values())
    if not best_row or missing:
        raise HTTPException(
            status_code=400,
            detail=(
                "Unable to detect the inventory header row. "
                f"Required columns: ENV, IP, APPLICATION. Missing: {', '.join(sorted(missing)) or 'unknown'}"
            ),
        )
    return best_row, best_mapping


def parse_inventory_workbook(content: bytes) -> dict[str, Any]:
    try:
        from openpyxl import load_workbook
    except ModuleNotFoundError as exc:
        raise HTTPException(
            status_code=503,
            detail="Excel inventory import dependency is unavailable. Rebuild the backend image with backend/requirements.txt.",
        ) from exc

    if not content:
        raise HTTPException(status_code=400, detail="Excel file is empty")
    if len(content) > MAX_IMPORT_BYTES:
        raise HTTPException(status_code=413, detail="Inventory Excel file must be 15 MB or smaller")

    try:
        from openpyxl import load_workbook
    except ModuleNotFoundError as exc:
        raise HTTPException(
            status_code=503,
            detail="Excel import dependency is unavailable. Rebuild the backend image with openpyxl installed.",
        ) from exc

    try:
        workbook = load_workbook(filename=BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Unable to read Excel workbook: {exc}") from exc

    sheet = workbook.active
    header_row, mapping = _detect_header_row(sheet)

    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    file_signatures: dict[tuple[str, ...], int] = {}

    for row_number, values in enumerate(
        sheet.iter_rows(min_row=header_row + 1, values_only=True),
        start=header_row + 1,
    ):
        record = {
            "source_row": row_number,
            "environment": "",
            "ip_address": "",
            "hostname": "",
            "application": "",
            "asset_type": "",
            "app_name": "",
            "ssh_username": "",
            "ssh_password": "",
            "application_username": "",
            "application_password": "",
            "console_details": "",
            "notes": "",
        }

        for column_index, field in mapping.items():
            if column_index < len(values):
                record[field] = _cell_text(values[column_index])

        if not any(
            record[key]
            for key in (
                "environment",
                "ip_address",
                "hostname",
                "application",
                "asset_type",
                "app_name",
                "ssh_username",
                "application_username",
                "console_details",
                "notes",
            )
        ):
            continue

        row_warnings: list[str] = []

        if not record["environment"]:
            row_warnings.append("Missing ENV")
        if not record["ip_address"] and not record["hostname"]:
            row_warnings.append("Both IP and HOSTNAME are blank")
        if not record["application"]:
            record["application"] = "UNASSIGNED"
            row_warnings.append("Blank APPLICATION will be imported as UNASSIGNED")

        signature = (
            record["application"].upper(),
            record["environment"].upper(),
            record["ip_address"].lower(),
            record["hostname"].lower(),
            record["asset_type"].lower(),
            record["app_name"].lower(),
        )
        file_signatures[signature] = file_signatures.get(signature, 0) + 1

        record["warnings"] = row_warnings
        rows.append(record)
        if len(rows) > MAX_IMPORT_ROWS:
            workbook.close()
            raise HTTPException(
                status_code=413,
                detail=f"Inventory workbook contains more than {MAX_IMPORT_ROWS} data rows",
            )

    workbook.close()

    for record in rows:
        signature = (
            record["application"].upper(),
            record["environment"].upper(),
            record["ip_address"].lower(),
            record["hostname"].lower(),
            record["asset_type"].lower(),
            record["app_name"].lower(),
        )
        if file_signatures.get(signature, 0) > 1:
            record["warnings"].append("Possible duplicate row in workbook")

    if not rows:
        raise HTTPException(status_code=400, detail="No inventory data rows were found in the Excel workbook")

    for record in rows:
        for warning in record["warnings"]:
            warnings.append(f"Row {record['source_row']}: {warning}")

    return {
        "sheet_name": sheet.title,
        "header_row": header_row,
        "rows": rows,
        "warnings": warnings,
        "file_sha256": hashlib.sha256(content).hexdigest(),
    }


def preview_inventory_workbook(content: bytes) -> dict[str, Any]:
    parsed = parse_inventory_workbook(content)
    rows = parsed["rows"]

    applications = sorted({str(row["application"]).strip().upper() for row in rows if row["application"]})
    environments = sorted({str(row["environment"]).strip().upper() for row in rows if row["environment"]})

    ready = [
        row
        for row in rows
        if row["environment"] and (row["ip_address"] or row["hostname"])
    ]
    invalid = len(rows) - len(ready)

    preview_rows = [
        {
            "source_row": row["source_row"],
            "environment": row["environment"],
            "ip_address": row["ip_address"],
            "hostname": row["hostname"],
            "application": row["application"],
            "asset_type": row["asset_type"],
            "app_name": row["app_name"],
            "ssh_username": row["ssh_username"],
            "ssh_password_configured": bool(row["ssh_password"]),
            "application_username": row["application_username"],
            "application_password_configured": bool(row["application_password"]),
            "console_details": row["console_details"],
            "notes": row["notes"],
            "warnings": row["warnings"],
        }
        for row in rows[:MAX_PREVIEW_ROWS]
    ]

    return {
        "file_sha256": parsed["file_sha256"],
        "sheet_name": parsed["sheet_name"],
        "header_row": parsed["header_row"],
        "total_rows": len(rows),
        "ready_rows": len(ready),
        "invalid_rows": invalid,
        "application_count": len(applications),
        "environment_count": len(environments),
        "applications": applications,
        "environments": environments,
        "warning_count": len(parsed["warnings"]),
        "warnings": parsed["warnings"][:100],
        "preview_rows": preview_rows,
        "preview_truncated": len(rows) > MAX_PREVIEW_ROWS,
    }


def commit_inventory_workbook(content: bytes, actor: str) -> dict[str, Any]:
    parsed = parse_inventory_workbook(content)
    result = import_inventory_rows(parsed["rows"], actor)
    return {
        "file_sha256": parsed["file_sha256"],
        "sheet_name": parsed["sheet_name"],
        "total_rows": len(parsed["rows"]),
        **result,
    }

_MS_HEADER_ALIASES = {
    "GROUP": "group",
    "GROUPNAME": "group",
    "SERVICE": "service",
    "SERVICENAME": "service",
    "APPLICATIONSERVICENAME": "service",
    "ENV": "environment",
    "ENVIRONMENT": "environment",
    "DBURL": "db_url",
    "DATABASEURL": "db_url",
    "DBNAME": "db_name",
    "DATABASENAME": "db_name",
    "DBUSERNAME": "db_username",
    "DATABASEUSERNAME": "db_username",
    "DBUSER": "db_username",
    "DBPASSWORD": "db_password",
    "DATABASEPASSWORD": "db_password",
    "CONNECTION": "connection_name",
    "CONNECTIONNAME": "connection_name",
    "DBCONNECTION": "connection_name",
    "NOTES": "notes",
    "COMMENTS": "notes",
}

_MS_REQUIRED_COLUMNS = {"group", "service", "environment"}


def _detect_header_row_with_aliases(sheet, aliases: dict[str, str], required: set[str]) -> tuple[int, dict[int, str]]:
    best_row = 0
    best_mapping: dict[int, str] = {}
    best_score = 0
    for row_number, row in enumerate(sheet.iter_rows(min_row=1, max_row=min(sheet.max_row, 20), values_only=True), start=1):
        mapping: dict[int, str] = {}
        for index, value in enumerate(row):
            field = aliases.get(_normalise_header(value))
            if field:
                mapping[index] = field
        score = len(set(mapping.values()))
        if score > best_score:
            best_row = row_number
            best_mapping = mapping
            best_score = score
    missing = required - set(best_mapping.values())
    if not best_row or missing:
        raise HTTPException(
            status_code=400,
            detail=f"Unable to detect the Microservices inventory header row. Missing: {', '.join(sorted(missing)) or 'unknown'}",
        )
    return best_row, best_mapping


def parse_microservice_workbook(content: bytes) -> dict[str, Any]:
    try:
        from openpyxl import load_workbook
    except ModuleNotFoundError as exc:
        raise HTTPException(
            status_code=503,
            detail="Excel inventory import dependency is unavailable. Rebuild the backend image with backend/requirements.txt.",
        ) from exc

    if not content:
        raise HTTPException(status_code=400, detail="Excel file is empty")
    if len(content) > MAX_IMPORT_BYTES:
        raise HTTPException(status_code=413, detail="Inventory Excel file must be 15 MB or smaller")

    try:
        workbook = load_workbook(filename=BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Unable to read Excel workbook: {exc}") from exc

    sheet = workbook.active
    header_row, mapping = _detect_header_row_with_aliases(sheet, _MS_HEADER_ALIASES, _MS_REQUIRED_COLUMNS)
    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    seen: dict[tuple[str, ...], int] = {}

    for row_number, values in enumerate(sheet.iter_rows(min_row=header_row + 1, values_only=True), start=header_row + 1):
        record = {
            "source_row": row_number,
            "group": "",
            "service": "",
            "environment": "",
            "connection_name": "PRIMARY",
            "db_url": "",
            "db_name": "",
            "db_username": "",
            "db_password": "",
            "notes": "",
        }
        for column_index, field in mapping.items():
            if column_index < len(values):
                record[field] = _cell_text(values[column_index])

        if not any(str(record[key]).strip() for key in ("group", "service", "environment", "db_url", "db_name", "db_username", "notes")):
            continue

        row_warnings: list[str] = []
        if not record["group"]:
            row_warnings.append("Missing GROUP")
        if not record["service"]:
            row_warnings.append("Missing SERVICE")
        if not record["environment"]:
            row_warnings.append("Missing ENV")
        if not record["db_url"]:
            row_warnings.append("DB URL is blank")
        if not record["db_name"]:
            row_warnings.append("DB NAME is blank")
        if not record["db_username"]:
            row_warnings.append("DB USERNAME is blank")
        if not record["connection_name"]:
            record["connection_name"] = "PRIMARY"

        signature = (
            str(record["group"]).strip().upper(),
            str(record["service"]).strip().lower(),
            str(record["environment"]).strip().upper(),
            str(record["connection_name"]).strip().upper(),
        )
        seen[signature] = seen.get(signature, 0) + 1
        record["warnings"] = row_warnings
        rows.append(record)
        if len(rows) > MAX_IMPORT_ROWS:
            workbook.close()
            raise HTTPException(status_code=413, detail=f"Inventory workbook contains more than {MAX_IMPORT_ROWS} data rows")

    workbook.close()

    if not rows:
        raise HTTPException(status_code=400, detail="No Microservices inventory rows were found in the Excel workbook")

    for record in rows:
        signature = (
            str(record["group"]).strip().upper(),
            str(record["service"]).strip().lower(),
            str(record["environment"]).strip().upper(),
            str(record["connection_name"]).strip().upper(),
        )
        if seen.get(signature, 0) > 1:
            record["warnings"].append("Possible duplicate group/service/environment/connection row in workbook")
        for warning in record["warnings"]:
            warnings.append(f"Row {record['source_row']}: {warning}")

    return {
        "sheet_name": sheet.title,
        "header_row": header_row,
        "rows": rows,
        "warnings": warnings,
        "file_sha256": hashlib.sha256(content).hexdigest(),
    }


def preview_microservice_workbook(content: bytes) -> dict[str, Any]:
    parsed = parse_microservice_workbook(content)
    rows = parsed["rows"]
    ready = [row for row in rows if row["group"] and row["service"] and row["environment"]]
    groups = sorted({str(row["group"]).strip() for row in rows if row["group"]})
    services = sorted({str(row["service"]).strip() for row in rows if row["service"]})
    environments = sorted({str(row["environment"]).strip().upper() for row in rows if row["environment"]})

    return {
        "file_sha256": parsed["file_sha256"],
        "sheet_name": parsed["sheet_name"],
        "header_row": parsed["header_row"],
        "total_rows": len(rows),
        "ready_rows": len(ready),
        "invalid_rows": len(rows) - len(ready),
        "group_count": len(groups),
        "service_count": len(services),
        "environment_count": len(environments),
        "groups": groups,
        "services": services,
        "environments": environments,
        "warning_count": len(parsed["warnings"]),
        "warnings": parsed["warnings"][:100],
        "preview_rows": [
            {
                "source_row": row["source_row"],
                "group": row["group"],
                "service": row["service"],
                "environment": row["environment"],
                "connection_name": row["connection_name"],
                "db_url": row["db_url"],
                "db_name": row["db_name"],
                "db_username": row["db_username"],
                "db_password_configured": bool(row["db_password"]),
                "notes": row["notes"],
                "warnings": row["warnings"],
            }
            for row in rows[:MAX_PREVIEW_ROWS]
        ],
        "preview_truncated": len(rows) > MAX_PREVIEW_ROWS,
    }


def commit_microservice_workbook(content: bytes, actor: str) -> dict[str, Any]:
    from .inventory_microservices import import_microservice_rows

    parsed = parse_microservice_workbook(content)
    result = import_microservice_rows(parsed["rows"], actor)
    return {
        "file_sha256": parsed["file_sha256"],
        "sheet_name": parsed["sheet_name"],
        "total_rows": len(parsed["rows"]),
        **result,
    }

