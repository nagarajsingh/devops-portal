from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, Header, HTTPException

from .config import (
    DEVELOPER_PASSWORD,
    DEVELOPER_USER,
    DEVOPS_PASSWORD,
    DEVOPS_USER,
    JWT_ALGORITHM,
    JWT_SECRET,
)
from .models import LoginRequest, LoginResponse, Role, UserContext


def create_token(username: str, role: Role) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": username,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=8)).timestamp()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def authenticate(payload: LoginRequest) -> LoginResponse:
    expected = {
        "devops": (DEVOPS_USER, DEVOPS_PASSWORD),
        "developer": (DEVELOPER_USER, DEVELOPER_PASSWORD),
    }[payload.role]
    valid = secrets.compare_digest(payload.username, expected[0]) and secrets.compare_digest(payload.password, expected[1])
    if not valid:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return LoginResponse(
        access_token=create_token(payload.username, payload.role),
        username=payload.username,
        role=payload.role,
    )


def current_user(authorization: str | None = Header(default=None)) -> UserContext:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        payload = jwt.decode(
            authorization.removeprefix("Bearer ").strip(),
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
        )
        return UserContext(username=payload["sub"], role=payload["role"])
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc


def require_devops(user: UserContext = Depends(current_user)) -> UserContext:
    if user.role != "devops":
        raise HTTPException(status_code=403, detail="DevOps access required")
    return user
