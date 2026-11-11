from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from kubernetes import client
from kubernetes.client.rest import ApiException
from pydantic import BaseModel, Field

from .auth import current_user, require_devops
from .cluster_inventory import inventory_namespaces
from .config import (
    KUBERNETES_INVENTORY_FILE,
    KUBERNETES_LOG_ACCESS_FILE,
    KUBERNETES_LOG_BROKER_DIR,
    KUBERNETES_LOG_BROKER_SECRET,
    KUBERNETES_LOG_MAX_BYTES,
    KUBERNETES_LOG_REMOTE_TIMEOUT_SECONDS,
    KUBERNETES_TARGETS,
    LOCAL_KUBERNETES_TARGET,
)
from .kubernetes_ops import load_k8s
from .logging_config import get_logger
from .models import UserContext

router = APIRouter(prefix="/kubernetes-logs", tags=["kubernetes-logs"])
logger = get_logger("kubernetes-logs")
ACCESS_LOCK = threading.RLock()

WINDOW_SECONDS: dict[str, int] = {
    "live": 120,
    "5m": 5 * 60,
    "10m": 10 * 60,
    "30m": 30 * 60,
    "1h": 60 * 60,
    "5h": 5 * 60 * 60,
    "12h": 12 * 60 * 60,
    "24h": 24 * 60 * 60,
    "3d": 3 * 24 * 60 * 60,
    "7d": 7 * 24 * 60 * 60,
}
SAFE_NAME = re.compile(r"^[a-z0-9](?:[a-z0-9._-]*[a-z0-9])?$", re.IGNORECASE)


class LogAccessUpdate(BaseModel):
    namespaces: list[str] = Field(default_factory=list, max_length=1000)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_cluster(cluster: str) -> str:
    value = cluster.strip()
    if value not in KUBERNETES_TARGETS:
        raise HTTPException(status_code=404, detail=f"Unknown Kubernetes target: {value}")
    return value


def _validate_name(value: str, label: str) -> str:
    cleaned = value.strip()
    if not cleaned or len(cleaned) > 253 or not SAFE_NAME.fullmatch(cleaned):
        raise HTTPException(status_code=400, detail=f"Invalid {label}")
    return cleaned


def _load_access() -> dict[str, list[str]]:
    with ACCESS_LOCK:
        if not KUBERNETES_LOG_ACCESS_FILE.exists():
            return {}
        try:
            payload = json.loads(KUBERNETES_LOG_ACCESS_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.exception("Unable to read Kubernetes log namespace access file=%s", KUBERNETES_LOG_ACCESS_FILE)
            return {}
        clusters = payload.get("clusters") if isinstance(payload, dict) else {}
        if not isinstance(clusters, dict):
            return {}
        result: dict[str, list[str]] = {}
        for cluster, namespaces in clusters.items():
            if isinstance(namespaces, list):
                result[str(cluster)] = sorted({str(item).strip() for item in namespaces if str(item).strip()})
        return result


def _save_access(access: dict[str, list[str]], actor: str) -> None:
    with ACCESS_LOCK:
        KUBERNETES_LOG_ACCESS_FILE.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "updated_at": _utc_now(),
            "updated_by": actor,
            "clusters": {cluster: sorted(set(namespaces)) for cluster, namespaces in sorted(access.items())},
        }
        temporary = KUBERNETES_LOG_ACCESS_FILE.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temporary.replace(KUBERNETES_LOG_ACCESS_FILE)


def _all_direct_namespaces() -> list[str]:
    try:
        load_k8s()
        return sorted(
            item.metadata.name
            for item in client.CoreV1Api().list_namespace().items
            if item.metadata and item.metadata.name
        )
    except ApiException as exc:
        raise HTTPException(
            status_code=exc.status or 500,
            detail=f"Unable to list local cluster namespaces: {exc.reason}",
        ) from exc


