from __future__ import annotations

import html
from typing import Any

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, SecretStr

from .auth import current_user, require_devops
from .deployment_management import (
    APPLICATION_TYPES,
    COLLECTIONS_COUNTRIES,
    extract_release_document,
    list_deployment_requests,
    submit_document,
)
from .deployment_notifications import decode_owner_action_token, send_devops_ready, send_owner_approval_request
from .deployment_runtime import perform_action as execute_action
from .logging_config import get_logger
from .models import UserContext

router = APIRouter(prefix="/deployment-management", tags=["Deployment Management"])
logger = get_logger("deployment-management")


class DeploymentAction(BaseModel):
    azure_devops_pat: SecretStr | None = None
    updates: dict[str, Any] = Field(default_factory=dict)


def _approval_result_page(title: str, detail: str, success: bool = True) -> HTMLResponse:
    accent = "#23824d" if success else "#b83d36"
    icon = "✓" if success else "!"
    return HTMLResponse(
        f"""
        <!doctype html>
        <html>
          <head><meta name="viewport" content="width=device-width,initial-scale=1"></head>
          <body style="margin:0;background:linear-gradient(135deg,#f4f6fa,#fff6ef);font-family:Arial,Helvetica,sans-serif;color:#24334a;min-height:100vh;display:grid;place-items:center;padding:24px">
            <div style="width:min(560px,100%);background:#fff;border:1px solid #e7ebf0;border-radius:24px;box-shadow:0 28px 80px rgba(24,59,104,.16);padding:38px;text-align:center;box-sizing:border-box">
              <div style="width:62px;height:62px;border-radius:20px;margin:0 auto 18px;background:{accent};color:#fff;display:grid;place-items:center;font-size:31px;font-weight:800">{icon}</div>
              <div style="font-size:11px;letter-spacing:.16em;font-weight:800;color:#ef6b22;text-transform:uppercase">Mashreq NEO CORP · DevOps Portal</div>
              <h1 style="margin:12px 0 10px;color:#183b68;font-size:27px">{html.escape(title)}</h1>
              <p style="margin:0;color:#6f7c8c;line-height:1.7">{html.escape(detail)}</p>
              <div style="margin-top:24px;padding:13px 16px;border-radius:12px;background:#f8fafc;border:1px solid #e7ebf0;color:#718094;font-size:12px">You can close this window. The DevOps Portal request has been updated.</div>
            </div>
          </body>
        </html>
        """,
        status_code=200 if success else 400,
    )


@router.get("/application-types")
def application_types(_: UserContext = Depends(current_user)) -> dict[str, list[str]]:
    return {
        "application_types": list(APPLICATION_TYPES),
        "collections_countries": list(COLLECTIONS_COUNTRIES),
    }


@router.get("/approval-action", response_class=HTMLResponse)
def deployment_owner_approval_action(token: str) -> HTMLResponse:
    try:
        payload = decode_owner_action_token(token)
        request_id = str(payload.get("request_id") or "")
        owner = str(payload.get("sub") or "").strip().lower()
        decision = str(payload.get("decision") or "")
        row = next((item for item in list_deployment_requests() if str(item.get("id")) == request_id), None)
        if not row:
            return _approval_result_page("Request not found", "The deployment request no longer exists or the link is invalid.", False)
        expected_owner = str(row.get("app_owner") or "").strip().lower()
        if not owner or owner != expected_owner:
            return _approval_result_page("Approval link is not valid", "This signed link does not match the application owner for the request.", False)
        approval_status = str((row.get("steps") or {}).get("owner_approval", {}).get("status") or "Pending")
        if approval_status != "Pending":
            return _approval_result_page(
                "Request already processed",
                f"Request {request_id} already has owner approval status: {approval_status}.",
                True,
            )

        action = "owner-approve" if decision == "approve" else "owner-reject"
        result = execute_action(request_id, action, expected_owner, "", {"email_action": True})
        if decision == "approve":
            send_devops_ready(result, bypassed=False)
            title = "Release approved"
            detail = f"Request {request_id} has been approved and is now available for DevOps processing."
        else:
            title = "Release rejected"
            detail = f"Request {request_id} has been rejected. DevOps Portal has recorded your decision."
        logger.info("Deployment owner email action request_id=%s owner=%s decision=%s", request_id, expected_owner, decision)
        return _approval_result_page(title, detail, True)
    except Exception as exc:
        logger.exception("Deployment owner email approval failed")
        return _approval_result_page("Approval link could not be processed", str(exc) or "The approval link is invalid or has expired.", False)


