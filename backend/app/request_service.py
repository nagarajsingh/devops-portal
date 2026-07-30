from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException

from .config import APP_OWNER_EMAILS, LANGUAGE_PORTS
from .email_service import decode_approval_token, send_app_owner_approval_email
from .kubernetes_ops import cluster_namespaces, namespace_ingresses
from .logging_config import get_logger
from .models import PipelineRequest, PipelineRequestCreate, ReviewUpdate, UserContext
from .provisioning import provision
from .storage import find_request, now_iso, read_requests, timeline_event, write_requests

logger = get_logger("requests")


def _record_notification_event(request_id: str, action: str, detail: str) -> PipelineRequest:
    items = read_requests()
    index, current = find_request(items, request_id)
    current.setdefault("timeline", []).append(timeline_event(action, "system", detail))
    current["updated_at"] = now_iso()
    items[index] = current
    write_requests(items)
    return PipelineRequest(**current)


def create_pipeline_request(payload: PipelineRequestCreate, user: UserContext) -> PipelineRequest:
    app_owner = APP_OWNER_EMAILS.get(payload.application_type)
    if not app_owner:
        raise HTTPException(status_code=400, detail=f"No app owner is configured for {payload.application_type}")

    pipeline_type = (payload.pipeline_type or "").strip()
    default_port = LANGUAGE_PORTS.get(pipeline_type, 8080)
    reference_repository_name = payload.reference_repository_name.strip()
    original = payload.model_dump()
    original.update({
        "app_owner": app_owner,
        "namespace": "",
        "setup_pipeline": bool(reference_repository_name),
        "create_service": False,
        "service_name": payload.repository_name.replace("_", "-"),
        "service_port": default_port,
        "reference_repository_name": reference_repository_name,
        "reference_branch": "develop" if payload.application_type == "Native-Mobile" else (payload.reference_branch or ""),
    })

    created = now_iso()
    request_id = f"PR-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:6].upper()}"
    item = PipelineRequest(
        **original,
        id=request_id,
        requested_by=user.username,
        status="Pending App Owner Approval",
        created_at=created,
        updated_at=created,
        original_request=original,
        timeline=[timeline_event("Submitted", user.username, f"Sent to app owner {app_owner} for approval")],
    )
    items = read_requests()
    items.append(item.model_dump())
    write_requests(items)

    try:
        send_app_owner_approval_email(item.model_dump())
        item = _record_notification_event(request_id, "Approval Email Sent", app_owner)
    except Exception as exc:
        logger.exception("Unable to send app owner email request_id=%s app_owner=%s", request_id, app_owner)
        item = _record_notification_event(request_id, "Approval Email Failed", str(exc))

    logger.info("Pipeline request submitted request_id=%s username=%s repository=%s app_owner=%s", item.id, user.username, item.repository_name, app_owner)
    return item


def _apply_app_owner_decision(
    request_id: str,
    decision: str,
    app_owner: str,
    comment: str | None = None,
    source: str = "approval link",
) -> tuple[str, str]:
    normalized_decision = decision.strip().lower()
    if normalized_decision not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="Invalid approval decision")

    items = read_requests()
    index, current = find_request(items, request_id)
    if current.get("status") != "Pending App Owner Approval":
        return current.get("status", "Unknown"), f"Request {request_id} has already been processed."
    if current.get("app_owner", "").lower() != app_owner.strip().lower():
        raise HTTPException(status_code=403, detail="The approver does not match the configured application owner")

    decided_at = now_iso()
    clean_comment = (comment or "").strip()
    if normalized_decision == "approve":
        status = "Pending Approval"
        detail = "Approved by app owner and moved to the DevOps provisioning queue"
        action = "Approved by App Owner"
    else:
        status = "Rejected"
        detail = clean_comment or "Rejected by app owner"
        action = "Rejected by App Owner"

    current.update({
        "status": status,
        "app_owner_decision_by": app_owner,
        "app_owner_decision_at": decided_at,
        "app_owner_comment": clean_comment or None,
        "updated_at": decided_at,
    })
    current.setdefault("timeline", []).append(timeline_event(action, app_owner, f"{detail} via {source}"))
    items[index] = current
    write_requests(items)
    logger.info(
        "App owner decision recorded request_id=%s decision=%s app_owner=%s source=%s",
        request_id,
        normalized_decision,
        app_owner,
        source,
    )
    return status, detail


