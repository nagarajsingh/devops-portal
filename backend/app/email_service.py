from __future__ import annotations

import html
import smtplib
import ssl
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

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

logger = get_logger("email")


def parse_recipients(value: str) -> list[str]:
    return [item.strip() for item in value.replace(";", ",").split(",") if item.strip()]


def create_approval_token(request_id: str, app_owner: str, decision: str) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": app_owner,
            "request_id": request_id,
            "decision": decision,
            "purpose": "app-owner-approval",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(hours=APPROVAL_TOKEN_HOURS)).timestamp()),
        },
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )


def decode_approval_token(token: str) -> dict:
    payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    if payload.get("purpose") != "app-owner-approval":
        raise ValueError("Invalid approval token purpose")
    return payload


def send_app_owner_approval_email(item: dict) -> None:
    if not SMTP_HOST or not MAIL_FROM:
        raise RuntimeError("SMTP_HOST and MAIL_FROM must be configured")

    app_owner = item["app_owner"]
    approve_token = create_approval_token(item["id"], app_owner, "approve")
    reject_token = create_approval_token(item["id"], app_owner, "reject")
    approve_url = f"{PORTAL_PUBLIC_URL}/api/app-owner/action?token={approve_token}"
    reject_url = f"{PORTAL_PUBLIC_URL}/api/app-owner/action?token={reject_token}"

    details = [
        ("Request ID", item["id"]),
        ("Application", item["application_type"]),
        ("Repository", item["repository_name"]),
        ("Language / Pipeline Type", item.get("pipeline_type") or "Not selected"),
        ("Reference Repository", item.get("reference_repository_name") or "Not requested"),
        ("Ingress Path", item.get("ingress_path") or "Not provided"),
        ("Requested By", item["requested_by"]),
        ("Comments", item.get("comments") or "None"),
    ]
    rows = "".join(
        f"<tr><td style='padding:10px;border-bottom:1px solid #e6eaf0;font-weight:700;color:#294766'>{html.escape(label)}</td>"
        f"<td style='padding:10px;border-bottom:1px solid #e6eaf0;color:#52657b'>{html.escape(str(value))}</td></tr>"
        for label, value in details
    )
    body = f"""
    <html><body style="font-family:Arial,sans-serif;background:#f5f7fb;padding:24px;color:#24334a">
      <div style="max-width:720px;margin:auto;background:white;border-radius:18px;padding:28px;border:1px solid #e5eaf0">
        <div style="color:#ef641f;font-weight:800;letter-spacing:1px;font-size:12px">DEVOPS PORTAL</div>
        <h2 style="color:#183b68">Application owner approval required</h2>
        <p>A new microservice onboarding request requires your approval before it is sent to the DevOps provisioning queue.</p>
        <table style="width:100%;border-collapse:collapse;margin:20px 0">{rows}</table>
        <div style="display:flex;gap:12px;margin-top:24px">
          <a href="{html.escape(approve_url)}" style="background:#23824d;color:white;padding:12px 22px;border-radius:10px;text-decoration:none;font-weight:700">Approve</a>
          <a href="{html.escape(reject_url)}" style="background:#c73e37;color:white;padding:12px 22px;border-radius:10px;text-decoration:none;font-weight:700">Reject</a>
        </div>
        <p style="font-size:12px;color:#788392;margin-top:22px">These links expire in {APPROVAL_TOKEN_HOURS} hours and can be used only while the request is awaiting app-owner approval.</p>
      </div>
    </body></html>
    """

    message = EmailMessage()
    message["From"] = MAIL_FROM
    message["To"] = app_owner
    message["Subject"] = f"[Approval Required] {item['repository_name']} onboarding request"
    message.set_content(f"Approval required for request {item['id']}. Use the HTML version of this email.")
    message.add_alternative(body, subtype="html")

    recipients = [app_owner] + parse_recipients(MAIL_BCC)
    if SMTP_SSL:
        smtp_client: smtplib.SMTP = smtplib.SMTP_SSL(
            SMTP_HOST,
            SMTP_PORT,
            timeout=SMTP_TIMEOUT_SECONDS,
            context=ssl.create_default_context(),
        )
    else:
        smtp_client = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT_SECONDS)

    with smtp_client as smtp:
        smtp.ehlo()
        if SMTP_STARTTLS and not SMTP_SSL:
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()
        if SMTP_USERNAME and SMTP_PASSWORD:
            smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
        smtp.send_message(message, from_addr=MAIL_FROM, to_addrs=recipients)

    logger.info("App owner approval email sent request_id=%s app_owner=%s", item["id"], app_owner)
