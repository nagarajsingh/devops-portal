from __future__ import annotations

import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

from docx import Document
from fastapi import HTTPException, UploadFile
from pypdf import PdfReader

from .azure_devops import azdo_request, find_pipeline_by_name

_DATA_FILE = Path(os.getenv("DEPLOYMENT_MANAGEMENT_FILE", "/app/data/deployment-management.json"))
_LOCK = threading.RLock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load() -> list[dict[str, Any]]:
    with _LOCK:
        if not _DATA_FILE.exists():
            return []
        try:
            value = json.loads(_DATA_FILE.read_text(encoding="utf-8"))
            return value if isinstance(value, list) else []
        except (OSError, json.JSONDecodeError):
            return []


def _save(rows: list[dict[str, Any]]) -> None:
    with _LOCK:
        _DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        temp = _DATA_FILE.with_suffix(".tmp")
        temp.write_text(json.dumps(rows, indent=2), encoding="utf-8")
        temp.replace(_DATA_FILE)


def _extract_text(name: str, raw: bytes) -> str:
    lowered = name.lower()
    if lowered.endswith(".pdf"):
        reader = PdfReader(BytesIO(raw))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    if lowered.endswith(".docx"):
        document = Document(BytesIO(raw))
        return "\n".join(paragraph.text for paragraph in document.paragraphs)
    if lowered.endswith((".txt", ".md")):
        return raw.decode("utf-8", errors="replace")
    raise HTTPException(status_code=400, detail="Supported release documents are PDF, DOCX, TXT and MD")


def _first_match(patterns: list[str], text: str) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        if match:
            return match.group(1).strip().strip(".,;:")
    return ""


def extract_release_document(upload: UploadFile, raw: bytes) -> dict[str, Any]:
    text = _extract_text(upload.filename or "release-document", raw)
    branch = _first_match([
        r"(?:source\s+)?branch\s*(?:name)?\s*[:=-]\s*([^\s,;]+)",
        r"\b((?:release|feature|hotfix|bugfix)/[A-Za-z0-9._/-]+)\b",
    ], text)
    application = _first_match([
        r"application\s*(?:name)?\s*[:=-]\s*([A-Za-z0-9._-]+)",
        r"service\s*(?:name)?\s*[:=-]\s*([A-Za-z0-9._-]+)",
    ], text)
    environment = _first_match([
        r"environment\s*[:=-]\s*([A-Za-z0-9_-]+)",
        r"\b(R2UAT|PREPRD|PPR|PROD|R2TRAIN|GOLD|SIT|UAT)\b",
    ], text).upper()
    war_files = sorted(set(re.findall(r"\b[\w.-]+\.war\b", text, flags=re.IGNORECASE)))
    jar_files = sorted(set(re.findall(r"\b[\w.-]+\.jar\b", text, flags=re.IGNORECASE)))
    return {
        "filename": upload.filename,
        "application": application,
        "branch_name": branch,
        "environment": environment,
        "war_files": war_files,
        "jar_files": jar_files,
        "text_preview": text[:4000],
        "confidence": {
            "application": "high" if application else "missing",
            "branch_name": "high" if branch else "missing",
            "environment": "high" if environment else "missing",
        },
    }


def create_deployment_request(payload: dict[str, Any], requested_by: str) -> dict[str, Any]:
    required = ["application", "branch_name", "environment", "app_owner"]
    missing = [field for field in required if not str(payload.get(field) or "").strip()]
    if missing:
        raise HTTPException(status_code=422, detail=f"Missing required fields: {', '.join(missing)}")
    now = _now()
    row = {
        "id": f"DM-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}",
        "status": "Pending App Owner Approval",
        "requested_by": requested_by,
        "created_at": now,
        "updated_at": now,
        "application": str(payload["application"]).strip(),
        "branch_name": str(payload["branch_name"]).strip(),
        "environment": str(payload["environment"]).strip().upper(),
        "app_owner": str(payload["app_owner"]).strip(),
        "repository": str(payload.get("repository") or payload["application"]).strip(),
        "target_branch": str(payload.get("target_branch") or "release/uat").strip(),
        "war_files": payload.get("war_files") or [],
        "jar_files": payload.get("jar_files") or [],
        "document_name": payload.get("document_name") or "",
        "steps": {
            "owner_approval": {"status": "Pending"},
            "devops_review": {"status": "Waiting"},
            "code_pull": {"status": "Waiting"},
            "pull_request": {"status": "Waiting"},
            "build": {"status": "Waiting"},
            "deployment": {"status": "Waiting"},
        },
        "timeline": [{"at": now, "action": "Submitted", "actor": requested_by}],
    }
    rows = _load()
    rows.insert(0, row)
    _save(rows)
    return row


def list_deployment_requests() -> list[dict[str, Any]]:
    return _load()


def update_action(request_id: str, action: str, actor: str, pat: str = "") -> dict[str, Any]:
    rows = _load()
    row = next((item for item in rows if item.get("id") == request_id), None)
    if not row:
        raise HTTPException(status_code=404, detail="Deployment request not found")
    now = _now()
    steps = row.setdefault("steps", {})
    if action == "owner-approve":
        row["status"] = "Awaiting DevOps"
        steps["owner_approval"] = {"status": "Approved", "actor": actor, "at": now}
    elif action == "owner-reject":
        row["status"] = "App Owner Rejected"
        steps["owner_approval"] = {"status": "Rejected", "actor": actor, "at": now}
    elif action == "trigger-code-pull":
        pipeline_name = os.getenv("CODE_PULL_PIPELINE_NAME", "code-pull-pipeline")
        pipeline = find_pipeline_by_name(pipeline_name, pat)
        if not pipeline:
            raise HTTPException(status_code=404, detail=f"Code-pull pipeline {pipeline_name} was not found")
        body = {
            "resources": {"repositories": {"self": {"refName": os.getenv("CODE_PULL_PIPELINE_REF", "refs/heads/master")}}},
            "templateParameters": {
                os.getenv("CODE_PULL_PARAM_APPLICATION", "APP"): row["application"],
                os.getenv("CODE_PULL_PARAM_BRANCH", "PROFINCH_BRANCH"): row["branch_name"],
                os.getenv("CODE_PULL_PARAM_LIST_ONLY", "LIST_ONLY"): False,
            },
        }
        code, run = azdo_request("POST", f"_apis/pipelines/{pipeline['id']}/runs?api-version=7.1", pat, body)
        if code not in (200, 201):
            raise HTTPException(status_code=502, detail=run.get("message", "Unable to trigger code-pull pipeline"))
        row["status"] = "Code Pull Running"
        steps["code_pull"] = {"status": "Running", "pipeline_id": pipeline["id"], "run_id": run.get("id"), "url": ((run.get("_links") or {}).get("web") or {}).get("href")}
    else:
        raise HTTPException(status_code=400, detail="Unsupported deployment action")
    row["updated_at"] = now
    row.setdefault("timeline", []).append({"at": now, "action": action, "actor": actor})
    _save(rows)
    return row
