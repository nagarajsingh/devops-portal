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
        if target == LOCAL_KUBERNETES_TARGET:
            cluster_payload = inventory_clusters.get(target) or {}
        else:
            cluster_payload = inventory_clusters.get(target) or {}

        namespaces = cluster_payload.get("namespaces") or {}
        namespace_count = len(namespaces)
        service_count = sum(len((value or {}).get("services") or []) for value in namespaces.values())
        ingress_count = sum(len((value or {}).get("ingresses") or []) for value in namespaces.values())
        collected_at = cluster_payload.get("collected_at") or inventory.get("generated_at")
        age_minutes = _age_minutes(collected_at)
        status = _inventory_status(age_minutes)

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
            }
        )

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

    cards = [
        {"label": "Configured Clusters", "value": len(KUBERNETES_TARGETS), "tone": "primary"},
        {"label": "Namespaces", "value": total_namespaces, "tone": "neutral"},
        {"label": "Services", "value": total_services, "tone": "healthy"},
        {"label": "Ingresses", "value": total_ingresses, "tone": "neutral"},
        {"label": "Pending Approval", "value": status_counts.get("Pending Approval", 0), "tone": "warning"},
        {"label": "Provisioning", "value": status_counts.get("In Progress", 0) + status_counts.get("Provisioning", 0), "tone": "progress"},
        {"label": "Failed / Partial", "value": sum(status_counts.get(name, 0) for name in failed_statuses), "tone": "danger"},
        {"label": "Completed", "value": status_counts.get("Completed", 0) + status_counts.get("Closed", 0), "tone": "healthy"},
    ]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inventory_generated_at": inventory.get("generated_at"),
        "cards": cards,
        "clusters": clusters,
        "request_statuses": dict(sorted(status_counts.items())),
        "recent_failures": recent_failures[:10],
    }
