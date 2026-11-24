from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import Boolean, DateTime, Integer, String, Text, or_, select
from sqlalchemy.orm import Mapped, mapped_column

from .user_store import Base, session_factory


INVENTORY_ITEM_TYPES: tuple[tuple[str, str], ...] = (
    ("environment", "Environment"),
    ("group", "Group"),
    ("application", "Application"),
    ("service", "Service"),
    ("server", "Server"),
    ("cluster", "Cluster"),
    ("namespace", "Namespace"),
    ("database", "Database"),
    ("middleware", "Middleware"),
    ("owner_team", "Owner / Team"),
    ("region", "Region"),
    ("patching_group", "Patching Group"),
)

VALID_ITEM_TYPES = {item[0] for item in INVENTORY_ITEM_TYPES}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class InventoryItem(Base):
    __tablename__ = "inventory_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    code: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    source_system: Mapped[str] = mapped_column(String(64), nullable=False, default="manual")
    details_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class InventoryAuditEvent(Base):
    __tablename__ = "inventory_audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    item_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    item_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    field_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_by: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="portal")
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, index=True)


def initialize_inventory_database() -> None:
    factory = session_factory()
    Base.metadata.create_all(bind=factory.kw["bind"])
    _seed_known_inventory()


def _clean_text(value: Any, *, required: bool = False, field: str = "value", max_len: int | None = None) -> str:
    text = str(value or "").strip()
    if required and not text:
        raise HTTPException(status_code=400, detail=f"{field} is required")
    if max_len and len(text) > max_len:
        raise HTTPException(status_code=400, detail=f"{field} must be {max_len} characters or fewer")
    return text


def _normalize_type(value: Any) -> str:
    item_type = _clean_text(value, required=True, field="Item type", max_len=64).lower().replace("-", "_").replace(" ", "_")
    if item_type not in VALID_ITEM_TYPES:
        allowed = ", ".join(sorted(VALID_ITEM_TYPES))
        raise HTTPException(status_code=400, detail=f"Unsupported inventory type '{item_type}'. Allowed: {allowed}")
    return item_type


def _details_to_text(details: Any) -> str:
    if details is None:
        details = {}
    if not isinstance(details, dict):
        raise HTTPException(status_code=400, detail="details must be a JSON object")
    return json.dumps(details, sort_keys=True, ensure_ascii=False)


def _details_from_text(value: str | None) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def _value_for_audit(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (dict, list, tuple, bool, int, float)):
        return json.dumps(value, sort_keys=True, ensure_ascii=False)
    return str(value)


def _add_audit(
    db,
    item: InventoryItem,
    *,
    action: str,
    actor: str,
    field_name: str | None,
    old_value: Any,
    new_value: Any,
    source: str = "portal",
) -> None:
    db.add(
        InventoryAuditEvent(
            item_id=item.id,
            item_type=item.item_type,
            item_name=item.name,
            action=action,
            field_name=field_name,
            old_value=_value_for_audit(old_value),
            new_value=_value_for_audit(new_value),
            changed_by=actor,
            source=source,
        )
    )


def _require_parent(db, parent_id: int | None, item_id: int | None = None) -> InventoryItem | None:
    if parent_id is None:
        return None
    if item_id is not None and parent_id == item_id:
        raise HTTPException(status_code=400, detail="An inventory item cannot be its own parent")
    parent = db.get(InventoryItem, parent_id)
    if not parent:
        raise HTTPException(status_code=400, detail="Selected parent inventory item does not exist")
    if not parent.is_active:
        raise HTTPException(status_code=400, detail="Selected parent inventory item is archived")
    return parent


def _ensure_unique(db, item_type: str, name: str, exclude_id: int | None = None) -> None:
    stmt = select(InventoryItem).where(
        InventoryItem.item_type == item_type,
        InventoryItem.name == name,
    )
    if exclude_id is not None:
        stmt = stmt.where(InventoryItem.id != exclude_id)
    existing = db.scalar(stmt)
    if existing:
        if existing.is_active:
            raise HTTPException(status_code=409, detail=f"{item_type.replace('_', ' ').title()} '{name}' already exists")
        raise HTTPException(status_code=409, detail=f"An archived {item_type.replace('_', ' ')} named '{name}' already exists. Restore it instead.")


