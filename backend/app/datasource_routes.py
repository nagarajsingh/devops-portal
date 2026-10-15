from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, SecretStr

from .auth import require_devops, require_devops_admin
from .datasource_pipeline import run_datasource_pipeline
from .datasource_store import (
    create_environment,
    create_operation,
    get_entity_runtime,
    get_environment_runtime,
    get_operation_runtime,
    list_applications,
    list_environments,
    list_operations,
    update_environment,
    update_operation,
    upsert_entity_profile,
)
from .logging_config import get_logger
from .models import UserContext

router = APIRouter(prefix="/datasources", tags=["datasources"])
logger = get_logger("datasources")


class DatasourceEnvironmentPayload(BaseModel):
    application: str = Field(min_length=2, max_length=50)
    environment: str = Field(min_length=2, max_length=50)
    instance_name: str = Field(default="app1", min_length=2, max_length=50)
    base_path: str = Field(default="", max_length=255)
    domain_name: str = Field(min_length=2, max_length=100)
    admin_host: str = Field(min_length=2, max_length=255)
    admin_port: int = Field(ge=1, le=65535)
    ssh_port: int = Field(default=22, ge=1, le=65535)
    wlst_path: str = Field(min_length=2, max_length=500)
    artifacts_location: str = Field(default="/azure_artifact", min_length=1, max_length=255)
    agent_pool: str = Field(min_length=2, max_length=100)
    default_db_host: str = Field(default="", max_length=255)
    default_db_port: int = Field(default=1531, ge=1, le=65535)
    default_ons_nodes: str = Field(default="", max_length=1000)
    weblogic_username: str = Field(default="", max_length=255)
    weblogic_password: SecretStr | None = None
    ssh_username: str = Field(default="", max_length=255)
    ssh_password: SecretStr | None = None
    is_production: bool = False
    is_active: bool = True


class DatasourceEntityPayload(BaseModel):
    service_id: str = Field(min_length=1, max_length=100)
    schema_username: str = Field(min_length=1, max_length=100)
    db_host: str = Field(min_length=2, max_length=255)
    db_port: int = Field(ge=1, le=65535)
    ons_nodes: str = Field(default="", max_length=1000)
    password_pattern: SecretStr | None = None


class DatasourcePreviewPayload(BaseModel):
    environment_instance_id: int
    reference_entity: str = Field(min_length=1, max_length=30)
    target_entity: str = Field(min_length=1, max_length=30)
    datasource_type: str = Field(pattern=r"^(standalone|gridlink)$")
    db_host: str = Field(min_length=2, max_length=255)
    db_port: int = Field(ge=1, le=65535)
    service_id: str = Field(min_length=1, max_length=100)
    schema_username: str = Field(min_length=1, max_length=100)
    password_pattern: SecretStr | None = None
    ons_nodes: str = Field(default="", max_length=1000)
    azure_devops_pat: SecretStr = Field(min_length=10)


class DatasourceApplyPayload(BaseModel):
    azure_devops_pat: SecretStr = Field(min_length=10)


def _environment_payload(payload: DatasourceEnvironmentPayload) -> dict:
    data = payload.model_dump(exclude={"weblogic_password", "ssh_password"})
    data["weblogic_password"] = (
        payload.weblogic_password.get_secret_value()
        if payload.weblogic_password
        else None
    )
    data["ssh_password"] = (
        payload.ssh_password.get_secret_value()
        if payload.ssh_password
        else None
    )
    return data


@router.get("/applications")
def applications(_: UserContext = Depends(require_devops)):
    return list_applications()


@router.get("/environments")
def environments(_: UserContext = Depends(require_devops)):
    return list_environments(active_only=False)


@router.post("/environments", status_code=201)
def add_environment(
    payload: DatasourceEnvironmentPayload,
    _: UserContext = Depends(require_devops_admin),
):
    return create_environment(_environment_payload(payload))


@router.put("/environments/{environment_id}")
def edit_environment(
    environment_id: int,
    payload: DatasourceEnvironmentPayload,
    _: UserContext = Depends(require_devops_admin),
):
    return update_environment(environment_id, _environment_payload(payload))


