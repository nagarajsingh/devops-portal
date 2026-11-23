from __future__ import annotations

from typing import Any

from .inventory_export import _audit_export, _pdf_bytes, _workbook_bytes
from .inventory_patching import list_assets


PATCH_HEADERS = [
    "IP / CLUSTER NAME",
    "HOSTNAME",
    "APPLICATION",
    "APPLICATION OWNER",
    "TYPE",
    "ENVIRONMENT",
    "PATCH CLASS",
    "SOURCE",
    "CYCLE",
    "PREVIOUS PATCHED DATE",
    "PLANNED DATE",
    "STATUS",
    "APP TEAM APPROVAL",
    "CR NUMBER",
    "COMMENTS",
    "PATCH ROLE",
]


def _rows(
    cycle_id: int | None = None,
    environment_class: str = "",
    status: str = "",
) -> list[dict[str, Any]]:
    return list_assets(
        cycle_id=cycle_id,
        environment_class=environment_class,
        status=status,
    )


def export_patching_excel(
    actor: str,
    cycle_id: int | None = None,
    environment_class: str = "",
    status: str = "",
) -> bytes:
    assets = _rows(cycle_id, environment_class, status)
    rows = []
    for item in assets:
        activity = item.get("activity") or {}
        rows.append([
            item["asset_identifier"],
            item["hostname"],
            item["application"],
            item["application_owner"],
            item["asset_type"],
            item["environment_name"],
            item["environment_class"],
            item["source_type"],
            activity.get("cycle_code", ""),
            activity.get("previous_patched_date", ""),
            activity.get("planned_date", ""),
            activity.get("status", "NOT_STARTED"),
            activity.get("app_team_approval", ""),
            activity.get("cr_number", ""),
            activity.get("comments", ""),
            activity.get("patch_role", ""),
        ])
    _audit_export(
        actor,
        "PATCH_EXCEL_EXPORT",
        f"rows={len(rows)} cycle_id={cycle_id or 0} environment_class={environment_class or 'ALL'} status={status or 'ALL'}",
    )
    return _workbook_bytes("Patching Inventory", PATCH_HEADERS, rows)


def export_patching_pdf(
    actor: str,
    cycle_id: int | None = None,
    environment_class: str = "",
    status: str = "",
) -> bytes:
    assets = _rows(cycle_id, environment_class, status)
    headers = [
        "IP / Cluster",
        "Hostname",
        "Application",
        "Owner",
        "Type",
        "Class",
        "Cycle",
        "Previous",
        "Planned",
        "Status",
        "Approval",
        "CR",
    ]
    rows = []
    for item in assets:
        activity = item.get("activity") or {}
        rows.append([
            item["asset_identifier"],
            item["hostname"],
            item["application"],
            item["application_owner"],
            item["asset_type"],
            item["environment_class"],
            activity.get("cycle_code", ""),
            activity.get("previous_patched_date", ""),
            activity.get("planned_date", ""),
            activity.get("status", "NOT_STARTED"),
            activity.get("app_team_approval", ""),
            activity.get("cr_number", ""),
        ])
    _audit_export(
        actor,
        "PATCH_PDF_EXPORT",
        f"rows={len(rows)} cycle_id={cycle_id or 0} environment_class={environment_class or 'ALL'} status={status or 'ALL'}",
    )
    return _pdf_bytes("Patching Inventory", headers, rows)
