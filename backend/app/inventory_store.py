from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func, or_, select
from sqlalchemy.orm import Mapped, mapped_column

from .config import CREDENTIAL_ENCRYPTION_KEY
from .user_store import Base, session_factory


GTB_APPLICATIONS = (
    "OBDX",
    "OBP",
    "OBTF",
    "OBTFPM",
    "CMNCORE",
    "MOCORE",
    "PLATO",
    "OBVAM",
    "OBVAMIC",
    "OBLM",
    "OBLMIC",
    "SCF",
    "BIP",
    "OBMA",
)

MICROSERVICE_APPLICATIONS = (
    "H2H",
    "COLLECTIONS",
    "NATIVE-MOBILE-APP",
    "SAFENET",
)

DEFAULT_ENVIRONMENTS = (
    "CIT",
    "DEV",
    "GOLD",
    "MIG",
    "OM-SIT",
    "PAK",
    "PAK-CIT",
    "PAK-SIT",
    "PAK-UAT",
    "PRE-PROD",
    "SIT",
    "T24-UAT",
    "TRAIN",
    "UAT",
    "GTB PROD",
    "PROD",
    "GTB DR",
    "SCF DR",
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class InventoryApplication(Base):
    __tablename__ = "inventory_applications"
    __table_args__ = (
        UniqueConstraint("category", "code", name="uq_inventory_application_category_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(150), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class InventoryEnvironment(Base):
    __tablename__ = "inventory_environments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(150), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class InventoryRecord(Base):
    __tablename__ = "inventory_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    application_id: Mapped[int] = mapped_column(Integer, ForeignKey("inventory_applications.id"), nullable=False, index=True)
    environment_id: Mapped[int] = mapped_column(Integer, ForeignKey("inventory_environments.id"), nullable=False, index=True)
    ip_address: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    hostname: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    asset_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    app_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ssh_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    application_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    console_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class InventoryCredential(Base):
    __tablename__ = "inventory_credentials"
    __table_args__ = (
        UniqueConstraint("inventory_record_id", "credential_type", name="uq_inventory_record_credential"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    inventory_record_id: Mapped[int] = mapped_column(Integer, ForeignKey("inventory_records.id", ondelete="CASCADE"), nullable=False, index=True)
    credential_type: Mapped[str] = mapped_column(String(40), nullable=False)
    password_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    updated_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class InventoryAudit(Base):
    __tablename__ = "inventory_audit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    inventory_record_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    detail: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)


def _fernet() -> Fernet:
    if not CREDENTIAL_ENCRYPTION_KEY:
        raise HTTPException(
            status_code=503,
            detail="Inventory credential encryption is not configured. Set CREDENTIAL_ENCRYPTION_KEY.",
        )
    try:
        return Fernet(CREDENTIAL_ENCRYPTION_KEY.encode())
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="CREDENTIAL_ENCRYPTION_KEY is invalid. Configure a Fernet-compatible key.",
        ) from exc


def _encrypt_secret(value: str) -> str:
    if not value:
        raise HTTPException(status_code=400, detail="Credential password cannot be empty")
    return _fernet().encrypt(value.encode()).decode()


def _decrypt_secret(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken as exc:
        raise HTTPException(status_code=503, detail="Stored inventory credential cannot be decrypted") from exc


def initialize_inventory_database() -> None:
    factory = session_factory()
    with factory() as db:
        for category, items in (("GTB", GTB_APPLICATIONS), ("MICROSERVICES", MICROSERVICE_APPLICATIONS)):
            for code in items:
                row = db.scalar(
                    select(InventoryApplication).where(
                        InventoryApplication.category == category,
                        InventoryApplication.code == code,
                    )
                )
                if not row:
                    db.add(
                        InventoryApplication(
                            category=category,
                            code=code,
                            display_name=code,
                            is_active=True,
                        )
                    )

        for index, name in enumerate(DEFAULT_ENVIRONMENTS, start=1):
            row = db.scalar(select(InventoryEnvironment).where(InventoryEnvironment.code == name))
            if not row:
                db.add(
                    InventoryEnvironment(
                        code=name,
                        display_name=name,
                        sort_order=index * 10,
                        is_active=True,
                    )
                )
        db.commit()


def _credential(db, record_id: int, credential_type: str) -> InventoryCredential | None:
    return db.scalar(
        select(InventoryCredential).where(
            InventoryCredential.inventory_record_id == record_id,
            InventoryCredential.credential_type == credential_type,
        )
    )


def _audit(db, record_id: int | None, action: str, actor: str, detail: str = "") -> None:
    db.add(
        InventoryAudit(
            inventory_record_id=record_id,
            action=action,
            actor=actor,
            detail=detail[:1000] if detail else None,
        )
    )


def _application_view(db, row: InventoryApplication) -> dict[str, Any]:
    record_count = db.scalar(
        select(func.count()).select_from(InventoryRecord).where(
            InventoryRecord.application_id == row.id,
            InventoryRecord.is_active == 1,
        )
    ) or 0
    environment_count = db.scalar(
        select(func.count(func.distinct(InventoryRecord.environment_id))).where(
            InventoryRecord.application_id == row.id,
            InventoryRecord.is_active == 1,
        )
    ) or 0
    return {
        "id": row.id,
        "category": row.category,
        "code": row.code,
        "display_name": row.display_name,
        "is_active": row.is_active,
        "record_count": int(record_count),
        "environment_count": int(environment_count),
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def list_applications(category: str | None = None) -> list[dict[str, Any]]:
    factory = session_factory()
    with factory() as db:
        query = select(InventoryApplication).where(InventoryApplication.is_active == 1)
        if category:
            query = query.where(InventoryApplication.category == category.strip().upper())
        rows = list(db.scalars(query.order_by(InventoryApplication.category, InventoryApplication.display_name)).all())
        return [_application_view(db, row) for row in rows]


def create_application(category: str, code: str, display_name: str, actor: str) -> dict[str, Any]:
    category = category.strip().upper()
    code = code.strip().upper()
    display_name = display_name.strip() or code
    if category not in {"GTB", "MICROSERVICES"}:
        raise HTTPException(status_code=400, detail="Category must be GTB or MICROSERVICES")
    factory = session_factory()
    with factory() as db:
        existing = db.scalar(
            select(InventoryApplication).where(
                InventoryApplication.category == category,
                InventoryApplication.code == code,
            )
        )
        if existing:
            raise HTTPException(status_code=409, detail="Inventory application already exists")
        row = InventoryApplication(category=category, code=code, display_name=display_name, is_active=True)
        db.add(row)
        _audit(db, None, "APPLICATION_CREATED", actor, f"{category}/{code}")
        db.commit()
        db.refresh(row)
        return _application_view(db, row)


def list_environments() -> list[dict[str, Any]]:
    factory = session_factory()
    with factory() as db:
        rows = list(
            db.scalars(
                select(InventoryEnvironment)
                .where(InventoryEnvironment.is_active == 1)
                .order_by(InventoryEnvironment.sort_order, InventoryEnvironment.display_name)
            ).all()
        )
        return [
            {
                "id": row.id,
                "code": row.code,
                "display_name": row.display_name,
                "sort_order": row.sort_order,
                "is_active": row.is_active,
                "created_at": row.created_at.isoformat(),
                "updated_at": row.updated_at.isoformat(),
            }
            for row in rows
        ]


def create_environment(code: str, display_name: str, actor: str) -> dict[str, Any]:
    code = code.strip().upper()
    display_name = display_name.strip() or code
    factory = session_factory()
    with factory() as db:
        if db.scalar(select(InventoryEnvironment).where(InventoryEnvironment.code == code)):
            raise HTTPException(status_code=409, detail="Inventory environment already exists")
        max_order = db.scalar(select(func.max(InventoryEnvironment.sort_order))) or 0
        row = InventoryEnvironment(code=code, display_name=display_name, sort_order=int(max_order) + 10, is_active=True)
        db.add(row)
        _audit(db, None, "ENVIRONMENT_CREATED", actor, code)
        db.commit()
        db.refresh(row)
        return {
            "id": row.id,
            "code": row.code,
            "display_name": row.display_name,
            "sort_order": row.sort_order,
            "is_active": row.is_active,
            "created_at": row.created_at.isoformat(),
            "updated_at": row.updated_at.isoformat(),
        }


def _record_view(db, row: InventoryRecord) -> dict[str, Any]:
    app = db.get(InventoryApplication, row.application_id)
    env = db.get(InventoryEnvironment, row.environment_id)
    ssh = _credential(db, row.id, "SSH")
    application = _credential(db, row.id, "APPLICATION")
    return {
        "id": row.id,
        "application_id": row.application_id,
        "application_code": app.code if app else "",
        "application_name": app.display_name if app else "",
        "category": app.category if app else "",
        "environment_id": row.environment_id,
        "environment_code": env.code if env else "",
        "environment_name": env.display_name if env else "",
        "ip_address": row.ip_address or "",
        "hostname": row.hostname or "",
        "asset_type": row.asset_type or "",
        "app_name": row.app_name or "",
        "ssh_username": row.ssh_username or "",
        "ssh_password_configured": bool(ssh),
        "application_username": row.application_username or "",
        "application_password_configured": bool(application),
        "console_details": row.console_details or "",
        "notes": row.notes or "",
        "is_active": row.is_active,
        "created_by": row.created_by,
        "updated_by": row.updated_by,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def list_records(
    application_id: int | None = None,
    environment_id: int | None = None,
    query_text: str = "",
) -> list[dict[str, Any]]:
    factory = session_factory()
    with factory() as db:
        query = select(InventoryRecord).where(InventoryRecord.is_active == 1)
        if application_id:
            query = query.where(InventoryRecord.application_id == application_id)
        if environment_id:
            query = query.where(InventoryRecord.environment_id == environment_id)
        if query_text.strip():
            token = f"%{query_text.strip()}%"
            query = query.where(
                or_(
                    InventoryRecord.ip_address.like(token),
                    InventoryRecord.hostname.like(token),
                    InventoryRecord.asset_type.like(token),
                    InventoryRecord.app_name.like(token),
                    InventoryRecord.console_details.like(token),
                    InventoryRecord.notes.like(token),
                )
            )
        rows = list(db.scalars(query.order_by(InventoryRecord.hostname, InventoryRecord.ip_address, InventoryRecord.id)).all())
        return [_record_view(db, row) for row in rows]


def get_record(record_id: int) -> dict[str, Any]:
    factory = session_factory()
    with factory() as db:
        row = db.get(InventoryRecord, record_id)
        if not row or not row.is_active:
            raise HTTPException(status_code=404, detail="Inventory record was not found")
        return _record_view(db, row)


def _validate_refs(db, application_id: int, environment_id: int) -> None:
    app = db.get(InventoryApplication, application_id)
    env = db.get(InventoryEnvironment, environment_id)
    if not app or not app.is_active:
        raise HTTPException(status_code=400, detail="Selected inventory application is not active")
    if not env or not env.is_active:
        raise HTTPException(status_code=400, detail="Selected inventory environment is not active")


def _upsert_credential(db, record_id: int, credential_type: str, password: str | None, actor: str) -> None:
    if not password:
        return
    existing = _credential(db, record_id, credential_type)
    ciphertext = _encrypt_secret(password)
    if existing:
        existing.password_ciphertext = ciphertext
        existing.updated_by = actor
        existing.updated_at = _utcnow()
    else:
        db.add(
            InventoryCredential(
                inventory_record_id=record_id,
                credential_type=credential_type,
                password_ciphertext=ciphertext,
                updated_by=actor,
            )
        )


def create_record(payload: dict[str, Any], actor: str) -> dict[str, Any]:
    factory = session_factory()
    with factory() as db:
        _validate_refs(db, int(payload["application_id"]), int(payload["environment_id"]))
        row = InventoryRecord(
            application_id=int(payload["application_id"]),
            environment_id=int(payload["environment_id"]),
            ip_address=(payload.get("ip_address") or "").strip() or None,
            hostname=(payload.get("hostname") or "").strip() or None,
            asset_type=(payload.get("asset_type") or "").strip() or None,
            app_name=(payload.get("app_name") or "").strip() or None,
            ssh_username=(payload.get("ssh_username") or "").strip() or None,
            application_username=(payload.get("application_username") or "").strip() or None,
            console_details=(payload.get("console_details") or "").strip() or None,
            notes=(payload.get("notes") or "").strip() or None,
            is_active=True,
            created_by=actor,
            updated_by=actor,
        )
        db.add(row)
        db.flush()
        _upsert_credential(db, row.id, "SSH", payload.get("ssh_password"), actor)
        _upsert_credential(db, row.id, "APPLICATION", payload.get("application_password"), actor)
        _audit(db, row.id, "RECORD_CREATED", actor, f"record={row.id}")
        db.commit()
        db.refresh(row)
        return _record_view(db, row)


def update_record(record_id: int, payload: dict[str, Any], actor: str) -> dict[str, Any]:
    factory = session_factory()
    with factory() as db:
        row = db.get(InventoryRecord, record_id)
        if not row or not row.is_active:
            raise HTTPException(status_code=404, detail="Inventory record was not found")
        _validate_refs(db, int(payload["application_id"]), int(payload["environment_id"]))
        row.application_id = int(payload["application_id"])
        row.environment_id = int(payload["environment_id"])
        row.ip_address = (payload.get("ip_address") or "").strip() or None
        row.hostname = (payload.get("hostname") or "").strip() or None
        row.asset_type = (payload.get("asset_type") or "").strip() or None
        row.app_name = (payload.get("app_name") or "").strip() or None
        row.ssh_username = (payload.get("ssh_username") or "").strip() or None
        row.application_username = (payload.get("application_username") or "").strip() or None
        row.console_details = (payload.get("console_details") or "").strip() or None
        row.notes = (payload.get("notes") or "").strip() or None
        row.updated_by = actor
        row.updated_at = _utcnow()
        _upsert_credential(db, row.id, "SSH", payload.get("ssh_password"), actor)
        _upsert_credential(db, row.id, "APPLICATION", payload.get("application_password"), actor)
        _audit(db, row.id, "RECORD_UPDATED", actor, f"record={row.id}")
        db.commit()
        db.refresh(row)
        return _record_view(db, row)


def delete_record(record_id: int, actor: str) -> None:
    factory = session_factory()
    with factory() as db:
        row = db.get(InventoryRecord, record_id)
        if not row or not row.is_active:
            raise HTTPException(status_code=404, detail="Inventory record was not found")
        row.is_active = False
        row.updated_by = actor
        row.updated_at = _utcnow()
        _audit(db, row.id, "RECORD_DELETED", actor, f"record={row.id}")
        db.commit()


def reveal_credential(record_id: int, credential_type: str, actor: str) -> dict[str, str]:
    credential_type = credential_type.strip().upper()
    if credential_type not in {"SSH", "APPLICATION"}:
        raise HTTPException(status_code=400, detail="Credential type must be SSH or APPLICATION")
    factory = session_factory()
    with factory() as db:
        row = db.get(InventoryRecord, record_id)
        if not row or not row.is_active:
            raise HTTPException(status_code=404, detail="Inventory record was not found")
        credential = _credential(db, record_id, credential_type)
        if not credential:
            raise HTTPException(status_code=404, detail=f"{credential_type.title()} password is not configured")
        _audit(db, row.id, f"{credential_type}_PASSWORD_REVEALED", actor, f"record={row.id}")
        db.commit()
        return {"password": _decrypt_secret(credential.password_ciphertext)}


def list_audit(limit: int = 100) -> list[dict[str, Any]]:
    factory = session_factory()
    with factory() as db:
        rows = list(
            db.scalars(
                select(InventoryAudit)
                .order_by(InventoryAudit.created_at.desc())
                .limit(limit)
            ).all()
        )
        return [
            {
                "id": row.id,
                "inventory_record_id": row.inventory_record_id,
                "action": row.action,
                "actor": row.actor,
                "detail": row.detail or "",
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]


def summary() -> dict[str, Any]:
    factory = session_factory()
    with factory() as db:
        categories = []
        for category in ("GTB", "MICROSERVICES"):
            application_count = db.scalar(
                select(func.count()).select_from(InventoryApplication).where(
                    InventoryApplication.category == category,
                    InventoryApplication.is_active == 1,
                )
            ) or 0
            record_count = db.scalar(
                select(func.count()).select_from(InventoryRecord)
                .join(InventoryApplication, InventoryApplication.id == InventoryRecord.application_id)
                .where(
                    InventoryApplication.category == category,
                    InventoryRecord.is_active == 1,
                )
            ) or 0
            environment_count = db.scalar(
                select(func.count(func.distinct(InventoryRecord.environment_id)))
                .select_from(InventoryRecord)
                .join(InventoryApplication, InventoryApplication.id == InventoryRecord.application_id)
                .where(
                    InventoryApplication.category == category,
                    InventoryRecord.is_active == 1,
                )
            ) or 0
            categories.append({
                "category": category,
                "application_count": int(application_count),
                "record_count": int(record_count),
                "environment_count": int(environment_count),
            })
        return {"categories": categories}
