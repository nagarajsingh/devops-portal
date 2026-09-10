from __future__ import annotations

import base64
import hashlib
import shlex
from datetime import datetime, timezone
from pathlib import PurePosixPath

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from kubernetes import client
from kubernetes.client.rest import ApiException
from kubernetes.stream import stream
from sqlalchemy import DateTime, Integer, String, Text, desc, select
from sqlalchemy.orm import Mapped, mapped_column

from .auth import require_devops
from .kubernetes_ops import cluster_namespaces, load_k8s
from .models import UserContext
from .user_store import Base, session_factory

router = APIRouter(prefix="/file-placement", tags=["file-placement"])

MAX_FILE_SIZE = 200 * 1024 * 1024
UPLOAD_CHUNK_SIZE = 768 * 1024


class FilePlacementAudit(Base):
    __tablename__ = "file_placement_audit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    user_role: Mapped[str] = mapped_column(String(32), nullable=False)
    file_name: Mapped[str] = mapped_column(String(512), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    namespace: Mapped[str] = mapped_column(String(253), nullable=False, index=True)
    pod_name: Mapped[str] = mapped_column(String(253), nullable=False)
    container_name: Mapped[str] = mapped_column(String(253), nullable=False)
    destination_path: Mapped[str] = mapped_column(String(2048), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True)


def _safe_filename(filename: str | None) -> str:
    value = (filename or "upload.bin").replace("\\", "/").rsplit("/", 1)[-1].strip()
    return value or "upload.bin"


def _validate_namespace(namespace: str) -> str:
    value = namespace.strip()
    if value not in cluster_namespaces():
        raise HTTPException(status_code=400, detail="Namespace is not allowed")
    return value


def _validate_destination_path(destination_path: str) -> str:
    value = destination_path.strip()
    if not value.startswith("/"):
        raise HTTPException(status_code=400, detail="Destination path must be an absolute path")
    if value == "/" or value.endswith("/"):
        raise HTTPException(status_code=400, detail="Destination path must include the destination filename")
    if "\x00" in value or "\n" in value or "\r" in value:
        raise HTTPException(status_code=400, detail="Destination path contains invalid characters")
    path = PurePosixPath(value)
    if ".." in path.parts:
        raise HTTPException(status_code=400, detail="Destination path cannot contain '..'")
    if len(value) > 2048:
        raise HTTPException(status_code=400, detail="Destination path is too long")
    return value


def _pod_and_container(namespace: str, pod_name: str, container_name: str | None) -> tuple[client.V1Pod, str]:
    try:
        load_k8s()
        pod = client.CoreV1Api().read_namespaced_pod(pod_name.strip(), namespace)
    except ApiException as exc:
        if exc.status == 404:
            raise HTTPException(status_code=404, detail="Pod not found") from exc
        raise HTTPException(status_code=exc.status or 500, detail=f"Unable to read pod: {exc.reason}") from exc

    if pod.status.phase != "Running":
        raise HTTPException(status_code=409, detail=f"Pod is not Running (current phase: {pod.status.phase})")

    containers = [item.name for item in pod.spec.containers or []]
    requested = (container_name or "").strip()
    if requested:
        if requested not in containers:
            raise HTTPException(status_code=400, detail="Selected container does not exist in the pod")
        return pod, requested
    if not containers:
        raise HTTPException(status_code=409, detail="Pod has no application containers")
    return pod, containers[0]


def _audit(
    user: UserContext,
    filename: str,
    size: int,
    sha256: str | None,
    namespace: str,
    pod_name: str,
    container_name: str,
    destination_path: str,
    status: str,
    detail: str | None = None,
) -> FilePlacementAudit:
    factory = session_factory()
    with factory() as db:
        record = FilePlacementAudit(
            user_email=user.username,
            user_role=user.role,
            file_name=filename,
            file_size=size,
            sha256=sha256,
            namespace=namespace,
            pod_name=pod_name,
            container_name=container_name,
            destination_path=destination_path,
            status=status,
            detail=(detail or "")[:4000] or None,
            created_at=datetime.now(timezone.utc),
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record


def _record_dict(record: FilePlacementAudit) -> dict:
    return {
        "id": record.id,
        "user_email": record.user_email,
        "user_role": record.user_role,
        "file_name": record.file_name,
        "file_size": record.file_size,
        "sha256": record.sha256,
        "namespace": record.namespace,
        "pod_name": record.pod_name,
        "container_name": record.container_name,
        "destination_path": record.destination_path,
        "status": record.status,
        "detail": record.detail,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }


@router.get("/namespaces")
def list_file_placement_namespaces(_: UserContext = Depends(require_devops)):
    return cluster_namespaces()


@router.get("/pods/{namespace}")
def list_file_placement_pods(namespace: str, _: UserContext = Depends(require_devops)):
    namespace = _validate_namespace(namespace)
    try:
        load_k8s()
        pods = client.CoreV1Api().list_namespaced_pod(namespace).items
    except ApiException as exc:
        raise HTTPException(status_code=exc.status or 500, detail=f"Unable to list pods: {exc.reason}") from exc
    return [
        {
            "name": pod.metadata.name,
            "phase": pod.status.phase,
            "containers": [container.name for container in pod.spec.containers or []],
        }
        for pod in pods
        if pod.metadata and pod.metadata.name and pod.status and pod.status.phase == "Running"
    ]


@router.get("/audit")
def list_file_placement_audit(limit: int = 25, _: UserContext = Depends(require_devops)):
    limit = min(max(limit, 1), 100)
    factory = session_factory()
    with factory() as db:
        records = list(db.scalars(select(FilePlacementAudit).order_by(desc(FilePlacementAudit.created_at)).limit(limit)).all())
        return [_record_dict(record) for record in records]


@router.post("/upload")
def upload_file_to_pod(
    namespace: str = Form(...),
    pod_name: str = Form(...),
    destination_path: str = Form(...),
    container_name: str = Form(""),
    upload: UploadFile = File(...),
    user: UserContext = Depends(require_devops),
):
    namespace = _validate_namespace(namespace)
    destination_path = _validate_destination_path(destination_path)
    filename = _safe_filename(upload.filename)
    _, selected_container = _pod_and_container(namespace, pod_name, container_name)

    if upload.size is not None and upload.size > MAX_FILE_SIZE:
        _audit(user, filename, upload.size, None, namespace, pod_name, selected_container, destination_path, "Rejected", "File exceeds 200 MB limit")
        raise HTTPException(status_code=413, detail="Maximum file size is 200 MB")

    target = shlex.quote(destination_path)
    parent = shlex.quote(str(PurePosixPath(destination_path).parent))
    temp_path = shlex.quote(f"{destination_path}.devops-portal-upload")
    remote_script = (
        "set -u; "
        "command -v base64 >/dev/null 2>&1 || { echo 'base64 utility is required in the target container' >&2; exit 46; }; "
        f"test -d {parent} || {{ echo 'Destination directory does not exist' >&2; exit 47; }}; "
        f": > {temp_path} || exit 48; "
        f"trap 'rm -f {temp_path}' EXIT; "
        "while IFS= read -r line; do "
        "case \"$line\" in "
        f"__DEVOPS_PORTAL_EOF__) mv -f {temp_path} {target} || exit 49; trap - EXIT; exit 0 ;; "
        "__DEVOPS_PORTAL_ABORT__) exit 50 ;; "
        f"*) printf '%s' \"$line\" | base64 -d >> {temp_path} || exit 51 ;; "
        "esac; done; exit 52"
    )

    load_k8s()
    api = client.CoreV1Api()
    ws = None
    size = 0
    digest = hashlib.sha256()
    stderr_parts: list[str] = []
    try:
        ws = stream(
            api.connect_get_namespaced_pod_exec,
            pod_name,
            namespace,
            command=["/bin/sh", "-c", remote_script],
            container=selected_container,
            stderr=True,
            stdin=True,
            stdout=True,
            tty=False,
            _preload_content=False,
        )
        while True:
            chunk = upload.file.read(UPLOAD_CHUNK_SIZE)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_FILE_SIZE:
                ws.write_stdin("__DEVOPS_PORTAL_ABORT__\n")
                raise HTTPException(status_code=413, detail="Maximum file size is 200 MB")
            digest.update(chunk)
            ws.write_stdin(base64.b64encode(chunk).decode("ascii") + "\n")
        ws.write_stdin("__DEVOPS_PORTAL_EOF__\n")

        while ws.is_open():
            ws.update(timeout=1)
            if ws.peek_stderr():
                stderr_parts.append(ws.read_stderr())
            if ws.peek_stdout():
                ws.read_stdout()

        return_code = ws.returncode
        if return_code not in (0, None):
            detail = "".join(stderr_parts).strip() or f"Target container returned exit code {return_code}"
            _audit(user, filename, size, digest.hexdigest(), namespace, pod_name, selected_container, destination_path, "Failed", detail)
            raise HTTPException(status_code=500, detail=f"File placement failed: {detail}")

        record = _audit(user, filename, size, digest.hexdigest(), namespace, pod_name, selected_container, destination_path, "Completed")
        return _record_dict(record)
    except HTTPException as exc:
        if exc.status_code == 413:
            _audit(user, filename, size, digest.hexdigest() if size else None, namespace, pod_name, selected_container, destination_path, "Rejected", "File exceeds 200 MB limit")
        raise
    except ApiException as exc:
        detail = f"Kubernetes exec failed: {exc.reason}"
        _audit(user, filename, size, digest.hexdigest() if size else None, namespace, pod_name, selected_container, destination_path, "Failed", detail)
        raise HTTPException(status_code=exc.status or 500, detail=detail) from exc
    except Exception as exc:
        detail = str(exc) or exc.__class__.__name__
        _audit(user, filename, size, digest.hexdigest() if size else None, namespace, pod_name, selected_container, destination_path, "Failed", detail)
        raise HTTPException(status_code=500, detail=f"File placement failed: {detail}") from exc
    finally:
        try:
            upload.file.close()
        except Exception:
            pass
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass
