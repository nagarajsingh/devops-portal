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
_MS_STATIC_FIELDS = {"group", "service", "environment"}
_MS_CONNECTION_FIELDS = {
    "connection_name",
    "db_url",
    "db_name",
    "db_username",
    "db_password",
    "notes",
}


def _match_microservice_header(value: Any) -> tuple[str | None, str | None]:
    """Return (field, slot) for Microservices import headers.

    Static fields use slot=None. Database fields use a slot key so repeated
    column groups in the same Excel row can be expanded into separate DB
    configurations.

    Supported examples:
      DB URL / DB NAME / DB USERNAME / DB PASSWORD
      DB URL 1 / DB NAME 1 / ...
      DB URL 2 / DB NAME 2 / ...
      DB2 URL / DB2 NAME / DB2 USER / DB2 PASSWORD
      DB URL REPORTING / DB NAME REPORTING / ...
    """
    normalised = _normalise_header(value)
    if not normalised:
        return None, None

    direct = _MS_HEADER_ALIASES.get(normalised)
    if direct:
        if direct in _MS_STATIC_FIELDS:
            return direct, None
        return direct, "1"

    # Prefix form: DBURL2, DBNAME2, DBUSERNAME2, DBPASSWORD2,
    # CONNECTION2, NOTES2, or named suffixes such as DBURLREPORTING.
    prefix_aliases = (
        ("DATABASEUSERNAME", "db_username"),
        ("DATABASEPASSWORD", "db_password"),
        ("DATABASEURL", "db_url"),
        ("DATABASENAME", "db_name"),
        ("CONNECTIONNAME", "connection_name"),
        ("DBCONNECTION", "connection_name"),
        ("DBUSERNAME", "db_username"),
        ("DBPASSWORD", "db_password"),
        ("DBURL", "db_url"),
        ("DBNAME", "db_name"),
        ("DBUSER", "db_username"),
        ("CONNECTION", "connection_name"),
        ("COMMENTS", "notes"),
        ("NOTES", "notes"),
    )
    for prefix, field in prefix_aliases:
        if normalised.startswith(prefix) and len(normalised) > len(prefix):
            suffix = normalised[len(prefix):]
            if suffix:
                return field, suffix

    # Infix form: DB2URL, DB2NAME, DB2USERNAME, DB2USER, DB2PASSWORD.
    match = re.fullmatch(r"DB([A-Z0-9]+)(URL|NAME|USERNAME|USER|PASSWORD)", normalised)
    if match:
        slot, suffix = match.groups()
        field = {
            "URL": "db_url",
            "NAME": "db_name",
            "USERNAME": "db_username",
            "USER": "db_username",
            "PASSWORD": "db_password",
        }[suffix]
        return field, slot

    return None, None


def _detect_microservice_header_row(sheet) -> tuple[int, dict[int, tuple[str, str | None]]]:
    best_row = 0
    best_mapping: dict[int, tuple[str, str | None]] = {}
    best_score = -1

    for row_number, row in enumerate(
        sheet.iter_rows(min_row=1, max_row=min(sheet.max_row, 20), values_only=True),
        start=1,
    ):
        mapping: dict[int, tuple[str, str | None]] = {}
        direct_occurrences: dict[str, int] = {}

        for index, value in enumerate(row):
            field, slot = _match_microservice_header(value)
            if not field:
                continue

            # When identical unnumbered database headers are repeated, assign
            # occurrence slots consistently: first DB URL -> 1, second -> 2,
            # and the same for DB NAME / USERNAME / PASSWORD.
            if field in _MS_CONNECTION_FIELDS and slot == "1":
                normalised = _normalise_header(value)
                if normalised in _MS_HEADER_ALIASES:
                    occurrence = direct_occurrences.get(field, 0) + 1
                    direct_occurrences[field] = occurrence
                    slot = str(occurrence)

            mapping[index] = (field, slot)

        static_fields = {field for field, slot in mapping.values() if slot is None}
        connection_fields = {field for field, slot in mapping.values() if slot is not None}
        score = (len(static_fields) * 20) + len(connection_fields) + len(mapping)

        if score > best_score:
            best_row = row_number
            best_mapping = mapping
            best_score = score

    static_fields = {field for field, slot in best_mapping.values() if slot is None}
    missing = _MS_REQUIRED_COLUMNS - static_fields
    if not best_row or missing:
        raise HTTPException(
            status_code=400,
            detail=(
                "Unable to detect the Microservices inventory header row. "
                f"Missing: {', '.join(sorted(missing)) or 'unknown'}"
            ),
        )
    return best_row, best_mapping


def _microservice_slot_sort_key(slot: str) -> tuple[int, Any]:
    if str(slot).isdigit():
        return (0, int(slot))
    return (1, str(slot))


