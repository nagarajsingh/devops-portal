from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any

from kubernetes import client
from kubernetes.client.rest import ApiException

from ..config import AZDO_ORG, AZDO_PROJECT, KUBERNETES_INVENTORY_PAT, LOCAL_KUBERNETES_TARGET, NAMESPACE_ALLOWLIST
from ..kubernetes_ops import load_k8s
from ..logging_config import get_logger
from .service import build_monitoring_summary as build_stored_summary

logger = get_logger("monitoring-live")


def _request_json(url: str) -> dict[str, Any]:
    if not KUBERNETES_INVENTORY_PAT:
        raise RuntimeError("KUBERNETES_INVENTORY_PAT is not configured")
    token = base64.b64encode(f":{KUBERNETES_INVENTORY_PAT}".encode()).decode()
    request = urllib.request.Request(url, headers={"Authorization": f"Basic {token}", "Accept": "application/json"}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            return json.loads(response.read().decode("utf-8", errors="replace") or "{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Azure DevOps returned HTTP {exc.code}: {detail[:300]}") from exc


def _azdo_url(path: str, release: bool = False) -> str:
    host = "vsrm.dev.azure.com" if release else "dev.azure.com"
    return f"https://{host}/{urllib.parse.quote(AZDO_ORG)}/{urllib.parse.quote(AZDO_PROJECT)}/{path}"


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _build_row(row: dict[str, Any], yaml_definition_ids: set[int]) -> dict[str, Any]:
    definition = row.get("definition") or {}
    definition_id = int(definition.get("id") or 0)
    name = str(definition.get("name") or row.get("buildNumber") or "").strip()
    lower_name = name.lower()
    is_yaml = definition_id in yaml_definition_ids
    is_deployment = "deploy-pipeline" in lower_name or "deploy" in lower_name

    if is_deployment:
        pipeline_type = "YAML Deployment"
    elif is_yaml:
        pipeline_type = "YAML Build"
    else:
        pipeline_type = "Classic build"

    return {
        "id": row.get("id"),
        "name": name,
        "build_number": row.get("buildNumber"),
        "status": row.get("status") or "unknown",
        "result": row.get("result") or "",
        "reason": row.get("reason") or "",
        "pipeline_type": pipeline_type,
        "queue_time": row.get("queueTime"),
        "start_time": row.get("startTime"),
        "finish_time": row.get("finishTime"),
        "requested_by": (row.get("requestedFor") or {}).get("displayName"),
        "url": ((row.get("_links") or {}).get("web") or {}).get("href"),
    }


def _release_row(row: dict[str, Any]) -> dict[str, Any]:
    release = row.get("release") or {}
    definition = release.get("releaseDefinition") or row.get("releaseDefinition") or {}
    environment = row.get("releaseEnvironment") or {}
    return {
        "id": row.get("id"),
        "name": definition.get("name") or release.get("name") or "Classic release",
        "release_name": release.get("name"),
        "environment": environment.get("name"),
        "status": row.get("deploymentStatus") or row.get("status") or "unknown",
        "started_on": row.get("startedOn") or row.get("queuedOn"),
        "completed_on": row.get("completedOn"),
        "requested_by": (row.get("requestedBy") or {}).get("displayName"),
        "url": ((release.get("_links") or {}).get("web") or {}).get("href"),
    }


def _live_pipeline_metrics(days: int) -> dict[str, Any]:
    if not AZDO_ORG or not AZDO_PROJECT:
        raise RuntimeError("AZURE_DEVOPS_ORGANIZATION and AZURE_DEVOPS_PROJECT are required")

    days = max(1, min(days, 90))
    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0) if days == 1 else now - timedelta(days=days)

    definitions = _request_json(
        _azdo_url("_apis/build/definitions?$top=10000&includeAllProperties=true&api-version=7.1")
    )
    definition_rows = definitions.get("value") or []
    yaml_definition_ids = {
        int(row.get("id"))
        for row in definition_rows
        if row.get("id")
        and (
            str((row.get("process") or {}).get("type") or "") == "2"
            or bool(str((row.get("process") or {}).get("yamlFilename") or "").strip())
        )
    }
    deployment_definition_ids = {
        int(row.get("id"))
        for row in definition_rows
        if row.get("id") and "deploy" in str(row.get("name") or "").lower()
    }

    build_query = urllib.parse.urlencode({"queryOrder": "queueTimeDescending", "minTime": _iso(start), "$top": "1000", "api-version": "7.1"})
    build_rows = _request_json(_azdo_url(f"_apis/build/builds?{build_query}")).get("value") or []
    builds = [_build_row(row, yaml_definition_ids) for row in build_rows]

    running_rows = [row for row in builds if str(row["status"]).lower() == "inprogress"]
    queued_rows = [row for row in builds if str(row["status"]).lower() in {"notstarted", "postponed"}]
    completed_rows = [row for row in builds if str(row["status"]).lower() == "completed"]
    succeeded_rows = [row for row in completed_rows if str(row["result"]).lower() in {"succeeded", "partiallysucceeded"}]
    failed_rows = [row for row in completed_rows if str(row["result"]).lower() in {"failed", "canceled"}]

    yaml_build_rows = [row for row in builds if row["pipeline_type"] == "YAML Build"]
    deployment_rows = [row for row in builds if row["pipeline_type"] == "YAML Deployment"]

    yaml_running = [row for row in yaml_build_rows if str(row["status"]).lower() == "inprogress"]
    yaml_queued = [row for row in yaml_build_rows if str(row["status"]).lower() in {"notstarted", "postponed"}]
    yaml_completed = [row for row in yaml_build_rows if str(row["status"]).lower() == "completed"]

    deploy_running = [row for row in deployment_rows if str(row["status"]).lower() == "inprogress"]
    deploy_queued = [row for row in deployment_rows if str(row["status"]).lower() in {"notstarted", "postponed"}]
    deploy_completed = [row for row in deployment_rows if str(row["status"]).lower() == "completed"]
    deploy_failed = [row for row in deploy_completed if str(row["result"]).lower() in {"failed", "canceled"}]

    release_definitions = 0
    classic_rows: list[dict[str, Any]] = []
    release_error = ""
    try:
        release_defs = _request_json(_azdo_url("_apis/release/definitions?$top=10000&api-version=7.1", release=True))
        release_definitions = int(release_defs.get("count") or len(release_defs.get("value") or []))
        release_query = urllib.parse.urlencode({"minModifiedTime": _iso(start), "$top": "1000", "queryOrder": "descending", "api-version": "7.1"})
        raw_deployments = _request_json(_azdo_url(f"_apis/release/deployments?{release_query}", release=True)).get("value") or []
        classic_rows = [_release_row(row) for row in raw_deployments]
    except Exception as exc:
        release_error = str(exc)
        logger.exception("Unable to load live classic release data")

    classic_running = [row for row in classic_rows if str(row["status"]).lower() == "inprogress"]
    classic_pending = [row for row in classic_rows if str(row["status"]).lower() in {"queued", "scheduled", "notdeployed", "pending"}]
    classic_completed = [row for row in classic_rows if str(row["status"]).lower() == "succeeded"]
    classic_failed = [row for row in classic_rows if str(row["status"]).lower() in {"failed", "canceled", "rejected"}]

    return {
        "days": days,
        "from": _iso(start),
        "to": _iso(now),
        "definitions": len(definition_rows),
        "running": len(running_rows),
        "queued": len(queued_rows),
        "builds_completed": len(completed_rows),
        "builds_succeeded": len(succeeded_rows),
        "builds_failed": len(failed_rows),
        "running_runs": running_rows[:50],
        "queued_runs": queued_rows[:50],
        "completed_runs": completed_rows[:100],
        "yaml": {
            "definitions": len(yaml_definition_ids - deployment_definition_ids),
            "running": len(yaml_running),
            "queued": len(yaml_queued),
            "completed": len(yaml_completed),
            "failed": sum(str(row["result"]).lower() in {"failed", "canceled"} for row in yaml_completed),
            "runs": yaml_build_rows[:100],
        },
        "yaml_deployments": {
            "definitions": len(deployment_definition_ids),
            "running": len(deploy_running),
            "queued": len(deploy_queued),
            "completed": len(deploy_completed),
            "failed": len(deploy_failed),
            "runs": deployment_rows[:100],
        },
        "classic": {
            "definitions": release_definitions,
            "running": len(classic_running),
            "pending": len(classic_pending),
            "completed": len(classic_completed),
            "failed": len(classic_failed),
            "deployments": classic_rows[:100],
            "error": release_error,
        },
        "source": "Titan live Azure DevOps API",
        "collected_at": _iso(now),
    }


