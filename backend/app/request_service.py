from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException

from .kubernetes_ops import cluster_namespaces, namespace_ingresses
from .logging_config import get_logger
from .models import PipelineRequest, PipelineRequestCreate, ReviewUpdate, UserContext
from .provisioning import provision
from .storage import find_request, now_iso, read_requests, timeline_event, write_requests

logger = get_logger("requests")


def create_pipeline_request(payload: PipelineRequestCreate, user: UserContext) -> PipelineRequest:
    if payload.namespace not in cluster_namespaces():
        raise HTTPException(status_code=400, detail="Namespace is not allowed")
    if payload.setup_pipeline and not payload.reference_repository_name.strip():
        raise HTTPException(status_code=400, detail="Reference repository is required when pipeline setup is enabled")
    created = now_iso()
    original = payload.model_dump()
    request_id = f"PR-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:6].upper()}"
    item = PipelineRequest(**original, id=request_id, requested_by=user.username, status="Pending Approval", created_at=created, updated_at=created, original_request=original, timeline=[timeline_event("Submitted", user.username)])
    items = read_requests()
    items.append(item.model_dump())
    write_requests(items)
    logger.info("Pipeline request submitted request_id=%s username=%s repository=%s", item.id, user.username, item.repository_name)
    return item


def list_pipeline_requests(user: UserContext) -> list[PipelineRequest]:
    items = [PipelineRequest(**item) for item in read_requests()]
    visible = items if user.role == "devops" else [item for item in items if item.requested_by == user.username]
    return list(reversed(visible))


def get_pipeline_request(request_id: str, user: UserContext) -> PipelineRequest:
    _, item = find_request(read_requests(), request_id)
    if user.role != "devops" and item.get("requested_by") != user.username:
        raise HTTPException(status_code=403, detail="Not allowed to view this request")
    return PipelineRequest(**item)


def update_pipeline_request(request_id: str, payload: ReviewUpdate, user: UserContext) -> PipelineRequest:
    items = read_requests()
    index, current = find_request(items, request_id)
    if current.get("status") not in ("Pending Approval", "Pending Action", "Partially Completed"):
        raise HTTPException(status_code=409, detail="Only pending requests can be modified")
    if payload.namespace not in cluster_namespaces():
        raise HTTPException(status_code=400, detail="Namespace is not allowed")
    if payload.ingress_name and payload.ingress_name not in namespace_ingresses(payload.namespace):
        raise HTTPException(status_code=400, detail=f"Ingress {payload.ingress_name} does not exist in namespace {payload.namespace}")
    if payload.setup_pipeline and not payload.reference_repository_name.strip():
        raise HTTPException(status_code=400, detail="Reference repository is required when pipeline setup is enabled")
    if payload.reference_repository_name.strip() and not payload.reference_branch.strip():
        raise HTTPException(status_code=400, detail="Reference repository branch must be provided when a reference repository is selected")
    original = current.get("original_request") or {key: current.get(key) for key in PipelineRequestCreate.model_fields}
    updated = {**current, **payload.model_dump(exclude={"review_comments"}), "review_comments": payload.review_comments, "reviewed_by": user.username, "updated_at": now_iso(), "original_request": original}
    updated.setdefault("timeline", []).append(timeline_event("Modified by DevOps", user.username, payload.review_comments or "Request values updated"))
    items[index] = updated
    write_requests(items)
    return PipelineRequest(**updated)


def reject_pipeline_request(request_id: str, reason: str, user: UserContext) -> PipelineRequest:
    items = read_requests()
    index, current = find_request(items, request_id)
    current.update({"status": "Rejected", "reviewed_by": user.username, "review_comments": reason, "updated_at": now_iso()})
    current.setdefault("timeline", []).append(timeline_event("Rejected", user.username, reason))
    items[index] = current
    write_requests(items)
    return PipelineRequest(**current)


def close_pipeline_request(request_id: str, comment: str, user: UserContext) -> PipelineRequest:
    items = read_requests()
    index, current = find_request(items, request_id)
    if current.get("status") in ("Completed", "Rejected", "Closed"):
        raise HTTPException(status_code=409, detail=f"Request cannot be closed from status {current.get('status')}")
    current.update({"status": "Closed", "reviewed_by": user.username, "closure_comment": comment, "updated_at": now_iso()})
    current.setdefault("timeline", []).append(timeline_event("Closed by DevOps", user.username, comment))
    items[index] = current
    write_requests(items)
    logger.info("Pipeline request closed request_id=%s username=%s", request_id, user.username)
    return PipelineRequest(**current)


def approve_pipeline_request(request_id: str, user: UserContext, azure_devops_pat: str) -> PipelineRequest:
    items = read_requests()
    index, current = find_request(items, request_id)
    if current.get("status") not in ("Pending Approval", "Pending Action", "Partially Completed"):
        raise HTTPException(status_code=409, detail=f"Request cannot be approved from status {current.get('status')}")
    if current.get("reference_repository_name", "").strip() and not current.get("reference_branch", "").strip():
        raise HTTPException(status_code=400, detail="Provide the reference repository branch before approval")
    if current.get("setup_pipeline") and not current.get("reference_repository_name", "").strip():
        raise HTTPException(status_code=400, detail="Pipeline setup requires a reference repository")
    if not current.get("ingress_name"):
        raise HTTPException(status_code=400, detail="Select an ingress resource before approval")
    if not azure_devops_pat.strip():
        raise HTTPException(status_code=400, detail="Azure DevOps PAT is required for provisioning")
    current.update({"status": "Provisioning", "reviewed_by": user.username, "updated_at": now_iso()})
    detail = f"Reference branch: {current.get('reference_branch')}" if current.get("reference_repository_name") else "No reference repository selected"
    current.setdefault("timeline", []).append(timeline_event("Approved", user.username, detail))
    final_status, steps = provision(current, azure_devops_pat)
    current.update({"provisioning": steps, "status": final_status, "updated_at": now_iso()})
    current["timeline"].append(timeline_event(final_status, "system", "Provisioning workflow finished"))
    items[index] = current
    write_requests(items)
    if steps.get("repository", {}).get("status") == "Warning":
        raise HTTPException(status_code=409, detail={"message": "Repository already exists", "request": current})
    return PipelineRequest(**current)
