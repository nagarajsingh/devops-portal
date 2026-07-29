from __future__ import annotations

import time

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from .auth import authenticate, current_user, require_devops
from .kubernetes_ops import cluster_namespaces, namespace_ingresses, namespace_services
from .logging_config import get_logger
from .models import ApproveRequest, LoginRequest, LoginResponse, PipelineRequest, PipelineRequestCreate, RejectRequest, ReviewUpdate, ServiceOption, UserContext
from .request_service import approve_pipeline_request, create_pipeline_request, get_pipeline_request, list_pipeline_requests, reject_pipeline_request, update_pipeline_request

logger = get_logger("api")
app = FastAPI(title="DevOps Portal API", version="3.2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


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


@app.post("/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest) -> LoginResponse:
    return authenticate(payload)


@app.get("/namespaces", response_model=list[str])
def list_namespaces(_: UserContext = Depends(current_user)) -> list[str]:
    return cluster_namespaces()


@app.get("/ingresses/{namespace}", response_model=list[str])
def list_ingresses(namespace: str, _: UserContext = Depends(require_devops)) -> list[str]:
    return namespace_ingresses(namespace)


@app.get("/services/{namespace}", response_model=list[ServiceOption])
def list_services(namespace: str, _: UserContext = Depends(require_devops)) -> list[ServiceOption]:
    return namespace_services(namespace)


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


@app.post("/requests/{request_id}/approve", response_model=PipelineRequest)
def approve_request(request_id: str, payload: ApproveRequest, user: UserContext = Depends(require_devops)) -> PipelineRequest:
    return approve_pipeline_request(request_id, user, payload.azure_devops_pat.get_secret_value())
