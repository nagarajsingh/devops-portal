from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import quote_plus

import bcrypt
from fastapi import HTTPException
from sqlalchemy import Boolean, DateTime, Integer, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .config import DB_DRIVER, DB_ENCRYPT, DB_NAME, DB_PASSWORD, DB_PORT, DB_SERVER, DB_TRUST_SERVER_CERTIFICATE, DB_USERNAME


class Base(DeclarativeBase):
    pass


class PortalUser(Base):
    __tablename__ = "portal_users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


def _connection_url() -> str:
    if not all((DB_SERVER, DB_NAME, DB_USERNAME, DB_PASSWORD)):
        raise RuntimeError("MS SQL is not configured. Set DB_SERVER, DB_NAME, DB_USERNAME and DB_PASSWORD.")
    odbc = f"DRIVER={{{DB_DRIVER}}};SERVER={DB_SERVER},{DB_PORT};DATABASE={DB_NAME};UID={DB_USERNAME};PWD={DB_PASSWORD};Encrypt={DB_ENCRYPT};TrustServerCertificate={DB_TRUST_SERVER_CERTIFICATE}"
    return f"mssql+pyodbc:///?odbc_connect={quote_plus(odbc)}"


_engine = None
_Session = None


def session_factory():
    global _engine, _Session
    if _Session is None:
        _engine = create_engine(_connection_url(), pool_pre_ping=True)
        _Session = sessionmaker(bind=_engine, expire_on_commit=False)
    return _Session


def initialize_user_database() -> None:
    factory = session_factory()
    Base.metadata.create_all(bind=factory.kw["bind"])


def normalize_email(email: str) -> str:
    value = email.strip().lower()
    if not value.endswith("@mashreq.com") or value.count("@") != 1 or not value.split("@", 1)[0]:
        raise HTTPException(status_code=400, detail="User ID must be a valid @mashreq.com email address")
    return value


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def get_user(email: str) -> PortalUser | None:
    factory = session_factory()
    with factory() as db:
        return db.scalar(select(PortalUser).where(PortalUser.email == email.strip().lower()))


def list_users() -> list[PortalUser]:
    factory = session_factory()
    with factory() as db:
        return list(db.scalars(select(PortalUser).order_by(PortalUser.email)).all())


def create_user(email: str, password: str, role: str, is_admin: bool = False) -> PortalUser:
    email = normalize_email(email)
    if role not in ("developer", "devops"):
        raise HTTPException(status_code=400, detail="Role must be developer or devops")
    if is_admin and role != "devops":
        raise HTTPException(status_code=400, detail="Admin privilege can only be assigned to a DevOps user")
    factory = session_factory()
    with factory() as db:
        if db.scalar(select(PortalUser).where(PortalUser.email == email)):
            raise HTTPException(status_code=409, detail="User already exists")
        user = PortalUser(email=email, password_hash=hash_password(password), role=role, is_admin=is_admin, is_active=True)
        db.add(user); db.commit(); db.refresh(user); return user


def update_user(user_id: int, role: str, is_admin: bool, is_active: bool, password: str | None = None) -> PortalUser:
    if role not in ("developer", "devops") or (is_admin and role != "devops"):
        raise HTTPException(status_code=400, detail="Invalid role/admin privilege combination")
    factory = session_factory()
    with factory() as db:
        user = db.get(PortalUser, user_id)
        if not user: raise HTTPException(status_code=404, detail="User not found")
        user.role, user.is_admin, user.is_active = role, is_admin, is_active
        if password: user.password_hash = hash_password(password)
        user.updated_at = datetime.now(timezone.utc); db.commit(); db.refresh(user); return user


def change_user_password(email: str, new_password: str) -> None:
    factory = session_factory()
    with factory() as db:
        user = db.scalar(select(PortalUser).where(PortalUser.email == email.strip().lower()))
        if not user or not user.is_active:
            raise HTTPException(status_code=404, detail="Active user account not found")
        user.password_hash = hash_password(new_password)
        user.updated_at = datetime.now(timezone.utc)
        db.commit()


def delete_user(user_id: int) -> None:
    factory = session_factory()
    with factory() as db:
        user = db.get(PortalUser, user_id)
        if not user: raise HTTPException(status_code=404, detail="User not found")
        db.delete(user); db.commit()
