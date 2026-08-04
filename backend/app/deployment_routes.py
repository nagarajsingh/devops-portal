from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, Field, SecretStr

from .auth import current_user, require_devops
from .deployment_management import create_deployment_request, extract_release_document, list_deployment_requests, update_action
from .models import UserContext

router = APIRouter(prefix="/deployment-management", tags=["Deployment Management"])


class DeploymentRequestCreate(BaseModel):
    application: str
    branch_name: str
    environment: str
    app_owner: str
    repository: str = ""
    target_branch: str = "release/uat"
    war_files: list[str] = Field(default_factory=list)
    jar_files: list[str] = Field(default_factory=list)
    document_name: str = ""


class DeploymentAction(BaseModel):
    azure_devops_pat: SecretStr | None = None


@router.post("/extract")
async def extract_document(
    document: UploadFile = File(...),
    _: UserContext = Depends(current_user),
) -> dict:
    raw = await document.read()
    return extract_release_document(document, raw)


@router.post("/requests", status_code=201)
def create_request(
    payload: DeploymentRequestCreate,
    user: UserContext = Depends(current_user),
) -> dict:
    return create_deployment_request(payload.model_dump(), user.username)


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
    return update_action(request_id, action, user.username, pat)