def _default_connection_name(slot: str) -> str:
    cleaned = str(slot or "1").strip().upper()
    if cleaned in {"", "1", "PRIMARY"}:
        return "PRIMARY"
    if cleaned.isdigit():
        return f"DB{cleaned}"
    return cleaned[:100]


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
    header_row, mapping = _detect_microservice_header_row(sheet)
    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    seen: dict[tuple[str, ...], int] = {}

    for row_number, values in enumerate(
        sheet.iter_rows(min_row=header_row + 1, values_only=True),
        start=header_row + 1,
    ):
        static_values = {
            "group": "",
            "service": "",
            "environment": "",
        }
        connection_values: dict[str, dict[str, str]] = {}

        for column_index, (field, slot) in mapping.items():
            if column_index >= len(values):
                continue
            value = _cell_text(values[column_index])
            if slot is None:
                static_values[field] = value
                continue
            connection_values.setdefault(
                slot,
                {
                    "connection_name": "",
                    "db_url": "",
                    "db_name": "",
                    "db_username": "",
                    "db_password": "",
                    "notes": "",
                },
            )
            connection_values[slot][field] = value

        if not any(str(value).strip() for value in static_values.values()) and not any(
            any(str(value).strip() for value in connection.values())
            for connection in connection_values.values()
        ):
            continue

        # If there are no DB-specific columns at all, preserve the old parser
        # behavior and emit one PRIMARY row so validation can show the blanks.
        if not connection_values:
            connection_values["1"] = {
                "connection_name": "",
                "db_url": "",
                "db_name": "",
                "db_username": "",
                "db_password": "",
                "notes": "",
            }

        emitted_for_source_row = 0
        for slot in sorted(connection_values, key=_microservice_slot_sort_key):
            connection = connection_values[slot]

            # Ignore completely empty secondary DB blocks. The first block is
            # retained for backward compatibility and validation warnings.
            has_connection_data = any(
                str(connection.get(field) or "").strip()
                for field in _MS_CONNECTION_FIELDS
            )
            if not has_connection_data and slot != "1":
                continue

            record = {
                "source_row": row_number,
                "source_connection": slot,
                "group": static_values["group"],
                "service": static_values["service"],
                "environment": static_values["environment"],
                "connection_name": (
                    str(connection.get("connection_name") or "").strip()
                    or _default_connection_name(slot)
                ),
                "db_url": connection.get("db_url", ""),
                "db_name": connection.get("db_name", ""),
                "db_username": connection.get("db_username", ""),
                "db_password": connection.get("db_password", ""),
                "notes": connection.get("notes", ""),
            }

            row_warnings: list[str] = []
            if not record["group"]:
                row_warnings.append("Missing GROUP")
            if not record["service"]:
                row_warnings.append("Missing SERVICE")
            if not record["environment"]:
                row_warnings.append("Missing ENV")
            if not record["db_url"]:
                row_warnings.append(f"{record['connection_name']}: DB URL is blank")
            if not record["db_name"]:
                row_warnings.append(f"{record['connection_name']}: DB NAME is blank")
            if not record["db_username"]:
                row_warnings.append(f"{record['connection_name']}: DB USERNAME is blank")

            signature = (
                str(record["group"]).strip().upper(),
                str(record["service"]).strip().lower(),
                str(record["environment"]).strip().upper(),
                str(record["connection_name"]).strip().upper(),
                str(record["db_name"]).strip().lower(),
            )
            seen[signature] = seen.get(signature, 0) + 1
            record["warnings"] = row_warnings
            rows.append(record)
            emitted_for_source_row += 1

            if len(rows) > MAX_IMPORT_ROWS:
                workbook.close()
                raise HTTPException(
                    status_code=413,
                    detail=f"Inventory workbook expands to more than {MAX_IMPORT_ROWS} database connections",
                )

        if emitted_for_source_row == 0 and any(str(value).strip() for value in static_values.values()):
            record = {
                "source_row": row_number,
                "source_connection": "1",
                "group": static_values["group"],
                "service": static_values["service"],
                "environment": static_values["environment"],
                "connection_name": "PRIMARY",
                "db_url": "",
                "db_name": "",
                "db_username": "",
                "db_password": "",
                "notes": "",
                "warnings": ["No populated database connection block was found"],
            }
            signature = (
                str(record["group"]).strip().upper(),
                str(record["service"]).strip().lower(),
                str(record["environment"]).strip().upper(),
                "PRIMARY",
                "",
            )
            seen[signature] = seen.get(signature, 0) + 1
            rows.append(record)

    workbook.close()

    if not rows:
        raise HTTPException(status_code=400, detail="No Microservices inventory rows were found in the Excel workbook")

    for record in rows:
        signature = (
            str(record["group"]).strip().upper(),
            str(record["service"]).strip().lower(),
            str(record["environment"]).strip().upper(),
            str(record["connection_name"]).strip().upper(),
            str(record["db_name"]).strip().lower(),
        )
        if seen.get(signature, 0) > 1:
            record["warnings"].append("Possible duplicate group/service/environment/connection/DB name row in workbook")
        for warning in record["warnings"]:
            warnings.append(
                f"Row {record['source_row']} / {record['connection_name']}: {warning}"
            )

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
                "source_connection": row.get("source_connection", "1"),
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

