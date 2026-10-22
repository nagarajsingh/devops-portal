from __future__ import annotations

from typing import Any

from . import deployment_management as dm


def normalize_collections_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep Collections application images while excluding obvious platform images.

    Known services receive their configured build-pipeline mapping during extraction.
    A newly introduced vt* service is intentionally retained even when no mapping exists
    yet so DevOps can review it and provide the pipeline name instead of silently losing
    the service from the extracted document.
    """
    if str(payload.get("application_type") or "") != "Collections":
        return payload

    filtered: list[dict[str, Any]] = []
    for item in payload.get("collections_items") or []:
        vendor_image = str(item.get("vendor_image") or "").strip()
        service = str(item.get("service") or "").strip().lower()
        if not vendor_image:
            continue

        # Collections application images consistently use vt* identifiers.
        # This still excludes platform/base images such as nginx/JDK images.
        if not service.startswith("vt"):
            continue

        filtered.append(item)

    payload["collections_items"] = filtered
    payload["container_images"] = [
        str(item.get("vendor_image") or "").strip()
        for item in filtered
        if str(item.get("vendor_image") or "").strip()
    ]
    return payload


def normalize_persisted_collections_request(request_id: str) -> dict[str, Any]:
    rows = dm._load()
    row = next((item for item in rows if str(item.get("id") or "") == request_id), None)
    if not row:
        return {}
    normalize_collections_payload(row)
    dm._save(rows)
    return row


def normalize_all_collections_requests() -> list[dict[str, Any]]:
    rows = dm._load()
    changed = False
    for row in rows:
        if str(row.get("application_type") or "") != "Collections":
            continue
        before_items = len(row.get("collections_items") or [])
        before_images = list(row.get("container_images") or [])
        normalize_collections_payload(row)
        if before_items != len(row.get("collections_items") or []) or before_images != list(row.get("container_images") or []):
            changed = True
    if changed:
        dm._save(rows)
    return rows
