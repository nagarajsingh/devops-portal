from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, inspect, select, text as sql_text
from sqlalchemy.orm import Mapped, mapped_column

from .config import CREDENTIAL_ENCRYPTION_KEY
from .user_store import Base, session_factory


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _derived_paths(environment: str, artifacts_location: str | None) -> tuple[str, str, str, str]:
    root = (artifacts_location or "/azure_artifact").rstrip("/") or "/azure_artifact"
    env = environment.strip().lower()
    common = f"{root}/{env}"
    return root, common, f"{common}/channel", f"{common}/consulting/deploy/"


def _normalize_wlst_path(base_path: str | None, wlst_path: str | None) -> str:
    value = (wlst_path or "").strip().rstrip("/")
    if value.endswith("/bin"):
        return value + "/wlst.sh"
    if value:
        return value
    base = (base_path or "").strip().rstrip("/")
    if not base:
        raise HTTPException(status_code=400, detail="BASE or WLST executable path is required")
    return f"{base}/Oracle/Middleware/Oracle_Home/oracle_common/common/bin/wlst.sh"


def initialize_datasource_database() -> None:
    """Create/upgrade datasource metadata tables and seed the supported applications."""
    factory = session_factory()
    engine = factory.kw["bind"]

    # create_all creates new tables. The ALTER statements below keep existing
    # installations forward-compatible because create_all does not add columns.
    inspector = inspect(engine)
    migrations = {
        "weblogic_environment_instances": {
            "inventory_hostname": "VARCHAR(255) NULL",
            "weblogic_username": "VARCHAR(255) NULL",
            "ssh_username": "VARCHAR(255) NULL",
            "artifacts_location": "VARCHAR(255) NULL",
            "common_artifacts_location": "VARCHAR(500) NULL",
            "cz_config_location": "VARCHAR(500) NULL",
            "ear_path": "VARCHAR(500) NULL",
        },
        "datasource_entity_profiles": {
            "schema_username": "VARCHAR(100) NULL",
        },
        "datasource_operations": {
            "schema_username": "VARCHAR(100) NULL",
            "operation_mode": "VARCHAR(20) NULL",
            "datasource_name": "VARCHAR(255) NULL",
            "target_targets": "VARCHAR(2000) NULL",
        },
    }
    with engine.begin() as connection:
        for table_name, columns in migrations.items():
            if not inspector.has_table(table_name):
                continue
            existing = {column["name"].lower() for column in inspector.get_columns(table_name)}
            for column_name, ddl in columns.items():
                if column_name.lower() not in existing:
                    connection.execute(
                        sql_text(f"ALTER TABLE {table_name} ADD {column_name} {ddl}")
                    )

    with factory() as db:
        for code in DATASOURCE_APPLICATIONS:
            existing = db.scalar(
                select(DatasourceApplication).where(DatasourceApplication.code == code)
            )
            if not existing:
                db.add(
                    DatasourceApplication(
                        code=code,
                        display_name=code,
                        is_active=True,
                    )
                )

        environments = list(db.scalars(select(WebLogicEnvironment)).all())
        for row in environments:
            # Existing installations stored usernames together with encrypted
            # passwords in weblogic_credentials. Copy only the usernames into
            # the environment record; passwords are now sourced exclusively
            # from the Ansible Vault file at pipeline runtime.
            if not row.weblogic_username:
                legacy_weblogic = _credential(db, row.id, "WEBLOGIC_ADMIN")
                if legacy_weblogic:
                    row.weblogic_username = legacy_weblogic.username
            if not row.ssh_username:
                legacy_ssh = _credential(db, row.id, "SSH")
                if legacy_ssh:
                    row.ssh_username = legacy_ssh.username

            root, common, channel, ear = _derived_paths(
                row.environment,
                row.artifacts_location,
            )
            changed = False
            if not row.artifacts_location:
                row.artifacts_location = root
                changed = True
            if not row.common_artifacts_location:
                row.common_artifacts_location = common
                changed = True
            if not row.cz_config_location:
                row.cz_config_location = channel
                changed = True
            if not row.ear_path:
                row.ear_path = ear
                changed = True
            if changed:
                row.updated_at = _utcnow()
        db.commit()