@router.put("/environments/{environment_id}/entities/{entity_code}")
def save_entity_profile(
    environment_id: int,
    entity_code: str,
    payload: DatasourceEntityPayload,
    _: UserContext = Depends(require_devops_admin),
):
    password_pattern = (
        payload.password_pattern.get_secret_value()
        if payload.password_pattern
        else None
    )
    return upsert_entity_profile(
        environment_id,
        entity_code,
        payload.service_id,
        payload.schema_username,
        payload.db_host,
        payload.db_port,
        payload.ons_nodes,
        password_pattern,
    )


@router.get("/operations")
def operations(
    limit: int = Query(default=50, ge=1, le=200),
    _: UserContext = Depends(require_devops),
):
    return list_operations(limit)


@router.post("/preview")
def preview_datasources(
    payload: DatasourcePreviewPayload,
    user: UserContext = Depends(require_devops),
):
    environment = get_environment_runtime(payload.environment_instance_id)
    target_entity = payload.target_entity.strip().upper()
    reference_entity = payload.reference_entity.strip().upper()
    if target_entity == reference_entity:
        raise HTTPException(
            status_code=400,
            detail="Target entity must be different from the reference entity",
        )

    password_pattern = (
        payload.password_pattern.get_secret_value()
        if payload.password_pattern
        else None
    )
    if password_pattern:
        upsert_entity_profile(
            payload.environment_instance_id,
            target_entity,
            payload.service_id,
            payload.schema_username,
            payload.db_host,
            payload.db_port,
            payload.ons_nodes,
            password_pattern,
        )
    else:
        existing = get_entity_runtime(payload.environment_instance_id, target_entity)
        password_pattern = existing["password_pattern"]

    operation = create_operation(
        payload.environment_instance_id,
        reference_entity,
        target_entity,
        payload.datasource_type,
        payload.db_host,
        payload.db_port,
        payload.service_id,
        payload.schema_username,
        payload.ons_nodes,
        password_pattern,
        user.username,
    )
    runtime_operation = get_operation_runtime(operation["id"])

    try:
        result = run_datasource_pipeline(
            action="preview",
            request_id=operation["request_id"],
            environment=environment,
            operation=runtime_operation,
            azure_devops_pat=payload.azure_devops_pat.get_secret_value(),
        )
        return update_operation(
            operation["id"],
            status="Previewed",
            pipeline_id=result["pipeline_id"],
            run_id=result["run_id"],
            run_url=result["run_url"],
            preview=result["plan"],
            message="Datasource preview completed from the live WebLogic reference configuration",
        )
    except Exception as exc:
        logger.exception(
            "Datasource preview failed request_id=%s application=%s environment=%s reference_entity=%s target_entity=%s",
            operation["request_id"],
            environment["application"],
            environment["environment"],
            reference_entity,
            target_entity,
        )
        update_operation(
            operation["id"],
            status="Failed",
            message=str(exc),
            completed=True,
        )
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/operations/{operation_id}/apply")
def apply_datasources(
    operation_id: int,
    payload: DatasourceApplyPayload,
    user: UserContext = Depends(require_devops),
):
    operation = get_operation_runtime(operation_id)
    if operation["status"] != "Previewed":
        raise HTTPException(
            status_code=409,
            detail=f"Datasource operation must be Previewed before apply; current status is {operation['status']}",
        )
    if operation["requested_by"].lower() != user.username.lower() and not user.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Only the requester or a DevOps administrator can apply this datasource change",
        )

    environment = get_environment_runtime(operation["environment_instance_id"])
    try:
        update_operation(
            operation_id,
            status="Apply Running",
            message="Datasource creation is running through Azure DevOps",
        )
        result = run_datasource_pipeline(
            action="apply",
            request_id=operation["request_id"],
            environment=environment,
            operation=operation,
            azure_devops_pat=payload.azure_devops_pat.get_secret_value(),
        )
        return update_operation(
            operation_id,
            status="Completed",
            pipeline_id=result["pipeline_id"],
            run_id=result["run_id"],
            run_url=result["run_url"],
            preview=result["plan"],
            message="Datasource changes were applied successfully through WLST",
            completed=True,
        )
    except Exception as exc:
        logger.exception(
            "Datasource apply failed request_id=%s operation_id=%s",
            operation["request_id"],
            operation_id,
        )
        update_operation(
            operation_id,
            status="Failed",
            message=str(exc),
            completed=True,
        )
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(status_code=502, detail=str(exc)) from exc
