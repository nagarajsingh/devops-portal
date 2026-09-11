from __future__ import annotations

import html
import os
import smtplib
import ssl
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any

import jwt

from .config import (
    APPROVAL_TOKEN_HOURS,
    JWT_ALGORITHM,
    JWT_SECRET,
    MAIL_BCC,
    MAIL_FROM,
    PORTAL_PUBLIC_URL,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_SSL,
    SMTP_STARTTLS,
    SMTP_TIMEOUT_SECONDS,
    SMTP_USERNAME,
)
from .logging_config import get_logger

logger = get_logger("deployment-notifications")


def _split_addresses(value: str) -> list[str]:
    return [item.strip() for item in value.replace(";", ",").split(",") if item.strip()]


def _devops_recipients() -> list[str]:
    return _split_addresses(
        os.getenv("DEPLOYMENT_DEVOPS_MAIL_TO", os.getenv("MAIL_TO", ""))
    )


def _request_url(request_id: str) -> str:
    return (
        f"{PORTAL_PUBLIC_URL.rstrip('/')}/deployment-management?request={request_id}"
        if PORTAL_PUBLIC_URL
        else ""
    )


def _create_owner_action_token(request_id: str, owner: str, decision: str) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": owner,
            "request_id": request_id,
            "decision": decision,
            "purpose": "deployment-owner-approval",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(hours=APPROVAL_TOKEN_HOURS)).timestamp()),
        },
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )


def decode_owner_action_token(token: str) -> dict[str, Any]:
    payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    if payload.get("purpose") != "deployment-owner-approval":
        raise ValueError("Invalid approval token purpose")
    if payload.get("decision") not in {"approve", "reject"}:
        raise ValueError("Invalid deployment decision")
    return payload


def _owner_action_url(request_id: str, owner: str, decision: str) -> str:
    if not PORTAL_PUBLIC_URL:
        return ""
    token = _create_owner_action_token(request_id, owner, decision)
    return f"{PORTAL_PUBLIC_URL.rstrip('/')}/api/deployment-management/approval-action?token={token}"


def _release_overview(row: dict[str, Any]) -> dict[str, Any]:
    overview: dict[str, Any] = {
        "application": row.get("application") or row.get("application_type") or "",
        "environment": row.get("country") or row.get("environment") or "",
        "branch": row.get("branch_name") or "",
        "repository": row.get("repository") or "",
        "services": row.get("collections_items") or [],
        "artifacts": (row.get("war_files") or []) + (row.get("jar_files") or []),
        "images": row.get("container_images") or [],
    }
    try:
        document_path = Path(str(row.get("document_path") or ""))
        if document_path.is_file():
            from .deployment_management import _structured_extract

            preview = _structured_extract(
                str(row.get("document_name") or document_path.name),
                document_path.read_bytes(),
                str(row.get("application_type") or ""),
                str(row.get("country") or ""),
            )
            overview.update(
                {
                    "application": preview.get("application") or overview["application"],
                    "environment": preview.get("environment") or overview["environment"],
                    "branch": preview.get("branch_name") or overview["branch"],
                    "repository": preview.get("repository") or overview["repository"],
                    "services": preview.get("collections_items") or overview["services"],
                    "artifacts": (preview.get("war_files") or []) + (preview.get("jar_files") or []) or overview["artifacts"],
                    "images": preview.get("container_images") or overview["images"],
                }
            )
    except Exception:
        logger.exception("Unable to build release overview request_id=%s", row.get("id"))
    return overview


def _smtp_client() -> smtplib.SMTP:
    if SMTP_SSL:
        return smtplib.SMTP_SSL(
            SMTP_HOST,
            SMTP_PORT,
            timeout=SMTP_TIMEOUT_SECONDS,
            context=ssl.create_default_context(),
        )
    return smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT_SECONDS)


def send_mail(subject: str, recipients: list[str], html_body: str) -> bool:
    recipients = list(dict.fromkeys(address.strip() for address in recipients if address.strip()))
    bcc = _split_addresses(MAIL_BCC)
    envelope_recipients = list(dict.fromkeys(recipients + bcc))

    if not SMTP_HOST or not MAIL_FROM or not recipients:
        logger.error(
            "Deployment email not sent subject=%s smtp_host_configured=%s mail_from_configured=%s recipients=%s",
            subject,
            bool(SMTP_HOST),
            bool(MAIL_FROM),
            recipients,
        )
        return False

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = MAIL_FROM
    message["To"] = ", ".join(recipients)
    message.set_content(
        "This is an automated notification from the DevOps Portal. "
        "Open the HTML version of this email for the release overview and approval actions."
    )
    message.add_alternative(html_body, subtype="html")

    try:
        with _smtp_client() as smtp:
            smtp.ehlo()
            if SMTP_STARTTLS and not SMTP_SSL:
                smtp.starttls(context=ssl.create_default_context())
                smtp.ehlo()
            if SMTP_USERNAME and SMTP_PASSWORD:
                smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
            smtp.send_message(
                message,
                from_addr=MAIL_FROM,
                to_addrs=envelope_recipients,
            )
        logger.info(
            "Deployment email sent subject=%s recipients=%s bcc_count=%s smtp_host=%s smtp_port=%s ssl=%s starttls=%s",
            subject,
            recipients,
            len(bcc),
            SMTP_HOST,
            SMTP_PORT,
            SMTP_SSL,
            SMTP_STARTTLS,
        )
        return True
    except Exception as exc:
        logger.exception(
            "Deployment email failed subject=%s recipients=%s smtp_host=%s smtp_port=%s ssl=%s starttls=%s error=%s",
            subject,
            recipients,
            SMTP_HOST,
            SMTP_PORT,
            SMTP_SSL,
            SMTP_STARTTLS,
            exc,
        )
        return False