def _serialize_item(item: InventoryItem, parent_name: str | None = None) -> dict[str, Any]:
    return {
        "id": item.id,
        "item_type": item.item_type,
        "name": item.name,
        "code": item.code or "",
        "description": item.description or "",
        "parent_id": item.parent_id,
        "parent_name": parent_name,
        "source_system": item.source_system,
        "details": _details_from_text(item.details_json),
        "is_active": item.is_active,
        "created_by": item.created_by,
        "updated_by": item.updated_by,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


def _serialize_items(db, items: list[InventoryItem]) -> list[dict[str, Any]]:
    parent_ids = {item.parent_id for item in items if item.parent_id is not None}
    parents = {}
    if parent_ids:
        parents = {item.id: item.name for item in db.scalars(select(InventoryItem).where(InventoryItem.id.in_(parent_ids))).all()}
    return [_serialize_item(item, parents.get(item.parent_id)) for item in items]


def _serialize_audit(event: InventoryAuditEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "item_id": event.item_id,
        "item_type": event.item_type,
        "item_name": event.item_name,
        "action": event.action,
        "field_name": event.field_name,
        "old_value": event.old_value,
        "new_value": event.new_value,
        "changed_by": event.changed_by,
        "source": event.source,
        "changed_at": event.changed_at.isoformat() if event.changed_at else None,
    }


def list_item_types() -> list[dict[str, str]]:
    return [{"value": value, "label": label} for value, label in INVENTORY_ITEM_TYPES]


def list_inventory_items(
    *,
    item_type: str | None = None,
    query: str = "",
    include_inactive: bool = False,
) -> list[dict[str, Any]]:
    factory = session_factory()
    with factory() as db:
        stmt = select(InventoryItem)
        if item_type:
            stmt = stmt.where(InventoryItem.item_type == _normalize_type(item_type))
        if not include_inactive:
            stmt = stmt.where(InventoryItem.is_active.is_(True))
        q = query.strip()
        if q:
            pattern = f"%{q}%"
            stmt = stmt.where(
                or_(
                    InventoryItem.name.ilike(pattern),
                    InventoryItem.code.ilike(pattern),
                    InventoryItem.description.ilike(pattern),
                    InventoryItem.source_system.ilike(pattern),
                    InventoryItem.details_json.ilike(pattern),
                )
            )
        items = list(db.scalars(stmt.order_by(InventoryItem.item_type, InventoryItem.name)).all())
        return _serialize_items(db, items)


def inventory_summary() -> dict[str, Any]:
    factory = session_factory()
    with factory() as db:
        items = list(db.scalars(select(InventoryItem)).all())
        active = [item for item in items if item.is_active]
        counts = Counter(item.item_type for item in active)
        return {
            "total": len(items),
            "active": len(active),
            "archived": len(items) - len(active),
            "by_type": dict(sorted(counts.items())),
        }


def create_inventory_item(payload: dict[str, Any], actor: str) -> dict[str, Any]:
    item_type = _normalize_type(payload.get("item_type"))
    name = _clean_text(payload.get("name"), required=True, field="Name", max_len=255)
    code = _clean_text(payload.get("code"), max_len=128) or None
    description = _clean_text(payload.get("description"))
    source_system = _clean_text(payload.get("source_system") or "manual", required=True, field="Source system", max_len=64)
    parent_id = payload.get("parent_id")
    details_text = _details_to_text(payload.get("details"))
    factory = session_factory()
    with factory() as db:
        _ensure_unique(db, item_type, name)
        parent = _require_parent(db, parent_id)
        item = InventoryItem(
            item_type=item_type,
            name=name,
            code=code,
            description=description,
            parent_id=parent.id if parent else None,
            source_system=source_system,
            details_json=details_text,
            is_active=True,
            created_by=actor,
            updated_by=actor,
        )
        db.add(item)
        db.flush()
        _add_audit(
            db,
            item,
            action="CREATE",
            actor=actor,
            field_name="record",
            old_value=None,
            new_value={
                "item_type": item.item_type,
                "name": item.name,
                "code": item.code,
                "parent_id": item.parent_id,
                "source_system": item.source_system,
                "details": _details_from_text(item.details_json),
            },
        )
        db.commit()
        db.refresh(item)
        return _serialize_item(item, parent.name if parent else None)


def update_inventory_item(item_id: int, payload: dict[str, Any], actor: str) -> dict[str, Any]:
    factory = session_factory()
    with factory() as db:
        item = db.get(InventoryItem, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Inventory item not found")

        changes: list[tuple[str, Any, Any]] = []
        next_type = _normalize_type(payload["item_type"]) if "item_type" in payload else item.item_type
        next_name = _clean_text(payload["name"], required=True, field="Name", max_len=255) if "name" in payload else item.name
        if next_type != item.item_type or next_name != item.name:
            _ensure_unique(db, next_type, next_name, exclude_id=item.id)

        if "item_type" in payload and next_type != item.item_type:
            changes.append(("item_type", item.item_type, next_type))
            item.item_type = next_type
        if "name" in payload and next_name != item.name:
            changes.append(("name", item.name, next_name))
            item.name = next_name
        if "code" in payload:
            new_value = _clean_text(payload.get("code"), max_len=128) or None
            if new_value != item.code:
                changes.append(("code", item.code, new_value))
                item.code = new_value
        if "description" in payload:
            new_value = _clean_text(payload.get("description"))
            if new_value != (item.description or ""):
                changes.append(("description", item.description or "", new_value))
                item.description = new_value
        if "source_system" in payload:
            new_value = _clean_text(payload.get("source_system") or "manual", required=True, field="Source system", max_len=64)
            if new_value != item.source_system:
                changes.append(("source_system", item.source_system, new_value))
                item.source_system = new_value
        if "parent_id" in payload:
            new_parent = _require_parent(db, payload.get("parent_id"), item.id)
            new_parent_id = new_parent.id if new_parent else None
            if new_parent_id != item.parent_id:
                changes.append(("parent_id", item.parent_id, new_parent_id))
                item.parent_id = new_parent_id
        if "details" in payload:
            old_details = _details_from_text(item.details_json)
            new_details = payload.get("details") or {}
            new_text = _details_to_text(new_details)
            if new_text != _details_to_text(old_details):
                changes.append(("details", old_details, new_details))
                item.details_json = new_text

        if not changes:
            parent = db.get(InventoryItem, item.parent_id) if item.parent_id else None
            return _serialize_item(item, parent.name if parent else None)

        item.updated_by = actor
        item.updated_at = _utcnow()
        for field_name, old_value, new_value in changes:
            _add_audit(db, item, action="UPDATE", actor=actor, field_name=field_name, old_value=old_value, new_value=new_value)
        db.commit()
        db.refresh(item)
        parent = db.get(InventoryItem, item.parent_id) if item.parent_id else None
        return _serialize_item(item, parent.name if parent else None)


def archive_inventory_item(item_id: int, actor: str) -> dict[str, Any]:
    factory = session_factory()
    with factory() as db:
        item = db.get(InventoryItem, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Inventory item not found")
        if not item.is_active:
            parent = db.get(InventoryItem, item.parent_id) if item.parent_id else None
            return _serialize_item(item, parent.name if parent else None)
        active_children = db.scalar(
            select(InventoryItem).where(
                InventoryItem.parent_id == item.id,
                InventoryItem.is_active.is_(True),
            )
        )
        if active_children:
            raise HTTPException(status_code=409, detail="Archive or move linked child inventory items before removing this item")
        item.is_active = False
        item.updated_by = actor
        item.updated_at = _utcnow()
        _add_audit(db, item, action="ARCHIVE", actor=actor, field_name="is_active", old_value=True, new_value=False)
        db.commit()
        db.refresh(item)
        parent = db.get(InventoryItem, item.parent_id) if item.parent_id else None
        return _serialize_item(item, parent.name if parent else None)


def restore_inventory_item(item_id: int, actor: str) -> dict[str, Any]:
    factory = session_factory()
    with factory() as db:
        item = db.get(InventoryItem, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Inventory item not found")
        if item.is_active:
            parent = db.get(InventoryItem, item.parent_id) if item.parent_id else None
            return _serialize_item(item, parent.name if parent else None)
        _ensure_unique(db, item.item_type, item.name, exclude_id=item.id)
        parent = _require_parent(db, item.parent_id, item.id)
        item.is_active = True
        item.updated_by = actor
        item.updated_at = _utcnow()
        _add_audit(db, item, action="RESTORE", actor=actor, field_name="is_active", old_value=False, new_value=True)
        db.commit()
        db.refresh(item)
        return _serialize_item(item, parent.name if parent else None)


def list_inventory_history(
    *,
    item_id: int | None = None,
    item_type: str | None = None,
    actor: str = "",
    action: str = "",
    query: str = "",
    limit: int = 250,
) -> list[dict[str, Any]]:
    factory = session_factory()
    with factory() as db:
        stmt = select(InventoryAuditEvent)
        if item_id is not None:
            stmt = stmt.where(InventoryAuditEvent.item_id == item_id)
        if item_type:
            stmt = stmt.where(InventoryAuditEvent.item_type == _normalize_type(item_type))
        if actor.strip():
            stmt = stmt.where(InventoryAuditEvent.changed_by.ilike(f"%{actor.strip()}%"))
        if action.strip():
            stmt = stmt.where(InventoryAuditEvent.action == action.strip().upper())
        if query.strip():
            pattern = f"%{query.strip()}%"
            stmt = stmt.where(
                or_(
                    InventoryAuditEvent.item_name.ilike(pattern),
                    InventoryAuditEvent.changed_by.ilike(pattern),
                    InventoryAuditEvent.field_name.ilike(pattern),
                    InventoryAuditEvent.old_value.ilike(pattern),
                    InventoryAuditEvent.new_value.ilike(pattern),
                )
            )
        events = list(db.scalars(stmt.order_by(InventoryAuditEvent.changed_at.desc(), InventoryAuditEvent.id.desc()).limit(limit)).all())
        return [_serialize_audit(event) for event in events]


def _seed_known_inventory() -> None:
    factory = session_factory()
    with factory() as db:
        if db.scalar(select(InventoryItem.id).limit(1)) is not None:
            return

        def add(item_type: str, name: str, *, parent_id: int | None = None, code: str | None = None, source: str = "bootstrap") -> InventoryItem:
            item = InventoryItem(
                item_type=item_type,
                name=name,
                code=code,
                parent_id=parent_id,
                source_system=source,
                details_json="{}",
                is_active=True,
                created_by="system",
                updated_by="system",
            )
            db.add(item)
            db.flush()
            _add_audit(db, item, action="CREATE", actor="system", field_name="record", old_value=None, new_value={"name": name, "item_type": item_type, "parent_id": parent_id}, source="bootstrap")
            return item

        for environment in ("DEV (CIT)", "SIT", "R2UAT", "PREPROD", "PROD", "DR", "EG-DR", "EG-PROD"):
            add("environment", environment)

        gtb = add("group", "GTB")
        for application in ("OBDX", "OBP", "OBTF", "OBTFPM", "CMNCORE", "MOCORE", "PLATO", "OBVAM", "OBVAMIC", "OBLM", "OBLMIC"):
            add("application", application, parent_id=gtb.id)

        microservices = add("group", "Microservices")
        for application in ("H2H", "COLLECTIONS", "NATIVE-MOBILE-APP", "SAFENET"):
            add("application", application, parent_id=microservices.id)

        db.commit()
