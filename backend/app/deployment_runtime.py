from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from . import deployment_management as dm
from .azure_devops import azdo_request
from .logging_config import get_logger

logger = get_logger("deployment-runtime")


def resolve_pat(explicit_pat: str = "") -> str:
    return (
        explicit_pat.strip()
        or os.getenv("AZURE_DEVOPS_PAT", "").strip()
        or os.getenv("KUBERNETES_INVENTORY_PAT", "").strip()
    )


def _refresh_build_run(run: dict[str, Any], pat: str) -> None:
    run_id = run.get("run_id")
    if not run_id:
        return

    code, body = azdo_request(
        "GET",
        f"_apis/build/builds/{run_id}?api-version=7.1",
        pat,
    )
    if code != 200:
        run["error"] = body.get("message", f"Unable to refresh build {run_id}")
        logger.warning("Build refresh failed run_id=%s status=%s", run_id, code)
        return

    status = str(body.get("status") or "").lower()
    result = str(body.get("result") or "").lower()
    normalized = "Running"
    if status in {"notstarted", "postponed", "none"}:
        normalized = "Queued"
    elif status == "completed":
        normalized = "Succeeded" if result == "succeeded" else "Failed"

    web_url = ((body.get("_links") or {}).get("web") or {}).get("href") or run.get("url")
    started_at = body.get("startTime") or body.get("queueTime") or run.get("started_at")
    finished_at = body.get("finishTime") or run.get("finished_at")
    run.update(
        {
            "status": normalized,
            "result": body.get("result") or "",
            "url": web_url,
            "logs_url": web_url,
            "started_at": started_at,
            "finished_at": finished_at,
            "duration_seconds": dm._duration_seconds(started_at, finished_at),
        }
    )


def refresh_status(request_id: str, pat: str, actor: str) -> dict[str, Any]:
    rows = dm._load()
    row = next((item for item in rows if item.get("id") == request_id), None)
    if not row:
        raise HTTPException(status_code=404, detail="Deployment request not found")

    steps = row.setdefault("steps", {})
    build = steps.setdefault("build", {"status": "Waiting", "runs": []})
    build_runs = build.setdefault("runs", [])
    for run in build_runs:
        _refresh_build_run(run, pat)

    if build_runs:
        statuses = [str(run.get("status") or "") for run in build_runs]
        if all(status == "Succeeded" for status in statuses):
            build["status"] = "Succeeded"
            row["status"] = "Build Completed"
        elif any(status == "Failed" for status in statuses):
            build["status"] = "Failed"
            row["status"] = "Build Failed"
        elif any(status == "Running" for status in statuses):
            build["status"] = "Running"
            row["status"] = "Build Running"
        else:
            build["status"] = "Queued"
            row["status"] = "Build Queued"

    deployment = steps.setdefault("deployment", {"status": "Waiting", "runs": []})
    for run in deployment.setdefault("runs", []):
        if run.get("run_id"):
            _refresh_build_run(run, pat)

    if row.get("application_type") == "Collections" and build.get("status") == "Succeeded":
        dm._refresh_collections_release_links(row, pat)

    dm._update_progress(row)
    now = dm._now()
    row["updated_at"] = now
    row.setdefault("timeline", []).append(
        {
            "at": now,
            "action": "Pipeline status refreshed",
            "actor": actor,
            "build_status": build.get("status"),
            "deployment_status": deployment.get("status"),
        }
    )
    dm._save(rows)
    logger.info(
        "Deployment status refreshed request_id=%s build=%s deployment=%s",
        request_id,
        build.get("status"),
        deployment.get("status"),
    )
    return row


