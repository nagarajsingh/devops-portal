from __future__ import annotations

from datetime import date, datetime
from io import BytesIO
import hashlib
import re
from typing import Any

from fastapi import HTTPException

from .inventory_patching import import_patching_rows


MAX_IMPORT_BYTES = 15 * 1024 * 1024
MAX_IMPORT_ROWS = 10000
MAX_PREVIEW_ROWS = 100

_HEADER_ALIASES = {
    "IPCLUSTERNAME": "asset_identifier",
    "IP": "asset_identifier",
    "CLUSTERNAME": "asset_identifier",
    "HOSTNAME": "hostname",
    "APPLICATION": "application",
    "APPLICATIONOWNER": "application_owner",
    "TYPE": "asset_type",
    "PREVIOUSPATCHEDDATE": "previous_patched_date",
    "PREVIOUSPATCHDATE": "previous_patched_date",
    "PREVIOUSPATCHEDDATEQ": "previous_patched_date",
    "PREVIOSPATCHEDDATE": "previous_patched_date",
    "PLANNEDDATE": "planned_date",
    "Q3STATUS": "status",
    "STATUS": "status",
    "APPTEAMAPPROVAL": "app_team_approval",
    "APPROVAL": "app_team_approval",
    "CRNUMBER": "cr_number",
    "CRNO": "cr_number",
    "COMMENTS": "comments",
    "COMMENT": "comments",
    "PATCHROLE": "patch_role",
    "ROLE": "patch_role",
}


def _normalise(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]+", "", str(value or "").strip().upper())


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value).strip()


