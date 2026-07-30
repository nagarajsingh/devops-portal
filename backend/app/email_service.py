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
        "<tr>"
        f"<td style='padding:14px 16px;border-bottom:1px solid #edf0f4;width:38%;font-size:12px;line-height:18px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:#7b8795;background:#fbfcfe'>{html.escape(label)}</td>"
        f"<td style='padding:14px 16px;border-bottom:1px solid #edf0f4;font-size:14px;line-height:21px;font-weight:600;color:#2f4664'>{html.escape(str(value))}</td>"
        "</tr>"
        for label, value in details
    )

    body = f"""
    <!doctype html>
    <html>
      <body style="margin:0;padding:0;background:#f4f6fa;font-family:Arial,Helvetica,sans-serif;color:#24334a">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#f4f6fa">
          <tr>
            <td align="center" style="padding:32px 16px">
              <table role="presentation" width="720" cellspacing="0" cellpadding="0" border="0" style="width:100%;max-width:720px;background:#ffffff;border:1px solid #e7ebf0;border-radius:22px;overflow:hidden;box-shadow:0 20px 55px rgba(24,59,104,.10)">
                <tr>
                  <td style="padding:0;background:linear-gradient(135deg,#173d70 0%,#214f88 62%,#ef6b22 160%)">
                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                      <tr>
                        <td style="padding:28px 32px 26px">
                          <table role="presentation" cellspacing="0" cellpadding="0" border="0">
                            <tr>
                              <td style="width:46px;height:46px;border-radius:14px;background:#ef6b22;color:#ffffff;text-align:center;font-size:24px;font-weight:800;vertical-align:middle">D</td>
                              <td style="padding-left:14px">
                                <div style="font-size:20px;line-height:24px;font-weight:800;color:#ffffff">DevOps Portal</div>
                                <div style="margin-top:3px;font-size:11px;line-height:16px;font-weight:700;letter-spacing:.16em;text-transform:uppercase;color:#cdd9e8">Microservice Onboarding</div>
                              </td>
                            </tr>
                          </table>
                          <div style="margin-top:28px;display:inline-block;padding:7px 11px;border-radius:999px;background:#fff1e8;color:#d95713;font-size:11px;line-height:14px;font-weight:800;letter-spacing:.08em;text-transform:uppercase">Approval required</div>
                          <h1 style="margin:14px 0 8px;font-size:28px;line-height:36px;color:#ffffff;letter-spacing:-.4px">Review a new onboarding request</h1>
                          <p style="margin:0;max-width:600px;font-size:14px;line-height:23px;color:#dbe5f0">A developer submitted a microservice onboarding request that requires your approval before it can move to the DevOps provisioning queue.</p>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
                <tr>
                  <td style="padding:28px 32px 10px">
                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="border:1px solid #e7ebf0;border-radius:16px;overflow:hidden;border-collapse:separate">
                      <tr>
                        <td colspan="2" style="padding:16px 18px;background:linear-gradient(90deg,#fff7f1,#ffffff);border-bottom:1px solid #e7ebf0">
                          <div style="font-size:12px;line-height:16px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:#ef641f">Request summary</div>
                          <div style="margin-top:5px;font-size:18px;line-height:24px;font-weight:800;color:#183b68">{html.escape(item['repository_name'])}</div>
                        </td>
                      </tr>
                      {rows}
                    </table>
                  </td>
                </tr>
                <tr>
                  <td style="padding:22px 32px 10px">
                    <table role="presentation" cellspacing="0" cellpadding="0" border="0" align="center">
                      <tr>
                        <td style="padding:0 7px 0 0">
                          <a href="{html.escape(approve_url)}" style="display:inline-block;min-width:150px;padding:14px 22px;border-radius:11px;background:linear-gradient(90deg,#ff6817,#ff8a21);color:#ffffff;text-align:center;text-decoration:none;font-size:14px;line-height:18px;font-weight:800;box-shadow:0 9px 20px rgba(244,103,28,.24)">Approve request</a>
                        </td>
                        <td style="padding:0 0 0 7px">
                          <a href="{html.escape(reject_url)}" style="display:inline-block;min-width:150px;padding:13px 22px;border:1px solid #e3b8b4;border-radius:11px;background:#fff4f3;color:#bd3e37;text-align:center;text-decoration:none;font-size:14px;line-height:18px;font-weight:800">Reject request</a>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
                <tr>
                  <td style="padding:18px 32px 30px">
                    <div style="padding:14px 16px;border-radius:12px;background:#f7f9fc;border:1px solid #e7ebf0;font-size:12px;line-height:19px;color:#6f7c8c">
                      These secure action links expire in <strong style="color:#354d69">{APPROVAL_TOKEN_HOURS} hours</strong> and remain valid only while the request is waiting for application-owner approval.
                    </div>
                  </td>
                </tr>
                <tr>
                  <td style="padding:18px 32px;background:#f8fafc;border-top:1px solid #e7ebf0;text-align:center;font-size:11px;line-height:17px;color:#8a95a3">
                    This is an automated notification from the DevOps Portal. Please do not forward this email because it contains secure approval links.
                  </td>
                </tr>
              </table>
            </td>
          </tr>
        </table>
      </body>
    </html>
    """

    message = EmailMessage()
    message["From"] = MAIL_FROM
    message["To"] = app_owner
    message["Subject"] = f"[Approval Required] {item['repository_name']} onboarding request"
    message.set_content(
        f"Approval required for request {item['id']} ({item['repository_name']}). "
        "Open the HTML version of this email to approve or reject the request."
    )
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
