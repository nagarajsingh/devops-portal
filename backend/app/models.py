from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, SecretStr

Role = Literal["developer", "devops"]
ApplicationType = Literal["H2H", "Collections", "Native-Mobile", "Safenet"]


class LoginRequest(BaseModel):
    username: str
    password: str
    role: Role


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: Role


class PipelineRequestCreate(BaseModel):
    application_type: ApplicationType = "H2H"
    app_owner: str = ""
    repository_name: str = Field(
        min_length=2,
        max_length=100,
        pattern=r"^[a-z0-9](?:[a-z0-9_-]*[a-z0-9])?$",
    )
    reference_repository_name: str = ""
    reference_branch: str = ""
    setup_pipeline: bool = False
    pipeline_type: str | None = None
    ingress_path: str
    ingress_name: str | None = None
    create_service: bool = False
    service_name: str = ""
    service_port: int = Field(default=8080, ge=1, le=65535)
    namespace: str = ""
    comments: str | None = None


class ReviewUpdate(PipelineRequestCreate):
    review_comments: str | None = None


class ApproveRequest(BaseModel):
    azure_devops_pat: SecretStr = Field(min_length=10)


class RejectRequest(BaseModel):
    reason: str = Field(min_length=2, max_length=1000)


class CloseRequest(BaseModel):
    comment: str = Field(min_length=3, max_length=2000)


class PowerAutomateApprovalCallback(BaseModel):
    request_id: str = Field(min_length=3, max_length=100)
    decision: str = Field(min_length=3, max_length=20)
    approver: str = Field(min_length=3, max_length=320)
    comment: str | None = Field(default=None, max_length=2000)
    callback_token: SecretStr = Field(min_length=10)


class PipelineRequest(PipelineRequestCreate):
    id: str
    requested_by: str
    status: str
    created_at: str
    updated_at: str | None = None
    reviewed_by: str | None = None
    review_comments: str | None = None
    closure_comment: str | None = None
    app_owner_decision_by: str | None = None
    app_owner_decision_at: str | None = None
    app_owner_comment: str | None = None
    original_request: dict[str, Any] | None = None
    provisioning: dict[str, Any] = Field(default_factory=dict)
    timeline: list[dict[str, str]] = Field(default_factory=list)


class UserContext(BaseModel):
    username: str
    role: Role


class ServiceOption(BaseModel):
    name: str
    ports: list[int]
