from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func, or_, select
from sqlalchemy.orm import Mapped, mapped_column

from .inventory_history import record_changes, record_history
from .inventory_store import InventoryApplication, InventoryEnvironment, InventoryRecord, _audit, _environment_scope
from .user_store import Base, session_factory


PATCH_STATUSES = ("NOT_STARTED", "SCHEDULED", "IN_PROGRESS", "COMPLETED", "BLOCKED")
ENVIRONMENT_CLASSES = ("NON_PROD", "PROD", "DR")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalise_status(value: str) -> str:
    cleaned = str(value or "").strip().upper().replace(" ", "_").replace("-", "_")
    aliases = {
        "": "NOT_STARTED",
        "NOTSTARTED": "NOT_STARTED",
        "NOT_STARTED": "NOT_STARTED",
        "SCHEDULED": "SCHEDULED",
        "INPROGRESS": "IN_PROGRESS",
        "IN_PROGRESS": "IN_PROGRESS",
        "COMPLETED": "COMPLETED",
        "BLOCKED": "BLOCKED",
    }
    resolved = aliases.get(cleaned.replace("_", ""), aliases.get(cleaned, cleaned))
    if resolved not in PATCH_STATUSES:
        return "NOT_STARTED"
    return resolved


def infer_environment_class(environment_name: str) -> str:
    value = str(environment_name or "").strip().upper()
    if "DR" in value:
        return "DR"
    if "PROD" in value and "PRE" not in value and "NON" not in value:
        return "PROD"
    return "NON_PROD"


