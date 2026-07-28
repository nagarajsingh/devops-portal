from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException

from .kubernetes_ops import cluster_namespaces, namespace_ingresses
from .logging_config import get_logger
from .models import PipelineRequest, PipelineRequestCreate, ReviewUpdate, UserContext
from .provisioning import provision
from .storage import find_request, now_iso, read_requests, timeline_event, write_requests

logger = get_logger("requests")


def create_pipeline_request(payload: PipelineRequestCreate, user: UserContext) -> PipelineRequest:
    if payload.namespace not in cluster_namespaces():
        logger.warning("Request submission rejected username=%s namespace=%s reason=namespace-not-allowed", user.username, payload.namespace)
        raise HTTPException(status_code=400, detail="Namespace is not allowed")
    if payload.application_type == "H2H" and not payload.reference_repository_name.strip():
        logger.warning("Request submission rejected username=%s repository=%s reason=missing-reference-repository", user.username, payload.repository_name)
        raise HTTPException(status_code=400, detail="Reference repository name is required for H2H")
    created = now_iso()
    original = payload.model_dump()
    item = PipelineRequest(
        **original,
        id=f"PR-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        requested_by=user.username,
        status="Pending Approval",
        created_at=created,
        updated_at=created,
        original_request=original,
        timeline=[timeline_event("Submitted", user.username)],
    )
    items = read_requests()
    items.append(item.model_dump())
    write_requests(items)
    logger.info(
        "Pipeline request submitted request_id=%s username=%s repository=%s namespace=%s",
        item.id,
        user.username,
        item.repository_name,
        item.namespace,
    )
    return item


def list_pipeline_requests(user: UserContext) -> list[PipelineRequest]:
    items = [PipelineRequest(**item) for item in read_requests()]
    visible = items if user.role == "devops" else [item for item in items if item.requested_by == user.username]
    logger.debug("Pipeline requests listed username=%s role=%s count=%s", user.username, user.role, len(visible))
    return list(reversed(visible))


def get_pipeline_request(request_id: str, user: UserContext) -> PipelineRequest:
    _, item = find_request(read_requests(), request_id)
    if user.role != "devops" and item.get("requested_by") != user.username:
        logger.warning("Request access denied request_id=%s username=%s role=%s", request_id, user.username, user.role)
        raise HTTPException(status_code=403, detail="Not allowed to view this request")
    logger.debug("Pipeline request viewed request_id=%s username=%s role=%s", request_id, user.username, user.role)
    return PipelineRequest(**item)


def update_pipeline_request(request_id: str, payload: ReviewUpdate, user: UserContext) -> PipelineRequest:
    items = read_requests()
    index, current = find_request(items, request_id)
    if current.get("status") not in ("Pending Approval", "Pending Action", "Partially Completed"):
        logger.warning("Request update rejected request_id=%s username=%s status=%s", request_id, user.username, current.get("status"))
        raise HTTPException(status_code=409, detail="Only pending requests can be modified")
    if payload.namespace not in cluster_namespaces():
        raise HTTPException(status_code=400, detail="Namespace is not allowed")
    if payload.ingress_name and payload.ingress_name not in namespace_ingresses(payload.namespace):
        raise HTTPException(status_code=400, detail=f"Ingress {payload.ingress_name} does not exist in namespace {payload.namespace}")
    if payload.application_type == "H2H" and not payload.reference_repository_name.strip():
        raise HTTPException(status_code=400, detail="Reference repository name is required for H2H")
    if payload.application_type == "H2H" and not payload.reference_branch.strip():
        raise HTTPException(status_code=400, detail="Reference repository branch must be provided by DevOps")
    original = current.get("original_request") or {key: current.get(key) for key in PipelineRequestCreate.model_fields}
    updated = {
        **current,
        **payload.model_dump(exclude={"review_comments"}),
        "review_comments": payload.review_comments,
        "reviewed_by": user.username,
        "updated_at": now_iso(),
        "original_request": original,
    }
    updated.setdefault("timeline", []).append(timeline_event("Modified by DevOps", user.username, payload.review_comments or "Request values updated"))
    items[index] = updated
    write_requests(items)
    logger.info(
        "Pipeline request updated request_id=%s username=%s repository=%s namespace=%s ingress=%s service=%s",
        request_id,
        user.username,
        updated.get("repository_name"),
        updated.get("namespace"),
        updated.get("ingress_name"),
        updated.get("service_name"),
    )
    return PipelineRequest(**updated)


def reject_pipeline_request(request_id: str, reason: str, user: UserContext) -> PipelineRequest:
    items = read_requests()
    index, current = find_request(items, request_id)
    current.update({"status": "Rejected", "reviewed_by": user.username, "review_comments": reason, "updated_at": now_iso()})
    current.setdefault("timeline", []).append(timeline_event("Rejected", user.username, reason))
    items[index] = current
    write_requests(items)
    logger.info("Pipeline request rejected request_id=%s username=%s reason=%s", request_id, user.username, reason)
    return PipelineRequest(**current)


def approve_pipeline_request(request_id: str, user: UserContext) -> PipelineRequest:
    items = read_requests()
    index, current = find_request(items, request_id)
    if current.get("status") not in ("Pending Approval", "Pending Action", "Partially Completed"):
        logger.warning("Approval rejected request_id=%s username=%s status=%s", request_id, user.username, current.get("status"))
        raise HTTPException(status_code=409, detail=f"Request cannot be approved from status {current.get('status')}")
    if not current.get("reference_branch", "").strip():
        raise HTTPException(status_code=400, detail="Provide the reference repository branch before approval")
    if not current.get("ingress_name"):
        raise HTTPException(status_code=400, detail="Select an ingress resource before approval")
    current.update({"status": "Provisioning", "reviewed_by": user.username, "updated_at": now_iso()})
    current.setdefault("timeline", []).append(timeline_event("Approved", user.username, f"Reference branch: {current['reference_branch']}"))
    logger.info(
        "Pipeline request approved request_id=%s username=%s repository=%s reference_repository=%s reference_branch=%s",
        request_id,
        user.username,
        current.get("repository_name"),
        current.get("reference_repository_name"),
        current.get("reference_branch"),
    )
    final_status, steps = provision(current)
    current.update({"provisioning": steps, "status": final_status, "updated_at": now_iso()})
    current["timeline"].append(timeline_event(final_status, "system", "Provisioning workflow finished"))
    items[index] = current
    write_requests(items)
    logger.info("Pipeline request provisioning saved request_id=%s status=%s", request_id, final_status)
    if steps.get("repository", {}).get("status") == "Warning":
        raise HTTPException(status_code=409, detail={"message": "Repository already exists", "request": current})
    return PipelineRequest(**current)
