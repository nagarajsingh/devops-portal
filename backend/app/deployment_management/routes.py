from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, Field, SecretStr

from ..auth import current_user, require_devops
from ..logging_config import get_logger
from ..models import UserContext
from .notifications import send_devops_ready, send_owner_approval_request
from .runtime import perform_action as execute_action
from .service import (
    APPLICATION_TYPES,
    COLLECTIONS_COUNTRIES,
    extract_release_document,
    list_deployment_requests,
    submit_document,
)

router = APIRouter(prefix="/deployment-management", tags=["Deployment Management"])
logger = get_logger("deployment-management")


class DeploymentAction(BaseModel):
    azure_devops_pat: SecretStr | None = None
    updates: dict[str, Any] = Field(default_factory=dict)


@router.get("/application-types")
def application_types(_: UserContext = Depends(current_user)) -> dict[str, list[str]]:
    return {
        "application_types": list(APPLICATION_TYPES),
        "collections_countries": list(COLLECTIONS_COUNTRIES),
    }


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
        result = submit_document(application_type, app_owner, document, raw, user.username, country)
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
        result = execute_action(request_id, action, user.username, explicit_pat, payload.updates)
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
