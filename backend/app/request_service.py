from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException

from .config import APP_OWNER_EMAILS, KUBERNETES_TARGETS, LANGUAGE_PORTS, LOCAL_KUBERNETES_TARGET
from .email_service import decode_approval_token, send_app_owner_approval_email
from .kubernetes_ops import cluster_namespaces, namespace_ingresses
from .logging_config import get_logger
from .models import PipelineRequest, PipelineRequestCreate, ReviewUpdate, UserContext
from .provisioning import provision
from .storage import find_request, now_iso, read_requests, timeline_event, write_requests

logger = get_logger("requests")


def _next_request_id(items: list[dict]) -> str:
    highest = 0
    for item in items:
        request_id = str(item.get("id", ""))
        if request_id.startswith("PCR-"):
            try:
                highest = max(highest, int(request_id.rsplit("-", 1)[-1]))
            except ValueError:
                pass
    return f"PCR-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{highest + 1:04d}"


def _record_notification_event(request_id: str, action: str, detail: str) -> PipelineRequest:
    items = read_requests(); index, current = find_request(items, request_id); current.setdefault("timeline", []).append(timeline_event(action, "system", detail)); current["updated_at"] = now_iso(); items[index] = current; write_requests(items); return PipelineRequest(**current)


def create_pipeline_request(payload: PipelineRequestCreate, user: UserContext) -> PipelineRequest:
    app_owner = APP_OWNER_EMAILS.get(payload.application_type)
    if not app_owner: raise HTTPException(status_code=400, detail=f"No app owner is configured for {payload.application_type}")
    pipeline_type = (payload.pipeline_type or "").strip(); default_port = LANGUAGE_PORTS.get(pipeline_type, 8080); reference_repository_name = payload.reference_repository_name.strip(); original = payload.model_dump()
    original.update({"app_owner": app_owner, "namespace": "", "target_cluster": LOCAL_KUBERNETES_TARGET, "setup_pipeline": bool(reference_repository_name), "create_service": False, "service_name": payload.repository_name.replace("_", "-"), "service_port": default_port, "reference_repository_name": reference_repository_name, "reference_branch": "develop" if payload.application_type == "Native-Mobile" else (payload.reference_branch or "")})
    created = now_iso(); items = read_requests(); request_id = _next_request_id(items)
    item = PipelineRequest(**original, id=request_id, requested_by=user.username, status="Pending App Owner Approval", created_at=created, updated_at=created, original_request=original, timeline=[timeline_event("Submitted", user.username, f"Sent to app owner {app_owner} for approval")])
    items.append(item.model_dump()); write_requests(items)
    try: send_app_owner_approval_email(item.model_dump()); item = _record_notification_event(request_id, "Approval Email Sent", app_owner)
    except Exception as exc: logger.exception("Unable to send app owner email request_id=%s app_owner=%s", request_id, app_owner); item = _record_notification_event(request_id, "Approval Email Failed", str(exc))
    return item


def _apply_app_owner_decision(request_id: str, decision: str, app_owner: str, comment: str | None = None, source: str = "approval link") -> tuple[str, str]:
    normalized_decision = decision.strip().lower()
    if normalized_decision not in ("approve", "reject"): raise HTTPException(status_code=400, detail="Invalid approval decision")
    items = read_requests(); index, current = find_request(items, request_id)
    if current.get("status") != "Pending App Owner Approval": return current.get("status", "Unknown"), f"Request {request_id} has already been processed."
    if current.get("app_owner", "").lower() != app_owner.strip().lower(): raise HTTPException(status_code=403, detail="The approver does not match the configured application owner")
    decided_at = now_iso(); clean_comment = (comment or "").strip()
    if normalized_decision == "approve": status, detail, action = "Pending Approval", "Approved by app owner and moved to the DevOps provisioning queue", "Approved by App Owner"
    else: status, detail, action = "Rejected", clean_comment or "Rejected by app owner", "Rejected by App Owner"
    current.update({"status": status, "app_owner_decision_by": app_owner, "app_owner_decision_at": decided_at, "app_owner_comment": clean_comment or None, "updated_at": decided_at}); current.setdefault("timeline", []).append(timeline_event(action, app_owner, f"{detail} via {source}")); items[index] = current; write_requests(items); return status, detail


def process_app_owner_action(token: str) -> tuple[str, str]:
    try: payload = decode_approval_token(token)
    except Exception as exc: raise HTTPException(status_code=400, detail="The approval link is invalid or has expired") from exc
    return _apply_app_owner_decision(payload.get("request_id", ""), payload.get("decision", ""), payload.get("sub", ""), source="email approval link")