def send_owner_approval_request(row: dict[str, Any]) -> bool:
    request_id = str(row.get("id") or "")
    owner = str(row.get("app_owner") or "").strip()
    portal_url = _request_url(request_id)

    if not owner:
        logger.error(
            "Deployment approval email not sent request_id=%s because app_owner is empty",
            request_id,
        )
        return False

    overview = _release_overview(row)
    approve_url = _owner_action_url(request_id, owner, "approve")
    reject_url = _owner_action_url(request_id, owner, "reject")
    services = overview.get("services") or []
    artifacts = overview.get("artifacts") or []
    images = overview.get("images") or []

    service_rows = "".join(
        "<tr>"
        f"<td style='padding:10px 12px;border-bottom:1px solid #edf0f4;font-weight:700;color:#294563'>{html.escape(str(item.get('service') or '—'))}</td>"
        f"<td style='padding:10px 12px;border-bottom:1px solid #edf0f4;color:#65758a;font-family:Consolas,monospace;font-size:12px'>{html.escape(str(item.get('vendor_image') or item.get('image_tag') or '—'))}</td>"
        "</tr>"
        for item in services[:20]
    )
    artifact_text = ", ".join(str(item) for item in artifacts[:12]) or "None detected"
    image_text = ", ".join(str(item) for item in images[:8]) or "None detected"

    safe_request_id = html.escape(request_id)
    safe_portal_url = html.escape(portal_url, quote=True)
    safe_approve_url = html.escape(approve_url, quote=True)
    safe_reject_url = html.escape(reject_url, quote=True)

    html_body = f"""
    <!doctype html>
    <html>
      <body style="margin:0;padding:0;background:#f4f6fa;font-family:Arial,Helvetica,sans-serif;color:#24334a">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#f4f6fa">
          <tr><td align="center" style="padding:32px 16px">
            <table role="presentation" width="720" cellspacing="0" cellpadding="0" border="0" style="width:100%;max-width:720px;background:#ffffff;border:1px solid #e7ebf0;border-radius:22px;overflow:hidden;box-shadow:0 18px 50px rgba(24,59,104,.10)">
              <tr><td style="padding:30px 34px;background:#173d70;background-image:linear-gradient(135deg,#173d70,#214f88 68%,#ef6b22 160%);color:#ffffff">
                <div style="font-size:11px;font-weight:800;letter-spacing:.14em;text-transform:uppercase;color:#ffbd8f">Release approval required</div>
                <h1 style="margin:12px 0 7px;font-size:28px;line-height:35px">{html.escape(str(row.get('application_type') or 'Deployment'))} release request</h1>
                <p style="margin:0;color:#dbe5f0;line-height:22px">Review the release overview below and approve or reject directly from this email.</p>
              </td></tr>

              <tr><td style="padding:28px 34px 10px">
                <div style="font-size:12px;font-weight:800;letter-spacing:.09em;text-transform:uppercase;color:#ef6b22;margin-bottom:12px">Release overview</div>
                <table width="100%" cellspacing="0" cellpadding="0" style="border:1px solid #e7ebf0;border-radius:14px;border-collapse:separate;overflow:hidden">
                  <tr><td style="padding:12px 14px;background:#fbfcfe;color:#7b8795;font-size:12px;font-weight:700;width:34%">Request ID</td><td style="padding:12px 14px;font-weight:800;color:#183b68">{safe_request_id}</td></tr>
                  <tr><td style="padding:12px 14px;background:#fbfcfe;color:#7b8795;font-size:12px;font-weight:700">Application</td><td style="padding:12px 14px">{html.escape(str(overview.get('application') or row.get('application_type') or '—'))}</td></tr>
                  <tr><td style="padding:12px 14px;background:#fbfcfe;color:#7b8795;font-size:12px;font-weight:700">Environment / Country</td><td style="padding:12px 14px">{html.escape(str(overview.get('environment') or '—'))}</td></tr>
                  <tr><td style="padding:12px 14px;background:#fbfcfe;color:#7b8795;font-size:12px;font-weight:700">Application owner</td><td style="padding:12px 14px">{html.escape(owner)}</td></tr>
                  <tr><td style="padding:12px 14px;background:#fbfcfe;color:#7b8795;font-size:12px;font-weight:700">Requested by</td><td style="padding:12px 14px">{html.escape(str(row.get('requested_by') or '—'))}</td></tr>
                  <tr><td style="padding:12px 14px;background:#fbfcfe;color:#7b8795;font-size:12px;font-weight:700">Document</td><td style="padding:12px 14px">{html.escape(str(row.get('document_name') or '—'))}</td></tr>
                  <tr><td style="padding:12px 14px;background:#fbfcfe;color:#7b8795;font-size:12px;font-weight:700">Branch</td><td style="padding:12px 14px">{html.escape(str(overview.get('branch') or 'Not applicable'))}</td></tr>
                  <tr><td style="padding:12px 14px;background:#fbfcfe;color:#7b8795;font-size:12px;font-weight:700">Artifacts</td><td style="padding:12px 14px">{html.escape(artifact_text)}</td></tr>
                  <tr><td style="padding:12px 14px;background:#fbfcfe;color:#7b8795;font-size:12px;font-weight:700">Container images</td><td style="padding:12px 14px;word-break:break-word">{html.escape(image_text)}</td></tr>
                </table>
              </td></tr>

              {f'''<tr><td style="padding:18px 34px 8px"><div style="font-size:12px;font-weight:800;letter-spacing:.09em;text-transform:uppercase;color:#ef6b22;margin-bottom:10px">Collections services · {len(services)} detected</div><table width="100%" cellspacing="0" cellpadding="0" style="border:1px solid #e7ebf0;border-radius:12px;border-collapse:separate;overflow:hidden"><tr><th align="left" style="padding:10px 12px;background:#fff6ef;color:#53677e;font-size:11px">Service</th><th align="left" style="padding:10px 12px;background:#fff6ef;color:#53677e;font-size:11px">Vendor image</th></tr>{service_rows}</table></td></tr>''' if services else ''}

              <tr><td align="center" style="padding:28px 34px 12px">
                <a href="{safe_approve_url}" style="display:inline-block;margin:0 5px 10px;padding:14px 24px;border-radius:11px;background:#ff7419;background-image:linear-gradient(90deg,#ff6516,#ff8d27);color:#ffffff;text-decoration:none;font-size:14px;font-weight:800">Approve release</a>
                <a href="{safe_reject_url}" style="display:inline-block;margin:0 5px 10px;padding:13px 24px;border:1px solid #e5b9b5;border-radius:11px;background:#fff5f4;color:#b83d36;text-decoration:none;font-size:14px;font-weight:800">Reject release</a>
              </td></tr>
              <tr><td align="center" style="padding:0 34px 26px">
                {f'<a href="{safe_portal_url}" style="color:#315b8a;font-size:12px;font-weight:700">Open full request in DevOps Portal</a>' if safe_portal_url else ''}
                <div style="margin-top:14px;color:#8793a2;font-size:11px;line-height:17px">Approval links are signed and expire in {APPROVAL_TOKEN_HOURS} hours. The request can only be actioned while owner approval is pending.</div>
              </td></tr>
              <tr><td style="padding:17px 34px;background:#f8fafc;border-top:1px solid #e7ebf0;color:#7b8795;font-size:11px;text-align:center">Mashreq NEO CORP · Internal DevOps Deployment Management</td></tr>
            </table>
          </td></tr>
        </table>
      </body>
    </html>
    """

    sent = send_mail(
        f"[Approval Required] Deployment Request {request_id}",
        [owner],
        html_body,
    )
    logger.info(
        "Deployment owner approval email result request_id=%s application_type=%s country=%s owner=%s sent=%s",
        request_id,
        row.get("application_type"),
        row.get("country"),
        owner,
        sent,
    )
    return sent


def send_devops_ready(row: dict[str, Any], bypassed: bool = False) -> bool:
    recipients = _devops_recipients()
    request_id = str(row.get("id") or "")
    url = _request_url(request_id)
    safe_url = html.escape(url, quote=True)

    html_body = f"""
    <h2>Deployment request ready for DevOps</h2>
    <p>{'Owner approval was bypassed by DevOps.' if bypassed else 'The application owner approved the request.'}</p>
    <table cellpadding="6">
      <tr><td><b>Request</b></td><td>{html.escape(request_id)}</td></tr>
      <tr><td><b>Application type</b></td><td>{html.escape(str(row.get('application_type', '')))}</td></tr>
      <tr><td><b>Country</b></td><td>{html.escape(str(row.get('country') or 'N/A'))}</td></tr>
      <tr><td><b>Document</b></td><td>{html.escape(str(row.get('document_name', '')))}</td></tr>
      <tr><td><b>Requested by</b></td><td>{html.escape(str(row.get('requested_by', '')))}</td></tr>
    </table>
    {f'<p><a href="{safe_url}">Open request in DevOps Portal</a></p>' if safe_url else ''}
    """
    return send_mail(
        f"[DevOps Action] Deployment Request {request_id}",
        recipients,
        html_body,
    )
