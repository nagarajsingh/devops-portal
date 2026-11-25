from __future__ import annotations

from datetime import date

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
from .inventory_patching import (
    create_asset as create_patching_asset,
    create_cycle as create_patch_cycle,
    delete_asset as delete_patching_asset,
    bulk_delete_assets as bulk_delete_patching_assets,
    list_assets as list_patching_assets,
    list_cycles as list_patch_cycles,
    patching_summary,
    update_asset as update_patching_asset,
    upsert_activity as upsert_patch_activity,
)
from .inventory_patching_export import export_patching_excel, export_patching_pdf
from .inventory_patching_import import commit_patching_workbook, preview_patching_workbook
from .inventory_history import list_history
from .inventory_search import search_inventory
from .inventory_microservices import (
    archive_group,
    archive_service,
    create_configuration,
    create_group,
    create_service,
    delete_configuration,
    list_configurations,
    list_groups,
    list_services,
    restore_group,
    restore_service,
    reveal_configuration_password,
    update_configuration,
    update_group,
    update_service,
)
from .inventory_store import (
    archive_application,
    archive_environment,
    create_application,
    create_environment,
    create_record,
    delete_record,
    get_record,
    list_applications,
    list_audit,
    list_environments,
    list_records,
    restore_application,
    restore_environment,
    reveal_credential,
    summary,
    update_application,
    update_environment,
    update_record,
)
from .models import UserContext

router = APIRouter(prefix="/inventory", tags=["inventory"])


class InventoryApplicationPayload(BaseModel):
    category: str = Field(pattern=r"^(GTB|MICROSERVICES)$")
    code: str = Field(min_length=1, max_length=100)
    display_name: str = Field(default="", max_length=150)


class InventoryEnvironmentPayload(BaseModel):
    category: str = Field(pattern=r"^(GTB|MICROSERVICES)$")
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




class InventoryPatchingAssetPayload(BaseModel):
    asset_identifier: str = Field(default="", max_length=255)
    hostname: str = Field(default="", max_length=255)
    application: str = Field(default="", max_length=255)
    application_owner: str = Field(default="", max_length=255)
    asset_type: str = Field(default="", max_length=100)
    environment_name: str = Field(default="", max_length=150)
    environment_class: str = Field(default="NON_PROD", pattern=r"^(NON_PROD|PROD|DR)$")


class InventoryPatchCyclePayload(BaseModel):
    code: str = Field(min_length=6, max_length=30)


class InventoryPatchingBulkDeletePayload(BaseModel):
    asset_ids: list[int] = Field(min_length=1, max_length=500)


class InventoryPatchActivityPayload(BaseModel):
    previous_patched_date: date | None = None
    planned_date: date | None = None
    status: str = Field(default="NOT_STARTED", max_length=30)
    app_team_approval: str = Field(default="", max_length=255)
    cr_number: str = Field(default="", max_length=100)
    comments: str = Field(default="", max_length=8000)
    patch_role: str = Field(default="", max_length=100)


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
    include_inactive: bool = Query(default=False),
    _: UserContext = Depends(require_devops),
):
    return list_applications(category, include_inactive)


@router.post("/applications", status_code=201)
def add_inventory_application(
    payload: InventoryApplicationPayload,
    user: UserContext = Depends(require_devops),
):
    return create_application(payload.category, payload.code, payload.display_name, user.username)


@router.put("/applications/{application_id}")
def edit_inventory_application(
    application_id: int,
    payload: InventoryApplicationPayload,
    user: UserContext = Depends(require_devops),
):
    return update_application(application_id, payload.category, payload.code, payload.display_name, user.username)


@router.delete("/applications/{application_id}")
def remove_inventory_application(
    application_id: int,
    user: UserContext = Depends(require_devops),
):
    return archive_application(application_id, user.username)


@router.post("/applications/{application_id}/restore")
def restore_inventory_application(
    application_id: int,
    user: UserContext = Depends(require_devops),
):
    return restore_application(application_id, user.username)


