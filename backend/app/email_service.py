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
        ("ACL Details", item.get("acl_details") or "Not requested"),
        ("Database Requests", len(item.get("database_requests") or [])),
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

    approve_href = html.escape(approve_url, quote=True)
    reject_href = html.escape(reject_url, quote=True)

    body = f"""
    <!doctype html>
    <html xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office">
      <head>
        <meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <!--[if mso]><xml><o:OfficeDocumentSettings><o:AllowPNG/><o:PixelsPerInch>96</o:PixelsPerInch></o:OfficeDocumentSettings></xml><![endif]-->
      </head>
      <body style="margin:0;padding:0;background:#f4f6fa;font-family:Arial,Helvetica,sans-serif;color:#24334a">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#f4f6fa">
          <tr><td align="center" style="padding:32px 16px">
            <table role="presentation" width="720" cellspacing="0" cellpadding="0" border="0" style="width:100%;max-width:720px;background:#ffffff;border:1px solid #e7ebf0;border-radius:22px;overflow:hidden;box-shadow:0 20px 55px rgba(24,59,104,.10)">
              <tr><td style="padding:28px 32px 26px;background:#173d70;background-image:linear-gradient(135deg,#173d70 0%,#214f88 62%,#ef6b22 160%)">
                <table role="presentation" cellspacing="0" cellpadding="0" border="0"><tr>
                  <td style="width:46px;height:46px;border-radius:14px;background:#ef6b22;color:#ffffff;text-align:center;font-size:24px;font-weight:800;vertical-align:middle">D</td>
                  <td style="padding-left:14px"><div style="font-size:20px;line-height:24px;font-weight:800;color:#ffffff">DevOps Portal</div><div style="margin-top:3px;font-size:11px;line-height:16px;font-weight:700;letter-spacing:.16em;text-transform:uppercase;color:#cdd9e8">Microservice Onboarding</div></td>
                </tr></table>
                <div style="margin-top:28px;display:inline-block;padding:7px 11px;border-radius:999px;background:#fff1e8;color:#d95713;font-size:11px;line-height:14px;font-weight:800;letter-spacing:.08em;text-transform:uppercase">Approval required</div>
                <h1 style="margin:14px 0 8px;font-size:28px;line-height:36px;color:#ffffff;letter-spacing:-.4px">Review a new onboarding request</h1>
                <p style="margin:0;max-width:600px;font-size:14px;line-height:23px;color:#dbe5f0">A developer submitted a microservice onboarding request that requires your approval before it can move to the DevOps provisioning queue.</p>
              </td></tr>
              <tr><td style="padding:28px 32px 10px">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="border:1px solid #e7ebf0;border-radius:16px;overflow:hidden;border-collapse:separate">
                  <tr><td colspan="2" style="padding:16px 18px;background:#fff7f1;background-image:linear-gradient(90deg,#fff7f1,#ffffff);border-bottom:1px solid #e7ebf0"><div style="font-size:12px;line-height:16px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:#ef641f">Request summary</div><div style="margin-top:5px;font-size:18px;line-height:24px;font-weight:800;color:#183b68">{html.escape(item['repository_name'])}</div></td></tr>
                  {rows}
                </table>
              </td></tr>
              <tr><td align="center" style="padding:24px 32px 8px">
                <table role="presentation" cellspacing="0" cellpadding="0" border="0" align="center"><tr>
                  <td align="center" style="padding:0 7px 12px 0">
                    <!--[if mso]><v:roundrect href="{approve_href}" style="height:48px;v-text-anchor:middle;width:190px" arcsize="22%" stroke="f" fillcolor="#ff7a1a"><v:fill type="gradient" color="#ff6817" color2="#ff8a21" angle="0"/><w:anchorlock/><center style="color:#ffffff;font-family:Arial,sans-serif;font-size:14px;font-weight:bold">Approve request</center></v:roundrect><![endif]-->
                    <!--[if !mso]><!-- --><a href="{approve_href}" style="display:inline-block;width:190px;padding:15px 0;border:1px solid rgba(255,255,255,.45);border-radius:12px;background:#ff7a1a;background-image:linear-gradient(90deg,#ff6817,#ff8a21);color:#ffffff;text-align:center;text-decoration:none;font-size:14px;line-height:18px;font-weight:800;box-shadow:0 10px 24px rgba(244,103,28,.28);text-shadow:0 1px 0 rgba(0,0,0,.08)">Approve request</a><!--<![endif]-->
                  </td>
                  <td align="center" style="padding:0 0 12px 7px">
                    <!--[if mso]><v:roundrect href="{reject_href}" style="height:48px;v-text-anchor:middle;width:190px" arcsize="22%" strokecolor="#e5b9b5" fillcolor="#fff5f4"><w:anchorlock/><center style="color:#b83d36;font-family:Arial,sans-serif;font-size:14px;font-weight:bold">Reject request</center></v:roundrect><![endif]-->
                    <!--[if !mso]><!-- --><a href="{reject_href}" style="display:inline-block;width:190px;padding:14px 0;border:1px solid rgba(229,185,181,.9);border-radius:12px;background:#fff5f4;background-image:linear-gradient(180deg,rgba(255,255,255,.96),rgba(255,240,239,.96));color:#b83d36;text-align:center;text-decoration:none;font-size:14px;line-height:18px;font-weight:800;box-shadow:inset 0 1px 0 rgba(255,255,255,.9),0 9px 20px rgba(184,61,54,.10)">Reject request</a><!--<![endif]-->
                  </td>
                </tr></table>
              </td></tr>
              <tr><td style="padding:16px 32px 30px"><div style="padding:14px 16px;border-radius:12px;background:#f7f9fc;border:1px solid #e7ebf0;font-size:12px;line-height:19px;color:#6f7c8c">These secure action links expire in <strong style="color:#354d69">{APPROVAL_TOKEN_HOURS} hours</strong> and remain valid only while the request is waiting for application-owner approval.</div></td></tr>
              <tr><td style="padding:18px 32px;background:#f8fafc;border-top:1px solid #e7ebf0;text-align:center;font-size:11px;line-height:17px;color:#8a95a3">This is an automated notification from the DevOps Portal. Please do not forward this email because it contains secure approval links.</td></tr>
            </table>
          </td></tr>
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



def send_pipeline_closure_email(
    item: dict,
    database_credentials: list[dict] | None = None,
) -> None:
    """Email final onboarding details to the developer.

    Database passwords are supplied only for this email operation and are never
    written into the persisted request object by the request service.
    """
    if not SMTP_HOST or not MAIL_FROM:
        raise RuntimeError("SMTP_HOST and MAIL_FROM must be configured")

    developer = str(item.get("requested_by") or "").strip()
    if not developer:
        raise RuntimeError("Pipeline request developer email is missing")

    credential_map = {
        int(entry.get("request_index", -1)): str(entry.get("password") or "")
        for entry in (database_credentials or [])
        if int(entry.get("request_index", -1)) >= 0
    }

    provisioning = item.get("provisioning") or {}
    repository_url = str((provisioning.get("repository") or {}).get("url") or "").strip()
    pipeline_url = str((provisioning.get("pipeline") or {}).get("url") or "").strip()
    release_pipeline_url = str((provisioning.get("release_pipeline") or {}).get("url") or "").strip()

    def resource_link(label: str, url: str) -> str:
        if not url:
            return (
                "<tr>"
                f"<td style='padding:12px 14px;background:#fbfcfe;border-bottom:1px solid #edf0f4;font-weight:700;width:31%'>{html.escape(label)}</td>"
                "<td style='padding:12px 14px;border-bottom:1px solid #edf0f4;color:#7b8795'>Not created or unavailable</td>"
                "</tr>"
            )
        safe_url = html.escape(url, quote=True)
        return (
            "<tr>"
            f"<td style='padding:12px 14px;background:#fbfcfe;border-bottom:1px solid #edf0f4;font-weight:700;width:31%'>{html.escape(label)}</td>"
            "<td style='padding:12px 14px;border-bottom:1px solid #edf0f4'>"
            f"<a href='{safe_url}' style='color:#315b8a;font-weight:700;text-decoration:none'>Open resource</a>"
            f"<div style='margin-top:5px;font-size:11px;line-height:17px;color:#7b8795;word-break:break-all'>{safe_url}</div>"
            "</td>"
            "</tr>"
        )

    pipeline_resources_section = f"""
        <div style="margin-top:24px">
          <div style="font-size:12px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:#ef641f">Provisioned resources</div>
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="margin-top:10px;border:1px solid #e7ebf0;border-radius:12px;border-collapse:separate;overflow:hidden">
            {resource_link("Repository URL", repository_url)}
            {resource_link("Build Pipeline URL", pipeline_url)}
            {resource_link("Release Pipeline URL", release_pipeline_url)}
          </table>
        </div>
    """

    database_requests = item.get("database_requests") or []
    database_rows = ""
    for index, request in enumerate(database_requests):
        password = credential_map.get(index, "")
        server = str(request.get("server_url") or "")
        port = request.get("server_port")
        server_display = f"{server}:{port}" if server and port else (server or (str(port) if port else "—"))
        database_rows += (
            "<tr>"
            f"<td style='padding:10px 12px;border-bottom:1px solid #edf0f4'>{html.escape(str(request.get('environment') or '—'))}</td>"
            f"<td style='padding:10px 12px;border-bottom:1px solid #edf0f4'>{html.escape(str(request.get('db_name') or '—'))}</td>"
            f"<td style='padding:10px 12px;border-bottom:1px solid #edf0f4'>{html.escape(str(request.get('db_username') or '—'))}</td>"
            f"<td style='padding:10px 12px;border-bottom:1px solid #edf0f4'>{html.escape(server_display)}</td>"
            f"<td style='padding:10px 12px;border-bottom:1px solid #edf0f4;font-family:monospace'>{html.escape(password or 'Not provided')}</td>"
            "</tr>"
        )

    database_section = (
        f"""
        <div style="margin-top:24px">
          <div style="font-size:12px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:#ef641f">Database connection details</div>
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="margin-top:10px;border:1px solid #e7ebf0;border-radius:12px;border-collapse:separate;overflow:hidden;font-size:12px">
            <tr style="background:#f8fafc;color:#54687f">
              <th align="left" style="padding:10px 12px">Environment</th>
              <th align="left" style="padding:10px 12px">DB Name</th>
              <th align="left" style="padding:10px 12px">Username</th>
              <th align="left" style="padding:10px 12px">Server</th>
              <th align="left" style="padding:10px 12px">Password</th>
            </tr>
            {database_rows}
          </table>
          <div style="margin-top:9px;padding:10px 12px;border-radius:10px;background:#fff8ef;border:1px solid #f0d5b9;color:#8d572f;font-size:11px;line-height:17px">Database passwords are sensitive. Store them in the approved secret-management location and avoid forwarding this email.</div>
        </div>
        """
        if database_requests
        else ""
    )

    review_comments = str(item.get("review_comments") or "").strip()
    review_comments_section = (
        f"""
        <div style="margin-top:24px">
          <div style="font-size:12px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:#ef641f">DevOps review comments</div>
          <div style="margin-top:9px;padding:14px 16px;border-radius:12px;background:#f8fafc;border:1px solid #e7ebf0;white-space:pre-wrap;line-height:21px">{html.escape(review_comments)}</div>
        </div>
        """
        if review_comments
        else ""
    )

    acl_details = str(item.get("acl_details") or "").strip()
    acl_section = (
        f"""
        <div style="margin-top:24px">
          <div style="font-size:12px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:#ef641f">ACL / Connectivity request</div>
          <pre style="margin:10px 0 0;padding:14px;border-radius:12px;background:#f8fafc;border:1px solid #e7ebf0;white-space:pre-wrap;word-break:break-word;font-family:Consolas,monospace;font-size:12px;line-height:19px;color:#334d6a">{html.escape(acl_details)}</pre>
        </div>
        """
        if acl_details
        else ""
    )

    portal_url = (
        f"{PORTAL_PUBLIC_URL.rstrip('/')}/requests"
        if PORTAL_PUBLIC_URL
        else ""
    )
    portal_link = (
        f'<p style="margin-top:22px"><a href="{html.escape(portal_url, quote=True)}" style="color:#315b8a;font-weight:700">Open request in DevOps Portal</a></p>'
        if portal_url
        else ""
    )

    body = f"""
    <!doctype html>
    <html>
      <body style="margin:0;padding:0;background:#f4f6fa;font-family:Arial,Helvetica,sans-serif;color:#24334a">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
          <tr><td align="center" style="padding:32px 16px">
            <table role="presentation" width="720" cellspacing="0" cellpadding="0" border="0" style="width:100%;max-width:720px;background:#fff;border:1px solid #e7ebf0;border-radius:20px;overflow:hidden">
              <tr><td style="padding:28px 32px;background:#173d70;color:#fff">
                <div style="font-size:11px;font-weight:800;letter-spacing:.12em;text-transform:uppercase;color:#ffbd8f">Request completed</div>
                <h1 style="margin:10px 0 6px;font-size:26px">{html.escape(str(item.get('repository_name') or 'Pipeline request'))}</h1>
                <p style="margin:0;color:#dbe5f0">DevOps has completed request {html.escape(str(item.get('id') or ''))}.</p>
              </td></tr>
              <tr><td style="padding:26px 32px">
                <table width="100%" cellspacing="0" cellpadding="0" style="border:1px solid #e7ebf0;border-radius:12px;border-collapse:separate;overflow:hidden">
                  <tr><td style="padding:11px 13px;background:#fbfcfe;font-weight:700;width:34%">Application</td><td style="padding:11px 13px">{html.escape(str(item.get('application_type') or '—'))}</td></tr>
                  <tr><td style="padding:11px 13px;background:#fbfcfe;font-weight:700">Repository</td><td style="padding:11px 13px">{html.escape(str(item.get('repository_name') or '—'))}</td></tr>
                  <tr><td style="padding:11px 13px;background:#fbfcfe;font-weight:700">Closed by</td><td style="padding:11px 13px">{html.escape(str(item.get('reviewed_by') or '—'))}</td></tr>
                </table>
                {pipeline_resources_section}
                {database_section}
                {acl_section}
                {review_comments_section}
                <div style="margin-top:24px;font-size:12px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:#ef641f">Final closure comments</div>
                <div style="margin-top:9px;padding:16px 18px;border-radius:12px;background:#fff8ef;border:1px solid #efd2b2;white-space:pre-wrap;line-height:22px;color:#704825">{html.escape(str(item.get('closure_comment') or 'Completed'))}</div>
                {portal_link}
              </td></tr>
              <tr><td style="padding:16px 32px;background:#f8fafc;border-top:1px solid #e7ebf0;color:#7b8795;font-size:11px;text-align:center">Mashreq NEO CORP · Internal DevOps Portal</td></tr>
            </table>
          </td></tr>
        </table>
      </body>
    </html>
    """

    message = EmailMessage()
    message["From"] = MAIL_FROM
    message["To"] = developer
    message["Subject"] = f"[Completed] {item.get('repository_name') or item.get('id')} onboarding request"
    message.set_content(
        "\n".join(
            [
                f"DevOps completed request {item.get('id')}.",
                f"Repository URL: {repository_url or 'Not created or unavailable'}",
                f"Build Pipeline URL: {pipeline_url or 'Not created or unavailable'}",
                f"Release Pipeline URL: {release_pipeline_url or 'Not created or unavailable'}",
                f"Closure comments: {item.get('closure_comment') or 'Completed'}",
                "Open the HTML version of this email for database and ACL details.",
            ]
        )
    )
    message.add_alternative(body, subtype="html")

    # Credential-bearing closure mail is intentionally sent only to the
    # original requester. Do not copy the general notification BCC list.
    recipients = [developer]
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

    logger.info(
        "Pipeline closure email sent request_id=%s developer=%s database_count=%s",
        item.get("id"),
        developer,
        len(database_requests),
    )
