from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, Field, SecretStr

from .auth import current_user, require_devops
from .deployment_management import (
    APPLICATION_TYPES,
    COLLECTIONS_COUNTRIES,
    extract_release_document,
    list_deployment_requests,
    submit_document,
)
from .deployment_runtime import perform_action as execute_action
from .logging_config import get_logger
from .models import UserContext

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
        "Deployment document submission started user=%s application_type=%s country=%s filename=%s size_bytes=%s",
        user.username,
        application_type,
        country or "N/A",
        document.filename or "release-document",
        len(raw),
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
    explicit_pat = (
        payload.azure_devops_pat.get_secret_value()
        if payload.azure_devops_pat
        else ""
    )
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