def _available_namespaces(cluster: str) -> list[str]:
    if cluster == LOCAL_KUBERNETES_TARGET:
        return _all_direct_namespaces()
    try:
        return inventory_namespaces(cluster)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Namespace inventory is unavailable for {cluster}: {exc}",
        ) from exc


def _allowed_namespaces(cluster: str) -> list[str]:
    configured = set(_load_access().get(cluster, []))
    if not configured:
        return []
    available = set(_available_namespaces(cluster))
    return sorted(configured.intersection(available))


def _require_allowed_namespace(cluster: str, namespace: str) -> tuple[str, str]:
    cluster = _validate_cluster(cluster)
    namespace = _validate_name(namespace, "namespace")
    if namespace not in _allowed_namespaces(cluster):
        raise HTTPException(status_code=403, detail="Kubernetes logs are not enabled for this namespace")
    return cluster, namespace


def _broker_root() -> Path:
    if KUBERNETES_LOG_BROKER_DIR is not None:
        return KUBERNETES_LOG_BROKER_DIR
    inventory_path = KUBERNETES_INVENTORY_FILE
    base = inventory_path if inventory_path.is_dir() else inventory_path.parent
    return base / "kubernetes-log-broker"


def _request_signature(payload: dict[str, Any]) -> str:
    if not KUBERNETES_LOG_BROKER_SECRET:
        raise HTTPException(
            status_code=503,
            detail="Remote Kubernetes log broker secret is not configured",
        )
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hmac.new(
        KUBERNETES_LOG_BROKER_SECRET.encode("utf-8"),
        canonical,
        hashlib.sha256,
    ).hexdigest()