def _quantity_to_gib(value: Any) -> float:
    text = str(value or "0")
    units = {"Ki": 1 / 1024 / 1024, "Mi": 1 / 1024, "Gi": 1, "Ti": 1024, "K": 1 / 1000 / 1000, "M": 1 / 1000, "G": 1, "T": 1000}
    for suffix, multiplier in units.items():
        if text.endswith(suffix):
            try:
                return round(float(text[:-len(suffix)]) * multiplier, 2)
            except ValueError:
                return 0.0
    try:
        return round(float(text) / 1024 / 1024 / 1024, 2)
    except ValueError:
        return 0.0


def _persistent_volume_data(core: client.CoreV1Api) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    total_capacity = 0.0
    total_allocated = 0.0
    try:
        volumes = core.list_persistent_volume().items
    except ApiException as exc:
        if exc.status == 403:
            logger.warning("Persistent volume monitoring unavailable: ServiceAccount lacks list persistentvolumes permission")
            return [], {
                "capacity_gib": 0.0,
                "allocated_gib": 0.0,
                "available_gib": 0.0,
                "available": False,
                "error": "The backend ServiceAccount is not permitted to list PersistentVolumes.",
            }
        raise

    for pv in volumes:
        capacity = _quantity_to_gib((pv.spec.capacity or {}).get("storage"))
        claim_ref = pv.spec.claim_ref
        requested = capacity if claim_ref else 0.0
        total_capacity += capacity
        total_allocated += requested
        rows.append({
            "name": pv.metadata.name,
            "capacity_gib": capacity,
            "allocated_gib": requested,
            "available_gib": round(max(0.0, capacity - requested), 2),
            "status": pv.status.phase if pv.status else "Unknown",
            "storage_class": pv.spec.storage_class_name or "",
            "access_modes": pv.spec.access_modes or [],
            "claim": f"{claim_ref.namespace}/{claim_ref.name}" if claim_ref else "",
        })

    return rows, {
        "capacity_gib": round(total_capacity, 2),
        "allocated_gib": round(total_allocated, 2),
        "available_gib": round(max(0.0, total_capacity - total_allocated), 2),
        "available": True,
        "error": "",
    }


