from __future__ import annotations

from io import BytesIO
from typing import Any

from fastapi import HTTPException
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

from .inventory_microservices import list_configurations
from .inventory_store import _audit, list_records
from .user_store import session_factory


GTB_HEADERS = [
    "APPLICATION",
    "ENV",
    "IP",
    "HOSTNAME",
    "TYPE",
    "APP NAME",
    "SSH USERNAME",
    "SSH PASSWORD",
    "APPLICATION USERNAME",
    "APPLICATION PASSWORD",
    "CONSOLE DETAILS",
    "NOTES",
    "UPDATED BY",
    "UPDATED AT",
]

MS_HEADERS = [
    "GROUP",
    "SERVICE",
    "ENV",
    "CONNECTION NAME",
    "DB URL",
    "DB NAME",
    "DB USERNAME",
    "DB PASSWORD",
    "NOTES",
    "UPDATED BY",
    "UPDATED AT",
]


def _audit_export(actor: str, action: str, detail: str) -> None:
    factory = session_factory()
    with factory() as db:
        _audit(db, None, action, actor, detail)
        db.commit()


def _workbook_bytes(title: str, headers: list[str], rows: list[list[Any]]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = title[:31]
    sheet.freeze_panes = "A2"

    for column_index, header in enumerate(headers, start=1):
        cell = sheet.cell(row=1, column=column_index, value=header)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="24496F")

    for row in rows:
        sheet.append(row)

    for column_cells in sheet.columns:
        width = min(
            max((len(str(cell.value or "")) for cell in column_cells), default=10) + 2,
            55,
        )
        sheet.column_dimensions[column_cells[0].column_letter].width = max(12, width)

    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def export_gtb_excel(
    actor: str,
    application_id: int | None = None,
    environment_id: int | None = None,
) -> bytes:
    records = list_records(application_id=application_id, environment_id=environment_id)
    rows = [
        [
            item["application_name"],
            item["environment_name"],
            item["ip_address"],
            item["hostname"],
            item["asset_type"],
            item["app_name"],
            item["ssh_username"],
            "Configured" if item["ssh_password_configured"] else "Not configured",
            item["application_username"],
            "Configured" if item["application_password_configured"] else "Not configured",
            item["console_details"],
            item["notes"],
            item["updated_by"],
            item["updated_at"],
        ]
        for item in records
    ]
    _audit_export(actor, "EXCEL_EXPORT", f"GTB rows={len(rows)} application_id={application_id or 0} environment_id={environment_id or 0}")
    return _workbook_bytes("GTB Inventory", GTB_HEADERS, rows)


def export_microservices_excel(
    actor: str,
    group_id: int | None = None,
    service_id: int | None = None,
    environment_id: int | None = None,
) -> bytes:
    configurations = list_configurations(service_id=service_id, environment_id=environment_id)
    if group_id:
        configurations = [item for item in configurations if item["group_id"] == group_id]
    rows = [
        [
            item["group_name"],
            item["service_name"],
            item["environment_name"],
            item["connection_name"],
            item["db_url"],
            item["db_name"],
            item["db_username"],
            "Configured" if item["db_password_configured"] else "Not configured",
            item["notes"],
            item["updated_by"],
            item["updated_at"],
        ]
        for item in configurations
    ]
    _audit_export(actor, "EXCEL_EXPORT", f"MICROSERVICES rows={len(rows)} group_id={group_id or 0} service_id={service_id or 0} environment_id={environment_id or 0}")
    return _workbook_bytes("Microservices Inventory", MS_HEADERS, rows)


def _pdf_bytes(title: str, headers: list[str], rows: list[list[Any]]) -> bytes:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ModuleNotFoundError as exc:
        raise HTTPException(
            status_code=503,
            detail="PDF export dependency is unavailable. Rebuild the backend image with backend/requirements.txt.",
        ) from exc

    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=landscape(A4),
        leftMargin=18,
        rightMargin=18,
        topMargin=22,
        bottomMargin=22,
        title=title,
    )
    styles = getSampleStyleSheet()
    story = [Paragraph(title, styles["Title"]), Spacer(1, 10)]

    safe_rows = []
    for row in rows:
        safe_rows.append([
            Paragraph(str(value or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"), styles["BodyText"])
            for value in row
        ])

    table_data = [
        [Paragraph(f"<b>{header}</b>", styles["BodyText"]) for header in headers],
        *safe_rows,
    ]
    available_width = landscape(A4)[0] - 36
    column_width = available_width / max(1, len(headers))
    table = Table(table_data, repeatRows=1, colWidths=[column_width] * len(headers), hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#24496F")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CCD5DE")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTSIZE", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(table)
    document.build(story)
    return output.getvalue()


def export_gtb_pdf(
    actor: str,
    application_id: int | None = None,
    environment_id: int | None = None,
) -> bytes:
    records = list_records(application_id=application_id, environment_id=environment_id)
    headers = ["APPLICATION", "ENV", "IP", "HOSTNAME", "TYPE", "APP NAME", "SSH USER", "SSH PWD", "APP USER", "APP PWD", "CONSOLE"]
    rows = [
        [
            item["application_name"],
            item["environment_name"],
            item["ip_address"],
            item["hostname"],
            item["asset_type"],
            item["app_name"],
            item["ssh_username"],
            "Configured" if item["ssh_password_configured"] else "No",
            item["application_username"],
            "Configured" if item["application_password_configured"] else "No",
            item["console_details"],
        ]
        for item in records
    ]
    _audit_export(actor, "PDF_EXPORT", f"GTB rows={len(rows)} application_id={application_id or 0} environment_id={environment_id or 0}")
    return _pdf_bytes("GTB Inventory", headers, rows)


def export_microservices_pdf(
    actor: str,
    group_id: int | None = None,
    service_id: int | None = None,
    environment_id: int | None = None,
) -> bytes:
    configurations = list_configurations(service_id=service_id, environment_id=environment_id)
    if group_id:
        configurations = [item for item in configurations if item["group_id"] == group_id]
    headers = ["GROUP", "SERVICE", "ENV", "CONNECTION", "DB URL", "DB NAME", "DB USER", "DB PWD", "NOTES"]
    rows = [
        [
            item["group_name"],
            item["service_name"],
            item["environment_name"],
            item["connection_name"],
            item["db_url"],
            item["db_name"],
            item["db_username"],
            "Configured" if item["db_password_configured"] else "No",
            item["notes"],
        ]
        for item in configurations
    ]
    _audit_export(actor, "PDF_EXPORT", f"MICROSERVICES rows={len(rows)} group_id={group_id or 0} service_id={service_id or 0} environment_id={environment_id or 0}")
    return _pdf_bytes("Microservices Inventory", headers, rows)
