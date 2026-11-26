from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from . import deployment_management as dm
from .azure_devops import azdo_request
from .azure_releases import discover_collections_releases
from .logging_config import get_logger

logger = get_logger("deployment-runtime")


def resolve_pat(explicit_pat: str = "") -> str:
    return (
        explicit_pat.strip()
        or os.getenv("AZURE_DEVOPS_PAT", "").strip()
        or os.getenv("KUBERNETES_INVENTORY_PAT", "").strip()
    )


def _refresh_build_run(run: dict[str, Any], pat: str) -> bool:
    run_id = run.get("run_id")
    if not run_id:
        return False

    code, body = azdo_request(
        "GET",
        f"_apis/build/builds/{run_id}?api-version=7.1",
        pat,
    )
    if code != 200:
        run["error"] = body.get("message", f"Unable to refresh build {run_id}")
        logger.warning("Build refresh failed run_id=%s status=%s", run_id, code)
        return False

    run.pop("error", None)
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
            "pipeline_id": (body.get("definition") or {}).get("id") or run.get("pipeline_id"),
            "pipeline_name": (body.get("definition") or {}).get("name") or run.get("pipeline_name"),
            "build_number": body.get("buildNumber") or run.get("build_number"),
            "project_id": (body.get("project") or {}).get("id") or run.get("project_id"),
            "source_branch": body.get("sourceBranch") or run.get("source_branch"),
        }
    )
    return True


COLLECTIONS_DEPLOYMENT_ENVIRONMENTS = dm.COLLECTIONS_DEPLOYMENT_ENVIRONMENTS

_COLLECTIONS_ENVIRONMENT_ALIASES = {
    "DEV": {"dev", "development"},
    "SIT": {"sit"},
    "UAT": {"uat"},
    "TRAINING/PPR": {"training", "train", "ppr", "preprd", "preprod", "trainingppr"},
    "PROD": {"prod", "production"},
    "DR": {"dr", "disasterrecovery"},
}


def _normalized_environment_name(value: Any) -> str:
    return "".join(
        char
        for char in str(value or "").strip().casefold()
        if char.isalnum()
    )


def _target_environment(environments: list[dict[str, Any]], target: str) -> dict[str, Any] | None:
    aliases = _COLLECTIONS_ENVIRONMENT_ALIASES.get(target, set())
    for environment in environments:
        if _normalized_environment_name(environment.get("name")) in aliases:
            return environment
    return None


def _target_environment_release_status(environments: list[dict[str, Any]], target: str) -> tuple[str, str]:
    environment = _target_environment(environments, target)
    if not environment:
        return "Ready", "Not Found"

    raw_status = str(environment.get("status") or "").strip()
    normalized = raw_status.casefold().replace("_", "").replace(" ", "")
    if normalized == "succeeded":
        return "Succeeded", raw_status or "succeeded"
    if normalized in {"rejected", "canceled", "cancelled", "failed", "partiallysucceeded"}:
        return "Failed", raw_status
    if normalized in {"queued", "inprogress", "scheduled"}:
        return "Running", raw_status
    return "Ready", raw_status or "notStarted"


