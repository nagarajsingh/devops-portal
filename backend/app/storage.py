from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

from .config import DATA_FILE, LOCAL_KUBERNETES_TARGET
from .logging_config import get_logger

logger = get_logger("storage")
_storage_lock = threading.RLock()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def timeline_event(action: str, actor: str, detail: str = "") -> dict[str, str]:
    return {"at": now_iso(), "action": action, "actor": actor, "detail": detail}


def normalize_stored_request(item: dict[str, Any]) -> dict[str, Any]:
    item.setdefault("application_type", "H2H")
    item.setdefault("reference_repository_name", "")
    item.setdefault("reference_branch", "")
    item.setdefault("ingress_name", None)
    item.setdefault("target_cluster", LOCAL_KUBERNETES_TARGET)
    item.setdefault("provisioning", {})
    item.setdefault("timeline", [])
    item.pop("application_name", None)
    item.pop("azure_devops_pat", None)
    return item


def read_requests() -> list[dict[str, Any]]:
    with _storage_lock:
        if not DATA_FILE.exists():
            return []
        try:
            items = json.loads(DATA_FILE.read_text(encoding="utf-8"))
            return [normalize_stored_request(item) for item in items]
        except (json.JSONDecodeError, OSError):
            logger.exception("Unable to read request storage file=%s", DATA_FILE)
            return []


def write_requests(items: list[dict[str, Any]]) -> None:
    with _storage_lock:
        DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        temporary = DATA_FILE.with_suffix(f"{DATA_FILE.suffix}.tmp")
        payload = json.dumps(items, indent=2)
        try:
            temporary.write_text(payload, encoding="utf-8")
            os.replace(temporary, DATA_FILE)
        except OSError:
            logger.exception("Unable to write request storage file=%s", DATA_FILE)
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise


def find_request(items: list[dict[str, Any]], request_id: str) -> tuple[int, dict[str, Any]]:
    for index, item in enumerate(items):
        if item.get("id") == request_id:
            return index, item
    raise HTTPException(status_code=404, detail="Pipeline request not found")
