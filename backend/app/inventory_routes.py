from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field, SecretStr

from .auth import require_devops
from .inventory_store import (
    create_application,
    create_environment,
    create_record,
    delete_record,
    get_record,
    list_applications,
    list_audit,
    list_environments,
    list_records,
    reveal_credential,
    summary,
    update_record,
)
from .models import UserContext

router = APIRouter(prefix="/inventory", tags=["inventory"])


class InventoryApplicationPayload(BaseModel):
    category: str = Field(pattern=r"^(GTB|MICROSERVICES)$")
    code: str = Field(min_length=1, max_length=100)
    display_name: str = Field(default="", max_length=150)


class InventoryEnvironmentPayload(BaseModel):
    code: str = Field(min_length=1, max_length=100)
    display_name: str = Field(default="", max_length=150)


class InventoryRecordPayload(BaseModel):
    application_id: int
    environment_id: int
    ip_address: str = Field(default="", max_length=100)
    hostname: str = Field(default="", max_length=255)
    asset_type: str = Field(default="", max_length=100)
    app_name: str = Field(default="", max_length=255)
    ssh_username: str = Field(default="", max_length=255)
    ssh_password: SecretStr | None = None
    application_username: str = Field(default="", max_length=255)
    application_password: SecretStr | None = None
    console_details: str = Field(default="", max_length=8000)
    notes: str = Field(default="", max_length=8000)


def _record_payload(payload: InventoryRecordPayload) -> dict:
    data = payload.model_dump(exclude={"ssh_password", "application_password"})
    data["ssh_password"] = payload.ssh_password.get_secret_value() if payload.ssh_password else None
    data["application_password"] = (
        payload.application_password.get_secret_value()
        if payload.application_password
        else None
    )
    return data


@router.get("/summary")
def inventory_summary(_: UserContext = Depends(require_devops)):
    return summary()


@router.get("/applications")
def inventory_applications(
    category: str | None = Query(default=None),
    _: UserContext = Depends(require_devops),
):
    return list_applications(category)


@router.post("/applications", status_code=201)
def add_inventory_application(
    payload: InventoryApplicationPayload,
    user: UserContext = Depends(require_devops),
):
    return create_application(payload.category, payload.code, payload.display_name, user.username)


@router.get("/environments")
def inventory_environments(_: UserContext = Depends(require_devops)):
    return list_environments()


@router.post("/environments", status_code=201)
def add_inventory_environment(
    payload: InventoryEnvironmentPayload,
    user: UserContext = Depends(require_devops),
):
    return create_environment(payload.code, payload.display_name, user.username)


@router.get("/records")
def inventory_records(
    application_id: int | None = Query(default=None, ge=1),
    environment_id: int | None = Query(default=None, ge=1),
    q: str = Query(default="", max_length=255),
    _: UserContext = Depends(require_devops),
):
    return list_records(application_id, environment_id, q)


@router.get("/records/{record_id}")
def inventory_record(record_id: int, _: UserContext = Depends(require_devops)):
    return get_record(record_id)


@router.post("/records", status_code=201)
def add_inventory_record(
    payload: InventoryRecordPayload,
    user: UserContext = Depends(require_devops),
):
    return create_record(_record_payload(payload), user.username)


@router.put("/records/{record_id}")
def edit_inventory_record(
    record_id: int,
    payload: InventoryRecordPayload,
    user: UserContext = Depends(require_devops),
):
    return update_record(record_id, _record_payload(payload), user.username)


@router.delete("/records/{record_id}", status_code=204)
def remove_inventory_record(
    record_id: int,
    user: UserContext = Depends(require_devops),
):
    delete_record(record_id, user.username)
    return Response(status_code=204)


@router.post("/records/{record_id}/credentials/{credential_type}/reveal")
def reveal_inventory_credential(
    record_id: int,
    credential_type: str,
    user: UserContext = Depends(require_devops),
):
    return reveal_credential(record_id, credential_type, user.username)


@router.get("/audit")
def inventory_audit(
    limit: int = Query(default=100, ge=1, le=500),
    _: UserContext = Depends(require_devops),
):
    return list_audit(limit)