def _sync_collections_releases(row: dict[str, Any], pat: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Discover Classic Releases and evaluate only the DevOps-selected environment."""
    runs, missing = discover_collections_releases(row, pat)
    deployment = row.setdefault("steps", {}).setdefault("deployment", {"status": "Waiting", "runs": []})
    target_environment = str(row.get("deployment_environment") or "").strip().upper()

    if runs:
        if target_environment:
            for run in runs:
                target_status, raw_status = _target_environment_release_status(
                    run.get("environments") or [],
                    target_environment,
                )
                run["overall_release_status"] = run.get("status")
                run["status"] = target_status
                run["result"] = target_status
                run["target_environment"] = target_environment
                run["target_environment_status"] = raw_status

        deployment["runs"] = runs
        deployment["discovery_missing"] = missing
        deployment["target_environment"] = target_environment
        statuses = [str(run.get("status") or "") for run in runs]

        if all(status == "Succeeded" for status in statuses) and not missing:
            deployment["status"] = "Succeeded"
            row["status"] = "Deployment Completed"
        elif any(status == "Failed" for status in statuses):
            deployment["status"] = "Failed"
            row["status"] = "Deployment Failed"
        elif any(status == "Running" for status in statuses):
            deployment["status"] = "Running"
            row["status"] = "Deployment Running"
        else:
            deployment["status"] = "Ready"
            row["status"] = "Release Discovery Pending" if missing else "Release Discovered"
    else:
        deployment["runs"] = []
        deployment["status"] = "Waiting"
        deployment["target_environment"] = target_environment
        deployment["discovery_missing"] = missing

    return runs, missing


def _update_build_status(row: dict[str, Any]) -> None:
    build = row["steps"]["build"]
    statuses = [str(run.get("status") or "") for run in build.get("runs", [])]
    if not statuses:
        return
    if any(status == "Running" for status in statuses):
        build["status"], row["status"] = "Running", "Build Running"
    elif any(status == "Queued" for status in statuses):
        build["status"], row["status"] = "Queued", "Build Queued"
    elif all(status == "Succeeded" for status in statuses):
        build["status"], row["status"] = "Succeeded", "Build Completed"
    else:
        build["status"], row["status"] = "Failed", "Build Failed"


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

    _update_build_status(row)

    deployment = steps.setdefault("deployment", {"status": "Waiting", "runs": []})
    for run in deployment.setdefault("runs", []):
        if run.get("run_id"):
            _refresh_build_run(run, pat)

    if row.get("application_type") == "Collections" and build.get("status") == "Succeeded":
        _sync_collections_releases(row, pat)

    dm._update_progress(row)
    now = dm._now()
    row["updated_at"] = now
    row.setdefault("timeline", []).append(
        {
            "at": now,
            "action": "Pipeline status refreshed",
            "actor": actor,
            "build_status": build.get("status"),
            "deployment_status": row.get("steps", {}).get("deployment", {}).get("status"),
        }
    )
    dm._save(rows)
    logger.info(
        "Deployment status refreshed request_id=%s build=%s deployment=%s",
        request_id,
        build.get("status"),
        row.get("steps", {}).get("deployment", {}).get("status"),
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


def retry_collections_builds(request_id: str, actor: str, pat: str, updates: dict[str, Any]) -> dict[str, Any]:
    """Queue new runs for explicitly selected failed attempts, keeping other runs unchanged."""
    rows = dm._load()
    row = next((item for item in rows if item.get("id") == request_id), None)
    if not row:
        raise HTTPException(status_code=404, detail="Deployment request not found")
    if row.get("application_type") != "Collections":
        raise HTTPException(status_code=422, detail="This retry action is for Collections builds")
    steps = row.get("steps") or {}
    if (steps.get("owner_approval") or {}).get("status") != "Approved" or row.get("status") == "Completed":
        raise HTTPException(status_code=409, detail="Only approved, open deployment requests can retry builds")
    deployment = steps.get("deployment") or {}
    if deployment.get("runs") or deployment.get("status") not in (None, "", "Waiting"):
        raise HTTPException(status_code=409, detail="Build retry is unavailable once deployment has started")
    build = steps.get("build") or {}
    runs = build.get("runs") or []
    requested = updates.get("run_ids")
    if not isinstance(requested, list) or not requested or any(type(value) is not int or value <= 0 for value in requested):
        raise HTTPException(status_code=422, detail="Select at least one failed build run")
    ids = set(requested)
    targets = [(index, run) for index, run in enumerate(runs) if run.get("run_id") in ids]
    if len(targets) != len(ids):
        raise HTTPException(status_code=409, detail="Build runs have changed. Refresh before retrying.")
    if any(run.get("status") != "Failed" for _, run in targets):
        raise HTTPException(status_code=409, detail="Only failed build runs may be retried")

    queued = []
    errors = []
    for index, old in targets:
        service = old.get("service") or old.get("pipeline_name") or str(old.get("run_id"))
        try:
            if not _refresh_build_run(old, pat):
                raise HTTPException(status_code=502, detail="Unable to verify the original build status")
            if old.get("status") != "Failed":
                raise HTTPException(status_code=409, detail="Original build is no longer failed")
            parameters = old.get("parameters")
            if not isinstance(parameters, dict):
                # Compatibility with older runs that stored the reviewed inputs directly.
                if "use_vendor_image" not in old or "vendor_image" not in old:
                    raise HTTPException(status_code=409, detail="Original build parameters are unavailable")
                parameters = {"vendorImage": old["vendor_image"], "useVendorImage": old["use_vendor_image"]}
            if not isinstance(parameters.get("useVendorImage"), bool) or (parameters["useVendorImage"] and not str(parameters.get("vendorImage") or "").strip()):
                raise HTTPException(status_code=409, detail="Original vendor image parameters are incomplete")
            pipeline_name = str(old.get("pipeline_name") or "")
            pipeline_id = old.get("pipeline_id")
            if not pipeline_name or not pipeline_id:
                raise HTTPException(status_code=409, detail="Original pipeline identity is unavailable")
            ref = str(old.get("source_branch") or "")
            if ref and not ref.startswith("refs/heads/"):
                raise HTTPException(status_code=409, detail="Original build branch is not supported for automatic retry")
            new = dm._pipeline_run(pipeline_name, parameters, pat, ref=ref, pipeline_id=int(pipeline_id))
            previous = {key: value for key, value in old.items() if key not in {"attempt_history", "parameters"}}
            history = list(old.get("attempt_history") or []) + [previous]
            # Replace the current attempt only; deployment discovery sees the new run ID.
            runs[index] = {
                **{key: old[key] for key in ("service", "image_tag", "vendor_image", "use_vendor_image", "country", "selected", "extraction_method") if key in old},
                **new,
                "parameters": parameters,
                "source_branch": ref,
                "attempt_history": history,
                "retry_of": old["run_id"],
            }
            queued.append({"service": service, "previous_run_id": old["run_id"], "run_id": new["run_id"]})
        except HTTPException as exc:
            errors.append({"service": service, "run_id": old.get("run_id"), "message": str(exc.detail)})
        except Exception:
            logger.exception("Collections retry failed request_id=%s run_id=%s", request_id, old.get("run_id"))
            errors.append({"service": service, "run_id": old.get("run_id"), "message": "Unable to queue retry; check Azure DevOps before trying again"})
        # Persist each accepted run immediately, including partial success.
        _update_build_status(row)
        dm._update_progress(row)
        row["updated_at"] = dm._now()
        dm._save(rows)

    result = {"queued": queued, "errors": errors}
    row.setdefault("timeline", []).append({"at": dm._now(), "actor": actor, "action": "Collections failed builds retried", **result})
    dm._save(rows)
    return {**row, "retry_result": result}


def trigger_collections_deployment(
    request_id: str,
    actor: str,
    pat: str,
    updates: dict[str, Any],
) -> dict[str, Any]:
    rows = dm._load()
    row = next((item for item in rows if item.get("id") == request_id), None)
    if not row:
        raise HTTPException(status_code=404, detail="Deployment request not found")

    requested_environment = str(row.get("deployment_environment") or "").strip().upper()
    if requested_environment not in COLLECTIONS_DEPLOYMENT_ENVIRONMENTS:
        raise HTTPException(
            status_code=422,
            detail=(
                "The Collections target environment is missing from the original deployment request. "
                "The developer must select one of: "
                + ", ".join(COLLECTIONS_DEPLOYMENT_ENVIRONMENTS)
            ),
        )

    steps = row.setdefault("steps", {})
    build = steps.setdefault("build", {"status": "Waiting", "runs": []})
    for run in build.setdefault("runs", []):
        _refresh_build_run(run, pat)

    statuses = [str(run.get("status") or "") for run in build.get("runs", [])]
    if not statuses or not all(status == "Succeeded" for status in statuses):
        raise HTTPException(status_code=409, detail="All Collections build pipelines must succeed before release discovery")
    build["status"] = "Succeeded"

    releases, missing = _sync_collections_releases(row, pat)
    if not releases:
        details = "; ".join(
            f"{item.get('build_pipeline_name') or item.get('build_run_id')}: {item.get('reason')}"
            for item in missing
        )
        raise HTTPException(
            status_code=409,
            detail=(
                "Builds succeeded, but no linked Azure DevOps Classic Release was found yet. "
                "The portal now discovers releases automatically from each exact build run. "
                f"{details}" if details else
                "Builds succeeded, but no linked Azure DevOps Classic Release was found yet."
            ),
        )

    now = dm._now()
    row["updated_at"] = now
    row.setdefault("timeline", []).append(
        {
            "at": now,
            "action": "Collections releases automatically discovered",
            "actor": actor,
            "releases": len(releases),
            "missing": len(missing),
            "deployment_environment": requested_environment,
        }
    )
    dm._update_progress(row)
    dm._save(rows)
    logger.info(
        "Collections release discovery completed request_id=%s releases=%s missing=%s",
        request_id,
        len(releases),
        len(missing),
    )
    return row


def complete_deployment_request(
    request_id: str,
    actor: str,
    updates: dict[str, Any],
) -> dict[str, Any]:
    rows = dm._load()
    row = next((item for item in rows if item.get("id") == request_id), None)
    if not row:
        raise HTTPException(status_code=404, detail="Deployment request not found")

    comment = str(updates.get("comment") or "").strip()
    if not comment:
        raise HTTPException(status_code=422, detail="Completion comment is required")

    deployment_status = str(
        ((row.get("steps") or {}).get("deployment") or {}).get("status") or ""
    )
    if deployment_status != "Succeeded":
        raise HTTPException(
            status_code=409,
            detail="Deployment can be completed only after the target deployment status is Succeeded",
        )

    if str(row.get("status") or "") == "Completed":
        raise HTTPException(status_code=409, detail="Deployment request is already completed")

    now = dm._now()
    row["status"] = "Completed"
    row["progress_percent"] = 100
    row["completion_comment"] = comment
    row["completed_by"] = actor
    row["completed_at"] = now
    row.setdefault("steps", {})["completion"] = {
        "status": "Completed",
        "actor": actor,
        "at": now,
        "comment": comment,
    }
    row.setdefault("timeline", []).append(
        {
            "at": now,
            "action": "Deployment request completed",
            "actor": actor,
            "comment": comment,
        }
    )
    row["updated_at"] = now
    dm._save(rows)
    logger.info(
        "Deployment request completed request_id=%s actor=%s requested_by=%s",
        request_id,
        actor,
        row.get("requested_by"),
    )
    return row


def _perform_action(
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
        "retry-build",
        "trigger-deployment",
        "refresh-status",
    }
    if requires_pat and not pat:
        raise HTTPException(
            status_code=422,
            detail="Azure DevOps PAT is not configured. Set KUBERNETES_INVENTORY_PAT or enter a PAT.",
        )

    if action == "complete-request":
        return complete_deployment_request(request_id, actor, updates)

    if action == "extract-document":
        return reextract_document(request_id, actor)

    if action == "refresh-status":
        return refresh_status(request_id, pat, actor)

    if action == "retry-build":
        return retry_collections_builds(request_id, actor, pat, updates)

    if action == "trigger-build":
        rows = dm._load()
        row = next((item for item in rows if item.get("id") == request_id), None)
        if row and row.get("application_type") == "Collections":
            return trigger_collections_build(request_id, actor, pat, updates)

    if action == "trigger-deployment":
        rows = dm._load()
        row = next((item for item in rows if item.get("id") == request_id), None)
        if row and row.get("application_type") == "Collections":
            return trigger_collections_deployment(request_id, actor, pat, updates)

    return dm.update_action(request_id, action, actor, pat, updates)


def perform_action(request_id: str, action: str, actor: str, explicit_pat: str = "", updates: dict[str, Any] | None = None) -> dict[str, Any]:
    # Prevent refresh and retry from overwriting one another in this process.
    with dm._LOCK:
        return _perform_action(request_id, action, actor, explicit_pat, updates)