def _remote_request(cluster: str, action: str, payload: dict[str, Any]) -> dict[str, Any]:
    root = _broker_root()
    requests_dir = root / "requests"
    responses_dir = root / "responses"
    try:
        requests_dir.mkdir(parents=True, exist_ok=True)
        responses_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Remote log broker storage is unavailable: {exc}",
        ) from exc

    request_id = uuid.uuid4().hex
    unsigned = {
        "id": request_id,
        "cluster": cluster,
        "action": action,
        "created_at": _utc_now(),
        "payload": payload,
    }
    request_payload = {**unsigned, "signature": _request_signature(unsigned)}
    request_path = requests_dir / f"{request_id}.json"
    temporary_path = requests_dir / f".{request_id}.tmp"
    response_path = responses_dir / f"{request_id}.json"

    try:
        temporary_path.write_text(json.dumps(request_payload), encoding="utf-8")
        temporary_path.replace(request_path)
    except OSError as exc:
        raise HTTPException(status_code=503, detail=f"Unable to submit remote log request: {exc}") from exc

    logger.info(
        "Remote Kubernetes log request submitted id=%s cluster=%s action=%s path=%s",
        request_id,
        cluster,
        action,
        request_path,
    )

    deadline = time.monotonic() + KUBERNETES_LOG_REMOTE_TIMEOUT_SECONDS
    try:
        while time.monotonic() < deadline:
            if response_path.exists():
                try:
                    response = json.loads(response_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as exc:
                    raise HTTPException(status_code=502, detail=f"Remote log agent returned an invalid response: {exc}") from exc
                response_signature = str(response.get("signature") or "")
                unsigned_response = {key: value for key, value in response.items() if key != "signature"}
                expected_response_signature = _request_signature(unsigned_response)
                if not response_signature or not hmac.compare_digest(response_signature, expected_response_signature):
                    raise HTTPException(status_code=502, detail="Remote log agent response signature is invalid")
                if not response.get("ok"):
                    raise HTTPException(status_code=502, detail=str(response.get("error") or "Remote log agent failed"))
                data = response.get("data")
                logger.info(
                    "Remote Kubernetes log response received id=%s cluster=%s action=%s",
                    request_id,
                    cluster,
                    action,
                )
                return data if isinstance(data, dict) else {}
            time.sleep(0.25)
    finally:
        for path in (request_path, temporary_path, response_path):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass

    logger.warning(
        "Remote Kubernetes log request timed out id=%s cluster=%s action=%s broker=%s timeout_seconds=%s",
        request_id,
        cluster,
        action,
        root,
        KUBERNETES_LOG_REMOTE_TIMEOUT_SECONDS,
    )
    raise HTTPException(
        status_code=504,
        detail=f"Timed out waiting for the Kubernetes log agent in {cluster}",
    )


def _pod_row(pod: client.V1Pod) -> dict[str, Any]:
    statuses = pod.status.container_statuses or []
    containers = [item.name for item in pod.spec.containers or []]
    restarts = sum(int(item.restart_count or 0) for item in statuses)
    ready = bool(statuses) and all(bool(item.ready) for item in statuses)
    return {
        "name": pod.metadata.name,
        "phase": pod.status.phase or "Unknown",
        "containers": containers,
        "restarts": restarts,
        "ready": ready,
        "created_at": pod.metadata.creation_timestamp.isoformat() if pod.metadata.creation_timestamp else None,
        "node": pod.spec.node_name or "",
    }


def _direct_pods(namespace: str) -> list[dict[str, Any]]:
    try:
        load_k8s()
        pods = client.CoreV1Api().list_namespaced_pod(namespace).items
    except ApiException as exc:
        raise HTTPException(status_code=exc.status or 500, detail=f"Unable to list pods: {exc.reason}") from exc
    rows = [_pod_row(pod) for pod in pods if pod.metadata and pod.metadata.name]
    return sorted(rows, key=lambda item: (str(item.get("created_at") or ""), item["name"]), reverse=True)


def _direct_log_segments(
    namespace: str,
    pod: str,
    container: str,
    since_seconds: int,
    include_previous: bool,
    live: bool,
) -> dict[str, Any]:
    load_k8s()
    api = client.CoreV1Api()
    try:
        selected = api.read_namespaced_pod(pod, namespace)
    except ApiException as exc:
        raise HTTPException(status_code=exc.status or 500, detail=f"Unable to read pod: {exc.reason}") from exc

    containers = [item.name for item in selected.spec.containers or []]
    if container not in containers:
        raise HTTPException(status_code=400, detail="Selected container does not exist in the pod")

    kwargs = {
        "name": pod,
        "namespace": namespace,
        "container": container,
        "timestamps": True,
        "since_seconds": since_seconds,
        "tail_lines": 1000 if live else None,
    }
    try:
        current = api.read_namespaced_pod_log(**kwargs) or ""
    except ApiException as exc:
        raise HTTPException(status_code=exc.status or 500, detail=f"Unable to read pod logs: {exc.reason}") from exc

    segments = [{"source": "current", "content": current}]
    if include_previous:
        try:
            previous = api.read_namespaced_pod_log(**kwargs, previous=True) or ""
            if previous.strip():
                segments.insert(0, {"source": "previous", "content": previous})
        except ApiException as exc:
            if exc.status not in {400, 404}:
                logger.warning(
                    "Previous container logs unavailable namespace=%s pod=%s container=%s status=%s",
                    namespace,
                    pod,
                    container,
                    exc.status,
                )

    return {"segments": segments, "truncated": False}


def _parse_timestamped_line(line: str) -> tuple[str | None, str]:
    if " " not in line:
        return None, line
    first, rest = line.split(" ", 1)
    if "T" in first and (first.endswith("Z") or "+" in first or first.count(":") >= 2):
        return first, rest
    return None, line


def _format_segments(
    cluster: str,
    namespace: str,
    pod: str,
    container: str,
    segments: list[dict[str, Any]],
    output_format: Literal["standard", "text", "json"],
) -> tuple[str, str]:
    records: list[dict[str, Any]] = []
    standard_lines: list[str] = []
    text_lines: list[str] = []

    for segment in segments:
        source = str(segment.get("source") or "current")
        content = str(segment.get("content") or "")
        for raw_line in content.splitlines():
            timestamp, message = _parse_timestamped_line(raw_line)
            standard_lines.append(f"[{source}] {raw_line}")
            text_lines.append(message)
            record: dict[str, Any] = {
                "cluster": cluster,
                "namespace": namespace,
                "pod": pod,
                "container": container,
                "source": source,
                "timestamp": timestamp,
                "message": message,
            }
            try:
                parsed = json.loads(message)
                if isinstance(parsed, (dict, list)):
                    record["payload"] = parsed
            except json.JSONDecodeError:
                pass
            records.append(record)

    if output_format == "json":
        return json.dumps(records, indent=2, ensure_ascii=False), "application/json"
    if output_format == "text":
        return "\n".join(text_lines) + ("\n" if text_lines else ""), "text/plain; charset=utf-8"
    return "\n".join(standard_lines) + ("\n" if standard_lines else ""), "text/plain; charset=utf-8"


def _trim_content(
    content: str,
    output_format: Literal["standard", "text", "json"],
) -> tuple[str, bool]:
    encoded = content.encode("utf-8")
    if len(encoded) <= KUBERNETES_LOG_MAX_BYTES:
        return content, False

    if output_format == "json":
        try:
            records = json.loads(content)
        except json.JSONDecodeError:
            records = []
        if isinstance(records, list):
            kept: list[Any] = []
            used = 2
            for record in reversed(records):
                serialized = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
                size = len(serialized.encode("utf-8")) + 2
                if kept and used + size > KUBERNETES_LOG_MAX_BYTES:
                    break
                if size > KUBERNETES_LOG_MAX_BYTES:
                    continue
                kept.append(record)
                used += size
            kept.reverse()
            return json.dumps(kept, indent=2, ensure_ascii=False), True

    tail = encoded[-KUBERNETES_LOG_MAX_BYTES :].decode("utf-8", errors="replace")
    return tail, True


def _query_logs(
    cluster: str,
    namespace: str,
    pod: str,
    container: str,
    window: str,
    output_format: Literal["standard", "text", "json"],
    include_previous: bool,
) -> dict[str, Any]:
    cluster, namespace = _require_allowed_namespace(cluster, namespace)
    pod = _validate_name(pod, "pod")
    container = _validate_name(container, "container")

    if window not in WINDOW_SECONDS:
        raise HTTPException(status_code=400, detail="Unsupported log time window")
    since_seconds = WINDOW_SECONDS[window]
    live = window == "live"

    if cluster == LOCAL_KUBERNETES_TARGET:
        result = _direct_log_segments(
            namespace,
            pod,
            container,
            since_seconds,
            include_previous,
            live,
        )
        source = "direct"
    else:
        result = _remote_request(
            cluster,
            "logs",
            {
                "namespace": namespace,
                "pod": pod,
                "container": container,
                "since_seconds": since_seconds,
                "include_previous": include_previous,
                "tail_lines": 1000 if live else None,
                "max_bytes": KUBERNETES_LOG_MAX_BYTES,
            },
        )
        source = "remote-agent"

    segments = result.get("segments") or []
    if not isinstance(segments, list):
        segments = []
    content, media_type = _format_segments(
        cluster,
        namespace,
        pod,
        container,
        segments,
        output_format,
    )
    content, backend_truncated = _trim_content(content, output_format)
    return {
        "content": content,
        "media_type": media_type,
        "format": output_format,
        "window": window,
        "source": source,
        "fetched_at": _utc_now(),
        "truncated": bool(result.get("truncated")) or backend_truncated,
        "line_count": len(content.splitlines()),
    }


@router.get("/clusters")
def list_log_clusters(_: UserContext = Depends(current_user)):
    access = _load_access()
    return [
        {
            "name": cluster,
            "mode": "direct" if cluster == LOCAL_KUBERNETES_TARGET else "remote-agent",
            "enabled_namespaces": len(access.get(cluster, [])),
        }
        for cluster in KUBERNETES_TARGETS
    ]


@router.get("/namespaces/{cluster}")
def list_log_namespaces(cluster: str, _: UserContext = Depends(current_user)):
    cluster = _validate_cluster(cluster)
    return _allowed_namespaces(cluster)


@router.get("/pods")
def list_log_pods(
    cluster: str = Query(...),
    namespace: str = Query(...),
    _: UserContext = Depends(current_user),
):
    cluster, namespace = _require_allowed_namespace(cluster, namespace)
    if cluster == LOCAL_KUBERNETES_TARGET:
        return _direct_pods(namespace)
    result = _remote_request(cluster, "pods", {"namespace": namespace})
    pods = result.get("pods") or []
    return pods if isinstance(pods, list) else []


@router.get("/logs")
def get_logs(
    cluster: str = Query(...),
    namespace: str = Query(...),
    pod: str = Query(...),
    container: str = Query(...),
    window: str = Query("live"),
    output_format: Literal["standard", "text", "json"] = Query("standard", alias="format"),
    include_previous: bool = Query(True),
    user: UserContext = Depends(current_user),
):
    result = _query_logs(
        cluster,
        namespace,
        pod,
        container,
        window,
        output_format,
        include_previous,
    )
    logger.info(
        "Kubernetes logs viewed user=%s role=%s cluster=%s namespace=%s pod=%s container=%s window=%s format=%s lines=%s",
        user.username,
        user.role,
        cluster,
        namespace,
        pod,
        container,
        window,
        output_format,
        result["line_count"],
    )
    return {key: value for key, value in result.items() if key != "media_type"}


@router.get("/download")
def download_logs(
    cluster: str = Query(...),
    namespace: str = Query(...),
    pod: str = Query(...),
    container: str = Query(...),
    window: str = Query("live"),
    output_format: Literal["standard", "text", "json"] = Query("standard", alias="format"),
    include_previous: bool = Query(True),
    user: UserContext = Depends(current_user),
):
    result = _query_logs(
        cluster,
        namespace,
        pod,
        container,
        window,
        output_format,
        include_previous,
    )
    extension = "json" if output_format == "json" else ("txt" if output_format == "text" else "log")
    filename = f"{cluster}_{namespace}_{pod}_{container}_{window}.{extension}"
    logger.info(
        "Kubernetes logs downloaded user=%s role=%s cluster=%s namespace=%s pod=%s container=%s window=%s format=%s",
        user.username,
        user.role,
        cluster,
        namespace,
        pod,
        container,
        window,
        output_format,
    )
    return Response(
        content=result["content"],
        media_type=result["media_type"],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/access")
def get_log_access(_: UserContext = Depends(require_devops)):
    return {"clusters": _load_access()}


@router.get("/admin/namespaces/{cluster}")
def list_manageable_namespaces(cluster: str, _: UserContext = Depends(require_devops)):
    cluster = _validate_cluster(cluster)
    return _available_namespaces(cluster)


@router.put("/access/{cluster}")
def update_log_access(
    cluster: str,
    payload: LogAccessUpdate,
    user: UserContext = Depends(require_devops),
):
    cluster = _validate_cluster(cluster)
    available = set(_available_namespaces(cluster))
    requested = sorted({_validate_name(item, "namespace") for item in payload.namespaces})
    unknown = [item for item in requested if item not in available]
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown namespaces for {cluster}: {', '.join(unknown[:10])}",
        )

    access = _load_access()
    access[cluster] = requested
    _save_access(access, user.username)
    logger.info(
        "Kubernetes log namespace access updated actor=%s cluster=%s namespaces=%s",
        user.username,
        cluster,
        len(requested),
    )
    return {"cluster": cluster, "namespaces": requested}
