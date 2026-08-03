from __future__ import annotations

import base64
import io
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import (
    AZDO_ORG,
    AZDO_PROJECT,
    KUBERNETES_INVENTORY_ARTIFACT_NAME,
    KUBERNETES_INVENTORY_FILE,
    KUBERNETES_INVENTORY_PAT,
    KUBERNETES_INVENTORY_PIPELINE_ID,
    KUBERNETES_INVENTORY_REFRESH_SECONDS,
    LOCAL_KUBERNETES_TARGET,
)
from .logging_config import get_logger
from .models import ServiceOption

logger = get_logger("cluster-inventory")
_refresh_lock = threading.RLock()
_last_refresh_monotonic = 0.0
_last_downloaded_run_id: int | None = None
EMPTY_INVENTORY: dict[str, Any] = {"generated_at": None, "clusters": {}}
LOCAL_CLUSTER_FALLBACK = "mashreq-titan-non-prod"


def _azdo_json(path: str) -> tuple[int, dict[str, Any]]:
    if not AZDO_ORG or not AZDO_PROJECT or not KUBERNETES_INVENTORY_PAT:
        raise RuntimeError(
            "AZURE_DEVOPS_ORGANIZATION, AZURE_DEVOPS_PROJECT and "
            "KUBERNETES_INVENTORY_PAT must be configured"
        )

    url = (
        f"https://dev.azure.com/{urllib.parse.quote(AZDO_ORG)}/"
        f"{urllib.parse.quote(AZDO_PROJECT)}/{path}"
    )
    token = base64.b64encode(f":{KUBERNETES_INVENTORY_PAT}".encode()).decode()
    request = urllib.request.Request(
        url,
        method="GET",
        headers={"Authorization": f"Basic {token}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return response.status, json.loads(raw or "{}")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw or "{}")
        except json.JSONDecodeError:
            body = {"message": raw or f"Azure DevOps request failed with HTTP {exc.code}"}
        return exc.code, body


def _download_bytes(url: str) -> bytes:
    token = base64.b64encode(f":{KUBERNETES_INVENTORY_PAT}".encode()).decode()
    request = urllib.request.Request(
        url,
        method="GET",
        headers={"Authorization": f"Basic {token}"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def _latest_successful_run() -> dict[str, Any] | None:
    if KUBERNETES_INVENTORY_PIPELINE_ID <= 0:
        return None
    query = urllib.parse.urlencode(
        {
            "definitions": str(KUBERNETES_INVENTORY_PIPELINE_ID),
            "statusFilter": "completed",
            "resultFilter": "succeeded",
            "queryOrder": "finishTimeDescending",
            "$top": "1",
            "api-version": "7.1",
        }
    )
    code, body = _azdo_json(f"_apis/build/builds?{query}")
    if code != 200:
        raise RuntimeError(body.get("message", f"Unable to read inventory pipeline runs with HTTP {code}"))
    values = body.get("value") or []
    return values[0] if values else None


def _download_inventory(run_id: int) -> dict[str, Any]:
    query = urllib.parse.urlencode(
        {
            "artifactName": KUBERNETES_INVENTORY_ARTIFACT_NAME,
            "api-version": "7.1",
        }
    )
    code, body = _azdo_json(f"_apis/build/builds/{run_id}/artifacts?{query}")
    if code != 200:
        raise RuntimeError(body.get("message", f"Unable to read inventory artifact with HTTP {code}"))
    download_url = ((body.get("resource") or {}).get("downloadUrl") or "").strip()
    if not download_url:
        raise RuntimeError(
            f"Artifact {KUBERNETES_INVENTORY_ARTIFACT_NAME} does not contain a download URL"
        )

    archive_bytes = _download_bytes(download_url)
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        candidates = [name for name in archive.namelist() if name.endswith("cluster-inventory.json")]
        if not candidates:
            raise RuntimeError("cluster-inventory.json was not found in the pipeline artifact")
        payload = json.loads(archive.read(candidates[0]).decode("utf-8"))

    if not isinstance(payload.get("clusters"), dict):
        raise RuntimeError("Inventory artifact does not contain a valid clusters object")
    return payload


def _read_json_file(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else None
    except (OSError, json.JSONDecodeError):
        logger.exception("Unable to read Kubernetes inventory JSON file=%s", path)
        return None


def _file_timestamp(path: Path) -> str | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()
    except OSError:
        return None


def _read_inventory_directory(directory: Path) -> dict[str, Any]:
    clusters: dict[str, Any] = {}
    generated_at: str | None = None

    for path in sorted(directory.glob("*.json")):
        payload = _read_json_file(path)
        if not payload:
            continue

        payload_generated_at = payload.get("generated_at") or payload.get("collected_at") or _file_timestamp(path)
        if payload_generated_at and (generated_at is None or str(payload_generated_at) > generated_at):
            generated_at = str(payload_generated_at)

        combined_clusters = payload.get("clusters")
        if isinstance(combined_clusters, dict):
            for name, cluster in combined_clusters.items():
                if isinstance(cluster, dict):
                    clusters[str(name)] = cluster
            continue

        cluster_name = str(payload.get("cluster") or path.stem).strip()
        namespaces = payload.get("namespaces")
        if cluster_name and isinstance(namespaces, dict):
            clusters[cluster_name] = {
                "collected_at": payload.get("collected_at") or payload_generated_at,
                "namespaces": namespaces,
            }

    return {"generated_at": generated_at, "clusters": clusters}


def refresh_inventory(force: bool = False) -> dict[str, Any]:
    global _last_refresh_monotonic, _last_downloaded_run_id

    with _refresh_lock:
        now = time.monotonic()
        if not force and now - _last_refresh_monotonic < KUBERNETES_INVENTORY_REFRESH_SECONDS:
            return read_inventory()
        _last_refresh_monotonic = now

        if KUBERNETES_INVENTORY_FILE.is_dir():
            return read_inventory()

        if KUBERNETES_INVENTORY_PIPELINE_ID <= 0 or not KUBERNETES_INVENTORY_PAT:
            logger.info("Using Kubernetes inventory from configured NFS file or directory")
            return read_inventory()

        latest = _latest_successful_run()
        if not latest or not latest.get("id"):
            logger.warning("No successful Kubernetes inventory pipeline run was found")
            return read_inventory()

        run_id = int(latest["id"])
        if run_id == _last_downloaded_run_id and KUBERNETES_INVENTORY_FILE.exists():
            return read_inventory()

        inventory = _download_inventory(run_id)
        KUBERNETES_INVENTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        temporary = KUBERNETES_INVENTORY_FILE.with_suffix(".tmp")
        temporary.write_text(json.dumps(inventory, indent=2), encoding="utf-8")
        temporary.replace(KUBERNETES_INVENTORY_FILE)
        _last_downloaded_run_id = run_id
        logger.info(
            "Kubernetes inventory synchronized pipeline_id=%s run_id=%s clusters=%s",
            KUBERNETES_INVENTORY_PIPELINE_ID,
            run_id,
            len(inventory.get("clusters", {})),
        )
        return inventory


def read_inventory() -> dict[str, Any]:
    if not KUBERNETES_INVENTORY_FILE.exists():
        return dict(EMPTY_INVENTORY)

    if KUBERNETES_INVENTORY_FILE.is_dir():
        return _read_inventory_directory(KUBERNETES_INVENTORY_FILE)

    payload = _read_json_file(KUBERNETES_INVENTORY_FILE)
    if not payload:
        return dict(EMPTY_INVENTORY)

    if isinstance(payload.get("clusters"), dict):
        return payload

    cluster_name = str(payload.get("cluster") or KUBERNETES_INVENTORY_FILE.stem).strip()
    namespaces = payload.get("namespaces")
    if cluster_name and isinstance(namespaces, dict):
        return {
            "generated_at": payload.get("collected_at") or _file_timestamp(KUBERNETES_INVENTORY_FILE),
            "clusters": {
                cluster_name: {
                    "collected_at": payload.get("collected_at"),
                    "namespaces": namespaces,
                }
            },
        }

    logger.error("Kubernetes inventory does not contain clusters or a single-cluster payload file=%s", KUBERNETES_INVENTORY_FILE)
    return dict(EMPTY_INVENTORY)


def _cluster(target_cluster: str) -> dict[str, Any]:
    inventory = refresh_inventory()
    clusters = inventory.get("clusters") or {}
    cluster = clusters.get(target_cluster)

    if not isinstance(cluster, dict) and target_cluster == LOCAL_KUBERNETES_TARGET:
        cluster = clusters.get(LOCAL_CLUSTER_FALLBACK)

    if not isinstance(cluster, dict):
        raise RuntimeError(
            f"No inventory is available for Kubernetes target {target_cluster}. "
            f"Verify JSON files under {KUBERNETES_INVENTORY_FILE}."
        )
    return cluster


def inventory_namespaces(target_cluster: str) -> list[str]:
    namespaces = _cluster(target_cluster).get("namespaces") or {}
    return sorted(namespaces.keys())


def inventory_ingresses(target_cluster: str, namespace: str) -> list[str]:
    namespaces = _cluster(target_cluster).get("namespaces") or {}
    resource = namespaces.get(namespace) or {}
    return sorted(str(name) for name in resource.get("ingresses", []) if name)


def inventory_services(target_cluster: str, namespace: str) -> list[ServiceOption]:
    namespaces = _cluster(target_cluster).get("namespaces") or {}
    resource = namespaces.get(namespace) or {}
    return [
        ServiceOption(
            name=str(service.get("name")),
            ports=sorted({int(port) for port in service.get("ports", [])}),
        )
        for service in resource.get("services", [])
        if service.get("name")
    ]
