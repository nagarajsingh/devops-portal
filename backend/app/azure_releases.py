from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

from .azure_devops import azdo_request
from .config import AZDO_ORG, AZDO_PROJECT
from .logging_config import get_logger

logger = get_logger("azure-releases")


def azdo_release_request(method: str, path: str, pat: str, payload: dict | None = None) -> tuple[int, dict]:
    """Call Azure DevOps Classic Release APIs on the vsrm endpoint."""
    if not AZDO_ORG or not AZDO_PROJECT or not pat.strip():
        raise RuntimeError("Azure DevOps organization, project and DevOps PAT are required")

    url = (
        f"https://vsrm.dev.azure.com/{urllib.parse.quote(AZDO_ORG)}/"
        f"{urllib.parse.quote(AZDO_PROJECT)}/{path}"
    )
    token = base64.b64encode(f":{pat.strip()}".encode()).decode()
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Basic {token}",
            "Content-Type": "application/json",
        },
    )

    logger.debug("Azure DevOps release request method=%s path=%s", method, path)
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
            body = {"message": raw or f"Azure DevOps release request failed with HTTP {exc.code}"}
        logger.error("Azure DevOps release request failed method=%s path=%s status=%s", method, path, exc.code)
        return exc.code, body


def _value_id(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("id") or value.get("name") or "")
    return str(value or "")


def _artifact_definition_id(artifact: dict[str, Any]) -> str:
    reference = artifact.get("definitionReference") or {}
    definition = reference.get("definition") or {}
    if isinstance(definition, dict) and definition.get("id") is not None:
        return str(definition.get("id"))

    source_id = str(artifact.get("sourceId") or "")
    if ":" in source_id:
        return source_id.rsplit(":", 1)[-1]
    return ""


def _definition_uses_build(definition: dict[str, Any], build_definition_id: str, source_id: str) -> bool:
    for artifact in definition.get("artifacts") or []:
        if str(artifact.get("type") or "").casefold() not in {"build", ""}:
            continue
        if build_definition_id and _artifact_definition_id(artifact) == build_definition_id:
            return True
        if source_id and str(artifact.get("sourceId") or "").casefold() == source_id.casefold():
            return True
    return False


def _release_matches_build(release: dict[str, Any], build_definition_id: str, build_run_id: str) -> bool:
    for artifact in release.get("artifacts") or []:
        definition_reference = artifact.get("definitionReference") or {}
        version_reference = definition_reference.get("version") or {}
        instance_reference = artifact.get("instanceReference") or {}

        artifact_build_definition_id = _artifact_definition_id(artifact)
        artifact_run_ids = {
            _value_id(instance_reference),
            _value_id(version_reference),
            str(instance_reference.get("id") or "") if isinstance(instance_reference, dict) else "",
            str(version_reference.get("id") or "") if isinstance(version_reference, dict) else "",
        }

        definition_matches = not build_definition_id or not artifact_build_definition_id or artifact_build_definition_id == build_definition_id
        if definition_matches and build_run_id in artifact_run_ids:
            return True
    return False


def _duration_seconds(started_at: str | None, finished_at: str | None) -> int | None:
    if not started_at:
        return None
    try:
        start = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        end = datetime.fromisoformat(finished_at.replace("Z", "+00:00")) if finished_at else datetime.now(timezone.utc)
        return max(0, int((end - start).total_seconds()))
    except ValueError:
        return None


def _release_status(environments: list[dict[str, Any]]) -> str:
    states = [str(item.get("status") or "").casefold() for item in environments]
    if not states:
        return "Ready"
    failed = {"rejected", "canceled", "cancelled", "failed", "partiallysucceeded"}
    running = {"queued", "inprogress", "in_progress", "scheduled"}
    waiting = {"notstarted", "not_started", "undefined"}
    if any(state in failed for state in states):
        return "Failed"
    if all(state == "succeeded" for state in states):
        return "Succeeded"
    if any(state in running for state in states):
        return "Running"
    if all(state in waiting or state == "succeeded" for state in states):
        return "Ready"
    return "Running"


def _release_definitions_for_build(build_definition_id: str, project_id: str, pat: str) -> list[dict[str, Any]]:
    source_id = f"{project_id}:{build_definition_id}" if project_id and build_definition_id else ""

    if source_id:
        query = urllib.parse.urlencode(
            {
                "artifactType": "Build",
                "artifactSourceId": source_id,
                "$expand": "artifacts",
                "$top": "500",
                "api-version": "7.1",
            }
        )
        code, body = azdo_release_request("GET", f"_apis/release/definitions?{query}", pat)
        if code == 200 and body.get("value"):
            return list(body.get("value") or [])

    query = urllib.parse.urlencode({"$expand": "artifacts", "$top": "500", "api-version": "7.1"})
    code, body = azdo_release_request("GET", f"_apis/release/definitions?{query}", pat)
    if code != 200:
        logger.warning("Unable to list release definitions status=%s message=%s", code, body.get("message"))
        return []

    definitions = list(body.get("value") or [])
    matches = [item for item in definitions if _definition_uses_build(item, build_definition_id, source_id)]
    if matches:
        return matches

    # Some Azure DevOps responses omit expanded artifact metadata on the definition list.
    # Inspect definition details as a compatibility fallback.
    detailed_matches: list[dict[str, Any]] = []
    for definition in definitions:
        definition_id = definition.get("id")
        if not definition_id:
            continue
        code, detail = azdo_release_request("GET", f"_apis/release/definitions/{definition_id}?api-version=7.1", pat)
        if code == 200 and _definition_uses_build(detail, build_definition_id, source_id):
            detailed_matches.append(detail)
    return detailed_matches


