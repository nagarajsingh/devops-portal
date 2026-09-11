from __future__ import annotations

from typing import Any

from . import deployment_management as dm


def normalize_collections_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep only Collections services that have a vendor image and a mapped build pipeline.

    Release documents can contain platform/base images such as nginx and JDK images. Those
    images are not application build inputs and must not appear in the Collections build review.
    """
    if str(payload.get("application_type") or "") != "Collections":
        return payload

    filtered: list[dict[str, Any]] = []
    for item in payload.get("collections_items") or []:
        vendor_image = str(item.get("vendor_image") or "").strip()
        pipeline_name = str(item.get("pipeline_name") or "").strip()
        if not vendor_image or not pipeline_name:
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