@router.post("/submit-document", status_code=201)
async def submit_release_document(
    application_type: str = Form(...),
    app_owner: str = Form(...),
    country: str = Form(""),
    document: UploadFile = File(...),
    user: UserContext = Depends(current_user),
) -> dict:
    raw = await document.read()
    logger.info(
        "Deployment document submission started user=%s application_type=%s country=%s filename=%s size_bytes=%s owner=%s",
        user.username,
        application_type,
        country or "N/A",
        document.filename or "release-document",
        len(raw),
        app_owner,
    )
    try:
        result = submit_document(
            application_type,
            app_owner,
            document,
            raw,
            user.username,
            country,
        )
        mail_sent = send_owner_approval_request(result)
        result["owner_mail_sent"] = mail_sent
        logger.info(
            "Owner approval email result request_id=%s owner=%s sent=%s",
            result.get("id"),
            app_owner,
            mail_sent,
        )
    except Exception:
        logger.exception(
            "Deployment document submission failed user=%s application_type=%s country=%s filename=%s",
            user.username,
            application_type,
            country or "N/A",
            document.filename or "release-document",
        )
        raise
    logger.info(
        "Deployment document submitted request_id=%s user=%s application_type=%s country=%s status=%s",
        result.get("id"),
        user.username,
        application_type,
        country or "N/A",
        result.get("status"),
    )
    return result


@router.post("/extract")
async def extract_document(
    application_type: str = Form(""),
    country: str = Form(""),
    document: UploadFile = File(...),
    user: UserContext = Depends(require_devops),
) -> dict:
    raw = await document.read()
    logger.info(
        "Standalone document extraction started user=%s application_type=%s country=%s filename=%s",
        user.username,
        application_type or "N/A",
        country or "N/A",
        document.filename or "release-document",
    )
    try:
        result = extract_release_document(document, raw, application_type, country)
    except Exception:
        logger.exception(
            "Standalone document extraction failed user=%s application_type=%s country=%s filename=%s",
            user.username,
            application_type or "N/A",
            country or "N/A",
            document.filename or "release-document",
        )
        raise
    logger.info(
        "Standalone document extraction completed user=%s application_type=%s country=%s extracted_images=%s",
        user.username,
        application_type or "N/A",
        country or "N/A",
        len(result.get("collections_items") or result.get("container_images") or []),
    )
    return result


@router.get("/requests")
def list_requests(_: UserContext = Depends(current_user)) -> list[dict]:
    return list_deployment_requests()


@router.post("/requests/{request_id}/{action}")
def perform_action(
    request_id: str,
    action: str,
    payload: DeploymentAction,
    user: UserContext = Depends(require_devops),
) -> dict:
    explicit_pat = payload.azure_devops_pat.get_secret_value() if payload.azure_devops_pat else ""
    logger.info(
        "Deployment action started request_id=%s action=%s actor=%s update_keys=%s explicit_pat=%s",
        request_id,
        action,
        user.username,
        sorted(payload.updates.keys()),
        bool(explicit_pat),
    )
    try:
        result = execute_action(
            request_id,
            action,
            user.username,
            explicit_pat,
            payload.updates,
        )
        if action == "owner-approve":
            bypassed = bool(payload.updates.get("bypass_owner_approval"))
            mail_sent = send_devops_ready(result, bypassed=bypassed)
            result["devops_mail_sent"] = mail_sent
            logger.info(
                "DevOps notification email result request_id=%s bypassed=%s sent=%s",
                request_id,
                bypassed,
                mail_sent,
            )
    except Exception:
        logger.exception(
            "Deployment action failed request_id=%s action=%s actor=%s",
            request_id,
            action,
            user.username,
        )
        raise
    logger.info(
        "Deployment action completed request_id=%s action=%s actor=%s status=%s progress_percent=%s",
        request_id,
        action,
        user.username,
        result.get("status"),
        result.get("progress_percent"),
    )
    return result
