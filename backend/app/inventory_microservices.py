from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func, or_, select, text
from sqlalchemy.orm import Mapped, mapped_column

from .inventory_history import record_changes, record_history
from .inventory_store import _audit, _decrypt_secret, _encrypt_secret
from .user_store import Base, session_factory


DEFAULT_GROUPS = (
    ("API-BANKING", "API Banking"),
    ("H2H", "H2H"),
    ("COLLECTIONS", "Collections"),
    ("NATIVE-MOBILE-APP", "Native Mobile App"),
    ("SAFENET", "Safenet"),
)

DEFAULT_SERVICES = (
    ("API-BANKING", "api-banking", "API Banking"),
    ("H2H", "h2h-statement-service", "H2H Statement Service"),
    ("COLLECTIONS", "collections-batch-01-service", "Collections Batch 01 Service"),
    ("NATIVE-MOBILE-APP", "native-mobile-auth-management", "Native Mobile Auth Management"),
)

DEFAULT_ENVIRONMENTS = ("DEV", "SIT", "UAT", "PPR", "PRD", "DR", "EG-UAT", "EG-PRD", "EG-DR")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class InventoryMsGroup(Base):
    __tablename__ = "inventory_ms_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(150), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class InventoryMsService(Base):
    __tablename__ = "inventory_ms_services"
    __table_args__ = (
        UniqueConstraint("group_id", "code", name="uq_inventory_ms_group_service"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(Integer, ForeignKey("inventory_ms_groups.id"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(220), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class InventoryMsConfiguration(Base):
    __tablename__ = "inventory_ms_configurations"
    __table_args__ = (
        UniqueConstraint(
            "service_id",
            "environment_id",
            "connection_name",
            "db_name",
            name="uq_inventory_ms_service_environment_connection_db",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    service_id: Mapped[int] = mapped_column(Integer, ForeignKey("inventory_ms_services.id"), nullable=False, index=True)
    environment_id: Mapped[int] = mapped_column(Integer, ForeignKey("inventory_environments.id"), nullable=False, index=True)
    connection_name: Mapped[str] = mapped_column(String(100), nullable=False, default="PRIMARY")
    db_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    db_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    db_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class InventoryMsCredential(Base):
    __tablename__ = "inventory_ms_credentials"
    __table_args__ = (
        UniqueConstraint("configuration_id", "credential_type", name="uq_inventory_ms_configuration_credential"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    configuration_id: Mapped[int] = mapped_column(Integer, ForeignKey("inventory_ms_configurations.id", ondelete="CASCADE"), nullable=False, index=True)
    credential_type: Mapped[str] = mapped_column(String(40), nullable=False, default="DATABASE")
    password_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    updated_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


def _migrate_configuration_uniqueness(db) -> None:
    """Allow multiple DBs to share the same connection name in one environment.

    Older deployments enforced service + environment + connection_name as the
    unique key. Excel inventories commonly use PRIMARY for several distinct DBs,
    so DB name must be part of the identity.
    """
    db.execute(text("""
        IF EXISTS (
            SELECT 1
            FROM sys.key_constraints
            WHERE [name] = 'uq_inventory_ms_service_environment_connection'
        )
        BEGIN
            ALTER TABLE inventory_ms_configurations
            DROP CONSTRAINT uq_inventory_ms_service_environment_connection;
        END;

        IF NOT EXISTS (
            SELECT 1
            FROM sys.key_constraints
            WHERE [name] = 'uq_inventory_ms_service_environment_connection_db'
        )
        BEGIN
            ALTER TABLE inventory_ms_configurations
            ADD CONSTRAINT uq_inventory_ms_service_environment_connection_db
            UNIQUE (service_id, environment_id, connection_name, db_name);
        END;
    """))


def initialize_microservice_inventory() -> None:
    from .inventory_store import InventoryEnvironment, ensure_environment_scope

    factory = session_factory()
    with factory() as db:
        _migrate_configuration_uniqueness(db)
        for code, display_name in DEFAULT_GROUPS:
            if not db.scalar(select(InventoryMsGroup).where(InventoryMsGroup.code == code)):
                db.add(InventoryMsGroup(code=code, display_name=display_name, is_active=True))

        db.flush()
        group_by_code = {
            row.code: row
            for row in db.scalars(select(InventoryMsGroup)).all()
        }
        for group_code, service_code, display_name in DEFAULT_SERVICES:
            group = group_by_code.get(group_code)
            if group and not db.scalar(
                select(InventoryMsService).where(
                    InventoryMsService.group_id == group.id,
                    InventoryMsService.code == service_code,
                )
            ):
                db.add(
                    InventoryMsService(
                        group_id=group.id,
                        code=service_code,
                        display_name=display_name,
                        is_active=True,
                    )
                )

        max_order = db.scalar(select(func.max(InventoryEnvironment.sort_order))) or 0
        next_order = int(max_order)
        for index, name in enumerate(DEFAULT_ENVIRONMENTS, start=1):
            environment = db.scalar(select(InventoryEnvironment).where(InventoryEnvironment.code == name))
            if not environment:
                next_order += 10
                environment = InventoryEnvironment(code=name, display_name=name, sort_order=next_order, is_active=True)
                db.add(environment)
                db.flush()
            ensure_environment_scope(
                db,
                environment,
                "MICROSERVICES",
                code=name,
                display_name=name,
                sort_order=index * 10,
            )

        # Preserve any environments already referenced by existing Microservices
        # configurations, including custom environments created before scopes.
        for environment_id in db.scalars(
            select(InventoryMsConfiguration.environment_id)
            .where(InventoryMsConfiguration.is_active == 1)
            .distinct()
        ).all():
            environment = db.get(InventoryEnvironment, int(environment_id))
            if environment:
                ensure_environment_scope(db, environment, "MICROSERVICES")
        db.commit()


def _credential(db, configuration_id: int) -> InventoryMsCredential | None:
    return db.scalar(
        select(InventoryMsCredential).where(
            InventoryMsCredential.configuration_id == configuration_id,
            InventoryMsCredential.credential_type == "DATABASE",
        )
    )


def _upsert_credential(db, configuration_id: int, password: str | None, actor: str) -> None:
    if not password:
        return
    existing = _credential(db, configuration_id)
    ciphertext = _encrypt_secret(password)
    if existing:
        existing.password_ciphertext = ciphertext
        existing.updated_by = actor
        existing.updated_at = _utcnow()
    else:
        db.add(
            InventoryMsCredential(
                configuration_id=configuration_id,
                credential_type="DATABASE",
                password_ciphertext=ciphertext,
                updated_by=actor,
            )
        )
    _audit(db, None, "MS_DB_PASSWORD_UPDATED", actor, f"configuration={configuration_id}")


def _group_view(db, row: InventoryMsGroup) -> dict[str, Any]:
    services = db.scalar(
        select(func.count()).select_from(InventoryMsService).where(
            InventoryMsService.group_id == row.id,
            InventoryMsService.is_active == 1,
        )
    ) or 0
    configurations = db.scalar(
        select(func.count()).select_from(InventoryMsConfiguration)
        .join(InventoryMsService, InventoryMsService.id == InventoryMsConfiguration.service_id)
        .where(
            InventoryMsService.group_id == row.id,
            InventoryMsConfiguration.is_active == 1,
        )
    ) or 0
    environments = db.scalar(
        select(func.count(func.distinct(InventoryMsConfiguration.environment_id)))
        .select_from(InventoryMsConfiguration)
        .join(InventoryMsService, InventoryMsService.id == InventoryMsConfiguration.service_id)
        .where(
            InventoryMsService.group_id == row.id,
            InventoryMsConfiguration.is_active == 1,
        )
    ) or 0
    return {
        "id": row.id,
        "code": row.code,
        "display_name": row.display_name,
        "is_active": row.is_active,
        "service_count": int(services),
        "configuration_count": int(configurations),
        "environment_count": int(environments),
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def list_groups(include_inactive: bool = False) -> list[dict[str, Any]]:
    factory = session_factory()
    with factory() as db:
        query = select(InventoryMsGroup)
        if not include_inactive:
            query = query.where(InventoryMsGroup.is_active == 1)
        rows = list(db.scalars(query.order_by(InventoryMsGroup.display_name)).all())
        return [_group_view(db, row) for row in rows]


def create_group(code: str, display_name: str, actor: str) -> dict[str, Any]:
    code = code.strip().upper().replace(" ", "-")
    display_name = display_name.strip() or code
    factory = session_factory()
    with factory() as db:
        if db.scalar(select(InventoryMsGroup).where(InventoryMsGroup.code == code)):
            raise HTTPException(status_code=409, detail="Microservices inventory group already exists")
        row = InventoryMsGroup(code=code, display_name=display_name, is_active=True)
        db.add(row)
        db.flush()
        _audit(db, None, "MS_GROUP_CREATED", actor, code)
        record_history(db, entity_type="MS_GROUP", entity_id=row.id, entity_name=display_name, action="CREATE", actor=actor, field_name="record", new_value={"code": code, "display_name": display_name})
        db.commit()
        db.refresh(row)
        return _group_view(db, row)


def update_group(group_id: int, code: str, display_name: str, actor: str) -> dict[str, Any]:
    code = code.strip().upper().replace(" ", "-")
    display_name = display_name.strip() or code
    factory = session_factory()
    with factory() as db:
        row = db.get(InventoryMsGroup, group_id)
        if not row:
            raise HTTPException(status_code=404, detail="Microservices inventory group was not found")
        duplicate = db.scalar(select(InventoryMsGroup).where(InventoryMsGroup.code == code, InventoryMsGroup.id != group_id))
        if duplicate:
            raise HTTPException(status_code=409, detail="Microservices inventory group already exists")
        old_values = {"code": row.code, "display_name": row.display_name}
        row.code = code
        row.display_name = display_name
        row.updated_at = _utcnow()
        record_changes(db, entity_type="MS_GROUP", entity_id=row.id, entity_name=row.display_name, actor=actor, old_values=old_values, new_values={"code": row.code, "display_name": row.display_name})
        _audit(db, None, "MS_GROUP_UPDATED", actor, code)
        db.commit()
        db.refresh(row)
        return _group_view(db, row)


def archive_group(group_id: int, actor: str) -> dict[str, Any]:
    factory = session_factory()
    with factory() as db:
        row = db.get(InventoryMsGroup, group_id)
        if not row:
            raise HTTPException(status_code=404, detail="Microservices inventory group was not found")
        active_services = db.scalar(select(func.count()).select_from(InventoryMsService).where(InventoryMsService.group_id == row.id, InventoryMsService.is_active == 1)) or 0
        if active_services:
            raise HTTPException(status_code=409, detail=f"Group has {active_services} active service(s). Archive or move them before archiving the group.")
        if row.is_active:
            row.is_active = False
            row.updated_at = _utcnow()
            record_history(db, entity_type="MS_GROUP", entity_id=row.id, entity_name=row.display_name, action="ARCHIVE", actor=actor, field_name="is_active", old_value=True, new_value=False)
            _audit(db, None, "MS_GROUP_ARCHIVED", actor, row.code)
            db.commit()
            db.refresh(row)
        return _group_view(db, row)


def restore_group(group_id: int, actor: str) -> dict[str, Any]:
    factory = session_factory()
    with factory() as db:
        row = db.get(InventoryMsGroup, group_id)
        if not row:
            raise HTTPException(status_code=404, detail="Microservices inventory group was not found")
        if not row.is_active:
            row.is_active = True
            row.updated_at = _utcnow()
            record_history(db, entity_type="MS_GROUP", entity_id=row.id, entity_name=row.display_name, action="RESTORE", actor=actor, field_name="is_active", old_value=False, new_value=True)
            _audit(db, None, "MS_GROUP_RESTORED", actor, row.code)
            db.commit()
            db.refresh(row)
        return _group_view(db, row)


def _service_view(db, row: InventoryMsService) -> dict[str, Any]:
    group = db.get(InventoryMsGroup, row.group_id)
    configurations = db.scalar(
        select(func.count()).select_from(InventoryMsConfiguration).where(
            InventoryMsConfiguration.service_id == row.id,
            InventoryMsConfiguration.is_active == 1,
        )
    ) or 0
    environments = db.scalar(
        select(func.count(func.distinct(InventoryMsConfiguration.environment_id))).where(
            InventoryMsConfiguration.service_id == row.id,
            InventoryMsConfiguration.is_active == 1,
        )
    ) or 0
    return {
        "id": row.id,
        "group_id": row.group_id,
        "group_code": group.code if group else "",
        "group_name": group.display_name if group else "",
        "code": row.code,
        "display_name": row.display_name,
        "is_active": row.is_active,
        "configuration_count": int(configurations),
        "environment_count": int(environments),
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def list_services(group_id: int | None = None, query_text: str = "", include_inactive: bool = False) -> list[dict[str, Any]]:
    factory = session_factory()
    with factory() as db:
        query = select(InventoryMsService)
        if not include_inactive:
            query = query.where(InventoryMsService.is_active == 1)
        if group_id:
            query = query.where(InventoryMsService.group_id == group_id)
        if query_text.strip():
            token = f"%{query_text.strip()}%"
            query = query.where(or_(InventoryMsService.code.like(token), InventoryMsService.display_name.like(token)))
        rows = list(db.scalars(query.order_by(InventoryMsService.display_name)).all())
        return [_service_view(db, row) for row in rows]


def create_service(group_id: int, code: str, display_name: str, actor: str) -> dict[str, Any]:
    code = code.strip()
    display_name = display_name.strip() or code
    factory = session_factory()
    with factory() as db:
        group = db.get(InventoryMsGroup, group_id)
        if not group or not group.is_active:
            raise HTTPException(status_code=400, detail="Selected microservices group is not active")
        if db.scalar(select(InventoryMsService).where(InventoryMsService.group_id == group_id, InventoryMsService.code == code)):
            raise HTTPException(status_code=409, detail="Service already exists in this group")
        row = InventoryMsService(group_id=group_id, code=code, display_name=display_name, is_active=True)
        db.add(row)
        db.flush()
        _audit(db, None, "MS_SERVICE_CREATED", actor, f"{group.code}/{code}")
        record_history(db, entity_type="MS_SERVICE", entity_id=row.id, entity_name=display_name, action="CREATE", actor=actor, field_name="record", new_value={"group_id": group_id, "code": code, "display_name": display_name})
        db.commit()
        db.refresh(row)
        return _service_view(db, row)


def update_service(service_id: int, group_id: int, code: str, display_name: str, actor: str) -> dict[str, Any]:
    code = code.strip()
    display_name = display_name.strip() or code
    factory = session_factory()
    with factory() as db:
        row = db.get(InventoryMsService, service_id)
        group = db.get(InventoryMsGroup, group_id)
        if not row:
            raise HTTPException(status_code=404, detail="Microservice was not found")
        if not group or not group.is_active:
            raise HTTPException(status_code=400, detail="Selected microservices group is not active")
        duplicate = db.scalar(select(InventoryMsService).where(InventoryMsService.group_id == group_id, InventoryMsService.code == code, InventoryMsService.id != service_id))
        if duplicate:
            raise HTTPException(status_code=409, detail="Service already exists in this group")
        old_values = {"group_id": row.group_id, "code": row.code, "display_name": row.display_name}
        row.group_id = group_id
        row.code = code
        row.display_name = display_name
        row.updated_at = _utcnow()
        record_changes(db, entity_type="MS_SERVICE", entity_id=row.id, entity_name=row.display_name, actor=actor, old_values=old_values, new_values={"group_id": row.group_id, "code": row.code, "display_name": row.display_name})
        _audit(db, None, "MS_SERVICE_UPDATED", actor, f"{group.code}/{code}")
        db.commit()
        db.refresh(row)
        return _service_view(db, row)


def archive_service(service_id: int, actor: str) -> dict[str, Any]:
    factory = session_factory()
    with factory() as db:
        row = db.get(InventoryMsService, service_id)
        if not row:
            raise HTTPException(status_code=404, detail="Microservice was not found")
        active_configurations = db.scalar(select(func.count()).select_from(InventoryMsConfiguration).where(InventoryMsConfiguration.service_id == row.id, InventoryMsConfiguration.is_active == 1)) or 0
        if active_configurations:
            raise HTTPException(status_code=409, detail=f"Service has {active_configurations} active configuration(s). Remove or move them before archiving the service.")
        if row.is_active:
            row.is_active = False
            row.updated_at = _utcnow()
            record_history(db, entity_type="MS_SERVICE", entity_id=row.id, entity_name=row.display_name, action="ARCHIVE", actor=actor, field_name="is_active", old_value=True, new_value=False)
            _audit(db, None, "MS_SERVICE_ARCHIVED", actor, row.code)
            db.commit()
            db.refresh(row)
        return _service_view(db, row)


def restore_service(service_id: int, actor: str) -> dict[str, Any]:
    factory = session_factory()
    with factory() as db:
        row = db.get(InventoryMsService, service_id)
        if not row:
            raise HTTPException(status_code=404, detail="Microservice was not found")
        group = db.get(InventoryMsGroup, row.group_id)
        if not group or not group.is_active:
            raise HTTPException(status_code=409, detail="Restore the parent group before restoring this service")
        if not row.is_active:
            row.is_active = True
            row.updated_at = _utcnow()
            record_history(db, entity_type="MS_SERVICE", entity_id=row.id, entity_name=row.display_name, action="RESTORE", actor=actor, field_name="is_active", old_value=False, new_value=True)
            _audit(db, None, "MS_SERVICE_RESTORED", actor, row.code)
            db.commit()
            db.refresh(row)
        return _service_view(db, row)


def _configuration_view(db, row: InventoryMsConfiguration) -> dict[str, Any]:
    from .inventory_store import InventoryEnvironment, _environment_scope

    service = db.get(InventoryMsService, row.service_id)
    group = db.get(InventoryMsGroup, service.group_id) if service else None
    environment = db.get(InventoryEnvironment, row.environment_id)
    environment_scope = _environment_scope(db, row.environment_id, "MICROSERVICES") if environment else None
    credential = _credential(db, row.id)
    return {
        "id": row.id,
        "group_id": group.id if group else 0,
        "group_code": group.code if group else "",
        "group_name": group.display_name if group else "",
        "service_id": row.service_id,
        "service_code": service.code if service else "",
        "service_name": service.display_name if service else "",
        "environment_id": row.environment_id,
        "environment_code": environment_scope.code if environment_scope else (environment.code if environment else ""),
        "environment_name": environment_scope.display_name if environment_scope else (environment.display_name if environment else ""),
        "connection_name": row.connection_name,
        "db_url": row.db_url or "",
        "db_name": row.db_name or "",
        "db_username": row.db_username or "",
        "db_password_configured": bool(credential),
        "notes": row.notes or "",
        "is_active": row.is_active,
        "created_by": row.created_by,
        "updated_by": row.updated_by,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def list_configurations(
    service_id: int | None = None,
    environment_id: int | None = None,
    query_text: str = "",
) -> list[dict[str, Any]]:
    factory = session_factory()
    with factory() as db:
        query = select(InventoryMsConfiguration).where(InventoryMsConfiguration.is_active == 1)
        if service_id:
            query = query.where(InventoryMsConfiguration.service_id == service_id)
        if environment_id:
            query = query.where(InventoryMsConfiguration.environment_id == environment_id)
        if query_text.strip():
            token = f"%{query_text.strip()}%"
            query = query.where(or_(
                InventoryMsConfiguration.connection_name.like(token),
                InventoryMsConfiguration.db_url.like(token),
                InventoryMsConfiguration.db_name.like(token),
                InventoryMsConfiguration.db_username.like(token),
                InventoryMsConfiguration.notes.like(token),
            ))
        rows = list(db.scalars(query.order_by(InventoryMsConfiguration.environment_id, InventoryMsConfiguration.connection_name)).all())
        return [_configuration_view(db, row) for row in rows]


def _validate_configuration_refs(db, service_id: int, environment_id: int) -> None:
    from .inventory_store import InventoryEnvironment, _environment_scope

    service = db.get(InventoryMsService, service_id)
    environment = db.get(InventoryEnvironment, environment_id)
    environment_scope = _environment_scope(db, environment_id, "MICROSERVICES")
    if not service or not service.is_active:
        raise HTTPException(status_code=400, detail="Selected microservice is not active")
    if not environment or not environment.is_active or not environment_scope or not environment_scope.is_active:
        raise HTTPException(status_code=400, detail="Selected environment is not active for MICROSERVICES")


def create_configuration(payload: dict[str, Any], actor: str) -> dict[str, Any]:
    factory = session_factory()
    with factory() as db:
        service_id = int(payload["service_id"])
        environment_id = int(payload["environment_id"])
        connection_name = str(payload.get("connection_name") or "PRIMARY").strip().upper()
        db_name = str(payload.get("db_name") or "").strip()
        _validate_configuration_refs(db, service_id, environment_id)
        existing = db.scalar(select(InventoryMsConfiguration).where(
            InventoryMsConfiguration.service_id == service_id,
            InventoryMsConfiguration.environment_id == environment_id,
            InventoryMsConfiguration.connection_name == connection_name,
            func.coalesce(InventoryMsConfiguration.db_name, "") == db_name,
            InventoryMsConfiguration.is_active == 1,
        ))
        if existing:
            raise HTTPException(status_code=409, detail="This service/environment/connection/DB name already exists")

        row = InventoryMsConfiguration(
            service_id=service_id,
            environment_id=environment_id,
            connection_name=connection_name,
            db_url=str(payload.get("db_url") or "").strip() or None,
            db_name=db_name or None,
            db_username=str(payload.get("db_username") or "").strip() or None,
            notes=str(payload.get("notes") or "").strip() or None,
            is_active=True,
            created_by=actor,
            updated_by=actor,
        )
        db.add(row)
        db.flush()
        _upsert_credential(db, row.id, payload.get("db_password"), actor)
        _audit(db, None, "MS_CONFIGURATION_CREATED", actor, f"configuration={row.id}")
        record_history(db, entity_type="MS_CONFIGURATION", entity_id=row.id, entity_name=f"{connection_name} / service {service_id}", action="CREATE", actor=actor, field_name="record", new_value={"service_id": service_id, "environment_id": environment_id, "connection_name": connection_name, "db_url": row.db_url, "db_name": row.db_name, "db_username": row.db_username, "notes": row.notes})
        db.commit()
        db.refresh(row)
        return _configuration_view(db, row)


def update_configuration(configuration_id: int, payload: dict[str, Any], actor: str) -> dict[str, Any]:
    factory = session_factory()
    with factory() as db:
        row = db.get(InventoryMsConfiguration, configuration_id)
        if not row or not row.is_active:
            raise HTTPException(status_code=404, detail="Microservice database configuration was not found")
        service_id = int(payload["service_id"])
        environment_id = int(payload["environment_id"])
        connection_name = str(payload.get("connection_name") or "PRIMARY").strip().upper()
        db_name = str(payload.get("db_name") or "").strip()
        _validate_configuration_refs(db, service_id, environment_id)

        old_values = {"service_id": row.service_id, "environment_id": row.environment_id, "connection_name": row.connection_name, "db_url": row.db_url or "", "db_name": row.db_name or "", "db_username": row.db_username or "", "notes": row.notes or ""}

        duplicate = db.scalar(select(InventoryMsConfiguration).where(
            InventoryMsConfiguration.service_id == service_id,
            InventoryMsConfiguration.environment_id == environment_id,
            InventoryMsConfiguration.connection_name == connection_name,
            func.coalesce(InventoryMsConfiguration.db_name, "") == db_name,
            InventoryMsConfiguration.id != configuration_id,
            InventoryMsConfiguration.is_active == 1,
        ))
        if duplicate:
            raise HTTPException(status_code=409, detail="Another configuration already uses this service/environment/connection/DB name")

        row.service_id = service_id
        row.environment_id = environment_id
        row.connection_name = connection_name
        row.db_url = str(payload.get("db_url") or "").strip() or None
        row.db_name = db_name or None
        row.db_username = str(payload.get("db_username") or "").strip() or None
        row.notes = str(payload.get("notes") or "").strip() or None
        row.updated_by = actor
        row.updated_at = _utcnow()
        _upsert_credential(db, row.id, payload.get("db_password"), actor)
        new_values = {"service_id": row.service_id, "environment_id": row.environment_id, "connection_name": row.connection_name, "db_url": row.db_url or "", "db_name": row.db_name or "", "db_username": row.db_username or "", "notes": row.notes or ""}
        record_changes(db, entity_type="MS_CONFIGURATION", entity_id=row.id, entity_name=f"{row.connection_name} / service {row.service_id}", actor=actor, old_values=old_values, new_values=new_values)
        if payload.get("db_password"):
            record_history(db, entity_type="MS_CONFIGURATION", entity_id=row.id, entity_name=f"{row.connection_name} / service {row.service_id}", action="UPDATE", actor=actor, field_name="db_password", old_value="[REDACTED]", new_value="[UPDATED]")
        _audit(db, None, "MS_CONFIGURATION_UPDATED", actor, f"configuration={row.id}")
        db.commit()
        db.refresh(row)
        return _configuration_view(db, row)


def delete_configuration(configuration_id: int, actor: str) -> None:
    factory = session_factory()
    with factory() as db:
        row = db.get(InventoryMsConfiguration, configuration_id)
        if not row or not row.is_active:
            raise HTTPException(status_code=404, detail="Microservice database configuration was not found")
        row.is_active = False
        row.updated_by = actor
        row.updated_at = _utcnow()
        _audit(db, None, "MS_CONFIGURATION_DELETED", actor, f"configuration={row.id}")
        record_history(db, entity_type="MS_CONFIGURATION", entity_id=row.id, entity_name=f"{row.connection_name} / service {row.service_id}", action="ARCHIVE", actor=actor, field_name="is_active", old_value=True, new_value=False)
        db.commit()


def reveal_configuration_password(configuration_id: int, actor: str) -> dict[str, str]:
    factory = session_factory()
    with factory() as db:
        row = db.get(InventoryMsConfiguration, configuration_id)
        if not row or not row.is_active:
            raise HTTPException(status_code=404, detail="Microservice database configuration was not found")
        credential = _credential(db, configuration_id)
        if not credential:
            raise HTTPException(status_code=404, detail="Database password is not configured")
        _audit(db, None, "MS_DB_PASSWORD_REVEALED", actor, f"configuration={configuration_id}")
        record_history(db, entity_type="MS_CONFIGURATION", entity_id=row.id, entity_name=f"{row.connection_name} / service {row.service_id}", action="ACCESS", actor=actor, field_name="db_password", new_value="[REVEALED]")
        db.commit()
        return {"password": _decrypt_secret(credential.password_ciphertext)}


def microservice_summary() -> dict[str, int]:
    factory = session_factory()
    with factory() as db:
        groups = db.scalar(select(func.count()).select_from(InventoryMsGroup).where(InventoryMsGroup.is_active == 1)) or 0
        services = db.scalar(select(func.count()).select_from(InventoryMsService).where(InventoryMsService.is_active == 1)) or 0
        configurations = db.scalar(select(func.count()).select_from(InventoryMsConfiguration).where(InventoryMsConfiguration.is_active == 1)) or 0
        environments = db.scalar(select(func.count(func.distinct(InventoryMsConfiguration.environment_id))).where(InventoryMsConfiguration.is_active == 1)) or 0
        return {
            "group_count": int(groups),
            "service_count": int(services),
            "configuration_count": int(configurations),
            "environment_count": int(environments),
        }


def import_microservice_rows(rows: list[dict[str, Any]], actor: str) -> dict[str, Any]:
    from .inventory_store import InventoryEnvironment, InventoryEnvironmentScope, ensure_environment_scope

    factory = session_factory()
    with factory() as db:
        groups = {row.code.upper(): row for row in db.scalars(select(InventoryMsGroup)).all()}
        services = {(row.group_id, row.code.lower()): row for row in db.scalars(select(InventoryMsService)).all()}
        environments = {
            scope.code.upper(): db.get(InventoryEnvironment, scope.environment_id)
            for scope in db.scalars(
                select(InventoryEnvironmentScope).where(InventoryEnvironmentScope.category == "MICROSERVICES")
            ).all()
        }
        configurations = {
            (
                row.service_id,
                row.environment_id,
                row.connection_name.upper(),
                (row.db_name or "").strip().lower(),
            ): row
            for row in db.scalars(select(InventoryMsConfiguration).where(InventoryMsConfiguration.is_active == 1)).all()
        }

        created = 0
        updated = 0
        skipped = 0
        created_groups: list[str] = []
        created_services: list[str] = []
        created_environments: list[str] = []
        errors: list[str] = []

        for source in rows:
            source_row = int(source.get("source_row") or 0)
            group_code = str(source.get("group") or "").strip().upper().replace(" ", "-")
            group_name = str(source.get("group") or "").strip() or group_code
            service_code = str(source.get("service") or "").strip()
            environment_code = str(source.get("environment") or "").strip().upper()
            connection_name = str(source.get("connection_name") or "PRIMARY").strip().upper() or "PRIMARY"
            db_name = str(source.get("db_name") or "").strip()

            if not group_code or not service_code or not environment_code:
                skipped += 1
                errors.append(f"Row {source_row}: GROUP, SERVICE and ENV are required")
                continue

            group = groups.get(group_code)
            if not group:
                group = InventoryMsGroup(code=group_code, display_name=group_name, is_active=True)
                db.add(group)
                db.flush()
                groups[group_code] = group
                created_groups.append(group_name)
                _audit(db, None, "MS_GROUP_CREATED_BY_IMPORT", actor, group_code)

            service_key = (group.id, service_code.lower())
            service = services.get(service_key)
            if not service:
                service = InventoryMsService(group_id=group.id, code=service_code, display_name=service_code, is_active=True)
                db.add(service)
                db.flush()
                services[service_key] = service
                created_services.append(f"{group.display_name}/{service_code}")
                _audit(db, None, "MS_SERVICE_CREATED_BY_IMPORT", actor, f"{group.code}/{service_code}")

            environment = environments.get(environment_code)
            if not environment:
                max_order = max((item.sort_order for item in environments.values()), default=0)
                environment = db.scalar(select(InventoryEnvironment).where(InventoryEnvironment.code == environment_code))
                if not environment:
                    environment = InventoryEnvironment(code=environment_code, display_name=environment_code, sort_order=max_order + 10, is_active=True)
                    db.add(environment)
                    db.flush()
                ensure_environment_scope(
                    db,
                    environment,
                    "MICROSERVICES",
                    code=environment_code,
                    display_name=environment_code,
                    sort_order=max_order + 10,
                )
                environments[environment_code] = environment
                created_environments.append(environment_code)
                _audit(db, None, "MICROSERVICES_ENVIRONMENT_CREATED_BY_IMPORT", actor, environment_code)

            key = (service.id, environment.id, connection_name, db_name.lower())
            configuration = configurations.get(key)
            if configuration:
                configuration.db_url = str(source.get("db_url") or "").strip() or None
                configuration.db_name = db_name or None
                configuration.db_username = str(source.get("db_username") or "").strip() or None
                configuration.notes = str(source.get("notes") or "").strip() or None
                configuration.updated_by = actor
                configuration.updated_at = _utcnow()
                _upsert_credential(db, configuration.id, str(source.get("db_password") or "").strip() or None, actor)
                _audit(db, None, "MS_CONFIGURATION_UPDATED_BY_IMPORT", actor, f"configuration={configuration.id} source_row={source_row}")
                updated += 1
            else:
                configuration = InventoryMsConfiguration(
                    service_id=service.id,
                    environment_id=environment.id,
                    connection_name=connection_name,
                    db_url=str(source.get("db_url") or "").strip() or None,
                    db_name=db_name or None,
                    db_username=str(source.get("db_username") or "").strip() or None,
                    notes=str(source.get("notes") or "").strip() or None,
                    is_active=True,
                    created_by=actor,
                    updated_by=actor,
                )
                db.add(configuration)
                db.flush()
                _upsert_credential(db, configuration.id, str(source.get("db_password") or "").strip() or None, actor)
                configurations[key] = configuration
                _audit(db, None, "MS_CONFIGURATION_CREATED_BY_IMPORT", actor, f"configuration={configuration.id} source_row={source_row}")
                created += 1

        _audit(
            db,
            None,
            "MS_EXCEL_IMPORT",
            actor,
            f"rows={len(rows)} created={created} updated={updated} skipped={skipped}",
        )
        db.commit()
        return {
            "created_count": created,
            "updated_count": updated,
            "skipped_count": skipped,
            "created_groups": created_groups,
            "created_services": created_services,
            "created_environments": created_environments,
            "errors": errors[:100],
        }
