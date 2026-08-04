from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from typing import Any

from .logging_config import get_logger

logger = get_logger("deployment-notifications")


def _split_addresses(value: str) -> list[str]:
    return [item.strip() for item in value.replace(";", ",").split(",") if item.strip()]


def _smtp_settings() -> dict[str, Any]:
    return {
        "host": os.getenv("SMTP_HOST", "").strip(),
        "port": int(os.getenv("SMTP_PORT", "25")),
        "username": os.getenv("SMTP_USERNAME", "").strip(),
        "password": os.getenv("SMTP_PASSWORD", ""),
        "starttls": os.getenv("SMTP_STARTTLS", "false").strip().lower() in {"1", "true", "yes", "y"},
        "sender": os.getenv("MAIL_FROM", "").strip(),
        "devops_to": _split_addresses(os.getenv("DEPLOYMENT_DEVOPS_MAIL_TO", os.getenv("MAIL_TO", ""))),
        "portal_url": os.getenv("DEVOPS_PORTAL_URL", "").rstrip("/"),
    }


def send_mail(subject: str, recipients: list[str], html: str) -> bool:
    settings = _smtp_settings()
    recipients = [address for address in recipients if address]
    if not settings["host"] or not settings["sender"] or not recipients:
        logger.warning(
            "Deployment email skipped subject=%s smtp_host=%s sender=%s recipients=%s",
            subject,
            bool(settings["host"]),
            bool(settings["sender"]),
            recipients,
        )
        return False

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings["sender"]
    message["To"] = ", ".join(recipients)
    message.set_content("This message requires an HTML-capable mail client.")
    message.add_alternative(html, subtype="html")

    try:
        with smtplib.SMTP(settings["host"], settings["port"], timeout=30) as smtp:
            smtp.ehlo()
            if settings["starttls"]:
                smtp.starttls()
                smtp.ehlo()
            if settings["username"]:
                smtp.login(settings["username"], settings["password"])
            smtp.send_message(message)
        logger.info("Deployment email sent subject=%s recipients=%s", subject, recipients)
        return True
    except Exception:
        logger.exception("Deployment email failed subject=%s recipients=%s", subject, recipients)
        return False


def _request_url(request_id: str) -> str:
    base = _smtp_settings()["portal_url"]
    return f"{base}/deployment-management?request={request_id}" if base else ""


def send_owner_approval_request(row: dict[str, Any]) -> bool:
    request_id = str(row.get("id") or "")
    owner = str(row.get("app_owner") or "").strip()
    url = _request_url(request_id)
    html = f"""
    <h2>Deployment approval required</h2>
    <p>A deployment request is waiting for your approval.</p>
    <table cellpadding="6">
      <tr><td><b>Request</b></td><td>{request_id}</td></tr>
      <tr><td><b>Application type</b></td><td>{row.get('application_type', '')}</td></tr>
      <tr><td><b>Country</b></td><td>{row.get('country') or 'N/A'}</td></tr>
      <tr><td><b>Document</b></td><td>{row.get('document_name', '')}</td></tr>
      <tr><td><b>Requested by</b></td><td>{row.get('requested_by', '')}</td></tr>
    </table>
    {f'<p><a href="{url}">Open request in DevOps Portal</a></p>' if url else ''}
    """
    return send_mail(f"[Approval Required] Deployment Request {request_id}", [owner], html)


def send_devops_ready(row: dict[str, Any], bypassed: bool = False) -> bool:
    settings = _smtp_settings()
    request_id = str(row.get("id") or "")
    url = _request_url(request_id)
    html = f"""
    <h2>Deployment request ready for DevOps</h2>
    <p>{'Owner approval was bypassed by DevOps.' if bypassed else 'The application owner approved the request.'}</p>
    <table cellpadding="6">
      <tr><td><b>Request</b></td><td>{request_id}</td></tr>
      <tr><td><b>Application type</b></td><td>{row.get('application_type', '')}</td></tr>
      <tr><td><b>Country</b></td><td>{row.get('country') or 'N/A'}</td></tr>
      <tr><td><b>Document</b></td><td>{row.get('document_name', '')}</td></tr>
      <tr><td><b>Requested by</b></td><td>{row.get('requested_by', '')}</td></tr>
    </table>
    {f'<p><a href="{url}">Open request in DevOps Portal</a></p>' if url else ''}
    """
    return send_mail(f"[DevOps Action] Deployment Request {request_id}", settings["devops_to"], html)
