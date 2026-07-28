from __future__ import annotations

import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

import jwt
from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from kubernetes import client, config
from pydantic import BaseModel, Field

Role = Literal["developer", "devops"]

JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-secret")
JWT_ALGORITHM = "HS256"
DATA_FILE = Path(os.getenv("REQUEST_DATA_FILE", "/data/requests.json"))
NAMESPACE_ALLOWLIST = [item.strip() for item in os.getenv("ALLOWED_NAMESPACES", "automation").split(",") if item.strip()]
DEVOPS_USER = os.getenv("DEVOPS_USERNAME", "devops")
DEVOPS_PASSWORD = os.getenv("DEVOPS_PASSWORD", "devops123")
DEVELOPER_USER = os.getenv("DEVELOPER_USERNAME", "developer")
DEVELOPER_PASSWORD = os.getenv("DEVELOPER_PASSWORD", "developer123")

app = FastAPI(title="DevOps Portal API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class LoginRequest(BaseModel):
    username: str
    password: str
    role: Role


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: Role


class PipelineRequestCreate(BaseModel):
    application_name: str = Field(min_length=2, max_length=63, pattern=r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")
    repository_name: str = Field(min_length=2, max_length=100)
    pipeline_type: str | None = None
    ingress_path: str
    create_service: bool = True
    service_name: str
    service_port: int = Field(default=8080, ge=1, le=65535)
    namespace: str
    comments: str | None = None


class PipelineRequest(PipelineRequestCreate):
    id: str
    requested_by: str
    status: str
    created_at: str


class UserContext(BaseModel):
    username: str
    role: Role


def create_token(username: str, role: Role) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": username,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=8)).timestamp()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def current_user(authorization: str | None = Header(default=None)) -> UserContext:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return UserContext(username=payload["sub"], role=payload["role"])
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token") from exc


def read_requests() -> list[dict]:
    if not DATA_FILE.exists():
        return []
    try:
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def write_requests(items: list[dict]) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(items, indent=2), encoding="utf-8")


def cluster_namespaces() -> list[str]:
    try:
        config.load_incluster_config()
        names = [item.metadata.name for item in client.CoreV1Api().list_namespace().items]
        if NAMESPACE_ALLOWLIST:
            return sorted(name for name in names if name in NAMESPACE_ALLOWLIST)
        return sorted(names)
    except Exception:
        return sorted(NAMESPACE_ALLOWLIST)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "healthy"}


@app.post("/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest) -> LoginResponse:
    expected = {
        "devops": (DEVOPS_USER, DEVOPS_PASSWORD),
        "developer": (DEVELOPER_USER, DEVELOPER_PASSWORD),
    }[payload.role]
    valid = secrets.compare_digest(payload.username, expected[0]) and secrets.compare_digest(payload.password, expected[1])
    if not valid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return LoginResponse(access_token=create_token(payload.username, payload.role), username=payload.username, role=payload.role)


@app.get("/namespaces", response_model=list[str])
def list_namespaces(_: UserContext = Depends(current_user)) -> list[str]:
    return cluster_namespaces()


@app.post("/requests", response_model=PipelineRequest, status_code=status.HTTP_201_CREATED)
def create_request(payload: PipelineRequestCreate, user: UserContext = Depends(current_user)) -> PipelineRequest:
    if payload.namespace not in cluster_namespaces():
        raise HTTPException(status_code=400, detail="Namespace is not allowed")
    item = PipelineRequest(
        **payload.model_dump(),
        id=f"PR-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        requested_by=user.username,
        status="Pending Approval",
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    items = read_requests()
    items.append(item.model_dump())
    write_requests(items)
    return item


@app.get("/requests", response_model=list[PipelineRequest])
def list_requests(user: UserContext = Depends(current_user)) -> list[PipelineRequest]:
    items = [PipelineRequest(**item) for item in read_requests()]
    if user.role == "devops":
        return list(reversed(items))
    return list(reversed([item for item in items if item.requested_by == user.username]))
