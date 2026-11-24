from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from .auth import require_devops
from .inventory_store import (
    archive_inventory_item,
    create_inventory_item,
    inventory_summary,
    list_inventory_history,
    list_inventory_items,
    list_item_types,
    restore_inventory_item,
    update_inventory_item,
)
from .models import UserContext


router = APIRouter(prefix="/inventory", tags=["inventory"])


class InventoryItemCreate(BaseModel):
    item_type: str
    name: str
    code: str = ""
    description: str = ""
    parent_id: int | None = None
    source_system: str = "manual"
    details: dict[str, Any] = Field(default_factory=dict)


class InventoryItemUpdate(BaseModel):
    item_type: str | None = None
    name: str | None = None
    code: str | None = None
    description: str | None = None
    parent_id: int | None = None
    source_system: str | None = None
    details: dict[str, Any] | None = None


@router.get("/types")
def get_inventory_types(_: UserContext = Depends(require_devops)):
    return list_item_types()


@router.get("/summary")
def get_inventory_summary(_: UserContext = Depends(require_devops)):
    return inventory_summary()


@router.get("/items")
def get_inventory_items(
    item_type: str | None = None,
    q: str = "",
    include_inactive: bool = False,
    _: UserContext = Depends(require_devops),
):
    return list_inventory_items(item_type=item_type, query=q, include_inactive=include_inactive)


@router.post("/items", status_code=201)
def add_inventory_item(payload: InventoryItemCreate, user: UserContext = Depends(require_devops)):
    return create_inventory_item(payload.model_dump(), user.username)


@router.put("/items/{item_id}")
def edit_inventory_item(item_id: int, payload: InventoryItemUpdate, user: UserContext = Depends(require_devops)):
    return update_inventory_item(item_id, payload.model_dump(exclude_unset=True), user.username)


@router.delete("/items/{item_id}")
def remove_inventory_item(item_id: int, user: UserContext = Depends(require_devops)):
    return archive_inventory_item(item_id, user.username)


@router.post("/items/{item_id}/restore")
def restore_item(item_id: int, user: UserContext = Depends(require_devops)):
    return restore_inventory_item(item_id, user.username)


@router.get("/items/{item_id}/history")
def get_item_history(
    item_id: int,
    limit: int = Query(250, ge=1, le=1000),
    _: UserContext = Depends(require_devops),
):
    return list_inventory_history(item_id=item_id, limit=limit)


@router.get("/history")
def get_inventory_history(
    item_type: str | None = None,
    actor: str = "",
    action: str = "",
    q: str = "",
    limit: int = Query(250, ge=1, le=1000),
    _: UserContext = Depends(require_devops),
):
    return list_inventory_history(item_type=item_type, actor=actor, action=action, query=q, limit=limit)