def _live_local_cluster() -> dict[str, Any]:
    load_k8s()
    core = client.CoreV1Api()
    apps = client.AppsV1Api()
    networking = client.NetworkingV1Api()
    all_namespaces = [item.metadata.name for item in core.list_namespace().items if item.metadata and item.metadata.name]
    show_all = any(value.lower() == "all" for value in NAMESPACE_ALLOWLIST)
    names = sorted(all_namespaces if show_all or not NAMESPACE_ALLOWLIST else [name for name in all_namespaces if name in NAMESPACE_ALLOWLIST])

    pv_rows, storage = _persistent_volume_data(core)

    rows: list[dict[str, Any]] = []
    services_total = ingresses_total = deployments_total = healthy = unhealthy = 0
    for namespace in names:
        services = core.list_namespaced_service(namespace).items
        ingresses = networking.list_namespaced_ingress(namespace).items
        deployments = apps.list_namespaced_deployment(namespace).items
        service_names = [item.metadata.name for item in services if item.metadata and item.metadata.name]
        ingress_names = [item.metadata.name for item in ingresses if item.metadata and item.metadata.name]
        deployment_details = []
        for deployment in deployments:
            desired = int(deployment.spec.replicas or 0)
            available = int(deployment.status.available_replicas or 0)
            unavailable = int(deployment.status.unavailable_replicas or 0)
            is_healthy = desired == available and unavailable == 0
            deployments_total += 1
            healthy += int(is_healthy)
            unhealthy += int(not is_healthy)
            deployment_details.append({"name": deployment.metadata.name, "desired": desired, "available": available, "unavailable": unavailable, "status": "Healthy" if is_healthy else "Warning"})
        services_total += len(service_names)
        ingresses_total += len(ingress_names)
        rows.append({"name": namespace, "services": len(service_names), "ingresses": len(ingress_names), "deployments": len(deployment_details), "service_names": service_names, "ingress_names": ingress_names, "deployment_details": deployment_details})

    return {
        "name": LOCAL_KUBERNETES_TARGET,
        "mode": "Direct service account",
        "status": "Healthy",
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "age_minutes": 0,
        "namespaces": len(rows),
        "services": services_total,
        "ingresses": ingresses_total,
        "deployments": deployments_total,
        "deployments_healthy": healthy,
        "deployments_unhealthy": unhealthy,
        "namespace_details": rows,
        "persistent_volumes": pv_rows,
        "storage": storage,
        "source": "Live in-cluster Kubernetes API",
    }


