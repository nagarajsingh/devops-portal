from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request

from .config import AZDO_ORG, AZDO_PROJECT
from .logging_config import get_logger

logger = get_logger("azure-devops")


def azdo_request(method: str, path: str, pat: str, payload: dict | None = None) -> tuple[int, dict]:
    if not AZDO_ORG or not AZDO_PROJECT or not pat.strip():
        raise RuntimeError("Azure DevOps organization, project and PAT are required")
    url = f"https://dev.azure.com/{urllib.parse.quote(AZDO_ORG)}/{urllib.parse.quote(AZDO_PROJECT)}/{path}"
    token = base64.b64encode(f":{pat.strip()}".encode()).decode()
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Authorization": f"Basic {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            raw = response.read().decode()
            try:
                body = json.loads(raw or "{}")
            except json.JSONDecodeError:
                body = {"content": raw}
            return response.status, body
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            body = json.loads(raw or "{}")
        except json.JSONDecodeError:
            body = {"message": raw or f"Azure DevOps request failed with HTTP {exc.code}"}
        logger.error("Azure DevOps request failed method=%s path=%s status=%s", method, path, exc.code)
        return exc.code, body


def find_pipeline_by_name(name: str, pat: str) -> dict | None:
    code, body = azdo_request("GET", "_apis/pipelines?api-version=7.1", pat)
    if code != 200:
        raise RuntimeError(body.get("message", f"Unable to list pipelines with HTTP {code}"))
    expected = name.strip().casefold()
    return next(
        (item for item in body.get("value", []) if str(item.get("name") or "").strip().casefold() == expected),
        None,
    )
