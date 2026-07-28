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
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from pydantic import BaseModel, Field

Role = Literal["developer", "devops"]
ApplicationType = Literal["H2H", "Collections", "Native-Mobile", "Safenet"]

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
BOOTSTRAP_BRANCH = os.getenv("BOOTSTRAP_BRANCH", "feature/devops").strip() or "feature/devops"

app = FastAPI(title="DevOps Portal API", version="2.2.0")
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
    application_type: ApplicationType = "H2H"
    repository_name: str = Field(min_length=2, max_length=100, pattern=r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")
    reference_repository_name: str = ""
    pipeline_type: str | None = None
    ingress_path: str
    ingress_name: str | None = None
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


def normalize_stored_request(item: dict[str, Any]) -> dict[str, Any]:
    item.setdefault("application_type", "H2H")
    item.setdefault("reference_repository_name", "")
    item.setdefault("ingress_name", None)
    # Older records used application_name. Repository name is now the source of
    # truth for service selectors, ingress defaults and repository provisioning.
    item.pop("application_name", None)
    return item


def read_requests() -> list[dict]:
    if not DATA_FILE.exists():
        return []
    try:
        items = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        return [normalize_stored_request(item) for item in items]
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


def load_k8s() -> None:
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()


def cluster_namespaces() -> list[str]:
    try:
        load_k8s()
        names = [item.metadata.name for item in client.CoreV1Api().list_namespace().items]
        return sorted(name for name in names if not NAMESPACE_ALLOWLIST or name in NAMESPACE_ALLOWLIST)
    except Exception:
        return sorted(NAMESPACE_ALLOWLIST)


def namespace_ingresses(namespace: str) -> list[str]:
    if namespace not in cluster_namespaces():
        raise HTTPException(status_code=400, detail="Namespace is not allowed")
    try:
        load_k8s()
        items = client.NetworkingV1Api().list_namespaced_ingress(namespace).items
        return sorted(item.metadata.name for item in items if item.metadata and item.metadata.name)
    except ApiException as exc:
        raise HTTPException(status_code=exc.status or 500, detail=f"Unable to list ingresses in namespace {namespace}: {exc.reason}") from exc


def azdo_request(method: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
    if not AZDO_ORG or not AZDO_PROJECT or not AZDO_PAT:
        raise RuntimeError("Azure DevOps organization, project or PAT is not configured")
    url = f"https://dev.azure.com/{urllib.parse.quote(AZDO_ORG)}/{urllib.parse.quote(AZDO_PROJECT)}/{path}"
    token = base64.b64encode(f":{AZDO_PAT}".encode()).decode()
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method, headers={"Authorization": f"Basic {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            return response.status, json.loads(response.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            body = json.loads(raw or "{}")
        except json.JSONDecodeError:
            body = {"message": raw or f"Azure DevOps request failed with HTTP {exc.code}"}
        return exc.code, body


def get_repository(name: str) -> dict | None:
    code, body = azdo_request("GET", f"_apis/git/repositories/{urllib.parse.quote(name)}?api-version=7.1")
    if code == 200:
        return body
    if code == 404:
        return None
    raise RuntimeError(body.get("message", f"Repository lookup failed with HTTP {code}"))


def create_repository(name: str) -> dict:
    code, body = azdo_request("POST", "_apis/git/repositories?api-version=7.1", {"name": name})
    if code not in (200, 201):
        raise RuntimeError(body.get("message", f"Repository creation failed with HTTP {code}"))
    return body


def reference_files(reference_repository_name: str) -> list[dict[str, str]]:
    repository = get_repository(reference_repository_name)
    if not repository:
        raise RuntimeError(f"Reference repository {reference_repository_name} was not found")

    default_branch = (repository.get("defaultBranch") or "refs/heads/main").removeprefix("refs/heads/")
    repository_id = repository["id"]
    query = urllib.parse.urlencode({
        "scopePath": "/",
        "recursionLevel": "Full",
        "includeContent": "true",
        "versionDescriptor.version": default_branch,
        "versionDescriptor.versionType": "branch",
        "api-version": "7.1",
    })
    code, body = azdo_request("GET", f"_apis/git/repositories/{repository_id}/items?{query}")
    if code != 200:
        raise RuntimeError(body.get("message", f"Unable to read reference repository with HTTP {code}"))

    selected: list[dict[str, str]] = []
    exact_files = {"/Dockerfile", "/azure-pipelines.yaml"}
    folder_prefixes = ("/manifests/", "/shared-config/")
    for item in body.get("value", []):
        path = item.get("path", "")
        if item.get("isFolder"):
            continue
        if path not in exact_files and not path.startswith(folder_prefixes):
            continue
        content = item.get("content")
        if content is None:
            raise RuntimeError(f"Content was not returned for reference file {path}")
        selected.append({"path": path, "content": content})

    selected_paths = {item["path"] for item in selected}
    missing_files = sorted(exact_files - selected_paths)
    if missing_files:
        raise RuntimeError(f"Reference repository is missing required files: {', '.join(missing_files)}")
    if not any(path.startswith("/manifests/") for path in selected_paths):
        selected.append({"path": "/manifests/.gitkeep", "content": ""})
    if not any(path.startswith("/shared-config/") for path in selected_paths):
        selected.append({"path": "/shared-config/.gitkeep", "content": ""})
    return selected


def bootstrap_repository(target_repository: dict, reference_repository_name: str, application_type: str) -> dict[str, Any]:
    if application_type != "H2H":
        raise RuntimeError(f"Template bootstrap is currently configured only for H2H, not {application_type}")
    if not reference_repository_name.strip():
        raise RuntimeError("Reference repository name is required for H2H")

    files = reference_files(reference_repository_name.strip())
    changes = [
        {
            "changeType": "add",
            "item": {"path": item["path"]},
            "newContent": {"content": item["content"], "contentType": "rawtext"},
        }
        for item in files
    ]
    payload = {
        "refUpdates": [{"name": f"refs/heads/{BOOTSTRAP_BRANCH}", "oldObjectId": "0" * 40}],
        "commits": [{
            "comment": f"Bootstrap {application_type} DevOps repository structure",
            "changes": changes,
        }],
    }
    code, body = azdo_request("POST", f"_apis/git/repositories/{target_repository['id']}/pushes?api-version=7.1", payload)
    if code not in (200, 201):
        raise RuntimeError(body.get("message", f"Repository bootstrap failed with HTTP {code}"))
    return {
        "status": "Completed",
        "message": f"Created {BOOTSTRAP_BRANCH} from reference repository {reference_repository_name}",
        "branch": BOOTSTRAP_BRANCH,
        "files": [item["path"] for item in files],
        "url": target_repository.get("webUrl") or target_repository.get("remoteUrl"),
    }


def ensure_service(item: dict) -> str:
    if not item.get("create_service"):
        return "Skipped"
    load_k8s()
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
        metadata=client.V1ObjectMeta(name=name, labels={"app": item["repository_name"], "managed-by": "devops-portal"}),
        spec=client.V1ServiceSpec(
            selector={"app": item["repository_name"]},
            ports=[client.V1ServicePort(name="http", port=item["service_port"], target_port=item["service_port"])],
            type="ClusterIP",
        ),
    )
    api.create_namespaced_service(namespace, service)
    return "Completed"


def ensure_ingress_path(item: dict) -> dict[str, str]:
    ingress_name = (item.get("ingress_name") or "").strip()
    if not ingress_name:
        raise RuntimeError("No ingress resource was selected by DevOps")
    if not item.get("create_service"):
        raise RuntimeError("Ingress provisioning requires Kubernetes service creation")

    load_k8s()
    api = client.NetworkingV1Api()
    namespace = item["namespace"]
    ingress = api.read_namespaced_ingress(ingress_name, namespace)
    rules = ingress.spec.rules or []
    if not rules:
        raise RuntimeError(f"Ingress {ingress_name} does not contain any rules")

    path_value = item["ingress_path"]
    if not path_value.startswith("/"):
        path_value = f"/{path_value}"
    if not path_value.endswith("(/|$)(.*)"):
        path_value = f"{path_value}(/|$)(.*)"

    target_rule = next((rule for rule in rules if rule.http is not None), None)
    if target_rule is None:
        raise RuntimeError(f"Ingress {ingress_name} does not contain an HTTP rule")

    paths = target_rule.http.paths or []
    existing = next((path for path in paths if path.path == path_value), None)
    backend = client.V1IngressBackend(service=client.V1IngressServiceBackend(name=item["service_name"], port=client.V1ServiceBackendPort(number=item["service_port"])))
    if existing:
        existing.backend = backend
        action = "Updated existing path"
    else:
        paths.append(client.V1HTTPIngressPath(path=path_value, path_type="ImplementationSpecific", backend=backend))
        action = "Added path"

    target_rule.http.paths = paths
    ingress.spec.rules = rules
    api.replace_namespaced_ingress(ingress_name, namespace, ingress)
    return {"status": "Completed", "message": f"{action} {path_value} in ingress {ingress_name}"}


def provision(item: dict) -> tuple[str, dict]:
    steps: dict[str, Any] = {}
    target_repo: dict | None = None
    try:
        existing_repo = get_repository(item["repository_name"])
        if existing_repo:
            steps["repository"] = {"status": "Warning", "message": "Repository already exists", "id": existing_repo.get("id"), "url": existing_repo.get("webUrl") or existing_repo.get("remoteUrl")}
            return "Pending Action", steps
        target_repo = create_repository(item["repository_name"])
        steps["repository"] = {"status": "Completed", "id": target_repo.get("id"), "url": target_repo.get("webUrl") or target_repo.get("remoteUrl")}
    except Exception as exc:
        steps["repository"] = {"status": "Failed", "message": str(exc)}

    if target_repo:
        try:
            steps["repository_bootstrap"] = bootstrap_repository(target_repo, item.get("reference_repository_name", ""), item.get("application_type", "H2H"))
            steps["pipeline"] = {"status": "Completed", "message": f"azure-pipelines.yaml committed to {BOOTSTRAP_BRANCH}"}
        except Exception as exc:
            steps["repository_bootstrap"] = {"status": "Failed", "message": str(exc)}
            steps["pipeline"] = {"status": "Failed", "message": "Pipeline file could not be bootstrapped"}
    else:
        steps["repository_bootstrap"] = {"status": "Pending", "message": "Waiting for repository creation"}
        steps["pipeline"] = {"status": "Pending", "message": "Waiting for repository bootstrap"}

    try:
        steps["service"] = {"status": ensure_service(item)}
    except Exception as exc:
        steps["service"] = {"status": "Failed", "message": str(exc)}

    try:
        steps["ingress"] = ensure_ingress_path(item)
    except Exception as exc:
        steps["ingress"] = {"status": "Failed", "message": str(exc)}

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


@app.get("/ingresses/{namespace}", response_model=list[str])
def list_ingresses(namespace: str, _: UserContext = Depends(require_devops)) -> list[str]:
    return namespace_ingresses(namespace)


@app.post("/requests", response_model=PipelineRequest, status_code=201)
def create_request(payload: PipelineRequestCreate, user: UserContext = Depends(current_user)) -> PipelineRequest:
    if payload.namespace not in cluster_namespaces():
        raise HTTPException(status_code=400, detail="Namespace is not allowed")
    if payload.application_type == "H2H" and not payload.reference_repository_name.strip():
        raise HTTPException(status_code=400, detail="Reference repository name is required for H2H")
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
    if current.get("status") not in ("Pending Approval", "Pending Action", "Partially Completed"):
        raise HTTPException(status_code=409, detail="Only pending requests can be modified")
    if payload.namespace not in cluster_namespaces():
        raise HTTPException(status_code=400, detail="Namespace is not allowed")
    if payload.ingress_name and payload.ingress_name not in namespace_ingresses(payload.namespace):
        raise HTTPException(status_code=400, detail=f"Ingress {payload.ingress_name} does not exist in namespace {payload.namespace}")
    if payload.application_type == "H2H" and not payload.reference_repository_name.strip():
        raise HTTPException(status_code=400, detail="Reference repository name is required for H2H")
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
    if not current.get("ingress_name"):
        raise HTTPException(status_code=400, detail="Select an ingress resource before approval")
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