def reextract_document(request_id: str, actor: str) -> dict[str, Any]:
    rows = dm._load()
    row = next((item for item in rows if item.get("id") == request_id), None)
    if not row:
        raise HTTPException(status_code=404, detail="Deployment request not found")

    document_path = Path(str(row.get("document_path") or ""))
    if not document_path.is_file():
        raise HTTPException(status_code=404, detail="Uploaded release document was not found")

    extracted = dm._structured_extract(
        str(row.get("document_name") or document_path.name),
        document_path.read_bytes(),
        str(row.get("application_type") or ""),
        str(row.get("country") or ""),
    )

    extracted_fields = (
        "filename",
        "application",
        "branch_name",
        "environment",
        "repository",
        "target_branch",
        "build_pipeline",
        "war_files",
        "jar_files",
        "container_images",
        "text_preview",
        "confidence",
        "collections_items",
        "country",
    )
    for key in extracted_fields:
        if key in extracted:
            row[key] = extracted[key]

    architecture = row.get("architecture") or dm.ARCHITECTURES.get(row.get("application_type"), {})
    steps = row.setdefault("steps", {})
    steps["document_extraction"] = {"status": "Completed", "actor": actor, "at": dm._now()}
    steps["devops_review"] = {"status": "In Progress", "actor": actor, "at": dm._now()}
    steps["code_pull"] = {"status": "Not Required" if not architecture.get("code_pull") else "Waiting"}
    steps["pull_request"] = {"status": "Not Required" if not architecture.get("pull_request") else "Waiting"}
    steps["build"] = {"status": "Waiting", "runs": []}
    steps["deployment"] = {"status": "Waiting", "runs": []}

    row["extracted"] = True
    row["status"] = "DevOps Review"
    row["progress_percent"] = 40 if row.get("application_type") == "Collections" else row.get("progress_percent", 0)
    now = dm._now()
    row["updated_at"] = now
    row.setdefault("timeline", []).append(
        {
            "at": now,
            "action": "Document fully re-extracted and orchestration state reset",
            "actor": actor,
            "extracted_items": len(row.get("collections_items") or row.get("container_images") or []),
        }
    )
    dm._save(rows)
    logger.info(
        "Document fully re-extracted request_id=%s actor=%s extracted_items=%s",
        request_id,
        actor,
        len(row.get("collections_items") or row.get("container_images") or []),
    )
    return row


def trigger_collections_build(request_id: str, actor: str, pat: str, updates: dict[str, Any]) -> dict[str, Any]:
    rows = dm._load()
    row = next((item for item in rows if item.get("id") == request_id), None)
    if not row:
        raise HTTPException(status_code=404, detail="Deployment request not found")

    items = updates.get("collections_items") or row.get("collections_items") or []
    selected = [item for item in items if item.get("selected", True)]
    if not selected:
        raise HTTPException(status_code=422, detail="Select at least one Collections service")

    runs: list[dict[str, Any]] = []
    for item in selected:
        pipeline_name = item.get("pipeline_name") or dm.COLLECTIONS_PIPELINES.get(
            row.get("country", ""), {}
        ).get(item.get("service", ""), "")
        if not pipeline_name:
            raise HTTPException(
                status_code=422,
                detail=f"Pipeline mapping is missing for {item.get('service', 'service')}",
            )

        use_vendor_image = bool(item.get("use_vendor_image", True))
        vendor_image = str(item.get("vendor_image") or "").strip()
        if use_vendor_image and not vendor_image:
            raise HTTPException(
                status_code=422,
                detail=f"vendorImage is required for {item.get('service', 'service')}",
            )

        parameters = {
            "vendorImage": vendor_image,
            "useVendorImage": use_vendor_image,
        }
        run = dm._pipeline_run(pipeline_name, parameters, pat)
        runs.append({**item, **run, "parameters": parameters})
        logger.info(
            "Collections build queued request_id=%s service=%s pipeline=%s use_vendor_image=%s vendor_image=%s run_id=%s",
            request_id,
            item.get("service"),
            pipeline_name,
            use_vendor_image,
            vendor_image,
            run.get("run_id"),
        )

    row["collections_items"] = selected
    row.setdefault("steps", {})["build"] = {"status": "Queued", "runs": runs}
    row["status"] = "Build Queued"
    dm._update_progress(row)
    now = dm._now()
    row["updated_at"] = now
    row.setdefault("timeline", []).append(
        {
            "at": now,
            "action": "Collections build pipelines triggered",
            "actor": actor,
            "runs": len(runs),
        }
    )
    dm._save(rows)
    return row


def perform_action(
    request_id: str,
    action: str,
    actor: str,
    explicit_pat: str = "",
    updates: dict[str, Any] | None = None,
) -> dict[str, Any]:
    pat = resolve_pat(explicit_pat)
    updates = updates or {}

    requires_pat = action in {
        "trigger-code-pull",
        "create-pr",
        "trigger-build",
        "trigger-deployment",
        "refresh-status",
    }
    if requires_pat and not pat:
        raise HTTPException(
            status_code=422,
            detail="Azure DevOps PAT is not configured. Set KUBERNETES_INVENTORY_PAT or enter a PAT.",
        )

    if action == "extract-document":
        return reextract_document(request_id, actor)

    if action == "refresh-status":
        return refresh_status(request_id, pat, actor)

    if action == "trigger-build":
        rows = dm._load()
        row = next((item for item in rows if item.get("id") == request_id), None)
        if row and row.get("application_type") == "Collections":
            return trigger_collections_build(request_id, actor, pat, updates)

    return dm.update_action(request_id, action, actor, pat, updates)