def list_applications() -> list[dict[str, Any]]:
    factory = session_factory()
    with factory() as db:
        rows = list(
            db.scalars(
                select(DatasourceApplication)
                .where(DatasourceApplication.is_active== 1)
                .order_by(DatasourceApplication.id)
            ).all()
        )
        return [
            {
                "id": row.id,
                "code": row.code,
                "display_name": row.display_name,
                "is_active": row.is_active,
            }
            for row in rows
        ]


DATASOURCE_APPLICATIONS = (
    "OBP",
    "OBTF",
    "OBTFPM",
    "OBLM",
    "OBVAM",
    "OBVAMIC",
    "OBLMIC",
    "PLATO",
    "CMNCORE",
    "MOCORE",
)


class DatasourceApplication(Base):
    __tablename__ = "datasource_applications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class WebLogicEnvironment(Base):
    __tablename__ = "weblogic_environment_instances"
    __table_args__ = (
        UniqueConstraint("application", "environment", "instance_name", name="uq_weblogic_environment_instance"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    application: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    environment: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    instance_name: Mapped[str] = mapped_column(String(50), nullable=False, default="app1")
    inventory_hostname: Mapped[str | None] = mapped_column(String(255), nullable=True)
    base_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    domain_name: Mapped[str] = mapped_column(String(100), nullable=False)
    admin_host: Mapped[str] = mapped_column(String(255), nullable=False)
    admin_port: Mapped[int] = mapped_column(Integer, nullable=False)
    ssh_port: Mapped[int] = mapped_column(Integer, nullable=False, default=22)
    weblogic_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ssh_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    wlst_path: Mapped[str] = mapped_column(String(500), nullable=False)
    artifacts_location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    common_artifacts_location: Mapped[str | None] = mapped_column(String(500), nullable=True)
    cz_config_location: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ear_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    agent_pool: Mapped[str] = mapped_column(String(100), nullable=False)
    default_db_host: Mapped[str] = mapped_column(String(255), nullable=False)
    default_db_port: Mapped[int] = mapped_column(Integer, nullable=False)
    default_ons_nodes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    is_production: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class WebLogicCredential(Base):
    __tablename__ = "weblogic_credentials"
    __table_args__ = (
        UniqueConstraint("environment_instance_id", "credential_type", name="uq_weblogic_environment_credential"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    environment_instance_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("weblogic_environment_instances.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    credential_type: Mapped[str] = mapped_column(String(50), nullable=False)
    username: Mapped[str] = mapped_column(String(255), nullable=False)
    password_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class DatasourceEntityProfile(Base):
    __tablename__ = "datasource_entity_profiles"
    __table_args__ = (
        UniqueConstraint("environment_instance_id", "entity_code", name="uq_datasource_entity_profile"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    environment_instance_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("weblogic_environment_instances.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entity_code: Mapped[str] = mapped_column(String(30), nullable=False)
    service_id: Mapped[str] = mapped_column(String(100), nullable=False)
    schema_username: Mapped[str | None] = mapped_column(String(100), nullable=True)
    db_host: Mapped[str] = mapped_column(String(255), nullable=False)
    db_port: Mapped[int] = mapped_column(Integer, nullable=False)
    ons_nodes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    password_pattern_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class DatasourceOperation(Base):
    __tablename__ = "datasource_operations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str | None] = mapped_column(String(40), unique=True, index=True, nullable=True)
    environment_instance_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("weblogic_environment_instances.id"),
        nullable=False,
        index=True,
    )
    reference_entity: Mapped[str] = mapped_column(String(30), nullable=False)
    target_entity: Mapped[str] = mapped_column(String(30), nullable=False)
    operation_mode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    datasource_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    target_targets: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    datasource_type: Mapped[str] = mapped_column(String(30), nullable=False)
    db_host: Mapped[str] = mapped_column(String(255), nullable=False)
    db_port: Mapped[int] = mapped_column(Integer, nullable=False)
    service_id: Mapped[str] = mapped_column(String(100), nullable=False)
    schema_username: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ons_nodes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    password_pattern_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="Queued")
    requested_by: Mapped[str] = mapped_column(String(255), nullable=False)
    azure_pipeline_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    azure_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    azure_run_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    preview_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


def _fernet() -> Fernet:
    if not CREDENTIAL_ENCRYPTION_KEY:
        raise HTTPException(
            status_code=503,
            detail="Datasource credential encryption is not configured. Set CREDENTIAL_ENCRYPTION_KEY.",
        )
    try:
        return Fernet(CREDENTIAL_ENCRYPTION_KEY.encode())
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="CREDENTIAL_ENCRYPTION_KEY is invalid. Configure a Fernet-compatible key.",
        ) from exc


def encrypt_secret(value: str) -> str:
    if not value:
        raise HTTPException(status_code=400, detail="Secret value cannot be empty")
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken as exc:
        raise HTTPException(
            status_code=503,
            detail="Stored datasource credential cannot be decrypted with the configured key",
        ) from exc


def _credential(db, environment_id: int, credential_type: str) -> WebLogicCredential | None:
    return db.scalar(
        select(WebLogicCredential).where(
            WebLogicCredential.environment_instance_id == environment_id,
            WebLogicCredential.credential_type == credential_type,
        )
    )


def _upsert_credential(
    db,
    environment_id: int,
    credential_type: str,
    username: str,
    password: str | None,
) -> None:
    username = username.strip()
    existing = _credential(db, environment_id, credential_type)
    if existing:
        if username:
            existing.username = username
        if password:
            existing.password_ciphertext = encrypt_secret(password)
        existing.updated_at = _utcnow()
        return
    if not username or not password:
        return
    db.add(
        WebLogicCredential(
            environment_instance_id=environment_id,
            credential_type=credential_type,
            username=username,
            password_ciphertext=encrypt_secret(password),
        )
    )


def _entity_views(db, environment_id: int) -> list[dict[str, Any]]:
    rows = list(
        db.scalars(
            select(DatasourceEntityProfile)
            .where(DatasourceEntityProfile.environment_instance_id == environment_id)
            .order_by(DatasourceEntityProfile.entity_code)
        ).all()
    )
    return [
        {
            "id": row.id,
            "entity_code": row.entity_code,
            "service_id": row.service_id,
            "schema_username": row.schema_username or "",
            "db_host": row.db_host,
            "db_port": row.db_port,
            "ons_nodes": row.ons_nodes or "",
            "password_pattern_configured": bool(row.password_pattern_ciphertext),
            "updated_at": row.updated_at.isoformat(),
        }
        for row in rows
    ]


def _environment_view(db, row: WebLogicEnvironment) -> dict[str, Any]:
    return {
        "id": row.id,
        "application": row.application,
        "environment": row.environment,
        "instance_name": row.instance_name,
        "inventory_hostname": row.inventory_hostname or "",
        "base_path": row.base_path or "",
        "domain_name": row.domain_name,
        "admin_host": row.admin_host,
        "admin_port": row.admin_port,
        "ssh_port": row.ssh_port,
        "wlst_path": row.wlst_path,
        "artifacts_location": row.artifacts_location or "",
        "common_artifacts_location": row.common_artifacts_location or "",
        "cz_config_location": row.cz_config_location or "",
        "ear_path": row.ear_path or "",
        "agent_pool": row.agent_pool,
        "default_db_host": row.default_db_host,
        "default_db_port": row.default_db_port,
        "default_ons_nodes": row.default_ons_nodes or "",
        "is_production": row.is_production,
        "is_active": row.is_active,
        "weblogic_username": row.weblogic_username or "",
        "ssh_username": row.ssh_username or "",
        "password_source": "ansible_vault",
        "entities": _entity_views(db, row.id),
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def list_environments(active_only: bool = False) -> list[dict[str, Any]]:
    factory = session_factory()
    with factory() as db:
        query = select(WebLogicEnvironment)
        if active_only:
            query = query.where(WebLogicEnvironment.is_active== 1)
        rows = list(
            db.scalars(
                query.order_by(
                    WebLogicEnvironment.application,
                    WebLogicEnvironment.environment,
                    WebLogicEnvironment.instance_name,
                )
            ).all()
        )
        return [_environment_view(db, row) for row in rows]


def get_environment(environment_id: int) -> dict[str, Any]:
    factory = session_factory()
    with factory() as db:
        row = db.get(WebLogicEnvironment, environment_id)
        if not row:
            raise HTTPException(status_code=404, detail="WebLogic environment was not found")
        return _environment_view(db, row)


def get_environment_runtime(environment_id: int) -> dict[str, Any]:
    factory = session_factory()
    with factory() as db:
        row = db.get(WebLogicEnvironment, environment_id)
        if not row or not row.is_active:
            raise HTTPException(status_code=404, detail="Active WebLogic environment was not found")
        if not (row.weblogic_username or "").strip() or not (row.ssh_username or "").strip():
            raise HTTPException(
                status_code=409,
                detail="WebLogic and SSH usernames must be configured in the dashboard environment",
            )
        return _environment_view(db, row)


def create_environment(payload: dict[str, Any]) -> dict[str, Any]:
    factory = session_factory()
    with factory() as db:
        duplicate = db.scalar(
            select(WebLogicEnvironment).where(
                WebLogicEnvironment.application == payload["application"].strip().upper(),
                WebLogicEnvironment.environment == payload["environment"].strip().lower(),
                WebLogicEnvironment.instance_name == payload["instance_name"].strip().lower(),
            )
        )
        if duplicate:
            raise HTTPException(status_code=409, detail="Application/environment/instance already exists")
        application = payload["application"].strip().upper()
        if application not in DATASOURCE_APPLICATIONS:
            raise HTTPException(status_code=400, detail="Unsupported datasource application")
        environment = payload["environment"].strip().lower()
        artifacts_location, common_artifacts_location, cz_config_location, ear_path = _derived_paths(
            environment,
            payload.get("artifacts_location"),
        )
        row = WebLogicEnvironment(
            application=application,
            environment=environment,
            instance_name=payload["instance_name"].strip().lower(),
            inventory_hostname=(payload.get("inventory_hostname") or "").strip() or None,
            base_path=(payload.get("base_path") or "").strip() or None,
            domain_name=payload["domain_name"].strip(),
            admin_host=payload["admin_host"].strip(),
            admin_port=int(payload["admin_port"]),
            ssh_port=int(payload.get("ssh_port") or 22),
            weblogic_username=(payload.get("weblogic_username") or "").strip() or None,
            ssh_username=(payload.get("ssh_username") or "").strip() or None,
            wlst_path=_normalize_wlst_path(payload.get("base_path"), payload.get("wlst_path")),
            artifacts_location=artifacts_location,
            common_artifacts_location=common_artifacts_location,
            cz_config_location=cz_config_location,
            ear_path=ear_path,
            agent_pool=payload["agent_pool"].strip(),
            default_db_host=payload["default_db_host"].strip(),
            default_db_port=int(payload["default_db_port"]),
            default_ons_nodes=(payload.get("default_ons_nodes") or "").strip() or None,
            is_production=bool(payload.get("is_production")),
            is_active=bool(payload.get("is_active", True)),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return _environment_view(db, row)


def update_environment(environment_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    factory = session_factory()
    with factory() as db:
        row = db.get(WebLogicEnvironment, environment_id)
        if not row:
            raise HTTPException(status_code=404, detail="WebLogic environment was not found")
        application = payload["application"].strip().upper()
        if application not in DATASOURCE_APPLICATIONS:
            raise HTTPException(status_code=400, detail="Unsupported datasource application")
        row.application = application
        row.environment = payload["environment"].strip().lower()
        row.instance_name = payload["instance_name"].strip().lower()
        row.inventory_hostname = (payload.get("inventory_hostname") or "").strip() or None
        row.base_path = (payload.get("base_path") or "").strip() or None
        row.domain_name = payload["domain_name"].strip()
        row.admin_host = payload["admin_host"].strip()
        row.admin_port = int(payload["admin_port"])
        row.ssh_port = int(payload.get("ssh_port") or 22)
        row.weblogic_username = (payload.get("weblogic_username") or "").strip() or None
        row.ssh_username = (payload.get("ssh_username") or "").strip() or None
        row.wlst_path = _normalize_wlst_path(payload.get("base_path"), payload.get("wlst_path"))
        (
            row.artifacts_location,
            row.common_artifacts_location,
            row.cz_config_location,
            row.ear_path,
        ) = _derived_paths(row.environment, payload.get("artifacts_location"))
        row.agent_pool = payload["agent_pool"].strip()
        row.default_db_host = payload["default_db_host"].strip()
        row.default_db_port = int(payload["default_db_port"])
        row.default_ons_nodes = (payload.get("default_ons_nodes") or "").strip() or None
        row.is_production = bool(payload.get("is_production"))
        row.is_active = bool(payload.get("is_active", True))
        row.updated_at = _utcnow()
        try:
            db.commit()
        except Exception as exc:
            db.rollback()
            raise HTTPException(status_code=409, detail="Application/environment/instance already exists") from exc
        db.refresh(row)
        return _environment_view(db, row)


def upsert_entity_profile(
    environment_id: int,
    entity_code: str,
    service_id: str,
    schema_username: str,
    db_host: str,
    db_port: int,
    ons_nodes: str,
    password_pattern: str | None,
) -> dict[str, Any]:
    factory = session_factory()
    entity = entity_code.strip().upper()
    with factory() as db:
        if not db.get(WebLogicEnvironment, environment_id):
            raise HTTPException(status_code=404, detail="WebLogic environment was not found")
        row = db.scalar(
            select(DatasourceEntityProfile).where(
                DatasourceEntityProfile.environment_instance_id == environment_id,
                DatasourceEntityProfile.entity_code == entity,
            )
        )
        if not row:
            if not password_pattern:
                raise HTTPException(
                    status_code=400,
                    detail="Password pattern is required when creating a datasource entity profile",
                )
            row = DatasourceEntityProfile(
                environment_instance_id=environment_id,
                entity_code=entity,
                service_id=service_id.strip(),
                schema_username=schema_username.strip().upper(),
                db_host=db_host.strip(),
                db_port=int(db_port),
                ons_nodes=ons_nodes.strip() or None,
                password_pattern_ciphertext=encrypt_secret(password_pattern),
            )
            db.add(row)
        else:
            row.service_id = service_id.strip()
            row.schema_username = schema_username.strip().upper()
            row.db_host = db_host.strip()
            row.db_port = int(db_port)
            row.ons_nodes = ons_nodes.strip() or None
            if password_pattern:
                row.password_pattern_ciphertext = encrypt_secret(password_pattern)
            row.updated_at = _utcnow()
        db.commit()
        db.refresh(row)
        return {
            "id": row.id,
            "entity_code": row.entity_code,
            "service_id": row.service_id,
            "schema_username": row.schema_username or "",
            "db_host": row.db_host,
            "db_port": row.db_port,
            "ons_nodes": row.ons_nodes or "",
            "password_pattern_configured": True,
        }


def get_entity_runtime(environment_id: int, entity_code: str) -> dict[str, Any]:
    factory = session_factory()
    with factory() as db:
        row = db.scalar(
            select(DatasourceEntityProfile).where(
                DatasourceEntityProfile.environment_instance_id == environment_id,
                DatasourceEntityProfile.entity_code == entity_code.strip().upper(),
            )
        )
        if not row:
            raise HTTPException(status_code=404, detail="Datasource entity profile was not found")
        return {
            "entity_code": row.entity_code,
            "service_id": row.service_id,
            "schema_username": row.schema_username or "",
            "db_host": row.db_host,
            "db_port": row.db_port,
            "ons_nodes": row.ons_nodes or "",
            "password_pattern": decrypt_secret(row.password_pattern_ciphertext),
        }


def create_operation(
    environment_id: int,
    reference_entity: str,
    target_entity: str,
    operation_mode: str,
    datasource_name: str,
    target_targets: list[str],
    datasource_type: str,
    db_host: str,
    db_port: int,
    service_id: str,
    schema_username: str,
    ons_nodes: str,
    password_pattern: str,
    requested_by: str,
) -> dict[str, Any]:
    factory = session_factory()
    with factory() as db:
        row = DatasourceOperation(
            environment_instance_id=environment_id,
            reference_entity=reference_entity.strip().upper(),
            target_entity=target_entity.strip().upper(),
            operation_mode=operation_mode.strip().lower(),
            datasource_name=datasource_name.strip() or None,
            target_targets=",".join([value.strip() for value in target_targets if value.strip()]) or None,
            datasource_type=datasource_type.strip().lower(),
            db_host=db_host.strip(),
            db_port=int(db_port),
            service_id=service_id.strip(),
            schema_username=schema_username.strip().upper(),
            ons_nodes=ons_nodes.strip() or None,
            password_pattern_ciphertext=encrypt_secret(password_pattern),
            status="Preview Queued",
            requested_by=requested_by,
        )
        db.add(row)
        db.flush()
        row.request_id = f"DSR-{row.id:06d}"
        db.commit()
        db.refresh(row)
        return operation_view(row)


def operation_view(row: DatasourceOperation) -> dict[str, Any]:
    preview: dict[str, Any] | None = None
    if row.preview_json:
        try:
            preview = json.loads(row.preview_json)
        except json.JSONDecodeError:
            preview = None
    return {
        "id": row.id,
        "request_id": row.request_id,
        "environment_instance_id": row.environment_instance_id,
        "reference_entity": row.reference_entity,
        "target_entity": row.target_entity,
        "operation_mode": row.operation_mode or "create",
        "datasource_name": row.datasource_name or "",
        "target_targets": [value.strip() for value in (row.target_targets or "").split(",") if value.strip()],
        "datasource_type": row.datasource_type,
        "db_host": row.db_host,
        "db_port": row.db_port,
        "service_id": row.service_id,
        "schema_username": row.schema_username or "",
        "ons_nodes": row.ons_nodes or "",
        "status": row.status,
        "requested_by": row.requested_by,
        "azure_pipeline_id": row.azure_pipeline_id,
        "azure_run_id": row.azure_run_id,
        "azure_run_url": row.azure_run_url,
        "preview": preview,
        "result_message": row.result_message,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
    }


def get_operation(operation_id: int) -> dict[str, Any]:
    factory = session_factory()
    with factory() as db:
        row = db.get(DatasourceOperation, operation_id)
        if not row:
            raise HTTPException(status_code=404, detail="Datasource operation was not found")
        return operation_view(row)


def get_operation_runtime(operation_id: int) -> dict[str, Any]:
    factory = session_factory()
    with factory() as db:
        row = db.get(DatasourceOperation, operation_id)
        if not row:
            raise HTTPException(status_code=404, detail="Datasource operation was not found")
        return {
            **operation_view(row),
            "password_pattern": decrypt_secret(row.password_pattern_ciphertext),
        }


def get_operation_runtime_by_request_id(request_id: str) -> dict[str, Any]:
    factory = session_factory()
    with factory() as db:
        row = db.scalar(
            select(DatasourceOperation).where(DatasourceOperation.request_id == request_id.strip())
        )
        if not row:
            raise HTTPException(status_code=404, detail="Datasource operation was not found")
        return {
            **operation_view(row),
            "password_pattern": decrypt_secret(row.password_pattern_ciphertext),
        }


def update_operation(
    operation_id: int,
    *,
    status: str,
    pipeline_id: int | None = None,
    run_id: int | None = None,
    run_url: str | None = None,
    preview: dict[str, Any] | None = None,
    message: str | None = None,
    completed: bool = False,
) -> dict[str, Any]:
    factory = session_factory()
    with factory() as db:
        row = db.get(DatasourceOperation, operation_id)
        if not row:
            raise HTTPException(status_code=404, detail="Datasource operation was not found")
        row.status = status
        if pipeline_id is not None:
            row.azure_pipeline_id = pipeline_id
        if run_id is not None:
            row.azure_run_id = run_id
        if run_url is not None:
            row.azure_run_url = run_url
        if preview is not None:
            row.preview_json = json.dumps(preview)
        if message is not None:
            row.result_message = message
        row.updated_at = _utcnow()
        if completed:
            row.completed_at = _utcnow()
        db.commit()
        db.refresh(row)
        return operation_view(row)


def list_operations(limit: int = 50) -> list[dict[str, Any]]:
    factory = session_factory()
    with factory() as db:
        rows = list(
            db.scalars(
                select(DatasourceOperation)
                .order_by(DatasourceOperation.id.desc())
                .limit(max(1, min(limit, 200)))
            ).all()
        )
        return [operation_view(row) for row in rows]