def discover_release_for_build(build_run: dict[str, Any], pat: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Discover the Classic Release created from a specific successful build."""
    build_run_id = str(build_run.get("run_id") or "")
    if not build_run_id:
        return None, {"reason": "Build run ID is missing"}

    code, build = azdo_request("GET", f"_apis/build/builds/{build_run_id}?api-version=7.1", pat)
    if code != 200:
        return None, {"reason": build.get("message", f"Unable to load build {build_run_id}")}

    build_definition = build.get("definition") or {}
    build_project = build.get("project") or {}
    build_definition_id = str(build_definition.get("id") or build_run.get("pipeline_id") or "")
    project_id = str(build_project.get("id") or "")
    build_pipeline_name = str(build_definition.get("name") or build_run.get("pipeline_name") or "")
    build_number = str(build.get("buildNumber") or "")

    definitions = _release_definitions_for_build(build_definition_id, project_id, pat)
    diagnostics: dict[str, Any] = {
        "build_run_id": build_run_id,
        "build_number": build_number,
        "build_pipeline_name": build_pipeline_name,
        "build_definition_id": build_definition_id,
        "release_definitions": [
            {"id": item.get("id"), "name": item.get("name")} for item in definitions
        ],
    }

    for definition in definitions:
        definition_id = definition.get("id")
        if not definition_id:
            continue
        query = urllib.parse.urlencode(
            {
                "definitionId": str(definition_id),
                "$top": "100",
                "queryOrder": "descending",
                "api-version": "7.1",
            }
        )
        code, releases = azdo_release_request("GET", f"_apis/release/releases?{query}", pat)
        if code != 200:
            continue

        for summary in releases.get("value") or []:
            release_id = summary.get("id")
            if not release_id:
                continue
            code, detail = azdo_release_request("GET", f"_apis/release/releases/{release_id}?api-version=7.1", pat)
            if code != 200:
                continue
            if not _release_matches_build(detail, build_definition_id, build_run_id):
                continue

            environments = detail.get("environments") or []
            status = _release_status(environments)
            web_url = ((detail.get("_links") or {}).get("web") or {}).get("href")
            finished_at = detail.get("modifiedOn") if status in {"Succeeded", "Failed"} else None
            result = {
                "pipeline_name": definition.get("name") or detail.get("releaseDefinition", {}).get("name") or "",
                "release_definition_id": definition_id,
                "release_definition_name": definition.get("name") or "",
                "release_id": detail.get("id"),
                "release_name": detail.get("name") or "",
                "status": status,
                "result": status,
                "url": web_url,
                "logs_url": web_url,
                "started_at": detail.get("createdOn"),
                "finished_at": finished_at,
                "duration_seconds": _duration_seconds(detail.get("createdOn"), finished_at),
                "environment_status": ", ".join(
                    f"{env.get('name')}={env.get('status')}" for env in environments
                ),
                "environments": [
                    {
                        "id": env.get("id"),
                        "name": env.get("name"),
                        "status": env.get("status"),
                        "rank": env.get("rank"),
                    }
                    for env in environments
                ],
                "source_build": {
                    "run_id": int(build_run_id),
                    "build_number": build_number,
                    "pipeline_id": build_definition_id,
                    "pipeline_name": build_pipeline_name,
                },
            }
            logger.info(
                "Classic release discovered build_pipeline=%s build_run=%s release_definition=%s release=%s",
                build_pipeline_name,
                build_run_id,
                result.get("release_definition_name"),
                result.get("release_name"),
            )
            return result, diagnostics

    diagnostics["reason"] = (
        "Release definition was discovered but no release linked to this exact build was found"
        if definitions
        else "No Classic Release definition using this build pipeline was discovered"
    )
    return None, diagnostics


def discover_collections_releases(row: dict[str, Any], pat: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    runs: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    seen_release_ids: set[str] = set()

    build_runs = ((row.get("steps") or {}).get("build") or {}).get("runs") or []
    for build_run in build_runs:
        if str(build_run.get("status") or "") != "Succeeded":
            continue
        release, diagnostics = discover_release_for_build(build_run, pat)
        if not release:
            missing.append(diagnostics)
            continue
        release_id = str(release.get("release_id") or "")
        if release_id and release_id in seen_release_ids:
            continue
        if release_id:
            seen_release_ids.add(release_id)
        release["service"] = build_run.get("service")
        runs.append(release)

    return runs, missing