def _date_value(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text or text.upper() in {"NOT DONE", "N/A", "NA", "-", "NONE"}:
        return None
    for fmt in ("%d-%b-%Y", "%d-%b-%y", "%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _section_from_row(values: tuple[Any, ...]) -> str | None:
    joined = " ".join(_text(value).upper() for value in values if _text(value))
    if "DISASTER RECOVERY ENVIRONMENT" in joined:
        return "DR"
    if "NON-PRODUCTION ENVIRONMENT" in joined or "NON PRODUCTION ENVIRONMENT" in joined:
        return "NON_PROD"
    if "PRODUCTION ENVIRONMENT" in joined and "NON" not in joined:
        return "PROD"
    return None


def _header_mapping(values: tuple[Any, ...]) -> dict[int, str]:
    mapping: dict[int, str] = {}
    for index, value in enumerate(values):
        key = _normalise(value)
        field = _HEADER_ALIASES.get(key)
        if field:
            mapping[index] = field
    return mapping


def parse_patching_workbook(content: bytes) -> dict[str, Any]:
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
        raise HTTPException(status_code=413, detail="Patching Excel file must be 15 MB or smaller")

    try:
        workbook = load_workbook(filename=BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Unable to read patching Excel workbook: {exc}") from exc

    sheet = workbook.active
    cycle_code = ""
    cycle_pattern = re.compile(r"Q([1-4])[-\s]?(20\d{2})", re.IGNORECASE)

    for values in sheet.iter_rows(min_row=1, max_row=min(sheet.max_row, 25), values_only=True):
        joined = " ".join(_text(value) for value in values if _text(value))
        match = cycle_pattern.search(joined)
        if match:
            cycle_code = f"Q{match.group(1)}-{match.group(2)}"
            break

    if not cycle_code:
        workbook.close()
        raise HTTPException(status_code=400, detail="Unable to detect patch cycle. Expected a title such as Q3-2026 PATCHING TRACKER")

    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    current_section: str | None = None
    mapping: dict[int, str] = {}

    for row_number, values in enumerate(sheet.iter_rows(values_only=True), start=1):
        joined_upper = " ".join(_text(value).upper() for value in values if _text(value))
        if "STATUS LEGEND" in joined_upper or "ENVIRONMENT COLORS" in joined_upper:
            break

        section = _section_from_row(values)
        if section:
            current_section = section
            mapping = {}
            continue

        detected = _header_mapping(values)
        if len(set(detected.values())) >= 5 and "asset_identifier" in detected.values():
            mapping = detected
            continue

        if not current_section or not mapping:
            continue

        record: dict[str, Any] = {
            "source_row": row_number,
            "environment_class": current_section,
            "environment_name": "NON-PROD" if current_section == "NON_PROD" else current_section,
            "asset_identifier": "",
            "hostname": "",
            "application": "",
            "application_owner": "",
            "asset_type": "",
            "previous_patched_date": None,
            "planned_date": None,
            "status": "NOT_STARTED",
            "app_team_approval": "",
            "cr_number": "",
            "comments": "",
            "patch_role": "",
            "warnings": [],
        }

        for index, field in mapping.items():
            if index >= len(values):
                continue
            value = values[index]
            if field in {"previous_patched_date", "planned_date"}:
                record[field] = _date_value(value)
            else:
                record[field] = _text(value)

        if not any(record[key] for key in ("asset_identifier", "hostname", "application", "asset_type")):
            continue

        if not record["asset_identifier"] and not record["hostname"]:
            record["warnings"].append("Both IP / Cluster Name and Hostname are blank")

        if not record["application"]:
            record["warnings"].append("Application is blank")

        # Some trackers place Primary / Secondary / DR in an unnamed trailing cell.
        if not record["patch_role"]:
            mapped_indexes = set(mapping.keys())
            trailing = [
                _text(value)
                for index, value in enumerate(values)
                if index not in mapped_indexes and _text(value).upper() in {"PRIMARY", "SECONDARY", "SECONDRY", "DR"}
            ]
            if trailing:
                record["patch_role"] = trailing[-1]

        rows.append(record)
        if len(rows) > MAX_IMPORT_ROWS:
            workbook.close()
            raise HTTPException(status_code=413, detail=f"Patching workbook contains more than {MAX_IMPORT_ROWS} data rows")

    workbook.close()

    if not rows:
        raise HTTPException(status_code=400, detail="No patching server rows were found in the workbook")

    for row in rows:
        for warning in row["warnings"]:
            warnings.append(f"Row {row['source_row']}: {warning}")

    return {
        "cycle_code": cycle_code,
        "sheet_name": sheet.title,
        "rows": rows,
        "warnings": warnings,
        "file_sha256": hashlib.sha256(content).hexdigest(),
    }


def preview_patching_workbook(content: bytes) -> dict[str, Any]:
    parsed = parse_patching_workbook(content)
    rows = parsed["rows"]
    environment_counts = {"NON_PROD": 0, "PROD": 0, "DR": 0}
    status_counts: dict[str, int] = {}
    for row in rows:
        environment_counts[row["environment_class"]] = environment_counts.get(row["environment_class"], 0) + 1
        status = str(row.get("status") or "NOT_STARTED").strip() or "NOT_STARTED"
        status_counts[status] = status_counts.get(status, 0) + 1

    return {
        "file_sha256": parsed["file_sha256"],
        "sheet_name": parsed["sheet_name"],
        "cycle_code": parsed["cycle_code"],
        "total_rows": len(rows),
        "environment_counts": environment_counts,
        "status_counts": status_counts,
        "warning_count": len(parsed["warnings"]),
        "warnings": parsed["warnings"][:100],
        "preview_rows": [
            {
                **{key: value for key, value in row.items() if key not in {"previous_patched_date", "planned_date"}},
                "previous_patched_date": row["previous_patched_date"].isoformat() if row["previous_patched_date"] else "",
                "planned_date": row["planned_date"].isoformat() if row["planned_date"] else "",
            }
            for row in rows[:MAX_PREVIEW_ROWS]
        ],
        "preview_truncated": len(rows) > MAX_PREVIEW_ROWS,
    }


def commit_patching_workbook(content: bytes, actor: str) -> dict[str, Any]:
    parsed = parse_patching_workbook(content)
    result = import_patching_rows(parsed["rows"], parsed["cycle_code"], actor)
    return {
        "file_sha256": parsed["file_sha256"],
        "sheet_name": parsed["sheet_name"],
        "total_rows": len(parsed["rows"]),
        **result,
    }
