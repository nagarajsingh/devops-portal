from __future__ import annotations

import base64
import json
import os
import secrets
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

import jwt
from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from kubernetes import client, config
from kubernetes.client.rest import ApiException
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
AZDO_ORG = os.getenv("AZURE_DEVOPS_ORGANIZATION", "").strip()
AZDO_PROJECT = os.getenv("AZURE_DEVOPS_PROJECT", "").strip()
AZDO_PAT = os.getenv("AZURE_DEVOPS_PAT", "").strip()

app = FastAPI(title="DevOps Portal API", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


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


class ReviewUpdate(PipelineRequestCreate):
    review_comments: str | None = None


class RejectRequest(BaseModel):
    reason: str = Field(min_length=2, max_length=1000)


class PipelineRequest(PipelineRequestCreate):
    id: str
    requested_by: str
    status: str
    created_at: str
    updated_at: str | None = None
    reviewed_by: str | None = None
    review_comments: str | None = None
    original_request: dict[str, Any] | None = None
    provisioning: dict[str, Any] = {}
    timeline: list[dict[str, str]] = []


class UserContext(BaseModel):
    username: str
    role: Role


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def timeline_event(action: str, actor: str, detail: str = "") -> dict[str, str]:
    return {"at": now_iso(), "action": action, "actor": actor, "detail": detail}


def create_token(username: str, role: Role) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": username, "role": role, "iat": int(now.timestamp()), "exp": int((now + timedelta(hours=8)).timestamp())}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def current_user(authorization: str | None = Header(default=None)) -> UserContext:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        payload = jwt.decode(authorization.removeprefix("Bearer ").strip(), JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return UserContext(username=payload["sub"], role=payload["role"])
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc


def require_devops(user: UserContext = Depends(current_user)) -> UserContext:
    if user.role != "devops":
        raise HTTPException(status_code=403, detail="DevOps access required")
    return user


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


def find_request(items: list[dict], request_id: str) -> tuple[int, dict]:
    for index, item in enumerate(items):
        if item.get("id") == request_id:
            return index, item
    raise HTTPException(status_code=404, detail="Pipeline request not found")


def cluster_namespaces() -> list[str]:
    try:
        config.load_incluster_config()
        names = [item.metadata.name for item in client.CoreV1Api().list_namespace().items]
        return sorted(name for name in names if not NAMESPACE_ALLOWLIST or name in NAMESPACE_ALLOWLIST)
    except Exception:
        return sorted(NAMESPACE_ALLOWLIST)


def azdo_request(method: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
    if not AZDO_ORG or not AZDO_PROJECT or not AZDO_PAT:
        raise RuntimeError("Azure DevOps organization, project or PAT is not configured")
    url = f"https://dev.azure.com/{urllib.parse.quote(AZDO_ORG)}/{urllib.parse.quote(AZDO_PROJECT)}/{path}"
    token = base64.b64encode(f":{AZDO_PAT}".encode()).decode()
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method, headers={"Authorization": f"Basic {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode() or "{}")
            return response.status, body
    except urllib.error.HTTPError as exc:
        body = json.loads(exc.read().decode() or "{}")
        return exc.code, body


def repository_exists(name: str) -> bool:
    code, _ = azdo_request("GET", f"_apis/git/repositories/{urllib.parse.quote(name)}?api-version=7.1")
    return code == 200


def create_repository(name: str) -> dict:
    code, body = azdo_request("POST", "_apis/git/repositories?api-version=7.1", {"name": name, "project": {"name": AZDO_PROJECT}})
    if code not in (200, 201):
        raise RuntimeError(body.get("message", f"Repository creation failed with HTTP {code}"))
    return body


def ensure_service(item: dict) -> str:
    if not item.get("create_service"):
        return "Skipped"
    config.load_incluster_config()
    api = client.CoreV1Api()
    name = item["service_name"]
    namespace = item["namespace"]
    try:
        api.read_namespaced_service(name, namespace)
        return "Already Exists"
    except ApiException as exc:
        if exc.status != 404:
            raise
    service = client.V1Service(
        metadata=client.V1ObjectMeta(name=name, labels={"app": item["application_name"], "managed-by": "devops-portal"}),
        spec=client.V1ServiceSpec(
            selector={"app": item["application_name"]},
            ports=[client.V1ServicePort(name="http", port=item["service_port"], target_port=item["service_port"])],
            type="ClusterIP",
        ),
    )
    api.create_namespaced_service(namespace, service)
    return "Completed"


def provision(item: dict) -> tuple[str, dict]:
    steps: dict[str, Any] = {}
    try:
        if repository_exists(item["repository_name"]):
            steps["repository"] = {"status": "Warning", "message": "Repository already exists"}
            return "Pending Action", steps
        repo = create_repository(item["repository_name"])
        steps["repository"] = {"status": "Completed", "id": repo.get("id"), "url": repo.get("webUrl")}
    except Exception as exc:
        steps["repository"] = {"status": "Failed", "message": str(exc)}

    try:
        service_status = ensure_service(item)
        steps["service"] = {"status": service_status}
    except Exception as exc:
        steps["service"] = {"status": "Failed", "message": str(exc)}

    steps["pipeline"] = {"status": "Pending", "message": "Pipeline template/configuration is not configured"}
    steps["ingress"] = {"status": "Pending", "message": f"Ingress path {item['ingress_path']} requires ingress resource configuration"}

    statuses = [step["status"] for step in steps.values()]
    if statuses and all(value in ("Completed", "Skipped", "Already Exists") for value in statuses):
        return "Completed", steps
    if any(value == "Failed" for value in statuses):
        return "Partially Completed", steps
    return "Pending Action", steps


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "healthy"}


@app.post("/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest) -> LoginResponse:
    expected = {"devops": (DEVOPS_USER, DEVOPS_PASSWORD), "developer": (DEVELOPER_USER, DEVELOPER_PASSWORD)}[payload.role]
    valid = secrets.compare_digest(payload.username, expected[0]) and secrets.compare_digest(payload.password, expected[1])
    if not valid:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return LoginResponse(access_token=create_token(payload.username, payload.role), username=payload.username, role=payload.role)


@app.get("/namespaces", response_model=list[str])
def list_namespaces(_: UserContext = Depends(current_user)) -> list[str]:
    return cluster_namespaces()


@app.post("/requests", response_model=PipelineRequest, status_code=201)
def create_request(payload: PipelineRequestCreate, user: UserContext = Depends(current_user)) -> PipelineRequest:
    if payload.namespace not in cluster_namespaces():
        raise HTTPException(status_code=400, detail="Namespace is not allowed")
    created = now_iso()
    original = payload.model_dump()
    item = PipelineRequest(**original, id=f"PR-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}", requested_by=user.username, status="Pending Approval", created_at=created, updated_at=created, original_request=original, timeline=[timeline_event("Submitted", user.username)])
    items = read_requests()
    items.append(item.model_dump())
    write_requests(items)
    return item


@app.get("/requests", response_model=list[PipelineRequest])
def list_requests(user: UserContext = Depends(current_user)) -> list[PipelineRequest]:
    items = [PipelineRequest(**item) for item in read_requests()]
    visible = items if user.role == "devops" else [item for item in items if item.requested_by == user.username]
    return list(reversed(visible))


@app.get("/requests/{request_id}", response_model=PipelineRequest)
def get_request(request_id: str, user: UserContext = Depends(current_user)) -> PipelineRequest:
    _, item = find_request(read_requests(), request_id)
    if user.role != "devops" and item.get("requested_by") != user.username:
        raise HTTPException(status_code=403, detail="Not allowed to view this request")
    return PipelineRequest(**item)


@app.put("/requests/{request_id}", response_model=PipelineRequest)
def update_request(request_id: str, payload: ReviewUpdate, user: UserContext = Depends(require_devops)) -> PipelineRequest:
    items = read_requests()
    index, current = find_request(items, request_id)
    if current.get("status") not in ("Pending Approval", "Pending Action"):
        raise HTTPException(status_code=409, detail="Only pending requests can be modified")
    original = current.get("original_request") or {key: current.get(key) for key in PipelineRequestCreate.model_fields}
    updated = {**current, **payload.model_dump(exclude={"review_comments"}), "review_comments": payload.review_comments, "reviewed_by": user.username, "updated_at": now_iso(), "original_request": original}
    updated.setdefault("timeline", []).append(timeline_event("Modified by DevOps", user.username, payload.review_comments or "Request values updated"))
    items[index] = updated
    write_requests(items)
    return PipelineRequest(**updated)


@app.post("/requests/{request_id}/reject", response_model=PipelineRequest)
def reject_request(request_id: str, payload: RejectRequest, user: UserContext = Depends(require_devops)) -> PipelineRequest:
    items = read_requests()
    index, current = find_request(items, request_id)
    current.update({"status": "Rejected", "reviewed_by": user.username, "review_comments": payload.reason, "updated_at": now_iso()})
    current.setdefault("timeline", []).append(timeline_event("Rejected", user.username, payload.reason))
    items[index] = current
    write_requests(items)
    return PipelineRequest(**current)


@app.post("/requests/{request_id}/approve", response_model=PipelineRequest)
def approve_request(request_id: str, user: UserContext = Depends(require_devops)) -> PipelineRequest:
    items = read_requests()
    index, current = find_request(items, request_id)
    if current.get("status") not in ("Pending Approval", "Pending Action", "Partially Completed"):
        raise HTTPException(status_code=409, detail=f"Request cannot be approved from status {current.get('status')}")
    current["status"] = "Provisioning"
    current["reviewed_by"] = user.username
    current["updated_at"] = now_iso()
    current.setdefault("timeline", []).append(timeline_event("Approved", user.username))
    final_status, steps = provision(current)
    current["provisioning"] = steps
    current["status"] = final_status
    current["updated_at"] = now_iso()
    current["timeline"].append(timeline_event(final_status, "system", "Provisioning workflow finished"))
    items[index] = current
    write_requests(items)
    if steps.get("repository", {}).get("status") == "Warning":
        raise HTTPException(status_code=409, detail={"message": "Repository already exists", "request": current})
    return PipelineRequest(**current)
