from __future__ import annotations
import html
import time
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from .admin_routes import router as admin_router
from .auth import authenticate, current_user, require_devops
from .cluster_inventory import inventory_ingresses, inventory_namespaces, inventory_services
from .config import APP_OWNER_EMAILS, KUBERNETES_TARGETS, LOCAL_KUBERNETES_TARGET
from .deployment_routes import router as deployment_management_router
from .devops_tasks import router as devops_tasks_router
from .file_placement import router as file_placement_router
from .kubernetes_ops import cluster_namespaces, namespace_ingresses, namespace_services
from .logging_config import get_logger
from .models import ApproveRequest, CloseRequest, KubernetesTargetOption, LoginRequest, LoginResponse, PipelineRequest, PipelineRequestCreate, RejectRequest, ReviewUpdate, ServiceOption, UserContext
from .monitoring import build_monitoring_summary
from .request_service import approve_pipeline_request, close_pipeline_request, confirm_existing_repository_bootstrap, create_pipeline_request, get_pipeline_request, list_pipeline_requests, process_app_owner_action, reject_pipeline_request, update_pipeline_request
from .user_store import initialize_user_database
logger=get_logger("api")
app=FastAPI(title="DevOps Portal API",version="4.2.0")
app.add_middleware(CORSMiddleware,allow_origins=["*"],allow_credentials=True,allow_methods=["*"],allow_headers=["*"])
app.include_router(deployment_management_router); app.include_router(admin_router); app.include_router(devops_tasks_router); app.include_router(file_placement_router)
@app.on_event("startup")
def startup_event():
    initialize_user_database(); logger.info("DevOps Portal backend started version=%s",app.version)
@app.middleware("http")
async def log_http_requests(request:Request,call_next):
    started=time.perf_counter()
    try: response=await call_next(request)
    except Exception:
        logger.exception("HTTP request failed method=%s path=%s duration_ms=%s",request.method,request.url.path,round((time.perf_counter()-started)*1000,2)); raise
    logger.info("HTTP request method=%s path=%s status=%s duration_ms=%s",request.method,request.url.path,response.status_code,round((time.perf_counter()-started)*1000,2)); return response
@app.get("/health")
def health(): return {"status":"healthy"}
@app.get("/app-owner/action",response_class=HTMLResponse)
def app_owner_action(token:str):
    status,detail=process_app_owner_action(token); success=status in ("Pending Approval","Completed","Closed"); accent="#23824d" if success else "#c73e37"
    return HTMLResponse(f"<html><body style='font-family:Arial;background:#f5f7fb;padding:40px'><div style='max-width:650px;margin:auto;background:white;padding:32px;text-align:center'><h2>Application owner response recorded</h2><b style='color:{accent}'>{html.escape(status)}</b><p>{html.escape(detail)}</p></div></body></html>")
@app.post("/auth/login",response_model=LoginResponse)
def login(payload:LoginRequest): return authenticate(payload)
@app.get("/configuration/app-owners",response_model=dict[str,str])
def application_owners(_:UserContext=Depends(current_user)): return dict(APP_OWNER_EMAILS)
@app.get("/configuration/kubernetes-targets",response_model=list[KubernetesTargetOption])
def kubernetes_targets(_:UserContext=Depends(require_devops)): return [KubernetesTargetOption(name=n,mode="direct" if n==LOCAL_KUBERNETES_TARGET else "azure_pipeline") for n in KUBERNETES_TARGETS]
@app.get("/monitoring/summary")
def monitoring_summary(days:int=Query(1,ge=1,le=90),_:UserContext=Depends(require_devops)): return build_monitoring_summary(days=days)
def _validate_target(target_cluster:str):
    if target_cluster not in KUBERNETES_TARGETS: raise HTTPException(status_code=404,detail=f"Unknown Kubernetes target: {target_cluster}")
@app.get("/namespaces",response_model=list[str])
def list_namespaces(_:UserContext=Depends(current_user)): return cluster_namespaces()
@app.get("/namespaces/{target_cluster}",response_model=list[str])
def list_target_namespaces(target_cluster:str,_:UserContext=Depends(require_devops)):
    _validate_target(target_cluster); return cluster_namespaces() if target_cluster==LOCAL_KUBERNETES_TARGET else inventory_namespaces(target_cluster)
@app.get("/ingresses/{namespace}",response_model=list[str])
def list_ingresses(namespace:str,_:UserContext=Depends(require_devops)): return namespace_ingresses(namespace)
@app.get("/ingresses/{target_cluster}/{namespace}",response_model=list[str])
def list_target_ingresses(target_cluster:str,namespace:str,_:UserContext=Depends(require_devops)):
    _validate_target(target_cluster); return namespace_ingresses(namespace) if target_cluster==LOCAL_KUBERNETES_TARGET else inventory_ingresses(target_cluster,namespace)
@app.get("/services/{namespace}",response_model=list[ServiceOption])
def list_services(namespace:str,_:UserContext=Depends(require_devops)): return namespace_services(namespace)
@app.get("/services/{target_cluster}/{namespace}",response_model=list[ServiceOption])
def list_target_services(target_cluster:str,namespace:str,_:UserContext=Depends(require_devops)):
    _validate_target(target_cluster); return namespace_services(namespace) if target_cluster==LOCAL_KUBERNETES_TARGET else inventory_services(target_cluster,namespace)
@app.post("/requests",response_model=PipelineRequest,status_code=201)
def create_request(payload:PipelineRequestCreate,user:UserContext=Depends(current_user)): return create_pipeline_request(payload,user)
@app.get("/requests",response_model=list[PipelineRequest])
def list_requests(user:UserContext=Depends(current_user)): return list_pipeline_requests(user)
@app.get("/requests/{request_id}",response_model=PipelineRequest)
def get_request(request_id:str,user:UserContext=Depends(current_user)): return get_pipeline_request(request_id,user)
@app.put("/requests/{request_id}",response_model=PipelineRequest)
def update_request(request_id:str,payload:ReviewUpdate,user:UserContext=Depends(require_devops)): return update_pipeline_request(request_id,payload,user)
@app.post("/requests/{request_id}/reject",response_model=PipelineRequest)
def reject_request(request_id:str,payload:RejectRequest,user:UserContext=Depends(require_devops)): return reject_pipeline_request(request_id,payload.reason,user)
@app.post("/requests/{request_id}/close",response_model=PipelineRequest)
def close_request(request_id:str,payload:CloseRequest,user:UserContext=Depends(require_devops)): return close_pipeline_request(request_id,payload.comment,user)
@app.post("/requests/{request_id}/approve",response_model=PipelineRequest)
def approve_request(request_id:str,payload:ApproveRequest,user:UserContext=Depends(require_devops)): return approve_pipeline_request(request_id,user,payload.azure_devops_pat.get_secret_value())
@app.post("/requests/{request_id}/confirm-existing-repository",response_model=PipelineRequest)
def confirm_existing_repository(request_id:str,payload:ApproveRequest,user:UserContext=Depends(require_devops)): return confirm_existing_repository_bootstrap(request_id,user,payload.azure_devops_pat.get_secret_value())
