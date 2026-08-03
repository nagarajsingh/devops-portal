from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

from ..cluster_inventory import read_inventory
from ..config import KUBERNETES_TARGETS, LOCAL_KUBERNETES_TARGET
from ..storage import read_requests


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _age_minutes(value: Any) -> int | None:
    parsed = _parse_datetime(value)
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)
    return max(0, int(age.total_seconds() // 60))


def _inventory_status(age_minutes: int | None) -> str:
    if age_minutes is None:
        return "Missing"
    if age_minutes <= 10:
        return "Healthy"
    if age_minutes <= 30:
        return "Warning"
    return "Stale"


def _request_status_counts(items: list[dict[str, Any]]) -> Counter[str]:
    return Counter(str(item.get("status") or "Unknown") for item in items)


def _step(item: dict[str, Any], name: str) -> dict[str, Any]:
    value = (item.get("provisioning") or {}).get(name) or {}
    return value if isinstance(value, dict) else {}


def _step_status(item: dict[str, Any], name: str) -> str:
    return str(_step(item, name).get("status") or "Not Started")


def _completed(status: str) -> bool:
    return status in {"Completed", "Already Exists"}


def _running_request(item: dict[str, Any]) -> bool:
    return str(item.get("status") or "") in {"In Progress", "Provisioning"}


def build_monitoring_summary() -> dict[str, Any]:
    inventory = read_inventory()
    inventory_clusters = inventory.get("clusters") or {}
    requests = read_requests()
    status_counts = _request_status_counts(requests)

    clusters: list[dict[str, Any]] = []
    total_namespaces = 0
    total_services = 0
    total_ingresses = 0

    for target in KUBERNETES_TARGETS:
        cluster_payload = inventory_clusters.get(target) or {}
        namespaces = cluster_payload.get("namespaces") or {}
        namespace_rows = []
        service_count = 0
        ingress_count = 0

        for namespace_name, namespace_payload in sorted(namespaces.items()):
            namespace_payload = namespace_payload or {}
            services = namespace_payload.get("services") or []
            ingresses = namespace_payload.get("ingresses") or []
            service_count += len(services)
            ingress_count += len(ingresses)
            namespace_rows.append(
                {
                    "name": namespace_name,
                    "services": len(services),
                    "ingresses": len(ingresses),
                    "service_names": [str(service.get("name")) for service in services if isinstance(service, dict) and service.get("name")],
                    "ingress_names": [str(name) for name in ingresses if name],
                }
            )

        collected_at = cluster_payload.get("collected_at") or inventory.get("generated_at")
        age_minutes = _age_minutes(collected_at)
        status = _inventory_status(age_minutes)
        namespace_count = len(namespace_rows)

        total_namespaces += namespace_count
        total_services += service_count
        total_ingresses += ingress_count

        clusters.append(
            {
                "name": target,
                "mode": "Direct" if target == LOCAL_KUBERNETES_TARGET else "Azure Pipeline",
                "status": status,
                "collected_at": collected_at,
                "age_minutes": age_minutes,
                "namespaces": namespace_count,
                "services": service_count,
                "ingresses": ingress_count,
                "namespace_details": namespace_rows,
            }
        )

    pipeline_created = sum(_completed(_step_status(item, "pipeline")) for item in requests)
    release_created = sum(_completed(_step_status(item, "release_pipeline")) for item in requests)
    pipeline_failed = sum(_step_status(item, "pipeline") == "Failed" for item in requests)
    release_failed = sum(_step_status(item, "release_pipeline") == "Failed" for item in requests)
    pipelines_running = sum(_running_request(item) and bool(item.get("setup_pipeline")) for item in requests)

    service_completed = sum(_completed(_step_status(item, "service")) for item in requests)
    ingress_completed = sum(_completed(_step_status(item, "ingress")) for item in requests)
    deployment_completed = sum(
        _completed(_step_status(item, "service")) and _completed(_step_status(item, "ingress"))
        for item in requests
    )
    remote_deployments = sum(
        deployment_completed_item
        for item in requests
        for deployment_completed_item in [
            _completed(_step_status(item, "service"))
            and _completed(_step_status(item, "ingress"))
            and str(item.get("target_cluster") or LOCAL_KUBERNETES_TARGET) != LOCAL_KUBERNETES_TARGET
        ]
    )
    direct_deployments = max(0, deployment_completed - remote_deployments)

    failed_statuses = {"Rejected", "Failed", "Partially Completed"}
    recent_failures = [
        {
            "id": item.get("id"),
            "repository": item.get("repository_name"),
            "application": item.get("application_type"),
            "status": item.get("status"),
            "updated_at": item.get("updated_at") or item.get("created_at"),
            "detail": item.get("review_comments") or item.get("closure_comment") or item.get("comments") or "",
        }
        for item in requests
        if item.get("status") in failed_statuses
    ]
    recent_failures.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)

    provisioning_rows = []
    for item in sorted(requests, key=lambda value: str(value.get("updated_at") or value.get("created_at") or ""), reverse=True)[:20]:
        provisioning_rows.append(
            {
                "id": item.get("id"),
                "repository": item.get("repository_name"),
                "application": item.get("application_type"),
                "target_cluster": item.get("target_cluster") or LOCAL_KUBERNETES_TARGET,
                "status": item.get("status"),
                "updated_at": item.get("updated_at") or item.get("created_at"),
                "pipeline_status": _step_status(item, "pipeline"),
                "release_status": _step_status(item, "release_pipeline"),
                "service_status": _step_status(item, "service"),
                "ingress_status": _step_status(item, "ingress"),
            }
        )

    cards = [
        {"key": "kubernetes", "label": "Kubernetes Overview", "value": len(KUBERNETES_TARGETS), "detail": f"{total_namespaces} namespaces · {total_services} services", "tone": "primary"},
        {"key": "pipelines", "label": "Pipelines Running", "value": pipelines_running, "detail": f"{pipeline_created} build · {release_created} release created", "tone": "progress"},
        {"key": "deployments", "label": "Deployments Completed", "value": deployment_completed, "detail": f"{direct_deployments} direct · {remote_deployments} pipeline based", "tone": "healthy"},
        {"key": "provisioning", "label": "Provisioning Queue", "value": status_counts.get("Pending Approval", 0) + status_counts.get("Approved", 0) + status_counts.get("In Progress", 0) + status_counts.get("Provisioning", 0), "detail": f"{status_counts.get('Pending Approval', 0)} awaiting approval", "tone": "warning"},
        {"key": "builds", "label": "Build Pipelines Created", "value": pipeline_created, "detail": f"{pipeline_failed} failed setup", "tone": "neutral"},
        {"key": "releases", "label": "Release Pipelines Created", "value": release_created, "detail": f"{release_failed} failed setup", "tone": "neutral"},
        {"key": "networking", "label": "Services & Ingresses", "value": service_completed + ingress_completed, "detail": f"{service_completed} services · {ingress_completed} ingress updates", "tone": "primary"},
        {"key": "exceptions", "label": "Failed / Partial", "value": sum(status_counts.get(name, 0) for name in failed_statuses), "detail": "Requests needing attention", "tone": "danger"},
    ]

    pipeline_metrics = {
        "running": pipelines_running,
        "build_created": pipeline_created,
        "release_created": release_created,
        "build_failed": pipeline_failed,
        "release_failed": release_failed,
    }
    deployment_metrics = {
        "completed": deployment_completed,
        "direct": direct_deployments,
        "pipeline_based": remote_deployments,
        "services_completed": service_completed,
        "ingresses_completed": ingress_completed,
    }
    provisioning_metrics = {
        "pending_approval": status_counts.get("Pending Approval", 0),
        "approved": status_counts.get("Approved", 0),
        "running": status_counts.get("In Progress", 0) + status_counts.get("Provisioning", 0),
        "completed": status_counts.get("Completed", 0) + status_counts.get("Closed", 0),
        "failed_partial": sum(status_counts.get(name, 0) for name in failed_statuses),
    }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inventory_generated_at": inventory.get("generated_at"),
        "cards": cards,
        "clusters": clusters,
        "pipeline_metrics": pipeline_metrics,
        "deployment_metrics": deployment_metrics,
        "provisioning_metrics": provisioning_metrics,
        "request_statuses": dict(sorted(status_counts.items())),
        "provisioning_activity": provisioning_rows,
        "recent_failures": recent_failures[:10],
    }
