from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

from kubernetes import client

from ..config import (
    AZDO_ORG,
    AZDO_PROJECT,
    KUBERNETES_INVENTORY_PAT,
    LOCAL_KUBERNETES_TARGET,
    NAMESPACE_ALLOWLIST,
)
from ..kubernetes_ops import load_k8s
from ..logging_config import get_logger
from .service import build_monitoring_summary as build_stored_summary

logger = get_logger("monitoring-live")


def _request_json(url: str) -> dict[str, Any]:
    if not KUBERNETES_INVENTORY_PAT:
        raise RuntimeError("KUBERNETES_INVENTORY_PAT is not configured")
    token = base64.b64encode(f":{KUBERNETES_INVENTORY_PAT}".encode()).decode()
    request = urllib.request.Request(
        url,
        headers={"Authorization": f"Basic {token}", "Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8", errors="replace") or "{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Azure DevOps returned HTTP {exc.code}: {detail[:300]}") from exc


def _azdo_url(path: str, release: bool = False) -> str:
    host = "vsrm.dev.azure.com" if release else "dev.azure.com"
    return (
        f"https://{host}/{urllib.parse.quote(AZDO_ORG)}/"
        f"{urllib.parse.quote(AZDO_PROJECT)}/{path}"
    )


def _live_pipeline_metrics() -> dict[str, Any]:
    if not AZDO_ORG or not AZDO_PROJECT:
        raise RuntimeError("AZURE_DEVOPS_ORGANIZATION and AZURE_DEVOPS_PROJECT are required")

    definitions = _request_json(_azdo_url("_apis/build/definitions?$top=10000&api-version=7.1"))
    builds = _request_json(
        _azdo_url(
            "_apis/build/builds?queryOrder=queueTimeDescending&$top=200&api-version=7.1"
        )
    )
    build_rows = builds.get("value") or []
    running = sum(str(row.get("status") or "").lower() in {"inprogress", "notstarted", "postponed"} for row in build_rows)
    completed = sum(str(row.get("status") or "").lower() == "completed" for row in build_rows)
    succeeded = sum(str(row.get("result") or "").lower() in {"succeeded", "partiallysucceeded"} for row in build_rows)
    failed = sum(str(row.get("result") or "").lower() in {"failed", "canceled"} for row in build_rows)
    manual_builds = sum(str(row.get("reason") or "").lower() == "manual" for row in build_rows)
    yaml_builds = sum(str(row.get("reason") or "").lower() != "manual" for row in build_rows)

    release_definitions = 0
    deployments_completed = 0
    deployments_running = 0
    deployments_failed = 0
    try:
        release_defs = _request_json(_azdo_url("_apis/release/definitions?$top=10000&api-version=7.1", release=True))
        release_definitions = int(release_defs.get("count") or len(release_defs.get("value") or []))
        deployments = _request_json(_azdo_url("_apis/release/deployments?$top=200&queryOrder=descending&api-version=7.1", release=True))
        deployment_rows = deployments.get("value") or []
        deployments_completed = sum(str(row.get("deploymentStatus") or "").lower() == "succeeded" for row in deployment_rows)
        deployments_running = sum(str(row.get("deploymentStatus") or "").lower() in {"inprogress", "queued", "scheduled"} for row in deployment_rows)
        deployments_failed = sum(str(row.get("deploymentStatus") or "").lower() in {"failed", "canceled", "rejected"} for row in deployment_rows)
    except Exception:
        logger.exception("Unable to load live classic release data; build data remains available")

    recent = [
        {
            "id": row.get("id"),
            "name": (row.get("definition") or {}).get("name") or row.get("buildNumber"),
            "build_number": row.get("buildNumber"),
            "status": row.get("status"),
            "result": row.get("result"),
            "reason": row.get("reason"),
            "queue_time": row.get("queueTime"),
            "finish_time": row.get("finishTime"),
            "requested_by": (row.get("requestedFor") or {}).get("displayName"),
            "url": ((row.get("_links") or {}).get("web") or {}).get("href"),
        }
        for row in build_rows[:20]
    ]

    return {
        "running": running,
        "definitions": int(definitions.get("count") or len(definitions.get("value") or [])),
        "builds_completed": completed,
        "builds_succeeded": succeeded,
        "builds_failed": failed,
        "manual_builds": manual_builds,
        "yaml_builds": yaml_builds,
        "release_definitions": release_definitions,
        "deployments_completed": deployments_completed,
        "deployments_running": deployments_running,
        "deployments_failed": deployments_failed,
        "recent_runs": recent,
        "source": "Titan live Azure DevOps API",
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }


