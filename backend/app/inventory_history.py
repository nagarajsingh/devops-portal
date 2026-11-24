from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, Integer, String, Text, or_, select
from sqlalchemy.orm import Mapped, mapped_column

from .user_store import Base, session_factory


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class InventoryHistory(Base):
    __tablename__ = "inventory_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    entity_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    field_name: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(60), nullable=False, default="portal", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, index=True)


def _serialise(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "isoformat") and not isinstance(value, str):
        try:
            return value.isoformat()
        except Exception:
            pass
    if isinstance(value, (dict, list, tuple, bool, int, float)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return str(value)


def record_history(
    db,
    *,
    entity_type: str,
    entity_id: int | None,
    entity_name: str,
    action: str,
    actor: str,
    field_name: str | None = None,
    old_value: Any = None,
    new_value: Any = None,
    source: str = "portal",
) -> None:
    db.add(
        InventoryHistory(
            entity_type=entity_type.strip().upper(),
            entity_id=entity_id,
            entity_name=(entity_name or f"{entity_type} #{entity_id or ''}").strip()[:255],
            action=action.strip().upper(),
            field_name=field_name.strip()[:120] if field_name else None,
            old_value=_serialise(old_value),
            new_value=_serialise(new_value),
            actor=actor.strip() or "system",
            source=source.strip().lower() or "portal",
        )
    )


def record_changes(
    db,
    *,
    entity_type: str,
    entity_id: int | None,
    entity_name: str,
    actor: str,
    old_values: dict[str, Any],
    new_values: dict[str, Any],
    source: str = "portal",
    action: str = "UPDATE",
    ignore_fields: set[str] | None = None,
) -> int:
    ignored = ignore_fields or set()
    count = 0
    for field_name in sorted(set(old_values) | set(new_values)):
        if field_name in ignored:
            continue
        old_value = old_values.get(field_name)
        new_value = new_values.get(field_name)
        if _serialise(old_value) == _serialise(new_value):
            continue
        record_history(
            db,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_name=entity_name,
            action=action,
            actor=actor,
            field_name=field_name,
            old_value=old_value,
            new_value=new_value,
            source=source,
        )
        count += 1
    return count


def list_history(
    *,
    entity_type: str = "",
    entity_id: int | None = None,
    actor: str = "",
    action: str = "",
    query_text: str = "",
    limit: int = 300,
) -> list[dict[str, Any]]:
    factory = session_factory()
    with factory() as db:
        query = select(InventoryHistory)
        if entity_type.strip():
            query = query.where(InventoryHistory.entity_type == entity_type.strip().upper())
        if entity_id is not None:
            query = query.where(InventoryHistory.entity_id == entity_id)
        if actor.strip():
            query = query.where(InventoryHistory.actor.like(f"%{actor.strip()}%"))
        if action.strip():
            query = query.where(InventoryHistory.action == action.strip().upper())
        if query_text.strip():
            token = f"%{query_text.strip()}%"
            query = query.where(
                or_(
                    InventoryHistory.entity_name.like(token),
                    InventoryHistory.field_name.like(token),
                    InventoryHistory.old_value.like(token),
                    InventoryHistory.new_value.like(token),
                    InventoryHistory.actor.like(token),
                    InventoryHistory.source.like(token),
                )
            )
        rows = list(
            db.scalars(
                query.order_by(InventoryHistory.created_at.desc(), InventoryHistory.id.desc()).limit(limit)
            ).all()
        )
        return [
            {
                "id": row.id,
                "entity_type": row.entity_type,
                "entity_id": row.entity_id,
                "entity_name": row.entity_name,
                "action": row.action,
                "field_name": row.field_name or "",
                "old_value": row.old_value,
                "new_value": row.new_value,
                "actor": row.actor,
                "source": row.source,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]
