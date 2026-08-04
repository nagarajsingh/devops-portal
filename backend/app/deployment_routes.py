from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, Field, SecretStr

from .auth import current_user, require_devops
from .deployment_management import APPLICATION_TYPES, COLLECTIONS_COUNTRIES, extract_release_document, list_deployment_requests, submit_document, update_action
from .models import UserContext

router = APIRouter(prefix="/deployment-management", tags=["Deployment Management"])


class DeploymentAction(BaseModel):
    azure_devops_pat: SecretStr | None = None
    updates: dict[str, Any] = Field(default_factory=dict)


@router.get("/application-types")
def application_types(_: UserContext = Depends(current_user)) -> dict[str, list[str]]:
    return {"application_types": list(APPLICATION_TYPES), "collections_countries": list(COLLECTIONS_COUNTRIES)}


@router.post("/submit-document", status_code=201)
async def submit_release_document(
    application_type: str = Form(...),
    app_owner: str = Form(...),
    country: str = Form(""),
    document: UploadFile = File(...),
    user: UserContext = Depends(current_user),
) -> dict:
    raw = await document.read()
    return submit_document(application_type, app_owner, document, raw, user.username, country)


@router.post("/extract")
async def extract_document(
    application_type: str = Form(""),
    country: str = Form(""),
    document: UploadFile = File(...),
    _: UserContext = Depends(require_devops),
) -> dict:
    raw = await document.read()
    return extract_release_document(document, raw, application_type, country)


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
    pat = payload.azure_devops_pat.get_secret_value() if payload.azure_devops_pat else ""
    return update_action(request_id, action, user.username, pat, payload.updates)
