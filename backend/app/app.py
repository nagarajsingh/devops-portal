from __future__ import annotations

import html
import time

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from .auth import authenticate, current_user, require_devops
from .cluster_inventory import inventory_ingresses, inventory_namespaces, inventory_services
from .config import APP_OWNER_EMAILS, KUBERNETES_TARGETS, LOCAL_KUBERNETES_TARGET
from .deployment_routes import router as deployment_management_router
from .kubernetes_ops import cluster_namespaces, namespace_ingresses, namespace_services
from .logging_config import get_logger
from .models import ApproveRequest, CloseRequest, KubernetesTargetOption, LoginRequest, LoginResponse, PipelineRequest, PipelineRequestCreate, RejectRequest, ReviewUpdate, ServiceOption, UserContext
from .monitoring import build_monitoring_summary
from .request_service import approve_pipeline_request, close_pipeline_request, confirm_existing_repository_bootstrap, create_pipeline_request, get_pipeline_request, list_pipeline_requests, process_app_owner_action, reject_pipeline_request, update_pipeline_request

logger = get_logger("api")
app = FastAPI(title="DevOps Portal API", version="3.9.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(deployment_management_router)


@app.on_event("startup")
def startup_event() -> None:
    logger.info("DevOps Portal backend started version=%s", app.version)


@app.middleware("http")
async def log_http_requests(request: Request, call_next):
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("HTTP request failed method=%s path=%s duration_ms=%s", request.method, request.url.path, round((time.perf_counter() - started) * 1000, 2))
        raise
    logger.info("HTTP request method=%s path=%s status=%s duration_ms=%s", request.method, request.url.path, response.status_code, round((time.perf_counter() - started) * 1000, 2))
    return response


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "healthy"}


@app.get("/app-owner/action", response_class=HTMLResponse)
def app_owner_action(token: str) -> HTMLResponse:
    status, detail = process_app_owner_action(token)
    success = status in ("Pending Approval", "Completed", "Closed")
    accent = "#23824d" if success else "#c73e37"
    page = f"""
    <html><body style='font-family:Arial,sans-serif;background:#f5f7fb;padding:40px;color:#24334a'>
      <div style='max-width:650px;margin:auto;background:white;border:1px solid #e5eaf0;border-radius:18px;padding:32px;text-align:center'>
        <div style='color:#ef641f;font-weight:800;letter-spacing:1px;font-size:12px'>DEVOPS PORTAL</div>
        <h2 style='color:#183b68'>Application owner response recorded</h2>
        <div style='display:inline-block;padding:9px 14px;border-radius:999px;background:{accent}18;color:{accent};font-weight:800'>{html.escape(status)}</div>
        <p style='line-height:1.7;color:#52657b'>{html.escape(detail)}</p>
        <p style='font-size:13px;color:#788392'>You may close this browser window.</p>
      </div>
    </body></html>
    """
    return HTMLResponse(page)