def process_app_owner_action(token: str) -> tuple[str, str]:
    try:
        payload = decode_approval_token(token)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="The approval link is invalid or has expired") from exc

    return _apply_app_owner_decision(
        request_id=payload.get("request_id", ""),
        decision=payload.get("decision", ""),
        app_owner=payload.get("sub", ""),
        source="email approval link",
    )


def list_pipeline_requests(user: UserContext) -> list[PipelineRequest]:
    items = [PipelineRequest(**item) for item in read_requests()]
    visible = [item for item in items if item.status != "Pending App Owner Approval"] if user.role == "devops" else [item for item in items if item.requested_by == user.username]
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
        raise HTTPException(status_code=409, detail="Only requests in the DevOps queue can be modified")
    if payload.namespace not in cluster_namespaces():
        raise HTTPException(status_code=400, detail="Namespace is not allowed")
    if payload.ingress_name and payload.ingress_name not in namespace_ingresses(payload.namespace):
        raise HTTPException(status_code=400, detail=f"Ingress {payload.ingress_name} does not exist in namespace {payload.namespace}")
    if payload.setup_pipeline and not payload.reference_repository_name.strip():
        raise HTTPException(status_code=400, detail="Reference repository is required when pipeline setup is enabled")

    reference_branch = payload.reference_branch.strip()
    if payload.application_type == "Native-Mobile" and payload.reference_repository_name.strip() and not reference_branch:
        reference_branch = "develop"
    if payload.reference_repository_name.strip() and not reference_branch:
        raise HTTPException(status_code=400, detail="Reference repository branch must be provided when a reference repository is selected")

    original = current.get("original_request") or {key: current.get(key) for key in PipelineRequestCreate.model_fields}
    updated_values = payload.model_dump(exclude={"review_comments", "app_owner"})
    updated_values["reference_branch"] = reference_branch
    updated = {
        **current,
        **updated_values,
        "app_owner": current.get("app_owner") or APP_OWNER_EMAILS.get(payload.application_type, ""),
        "review_comments": payload.review_comments,
        "reviewed_by": user.username,
        "updated_at": now_iso(),
        "original_request": original,
    }
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
    if current.get("status") in ("Rejected", "Closed", "Provisioning", "Pending App Owner Approval"):
        raise HTTPException(status_code=409, detail=f"Request cannot be closed from status {current.get('status')}")
    if not comment.strip():
        raise HTTPException(status_code=400, detail="Closure comment is mandatory")
    current.update({"status": "Closed", "reviewed_by": user.username, "closure_comment": comment.strip(), "updated_at": now_iso()})
    current.setdefault("timeline", []).append(timeline_event("Closed by DevOps", user.username, comment.strip()))
    items[index] = current
    write_requests(items)
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
    if not current.get("namespace"):
        raise HTTPException(status_code=400, detail="Select a namespace before approval")
    if not current.get("ingress_name"):
        raise HTTPException(status_code=400, detail="Select an ingress resource before approval")
    if not azure_devops_pat.strip():
        raise HTTPException(status_code=400, detail="Azure DevOps PAT is required for provisioning")

    current.update({"status": "Provisioning", "reviewed_by": user.username, "updated_at": now_iso()})
    current.setdefault("timeline", []).append(timeline_event("Approved by DevOps", user.username, "Provisioning started"))
    final_status, steps = provision(current, azure_devops_pat)
    current.update({"provisioning": steps, "status": final_status, "updated_at": now_iso()})
    current["timeline"].append(timeline_event(final_status, "system", "Provisioning workflow finished"))
    items[index] = current
    write_requests(items)
    if steps.get("repository", {}).get("status") == "Warning":
        raise HTTPException(status_code=409, detail={"message": "Repository already exists", "request": current})
    return PipelineRequest(**current)