@router.get("/environments")
def inventory_environments(
    category: str | None = Query(default=None, pattern=r"^(GTB|MICROSERVICES)$"),
    include_inactive: bool = Query(default=False),
    _: UserContext = Depends(require_devops),
):
    return list_environments(category, include_inactive)


@router.post("/environments", status_code=201)
def add_inventory_environment(
    payload: InventoryEnvironmentPayload,
    user: UserContext = Depends(require_devops),
):
    return create_environment(payload.category, payload.code, payload.display_name, user.username)


@router.put("/environments/{environment_id}")
def edit_inventory_environment(
    environment_id: int,
    payload: InventoryEnvironmentPayload,
    user: UserContext = Depends(require_devops),
):
    return update_environment(environment_id, payload.category, payload.code, payload.display_name, user.username)


@router.delete("/environments/{environment_id}")
def remove_inventory_environment(
    environment_id: int,
    category: str = Query(pattern=r"^(GTB|MICROSERVICES)$"),
    user: UserContext = Depends(require_devops),
):
    return archive_environment(environment_id, category, user.username)


@router.post("/environments/{environment_id}/restore")
def restore_inventory_environment(
    environment_id: int,
    category: str = Query(pattern=r"^(GTB|MICROSERVICES)$"),
    user: UserContext = Depends(require_devops),
):
    return restore_environment(environment_id, category, user.username)


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


@router.get("/history")
def inventory_history(
    entity_type: str = Query(default="", max_length=80),
    entity_id: int | None = Query(default=None, ge=1),
    actor: str = Query(default="", max_length=255),
    action: str = Query(default="", max_length=40),
    q: str = Query(default="", max_length=255),
    limit: int = Query(default=300, ge=1, le=1000),
    _: UserContext = Depends(require_devops),
):
    return list_history(
        entity_type=entity_type,
        entity_id=entity_id,
        actor=actor,
        action=action,
        query_text=q,
        limit=limit,
    )


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
def microservice_groups(
    include_inactive: bool = Query(default=False),
    _: UserContext = Depends(require_devops),
):
    return list_groups(include_inactive)


@router.post("/microservices/groups", status_code=201)
def add_microservice_group(
    payload: InventoryMsGroupPayload,
    user: UserContext = Depends(require_devops),
):
    return create_group(payload.code, payload.display_name, user.username)


@router.put("/microservices/groups/{group_id}")
def edit_microservice_group(
    group_id: int,
    payload: InventoryMsGroupPayload,
    user: UserContext = Depends(require_devops),
):
    return update_group(group_id, payload.code, payload.display_name, user.username)


@router.delete("/microservices/groups/{group_id}")
def remove_microservice_group(
    group_id: int,
    user: UserContext = Depends(require_devops),
):
    return archive_group(group_id, user.username)


@router.post("/microservices/groups/{group_id}/restore")
def restore_microservice_group(
    group_id: int,
    user: UserContext = Depends(require_devops),
):
    return restore_group(group_id, user.username)


@router.get("/microservices/services")
def microservice_services(
    group_id: int | None = Query(default=None, ge=1),
    q: str = Query(default="", max_length=255),
    include_inactive: bool = Query(default=False),
    _: UserContext = Depends(require_devops),
):
    return list_services(group_id, q, include_inactive)


@router.post("/microservices/services", status_code=201)
def add_microservice_service(
    payload: InventoryMsServicePayload,
    user: UserContext = Depends(require_devops),
):
    return create_service(payload.group_id, payload.code, payload.display_name, user.username)


@router.put("/microservices/services/{service_id}")
def edit_microservice_service(
    service_id: int,
    payload: InventoryMsServicePayload,
    user: UserContext = Depends(require_devops),
):
    return update_service(service_id, payload.group_id, payload.code, payload.display_name, user.username)


@router.delete("/microservices/services/{service_id}")
def remove_microservice_service(
    service_id: int,
    user: UserContext = Depends(require_devops),
):
    return archive_service(service_id, user.username)


