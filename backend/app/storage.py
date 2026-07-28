from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

from .config import DATA_FILE


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def timeline_event(action: str, actor: str, detail: str = "") -> dict[str, str]:
    return {"at": now_iso(), "action": action, "actor": actor, "detail": detail}


def normalize_stored_request(item: dict[str, Any]) -> dict[str, Any]:
    item.setdefault("application_type", "H2H")
    item.setdefault("reference_repository_name", "")
    item.setdefault("reference_branch", "")
    item.setdefault("ingress_name", None)
    item.pop("application_name", None)
    return item


def read_requests() -> list[dict[str, Any]]:
    if not DATA_FILE.exists():
        return []
    try:
        items = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        return [normalize_stored_request(item) for item in items]
    except (json.JSONDecodeError, OSError):
        return []


def write_requests(items: list[dict[str, Any]]) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(items, indent=2), encoding="utf-8")


def find_request(items: list[dict[str, Any]], request_id: str) -> tuple[int, dict[str, Any]]:
    for index, item in enumerate(items):
        if item.get("id") == request_id:
            return index, item
    raise HTTPException(status_code=404, detail="Pipeline request not found")