class InventoryPatchingAsset(Base):
    __tablename__ = "inventory_patching_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False, default="MANUAL", index=True)
    source_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    asset_identifier: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    hostname: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    application: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    application_owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    asset_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    environment_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    environment_class: Mapped[str] = mapped_column(String(30), nullable=False, default="NON_PROD", index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class InventoryPatchCycle(Base):
    __tablename__ = "inventory_patch_cycles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    quarter: Mapped[int] = mapped_column(Integer, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class InventoryPatchActivity(Base):
    __tablename__ = "inventory_patch_activities"
    __table_args__ = (
        UniqueConstraint("patching_asset_id", "cycle_id", name="uq_inventory_patch_asset_cycle"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patching_asset_id: Mapped[int] = mapped_column(Integer, ForeignKey("inventory_patching_assets.id"), nullable=False, index=True)
    cycle_id: Mapped[int] = mapped_column(Integer, ForeignKey("inventory_patch_cycles.id"), nullable=False, index=True)
    previous_patched_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    planned_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="NOT_STARTED", index=True)
    app_team_approval: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cr_number: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    patch_role: Mapped[str | None] = mapped_column(String(100), nullable=True)
    updated_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


def _cycle_code(quarter: int, year: int) -> str:
    return f"Q{quarter}-{year}"


def ensure_cycle(code: str, actor: str = "system") -> InventoryPatchCycle:
    cleaned = str(code or "").strip().upper().replace(" ", "")
    if not cleaned.startswith("Q") or "-" not in cleaned:
        raise HTTPException(status_code=400, detail="Patch cycle must use format Q3-2026")
    try:
        quarter = int(cleaned[1])
        year = int(cleaned.split("-", 1)[1])
    except (ValueError, IndexError) as exc:
        raise HTTPException(status_code=400, detail="Patch cycle must use format Q3-2026") from exc
    if quarter not in {1, 2, 3, 4} or year < 2000 or year > 2200:
        raise HTTPException(status_code=400, detail="Invalid patch cycle")

    factory = session_factory()
    with factory() as db:
        row = db.scalar(select(InventoryPatchCycle).where(InventoryPatchCycle.code == cleaned))
        if row:
            return row
        row = InventoryPatchCycle(code=cleaned, quarter=quarter, year=year, is_active=True)
        db.add(row)
        db.flush()
        _audit(db, None, "PATCH_CYCLE_CREATED", actor, cleaned)
        record_history(db, entity_type="PATCH_CYCLE", entity_id=row.id, entity_name=cleaned, action="CREATE", actor=actor, field_name="record", new_value={"code": cleaned, "quarter": quarter, "year": year})
        db.commit()
        db.refresh(row)
        return row


def initialize_patching_inventory() -> None:
    now = _utcnow()
    current_quarter = ((now.month - 1) // 3) + 1
    ensure_cycle(_cycle_code(current_quarter, now.year), "system")
    sync_all_gtb_records("system")


def _asset_view(db, row: InventoryPatchingAsset, cycle_id: int | None = None) -> dict[str, Any]:
    if cycle_id:
        activity = db.scalar(
            select(InventoryPatchActivity).where(
                InventoryPatchActivity.patching_asset_id == row.id,
                InventoryPatchActivity.cycle_id == cycle_id,
            )
        )
    else:
        activity = db.scalar(
            select(InventoryPatchActivity)
            .where(InventoryPatchActivity.patching_asset_id == row.id)
            .order_by(InventoryPatchActivity.updated_at.desc())
        )

    cycle = db.get(InventoryPatchCycle, activity.cycle_id) if activity else None
    return {
        "id": row.id,
        "source_type": row.source_type,
        "source_id": row.source_id,
        "asset_identifier": row.asset_identifier,
        "hostname": row.hostname or "",
        "application": row.application or "",
        "application_owner": row.application_owner or "",
        "asset_type": row.asset_type or "",
        "environment_name": row.environment_name or "",
        "environment_class": row.environment_class,
        "is_active": row.is_active,
        "activity": {
            "id": activity.id,
            "cycle_id": activity.cycle_id,
            "cycle_code": cycle.code if cycle else "",
            "previous_patched_date": activity.previous_patched_date.isoformat() if activity.previous_patched_date else "",
            "planned_date": activity.planned_date.isoformat() if activity.planned_date else "",
            "status": activity.status,
            "app_team_approval": activity.app_team_approval or "",
            "cr_number": activity.cr_number or "",
            "comments": activity.comments or "",
            "patch_role": activity.patch_role or "",
            "updated_by": activity.updated_by,
            "updated_at": activity.updated_at.isoformat(),
        } if activity else None,
        "created_by": row.created_by,
        "updated_by": row.updated_by,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def list_cycles() -> list[dict[str, Any]]:
    factory = session_factory()
    with factory() as db:
        rows = list(
            db.scalars(
                select(InventoryPatchCycle)
                .where(InventoryPatchCycle.is_active == 1)
                .order_by(InventoryPatchCycle.year.desc(), InventoryPatchCycle.quarter.desc())
            ).all()
        )
        return [
            {
                "id": row.id,
                "code": row.code,
                "quarter": row.quarter,
                "year": row.year,
                "start_date": row.start_date.isoformat() if row.start_date else "",
                "end_date": row.end_date.isoformat() if row.end_date else "",
                "is_active": row.is_active,
            }
            for row in rows
        ]


def create_cycle(code: str, actor: str) -> dict[str, Any]:
    row = ensure_cycle(code, actor)
    return {
        "id": row.id,
        "code": row.code,
        "quarter": row.quarter,
        "year": row.year,
        "start_date": row.start_date.isoformat() if row.start_date else "",
        "end_date": row.end_date.isoformat() if row.end_date else "",
        "is_active": row.is_active,
    }


def _find_linked_gtb_asset(db, record_id: int) -> InventoryPatchingAsset | None:
    return db.scalar(
        select(InventoryPatchingAsset).where(
            InventoryPatchingAsset.source_type == "GTB",
            InventoryPatchingAsset.source_id == record_id,
        )
    )


def sync_gtb_record(record_id: int, actor: str = "system") -> None:
    factory = session_factory()
    with factory() as db:
        record = db.get(InventoryRecord, record_id)
        if not record or not record.is_active:
            return
        app = db.get(InventoryApplication, record.application_id)
        env = db.get(InventoryEnvironment, record.environment_id)
        env_scope = _environment_scope(db, record.environment_id, "GTB") if env else None
        env_name = env_scope.display_name if env_scope else (env.display_name if env else "")
        if not app or app.category != "GTB":
            return
        identifier = (record.ip_address or record.hostname or "").strip()
        if not identifier:
            return

        row = _find_linked_gtb_asset(db, record.id)
        if not row:
            row = InventoryPatchingAsset(
                source_type="GTB",
                source_id=record.id,
                asset_identifier=identifier,
                hostname=record.hostname or None,
                application=app.display_name,
                application_owner=None,
                asset_type=record.asset_type or None,
                environment_name=env_name or None,
                environment_class=infer_environment_class(env_name),
                is_active=True,
                created_by=actor,
                updated_by=actor,
            )
            db.add(row)
            db.flush()
            _audit(db, None, "PATCH_ASSET_LINKED_FROM_GTB", actor, f"record={record.id} asset={row.id}")
            record_history(db, entity_type="PATCH_ASSET", entity_id=row.id, entity_name=row.hostname or row.asset_identifier, action="CREATE", actor=actor, field_name="record", new_value={"source_type": "GTB", "source_id": record.id, "asset_identifier": row.asset_identifier, "hostname": row.hostname, "application": row.application, "asset_type": row.asset_type, "environment_name": row.environment_name, "environment_class": row.environment_class}, source="gtb_sync")
        else:
            row.asset_identifier = identifier
            row.hostname = record.hostname or None
            row.application = app.display_name
            row.asset_type = record.asset_type or None
            row.environment_name = env_name or None
            row.environment_class = infer_environment_class(env_name)
            row.is_active = True
            row.updated_by = actor
            row.updated_at = _utcnow()
        db.commit()


def sync_all_gtb_records(actor: str = "system") -> None:
    factory = session_factory()
    with factory() as db:
        ids = list(
            db.scalars(
                select(InventoryRecord.id)
                .join(InventoryApplication, InventoryApplication.id == InventoryRecord.application_id)
                .where(
                    InventoryApplication.category == "GTB",
                    InventoryRecord.is_active == 1,
                )
            ).all()
        )
    for record_id in ids:
        sync_gtb_record(int(record_id), actor)


def _find_asset_for_import(db, identifier: str, hostname: str, application: str) -> InventoryPatchingAsset | None:
    clauses = []
    if identifier:
        clauses.append(InventoryPatchingAsset.asset_identifier == identifier)
    if hostname:
        clauses.append(InventoryPatchingAsset.hostname == hostname)
    if not clauses:
        return None
    query = select(InventoryPatchingAsset).where(InventoryPatchingAsset.is_active == 1, or_(*clauses))
    rows = list(db.scalars(query).all())
    if application:
        exact = [row for row in rows if (row.application or "").strip().lower() == application.strip().lower()]
        return exact[0] if exact else None
    return rows[0] if rows else None


def create_asset(payload: dict[str, Any], actor: str) -> dict[str, Any]:
    identifier = str(payload.get("asset_identifier") or "").strip()
    hostname = str(payload.get("hostname") or "").strip()
    if not identifier and not hostname:
        raise HTTPException(status_code=400, detail="IP / Cluster Name or hostname is required")
    identifier = identifier or hostname
    env_class = str(payload.get("environment_class") or "NON_PROD").strip().upper().replace("-", "_")
    if env_class not in ENVIRONMENT_CLASSES:
        raise HTTPException(status_code=400, detail="Environment class must be NON_PROD, PROD or DR")

    factory = session_factory()
    with factory() as db:
        existing = _find_asset_for_import(db, identifier, hostname, str(payload.get("application") or ""))
        if existing:
            raise HTTPException(status_code=409, detail="A matching patching asset already exists")
        row = InventoryPatchingAsset(
            source_type="MANUAL",
            source_id=None,
            asset_identifier=identifier,
            hostname=hostname or None,
            application=str(payload.get("application") or "").strip() or None,
            application_owner=str(payload.get("application_owner") or "").strip() or None,
            asset_type=str(payload.get("asset_type") or "").strip() or None,
            environment_name=str(payload.get("environment_name") or "").strip() or None,
            environment_class=env_class,
            is_active=True,
            created_by=actor,
            updated_by=actor,
        )
        db.add(row)
        db.flush()
        _audit(db, None, "PATCH_ASSET_CREATED", actor, f"asset={row.id}")
        record_history(db, entity_type="PATCH_ASSET", entity_id=row.id, entity_name=row.hostname or row.asset_identifier, action="CREATE", actor=actor, field_name="record", new_value={"asset_identifier": row.asset_identifier, "hostname": row.hostname, "application": row.application, "application_owner": row.application_owner, "asset_type": row.asset_type, "environment_name": row.environment_name, "environment_class": row.environment_class})
        db.commit()
        db.refresh(row)
        return _asset_view(db, row)


def update_asset(asset_id: int, payload: dict[str, Any], actor: str) -> dict[str, Any]:
    factory = session_factory()
    with factory() as db:
        row = db.get(InventoryPatchingAsset, asset_id)
        if not row or not row.is_active:
            raise HTTPException(status_code=404, detail="Patching asset was not found")
        identifier = str(payload.get("asset_identifier") or "").strip()
        hostname = str(payload.get("hostname") or "").strip()
        if not identifier and not hostname:
            raise HTTPException(status_code=400, detail="IP / Cluster Name or hostname is required")
        old_values = {"asset_identifier": row.asset_identifier, "hostname": row.hostname or "", "application": row.application or "", "application_owner": row.application_owner or "", "asset_type": row.asset_type or "", "environment_name": row.environment_name or "", "environment_class": row.environment_class}
        env_class = str(payload.get("environment_class") or row.environment_class).strip().upper().replace("-", "_")
        if env_class not in ENVIRONMENT_CLASSES:
            raise HTTPException(status_code=400, detail="Environment class must be NON_PROD, PROD or DR")
        row.asset_identifier = identifier or hostname
        row.hostname = hostname or None
        row.application = str(payload.get("application") or "").strip() or None
        row.application_owner = str(payload.get("application_owner") or "").strip() or None
        row.asset_type = str(payload.get("asset_type") or "").strip() or None
        row.environment_name = str(payload.get("environment_name") or "").strip() or None
        row.environment_class = env_class
        row.updated_by = actor
        row.updated_at = _utcnow()
        record_changes(db, entity_type="PATCH_ASSET", entity_id=row.id, entity_name=row.hostname or row.asset_identifier, actor=actor, old_values=old_values, new_values={"asset_identifier": row.asset_identifier, "hostname": row.hostname or "", "application": row.application or "", "application_owner": row.application_owner or "", "asset_type": row.asset_type or "", "environment_name": row.environment_name or "", "environment_class": row.environment_class})
        _audit(db, None, "PATCH_ASSET_UPDATED", actor, f"asset={row.id}")
        db.commit()
        db.refresh(row)
        return _asset_view(db, row)


def delete_asset(asset_id: int, actor: str) -> None:
    factory = session_factory()
    with factory() as db:
        row = db.get(InventoryPatchingAsset, asset_id)
        if not row or not row.is_active:
            raise HTTPException(status_code=404, detail="Patching asset was not found")
        if row.source_type == "GTB":
            raise HTTPException(status_code=409, detail="GTB-linked assets remain visible while the GTB record is active")
        row.is_active = False
        row.updated_by = actor
        row.updated_at = _utcnow()
        _audit(db, None, "PATCH_ASSET_DELETED", actor, f"asset={row.id}")
        record_history(db, entity_type="PATCH_ASSET", entity_id=row.id, entity_name=row.hostname or row.asset_identifier, action="ARCHIVE", actor=actor, field_name="is_active", old_value=True, new_value=False)
        db.commit()


def upsert_activity(asset_id: int, cycle_id: int, payload: dict[str, Any], actor: str) -> dict[str, Any]:
    factory = session_factory()
    with factory() as db:
        asset = db.get(InventoryPatchingAsset, asset_id)
        cycle = db.get(InventoryPatchCycle, cycle_id)
        if not asset or not asset.is_active:
            raise HTTPException(status_code=404, detail="Patching asset was not found")
        if not cycle or not cycle.is_active:
            raise HTTPException(status_code=404, detail="Patch cycle was not found")
        row = db.scalar(
            select(InventoryPatchActivity).where(
                InventoryPatchActivity.patching_asset_id == asset_id,
                InventoryPatchActivity.cycle_id == cycle_id,
            )
        )
        created = row is None
        if not row:
            row = InventoryPatchActivity(
                patching_asset_id=asset_id,
                cycle_id=cycle_id,
                updated_by=actor,
            )
            db.add(row)
            db.flush()
        old_values = {"previous_patched_date": row.previous_patched_date, "planned_date": row.planned_date, "status": row.status, "app_team_approval": row.app_team_approval or "", "cr_number": row.cr_number or "", "comments": row.comments or "", "patch_role": row.patch_role or ""}

        row.previous_patched_date = payload.get("previous_patched_date")
        row.planned_date = payload.get("planned_date")
        row.status = _normalise_status(str(payload.get("status") or "NOT_STARTED"))
        row.app_team_approval = str(payload.get("app_team_approval") or "").strip() or None
        row.cr_number = str(payload.get("cr_number") or "").strip() or None
        row.comments = str(payload.get("comments") or "").strip() or None
        row.patch_role = str(payload.get("patch_role") or "").strip() or None
        row.updated_by = actor
        row.updated_at = _utcnow()
        new_values = {"previous_patched_date": row.previous_patched_date, "planned_date": row.planned_date, "status": row.status, "app_team_approval": row.app_team_approval or "", "cr_number": row.cr_number or "", "comments": row.comments or "", "patch_role": row.patch_role or ""}
        if created:
            record_history(db, entity_type="PATCH_ASSET", entity_id=asset.id, entity_name=asset.hostname or asset.asset_identifier, action="UPDATE", actor=actor, field_name=f"{cycle.code}.activity", old_value=None, new_value=new_values)
        else:
            record_changes(db, entity_type="PATCH_ASSET", entity_id=asset.id, entity_name=asset.hostname or asset.asset_identifier, actor=actor, old_values={f"{cycle.code}.{key}": value for key, value in old_values.items()}, new_values={f"{cycle.code}.{key}": value for key, value in new_values.items()})
        _audit(db, None, "PATCH_ACTIVITY_UPDATED", actor, f"asset={asset_id} cycle={cycle.code}")
        db.commit()
        db.refresh(asset)
        return _asset_view(db, asset, cycle_id)


def list_assets(
    cycle_id: int | None = None,
    environment_class: str = "",
    status: str = "",
    query_text: str = "",
) -> list[dict[str, Any]]:
    sync_all_gtb_records("system")
    factory = session_factory()
    with factory() as db:
        query = select(InventoryPatchingAsset).where(InventoryPatchingAsset.is_active == 1)
        if environment_class:
            query = query.where(InventoryPatchingAsset.environment_class == environment_class.strip().upper())
        if query_text.strip():
            token = f"%{query_text.strip()}%"
            query = query.where(or_(
                InventoryPatchingAsset.asset_identifier.like(token),
                InventoryPatchingAsset.hostname.like(token),
                InventoryPatchingAsset.application.like(token),
                InventoryPatchingAsset.application_owner.like(token),
                InventoryPatchingAsset.asset_type.like(token),
                InventoryPatchingAsset.environment_name.like(token),
            ))
        rows = list(db.scalars(query.order_by(InventoryPatchingAsset.environment_class, InventoryPatchingAsset.application, InventoryPatchingAsset.hostname)).all())
        result = [_asset_view(db, row, cycle_id) for row in rows]
        if status:
            wanted = _normalise_status(status)
            if wanted == "NOT_STARTED":
                result = [item for item in result if not item["activity"] or item["activity"]["status"] == wanted]
            else:
                result = [item for item in result if item["activity"] and item["activity"]["status"] == wanted]
        return result


def patching_summary(cycle_id: int | None = None) -> dict[str, Any]:
    rows = list_assets(cycle_id=cycle_id)
    counts = {"NON_PROD": 0, "PROD": 0, "DR": 0}
    statuses = {key: 0 for key in PATCH_STATUSES}
    for item in rows:
        counts[item["environment_class"]] = counts.get(item["environment_class"], 0) + 1
        activity = item.get("activity")
        if activity:
            statuses[activity["status"]] = statuses.get(activity["status"], 0) + 1
        else:
            statuses["NOT_STARTED"] += 1
    return {
        "total_assets": len(rows),
        "environment_counts": counts,
        "status_counts": statuses,
    }


def import_patching_rows(rows: list[dict[str, Any]], cycle_code: str, actor: str) -> dict[str, Any]:
    cycle = ensure_cycle(cycle_code, actor)
    factory = session_factory()
    created_assets = 0
    updated_assets = 0
    updated_activities = 0
    errors: list[str] = []

    with factory() as db:
        for source in rows:
            source_row = int(source.get("source_row") or 0)
            identifier = str(source.get("asset_identifier") or "").strip()
            hostname = str(source.get("hostname") or "").strip()
            application = str(source.get("application") or "").strip()
            if not identifier and not hostname:
                errors.append(f"Row {source_row}: IP / Cluster Name and Hostname are both blank")
                continue

            asset = _find_asset_for_import(db, identifier, hostname, application)
            if not asset:
                asset = InventoryPatchingAsset(
                    source_type="IMPORT",
                    source_id=None,
                    asset_identifier=identifier or hostname,
                    hostname=hostname or None,
                    application=application or None,
                    application_owner=str(source.get("application_owner") or "").strip() or None,
                    asset_type=str(source.get("asset_type") or "").strip() or None,
                    environment_name=str(source.get("environment_name") or "").strip() or None,
                    environment_class=str(source.get("environment_class") or "NON_PROD"),
                    is_active=True,
                    created_by=actor,
                    updated_by=actor,
                )
                db.add(asset)
                db.flush()
                created_assets += 1
            else:
                if asset.source_type != "GTB":
                    asset.hostname = hostname or asset.hostname
                    asset.application = application or asset.application
                    asset.application_owner = str(source.get("application_owner") or "").strip() or asset.application_owner
                    asset.asset_type = str(source.get("asset_type") or "").strip() or asset.asset_type
                    asset.environment_class = str(source.get("environment_class") or asset.environment_class)
                    asset.updated_by = actor
                    asset.updated_at = _utcnow()
                updated_assets += 1

            activity = db.scalar(
                select(InventoryPatchActivity).where(
                    InventoryPatchActivity.patching_asset_id == asset.id,
                    InventoryPatchActivity.cycle_id == cycle.id,
                )
            )
            if not activity:
                activity = InventoryPatchActivity(
                    patching_asset_id=asset.id,
                    cycle_id=cycle.id,
                    updated_by=actor,
                )
                db.add(activity)
            activity.previous_patched_date = source.get("previous_patched_date")
            activity.planned_date = source.get("planned_date")
            activity.status = _normalise_status(str(source.get("status") or "NOT_STARTED"))
            activity.app_team_approval = str(source.get("app_team_approval") or "").strip() or None
            activity.cr_number = str(source.get("cr_number") or "").strip() or None
            activity.comments = str(source.get("comments") or "").strip() or None
            activity.patch_role = str(source.get("patch_role") or "").strip() or None
            activity.updated_by = actor
            activity.updated_at = _utcnow()
            updated_activities += 1

        _audit(
            db,
            None,
            "PATCH_EXCEL_IMPORT",
            actor,
            f"cycle={cycle.code} rows={len(rows)} created_assets={created_assets} updated_assets={updated_assets} activities={updated_activities}",
        )
        db.commit()

    return {
        "cycle_id": cycle.id,
        "cycle_code": cycle.code,
        "created_assets": created_assets,
        "updated_assets": updated_assets,
        "updated_activities": updated_activities,
        "errors": errors[:100],
    }