def list_pipeline_requests(user: UserContext) -> list[PipelineRequest]:
    items = [PipelineRequest(**item) for item in read_requests()]; visible = [item for item in items if item.status != "Pending App Owner Approval"] if user.role == "devops" else [item for item in items if item.requested_by == user.username]; return list(reversed(visible))


def get_pipeline_request(request_id: str, user: UserContext) -> PipelineRequest:
    _, item = find_request(read_requests(), request_id)
    if user.role != "devops" and item.get("requested_by") != user.username: raise HTTPException(status_code=403, detail="Not allowed to view this request")
    return PipelineRequest(**item)


def update_pipeline_request(request_id: str, payload: ReviewUpdate, user: UserContext) -> PipelineRequest:
    items = read_requests(); index, current = find_request(items, request_id)
    if current.get("status") not in ("Pending Approval", "Pending Action", "Partially Completed"): raise HTTPException(status_code=409, detail="Only requests in the DevOps queue can be modified")
    target_cluster = (payload.target_cluster or LOCAL_KUBERNETES_TARGET).strip()
    if target_cluster not in KUBERNETES_TARGETS: raise HTTPException(status_code=400, detail=f"Kubernetes target {target_cluster} is not configured")
    if not payload.namespace.strip(): raise HTTPException(status_code=400, detail="Namespace is required")
    if target_cluster == LOCAL_KUBERNETES_TARGET:
        if payload.namespace not in cluster_namespaces(): raise HTTPException(status_code=400, detail="Namespace is not allowed")
        if payload.ingress_name and payload.ingress_name not in namespace_ingresses(payload.namespace): raise HTTPException(status_code=400, detail=f"Ingress {payload.ingress_name} does not exist in namespace {payload.namespace}")
    if payload.setup_pipeline and not payload.reference_repository_name.strip(): raise HTTPException(status_code=400, detail="Reference repository is required when pipeline setup is enabled")
    reference_branch = payload.reference_branch.strip()
    if payload.application_type == "Native-Mobile" and payload.reference_repository_name.strip() and not reference_branch: reference_branch = "develop"
    if payload.reference_repository_name.strip() and not reference_branch: raise HTTPException(status_code=400, detail="Reference repository branch must be provided when a reference repository is selected")
    original = current.get("original_request") or {key: current.get(key) for key in PipelineRequestCreate.model_fields}; updated_values = payload.model_dump(exclude={"review_comments", "app_owner"}); updated_values["reference_branch"] = reference_branch; updated_values["target_cluster"] = target_cluster
    updated = {**current, **updated_values, "app_owner": current.get("app_owner") or APP_OWNER_EMAILS.get(payload.application_type, ""), "review_comments": payload.review_comments, "reviewed_by": user.username, "updated_at": now_iso(), "original_request": original}; updated.setdefault("timeline", []).append(timeline_event("Modified by DevOps", user.username, payload.review_comments or "Request values updated")); items[index] = updated; write_requests(items); return PipelineRequest(**updated)


def reject_pipeline_request(request_id: str, reason: str, user: UserContext) -> PipelineRequest:
    items = read_requests(); index, current = find_request(items, request_id); current.update({"status": "Rejected", "reviewed_by": user.username, "review_comments": reason, "updated_at": now_iso()}); current.setdefault("timeline", []).append(timeline_event("Rejected", user.username, reason)); items[index] = current; write_requests(items); return PipelineRequest(**current)


def close_pipeline_request(request_id: str, comment: str, user: UserContext) -> PipelineRequest:
    items = read_requests(); index, current = find_request(items, request_id)
    if current.get("status") in ("Rejected", "Closed", "Provisioning", "Pending App Owner Approval"): raise HTTPException(status_code=409, detail=f"Request cannot be closed from status {current.get('status')}")
    if not comment.strip(): raise HTTPException(status_code=400, detail="Closure comment is mandatory")
    current.update({"status": "Closed", "reviewed_by": user.username, "closure_comment": comment.strip(), "updated_at": now_iso()}); current.setdefault("timeline", []).append(timeline_event("Closed by DevOps", user.username, comment.strip())); items[index] = current; write_requests(items); return PipelineRequest(**current)


def _save_provisioning_result(items: list[dict], index: int, current: dict, final_status: str, steps: dict) -> None:
    current.update({"provisioning": steps, "status": final_status, "updated_at": now_iso()}); current.setdefault("timeline", []).append(timeline_event(final_status, "system", "Provisioning workflow paused" if final_status == "Pending Action" else "Provisioning workflow finished")); items[index] = current; write_requests(items)


