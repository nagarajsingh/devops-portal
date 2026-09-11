from __future__ import annotations

import html
import os
import smtplib
import ssl
from email.message import EmailMessage
from typing import Any

from .config import (
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
        "Open the HTML version of this email for the request details."
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
    url = _request_url(request_id)

    if not owner:
        logger.error(
            "Deployment approval email not sent request_id=%s because app_owner is empty",
            request_id,
        )
        return False

    application_type = html.escape(str(row.get("application_type") or ""))
    country = html.escape(str(row.get("country") or "N/A"))
    document_name = html.escape(str(row.get("document_name") or ""))
    requested_by = html.escape(str(row.get("requested_by") or ""))
    safe_request_id = html.escape(request_id)
    safe_url = html.escape(url, quote=True)

    html_body = f"""
    <!doctype html>
    <html>
      <body style="margin:0;padding:0;background:#f4f6fa;font-family:Arial,Helvetica,sans-serif;color:#24334a">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#f4f6fa">
          <tr><td align="center" style="padding:32px 16px">
            <table role="presentation" width="700" cellspacing="0" cellpadding="0" border="0" style="width:100%;max-width:700px;background:#ffffff;border:1px solid #e7ebf0;border-radius:20px;overflow:hidden">
              <tr><td style="padding:28px 32px;background:#173d70;color:#ffffff">
                <div style="font-size:12px;font-weight:800;letter-spacing:.12em;text-transform:uppercase;color:#ffb47d">Approval required</div>
                <h1 style="margin:10px 0 6px;font-size:27px">Collections deployment request</h1>
                <p style="margin:0;color:#dbe5f0">A deployment request is waiting for your application-owner approval.</p>
              </td></tr>
              <tr><td style="padding:26px 32px">
                <table width="100%" cellspacing="0" cellpadding="8" style="border-collapse:collapse">
                  <tr><td><b>Request</b></td><td>{safe_request_id}</td></tr>
                  <tr><td><b>Application type</b></td><td>{application_type}</td></tr>
                  <tr><td><b>Country</b></td><td>{country}</td></tr>
                  <tr><td><b>Document</b></td><td>{document_name}</td></tr>
                  <tr><td><b>Requested by</b></td><td>{requested_by}</td></tr>
                </table>
                {f'<p style="margin-top:24px"><a href="{safe_url}" style="display:inline-block;background:#f36b21;color:#fff;text-decoration:none;padding:13px 20px;border-radius:10px;font-weight:700">Open request in DevOps Portal</a></p>' if safe_url else ''}
              </td></tr>
              <tr><td style="padding:16px 32px;background:#f8fafc;border-top:1px solid #e7ebf0;color:#7b8795;font-size:12px">Mashreq NEO CORP · Internal DevOps Deployment Management</td></tr>
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