@app.post("/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest) -> LoginResponse:
    return authenticate(payload)


@app.get("/configuration/app-owners", response_model=dict[str, str])
def application_owners(_: UserContext = Depends(current_user)) -> dict[str, str]:
    return dict(APP_OWNER_EMAILS)


@app.get("/configuration/kubernetes-targets", response_model=list[KubernetesTargetOption])
def kubernetes_targets(_: UserContext = Depends(require_devops)) -> list[KubernetesTargetOption]:
    return [KubernetesTargetOption(name=name, mode="direct" if name == LOCAL_KUBERNETES_TARGET else "azure_pipeline") for name in KUBERNETES_TARGETS]


@app.get("/monitoring/summary")
def monitoring_summary(days: int = Query(1, ge=1, le=90), _: UserContext = Depends(require_devops)) -> dict:
    return build_monitoring_summary(days=days)


def _validate_target(target_cluster: str) -> None:
    if target_cluster not in KUBERNETES_TARGETS:
        raise HTTPException(status_code=404, detail=f"Unknown Kubernetes target: {target_cluster}")


@app.get("/namespaces", response_model=list[str])
def list_namespaces(_: UserContext = Depends(current_user)) -> list[str]:
    return cluster_namespaces()


@app.get("/namespaces/{target_cluster}", response_model=list[str])
def list_target_namespaces(target_cluster: str, _: UserContext = Depends(require_devops)) -> list[str]:
    _validate_target(target_cluster)
    if target_cluster == LOCAL_KUBERNETES_TARGET:
        return cluster_namespaces()
    try:
        return inventory_namespaces(target_cluster)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/ingresses/{namespace}", response_model=list[str])
def list_ingresses(namespace: str, _: UserContext = Depends(require_devops)) -> list[str]:
    return namespace_ingresses(namespace)


@app.get("/ingresses/{target_cluster}/{namespace}", response_model=list[str])
def list_target_ingresses(target_cluster: str, namespace: str, _: UserContext = Depends(require_devops)) -> list[str]:
    _validate_target(target_cluster)
    if target_cluster == LOCAL_KUBERNETES_TARGET:
        return namespace_ingresses(namespace)
    try:
        return inventory_ingresses(target_cluster, namespace)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/services/{namespace}", response_model=list[ServiceOption])
def list_services(namespace: str, _: UserContext = Depends(require_devops)) -> list[ServiceOption]:
    return namespace_services(namespace)


@app.get("/services/{target_cluster}/{namespace}", response_model=list[ServiceOption])
def list_target_services(target_cluster: str, namespace: str, _: UserContext = Depends(require_devops)) -> list[ServiceOption]:
    _validate_target(target_cluster)
    if target_cluster == LOCAL_KUBERNETES_TARGET:
        return namespace_services(namespace)
    try:
        return inventory_services(target_cluster, namespace)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/requests", response_model=PipelineRequest, status_code=201)
def create_request(payload: PipelineRequestCreate, user: UserContext = Depends(current_user)) -> PipelineRequest:
    return create_pipeline_request(payload, user)


@app.get("/requests", response_model=list[PipelineRequest])
def list_requests(user: UserContext = Depends(current_user)) -> list[PipelineRequest]:
    return list_pipeline_requests(user)


@app.get("/requests/{request_id}", response_model=PipelineRequest)
def get_request(request_id: str, user: UserContext = Depends(current_user)) -> PipelineRequest:
    return get_pipeline_request(request_id, user)


@app.put("/requests/{request_id}", response_model=PipelineRequest)
def update_request(request_id: str, payload: ReviewUpdate, user: UserContext = Depends(require_devops)) -> PipelineRequest:
    return update_pipeline_request(request_id, payload, user)


@app.post("/requests/{request_id}/reject", response_model=PipelineRequest)
def reject_request(request_id: str, payload: RejectRequest, user: UserContext = Depends(require_devops)) -> PipelineRequest:
    return reject_pipeline_request(request_id, payload.reason, user)


@app.post("/requests/{request_id}/close", response_model=PipelineRequest)
def close_request(request_id: str, payload: CloseRequest, user: UserContext = Depends(require_devops)) -> PipelineRequest:
    return close_pipeline_request(request_id, payload.comment, user)


@app.post("/requests/{request_id}/approve", response_model=PipelineRequest)
def approve_request(request_id: str, payload: ApproveRequest, user: UserContext = Depends(require_devops)) -> PipelineRequest:
    return approve_pipeline_request(request_id, user, payload.azure_devops_pat.get_secret_value())


@app.post("/requests/{request_id}/confirm-existing-repository", response_model=PipelineRequest)
def confirm_existing_repository(request_id: str, payload: ApproveRequest, user: UserContext = Depends(require_devops)) -> PipelineRequest:
    return confirm_existing_repository_bootstrap(request_id, user, payload.azure_devops_pat.get_secret_value())