def _raise_confirmation_if_needed(current: dict, steps: dict) -> None:
    repository_step = steps.get("repository", {})
    if repository_step.get("requires_confirmation"): raise HTTPException(status_code=409, detail={"code": "existing_repository_confirmation_required", "message": "Repository already exists. Create the isolated pipeline branch from the selected reference repository without modifying existing branches or code?", "request": current})
    pipeline_step = steps.get("pipeline", {})
    if pipeline_step.get("requires_confirmation"): raise HTTPException(status_code=409, detail={"code": "existing_build_pipeline_confirmation_required", "message": pipeline_step.get("message") or "Build pipeline already exists. Proceed with release pipeline creation using it?", "request": current})


def approve_pipeline_request(request_id: str, user: UserContext, azure_devops_pat: str) -> PipelineRequest:
    items = read_requests(); index, current = find_request(items, request_id)
    if current.get("status") not in ("Pending Approval", "Pending Action", "Partially Completed"): raise HTTPException(status_code=409, detail=f"Request cannot be approved from status {current.get('status')}")
    if current.get("reference_repository_name", "").strip() and not current.get("reference_branch", "").strip(): raise HTTPException(status_code=400, detail="Provide the reference repository branch before approval")
    if current.get("setup_pipeline") and not current.get("reference_repository_name", "").strip(): raise HTTPException(status_code=400, detail="Pipeline setup requires a reference repository")
    if not current.get("namespace"): raise HTTPException(status_code=400, detail="Select a namespace before approval")
    if not current.get("ingress_name"): raise HTTPException(status_code=400, detail="Select an ingress resource before approval")
    if (current.get("target_cluster") or LOCAL_KUBERNETES_TARGET) not in KUBERNETES_TARGETS: raise HTTPException(status_code=400, detail="Select a configured Kubernetes target before approval")
    if not azure_devops_pat.strip(): raise HTTPException(status_code=400, detail="Azure DevOps PAT is required for provisioning")
    current.update({"status": "Provisioning", "reviewed_by": user.username, "updated_at": now_iso()}); current.setdefault("timeline", []).append(timeline_event("Approved by DevOps", user.username, "Provisioning started")); final_status, steps = provision(current, azure_devops_pat); _save_provisioning_result(items, index, current, final_status, steps); _raise_confirmation_if_needed(current, steps); return PipelineRequest(**current)


def confirm_existing_repository_bootstrap(request_id: str, user: UserContext, azure_devops_pat: str) -> PipelineRequest:
    items = read_requests(); index, current = find_request(items, request_id)
    if current.get("status") != "Pending Action": raise HTTPException(status_code=409, detail=f"Request cannot continue from status {current.get('status')}")
    if not azure_devops_pat.strip(): raise HTTPException(status_code=400, detail="Azure DevOps PAT is required for provisioning")
    pending_pipeline = current.get("provisioning", {}).get("pipeline", {})
    if pending_pipeline.get("requires_confirmation"):
        current["allow_existing_repo_bootstrap"] = True; current["allow_existing_pipeline_release"] = True; current["status"] = "Provisioning"; current["updated_at"] = now_iso(); current.setdefault("timeline", []).append(timeline_event("Existing Build Pipeline Confirmed", user.username, f"DevOps confirmed reuse of build pipeline {pending_pipeline.get('name') or pending_pipeline.get('id')} for release pipeline creation"))
        final_status, steps = provision(current, azure_devops_pat); current.pop("allow_existing_repo_bootstrap", None); current.pop("allow_existing_pipeline_release", None); _save_provisioning_result(items, index, current, final_status, steps); return PipelineRequest(**current)
    if not current.get("reference_repository_name", "").strip(): raise HTTPException(status_code=400, detail="Reference repository is required")
    if not current.get("reference_branch", "").strip(): raise HTTPException(status_code=400, detail="Reference repository branch is required")
    current["allow_existing_repo_bootstrap"] = True; current["status"] = "Provisioning"; current["updated_at"] = now_iso(); current.setdefault("timeline", []).append(timeline_event("Existing Repository Confirmed", user.username, "DevOps confirmed isolated pipeline branch creation; existing branches and code remain unchanged"))
    final_status, steps = provision(current, azure_devops_pat); current.pop("allow_existing_repo_bootstrap", None); _save_provisioning_result(items, index, current, final_status, steps); _raise_confirmation_if_needed(current, steps); return PipelineRequest(**current)


def confirm_existing_build_pipeline(request_id: str, user: UserContext, azure_devops_pat: str) -> PipelineRequest:
    return confirm_existing_repository_bootstrap(request_id, user, azure_devops_pat)