@router.post("/microservices/services/{service_id}/restore")
def restore_microservice_service(
    service_id: int,
    user: UserContext = Depends(require_devops),
):
    return restore_service(service_id, user.username)


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

@router.get("/search")
def unified_inventory_search(
    q: str = Query(min_length=2, max_length=255),
    limit: int = Query(default=50, ge=1, le=100),
    _: UserContext = Depends(require_devops),
):
    return search_inventory(q, limit)


@router.get("/patching/summary")
def patching_inventory_summary(
    cycle_id: int | None = Query(default=None, ge=1),
    _: UserContext = Depends(require_devops),
):
    return patching_summary(cycle_id)


@router.get("/patching/cycles")
def patching_cycles(_: UserContext = Depends(require_devops)):
    return list_patch_cycles()


@router.post("/patching/cycles", status_code=201)
def add_patching_cycle(
    payload: InventoryPatchCyclePayload,
    user: UserContext = Depends(require_devops),
):
    return create_patch_cycle(payload.code, user.username)


@router.get("/patching/assets")
def patching_assets(
    cycle_id: int | None = Query(default=None, ge=1),
    environment_class: str = Query(default="", max_length=30),
    status: str = Query(default="", max_length=30),
    q: str = Query(default="", max_length=255),
    _: UserContext = Depends(require_devops),
):
    return list_patching_assets(cycle_id, environment_class, status, q)


@router.post("/patching/assets", status_code=201)
def add_patching_asset(
    payload: InventoryPatchingAssetPayload,
    user: UserContext = Depends(require_devops),
):
    return create_patching_asset(payload.model_dump(), user.username)


@router.put("/patching/assets/{asset_id}")
def edit_patching_asset(
    asset_id: int,
    payload: InventoryPatchingAssetPayload,
    user: UserContext = Depends(require_devops),
):
    return update_patching_asset(asset_id, payload.model_dump(), user.username)


@router.delete("/patching/assets/{asset_id}", status_code=204)
def remove_patching_asset(
    asset_id: int,
    user: UserContext = Depends(require_devops),
):
    delete_patching_asset(asset_id, user.username)
    return Response(status_code=204)


@router.post("/patching/assets/bulk-delete")
def remove_patching_assets_bulk(
    payload: InventoryPatchingBulkDeletePayload,
    user: UserContext = Depends(require_devops),
):
    return bulk_delete_patching_assets(payload.asset_ids, user.username)


@router.put("/patching/assets/{asset_id}/cycles/{cycle_id}")
def save_patching_activity(
    asset_id: int,
    cycle_id: int,
    payload: InventoryPatchActivityPayload,
    user: UserContext = Depends(require_devops),
):
    return upsert_patch_activity(asset_id, cycle_id, payload.model_dump(), user.username)


@router.post("/patching/import/preview")
async def preview_patching_import(
    upload: UploadFile = File(...),
    _: UserContext = Depends(require_devops),
):
    content = await _read_inventory_upload(upload)
    return preview_patching_workbook(content)


@router.post("/patching/import/commit")
async def commit_patching_import(
    upload: UploadFile = File(...),
    user: UserContext = Depends(require_devops),
):
    content = await _read_inventory_upload(upload)
    return commit_patching_workbook(content, user.username)


@router.get("/export/patching.xlsx")
def download_patching_excel(
    cycle_id: int | None = Query(default=None, ge=1),
    environment_class: str = Query(default="", max_length=30),
    status: str = Query(default="", max_length=30),
    user: UserContext = Depends(require_devops),
):
    content = export_patching_excel(user.username, cycle_id, environment_class, status)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="patching-inventory.xlsx"'},
    )


@router.get("/export/patching.pdf")
def download_patching_pdf(
    cycle_id: int | None = Query(default=None, ge=1),
    environment_class: str = Query(default="", max_length=30),
    status: str = Query(default="", max_length=30),
    user: UserContext = Depends(require_devops),
):
    content = export_patching_pdf(user.username, cycle_id, environment_class, status)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="patching-inventory.pdf"'},
    )