def _live_local_cluster() -> dict[str, Any]:
    load_k8s()
    core = client.CoreV1Api()
    apps = client.AppsV1Api()
    networking = client.NetworkingV1Api()
    all_namespaces = [item.metadata.name for item in core.list_namespace().items if item.metadata and item.metadata.name]
    names = sorted(name for name in all_namespaces if not NAMESPACE_ALLOWLIST or name in NAMESPACE_ALLOWLIST)
    rows: list[dict[str, Any]] = []
    services_total = 0
    ingresses_total = 0
    deployments_total = 0
    deployments_available = 0
    deployments_unavailable = 0

    for namespace in names:
        services = core.list_namespaced_service(namespace).items
        ingresses = networking.list_namespaced_ingress(namespace).items
        deployments = apps.list_namespaced_deployment(namespace).items
        service_names = [item.metadata.name for item in services if item.metadata and item.metadata.name]
        ingress_names = [item.metadata.name for item in ingresses if item.metadata and item.metadata.name]
        deployment_rows = []
        for deployment in deployments:
            desired = int(deployment.spec.replicas or 0)
            available = int(deployment.status.available_replicas or 0)
            unavailable = int(deployment.status.unavailable_replicas or 0)
            deployments_total += 1
            deployments_available += 1 if desired == available and unavailable == 0 else 0
            deployments_unavailable += 1 if desired != available or unavailable > 0 else 0
            deployment_rows.append({
                "name": deployment.metadata.name,
                "desired": desired,
                "available": available,
                "unavailable": unavailable,
                "status": "Healthy" if desired == available and unavailable == 0 else "Warning",
            })
        services_total += len(service_names)
        ingresses_total += len(ingress_names)
        rows.append({
            "name": namespace,
            "services": len(service_names),
            "ingresses": len(ingress_names),
            "deployments": len(deployment_rows),
            "service_names": service_names,
            "ingress_names": ingress_names,
            "deployment_details": deployment_rows,
        })

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
        "deployments_healthy": deployments_available,
        "deployments_unhealthy": deployments_unavailable,
        "namespace_details": rows,
        "source": "Live in-cluster Kubernetes API",
    }


def build_monitoring_summary() -> dict[str, Any]:
    summary = build_stored_summary()

    try:
        local = _live_local_cluster()
        clusters = [row for row in summary.get("clusters", []) if row.get("name") != LOCAL_KUBERNETES_TARGET]
        summary["clusters"] = [local, *clusters]
    except Exception as exc:
        logger.exception("Unable to collect live local Kubernetes monitoring data")
        summary["kubernetes_live_error"] = str(exc)

    try:
        live = _live_pipeline_metrics()
        summary["live_pipeline_metrics"] = live
        summary["pipeline_metrics"] = {
            "running": live["running"],
            "build_created": live["definitions"],
            "release_created": live["release_definitions"],
            "build_failed": live["builds_failed"],
            "release_failed": live["deployments_failed"],
            "builds_completed": live["builds_completed"],
            "builds_succeeded": live["builds_succeeded"],
            "manual_builds": live["manual_builds"],
            "yaml_builds": live["yaml_builds"],
            "deployments_completed": live["deployments_completed"],
            "deployments_running": live["deployments_running"],
        }
        for card in summary.get("cards", []):
            if card.get("key") == "pipelines":
                card.update(value=live["running"], detail=f"{live['builds_completed']} completed · {live['definitions']} definitions")
            elif card.get("key") == "builds":
                card.update(value=live["builds_completed"], detail=f"{live['builds_succeeded']} succeeded · {live['builds_failed']} failed")
            elif card.get("key") == "releases":
                card.update(value=live["deployments_completed"], detail=f"{live['deployments_running']} running · {live['release_definitions']} definitions")
    except Exception as exc:
        logger.exception("Unable to collect live Titan Azure DevOps monitoring data")
        summary["pipeline_live_error"] = str(exc)

    summary["generated_at"] = datetime.now(timezone.utc).isoformat()
    return summary
