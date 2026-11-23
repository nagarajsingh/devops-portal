from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel, Field, SecretStr

from .auth import require_devops
from .inventory_export import (
    export_gtb_excel,
    export_gtb_pdf,
    export_microservices_excel,
    export_microservices_pdf,
)
from .inventory_import import (
    commit_inventory_workbook,
    commit_microservice_workbook,
    preview_inventory_workbook,
    preview_microservice_workbook,
)
from .inventory_microservices import (
    create_configuration,
    create_group,
    create_service,
    delete_configuration,
    list_configurations,
    list_groups,
    list_services,
    reveal_configuration_password,
    update_configuration,
)
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




class InventoryMsGroupPayload(BaseModel):
    code: str = Field(min_length=1, max_length=100)
    display_name: str = Field(default="", max_length=150)


class InventoryMsServicePayload(BaseModel):
    group_id: int = Field(ge=1)
    code: str = Field(min_length=1, max_length=180)
    display_name: str = Field(default="", max_length=220)


class InventoryMsConfigurationPayload(BaseModel):
    service_id: int = Field(ge=1)
    environment_id: int = Field(ge=1)
    connection_name: str = Field(default="PRIMARY", min_length=1, max_length=100)
    db_url: str = Field(default="", max_length=1000)
    db_name: str = Field(default="", max_length=255)
    db_username: str = Field(default="", max_length=255)
    db_password: SecretStr | None = None
    notes: str = Field(default="", max_length=8000)


def _ms_configuration_payload(payload: InventoryMsConfigurationPayload) -> dict:
    data = payload.model_dump(exclude={"db_password"})
    data["db_password"] = payload.db_password.get_secret_value() if payload.db_password else None
    return data


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


async def _read_inventory_upload(upload: UploadFile) -> bytes:
    filename = (upload.filename or "").strip()
    if not filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Inventory import requires an .xlsx Excel file")
    content = await upload.read()
    await upload.close()
    return content


@router.post("/import/preview")
async def preview_inventory_import(
    upload: UploadFile = File(...),
    _: UserContext = Depends(require_devops),
):
    content = await _read_inventory_upload(upload)
    return preview_inventory_workbook(content)


@router.post("/import/commit")
async def commit_inventory_import(
    upload: UploadFile = File(...),
    user: UserContext = Depends(require_devops),
):
    content = await _read_inventory_upload(upload)
    return commit_inventory_workbook(content, user.username)

@router.get("/microservices/groups")
def microservice_groups(_: UserContext = Depends(require_devops)):
    return list_groups()


@router.post("/microservices/groups", status_code=201)
def add_microservice_group(
    payload: InventoryMsGroupPayload,
    user: UserContext = Depends(require_devops),
):
    return create_group(payload.code, payload.display_name, user.username)


@router.get("/microservices/services")
def microservice_services(
    group_id: int | None = Query(default=None, ge=1),
    q: str = Query(default="", max_length=255),
    _: UserContext = Depends(require_devops),
):
    return list_services(group_id, q)


@router.post("/microservices/services", status_code=201)
def add_microservice_service(
    payload: InventoryMsServicePayload,
    user: UserContext = Depends(require_devops),
):
    return create_service(payload.group_id, payload.code, payload.display_name, user.username)


@router.get("/microservices/configurations")
def microservice_configurations(
    service_id: int | None = Query(default=None, ge=1),
    environment_id: int | None = Query(default=None, ge=1),
    q: str = Query(default="", max_length=255),
    _: UserContext = Depends(require_devops),
):
    return list_configurations(service_id, environment_id, q)


@router.post("/microservices/configurations", status_code=201)
def add_microservice_configuration(
    payload: InventoryMsConfigurationPayload,
    user: UserContext = Depends(require_devops),
):
    return create_configuration(_ms_configuration_payload(payload), user.username)


@router.put("/microservices/configurations/{configuration_id}")
def edit_microservice_configuration(
    configuration_id: int,
    payload: InventoryMsConfigurationPayload,
    user: UserContext = Depends(require_devops),
):
    return update_configuration(configuration_id, _ms_configuration_payload(payload), user.username)


@router.delete("/microservices/configurations/{configuration_id}", status_code=204)
def remove_microservice_configuration(
    configuration_id: int,
    user: UserContext = Depends(require_devops),
):
    delete_configuration(configuration_id, user.username)
    return Response(status_code=204)


@router.post("/microservices/configurations/{configuration_id}/credential/reveal")
def reveal_microservice_configuration_password(
    configuration_id: int,
    user: UserContext = Depends(require_devops),
):
    return reveal_configuration_password(configuration_id, user.username)


@router.post("/microservices/import/preview")
async def preview_microservice_import(
    upload: UploadFile = File(...),
    _: UserContext = Depends(require_devops),
):
    content = await _read_inventory_upload(upload)
    return preview_microservice_workbook(content)


@router.post("/microservices/import/commit")
async def commit_microservice_import(
    upload: UploadFile = File(...),
    user: UserContext = Depends(require_devops),
):
    content = await _read_inventory_upload(upload)
    return commit_microservice_workbook(content, user.username)


@router.get("/export/gtb.xlsx")
def download_gtb_excel(
    application_id: int | None = Query(default=None, ge=1),
    environment_id: int | None = Query(default=None, ge=1),
    user: UserContext = Depends(require_devops),
):
    content = export_gtb_excel(user.username, application_id, environment_id)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="gtb-inventory.xlsx"'},
    )


@router.get("/export/gtb.pdf")
def download_gtb_pdf(
    application_id: int | None = Query(default=None, ge=1),
    environment_id: int | None = Query(default=None, ge=1),
    user: UserContext = Depends(require_devops),
):
    content = export_gtb_pdf(user.username, application_id, environment_id)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="gtb-inventory.pdf"'},
    )


@router.get("/export/microservices.xlsx")
def download_microservices_excel(
    group_id: int | None = Query(default=None, ge=1),
    service_id: int | None = Query(default=None, ge=1),
    environment_id: int | None = Query(default=None, ge=1),
    user: UserContext = Depends(require_devops),
):
    content = export_microservices_excel(user.username, group_id, service_id, environment_id)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="microservices-inventory.xlsx"'},
    )


@router.get("/export/microservices.pdf")
def download_microservices_pdf(
    group_id: int | None = Query(default=None, ge=1),
    service_id: int | None = Query(default=None, ge=1),
    environment_id: int | None = Query(default=None, ge=1),
    user: UserContext = Depends(require_devops),
):
    content = export_microservices_pdf(user.username, group_id, service_id, environment_id)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="microservices-inventory.pdf"'},
    )