def build_monitoring_summary(days: int = 1) -> dict[str, Any]:
    summary = build_stored_summary()
    try:
        local = _live_local_cluster()
        clusters = [row for row in summary.get("clusters", []) if row.get("name") != LOCAL_KUBERNETES_TARGET]
        summary["clusters"] = [local, *clusters]
    except Exception as exc:
        logger.exception("Unable to collect live local Kubernetes monitoring data")
        summary["kubernetes_live_error"] = str(exc)

    try:
        live = _live_pipeline_metrics(days)
        summary["live_pipeline_metrics"] = live
        summary["pipeline_metrics"] = {
            "running": live["running"],
            "queued": live["queued"],
            "build_created": live["builds_completed"],
            "release_created": live["classic"]["completed"],
            "build_failed": live["builds_failed"],
            "release_failed": live["classic"]["failed"],
            "builds_completed": live["builds_completed"],
            "builds_succeeded": live["builds_succeeded"],
            "manual_builds": 0,
            "yaml_builds": live["yaml"]["completed"],
            "deployments_completed": live["classic"]["completed"] + live["yaml_deployments"]["completed"],
            "deployments_running": live["classic"]["running"] + live["yaml_deployments"]["running"],
        }
        for card in summary.get("cards", []):
            if card.get("key") == "pipelines":
                card.update(value=live["running"], detail=f"{live['queued']} queued · {live['builds_completed']} completed")
            elif card.get("key") == "builds":
                card.update(value=live["builds_completed"], label="Build Runs Completed", detail=f"{live['builds_succeeded']} succeeded · {live['builds_failed']} failed")
            elif card.get("key") == "releases":
                total_completed = live["classic"]["completed"] + live["yaml_deployments"]["completed"]
                total_running = live["classic"]["running"] + live["yaml_deployments"]["running"]
                total_pending = live["classic"]["pending"] + live["yaml_deployments"]["queued"]
                card.update(value=total_completed, label="Deployment Pipelines Completed", detail=f"{total_running} running · {total_pending} pending")
    except Exception as exc:
        logger.exception("Unable to collect live Titan Azure DevOps monitoring data")
        summary["pipeline_live_error"] = str(exc)

    summary["generated_at"] = datetime.now(timezone.utc).isoformat()
    return summary
