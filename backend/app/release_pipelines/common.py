from __future__ import annotations

import base64
import copy
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

from ..azure_devops import find_pipeline_by_name
from ..config import AZDO_ORG, AZDO_PROJECT
from ..logging_config import get_logger

logger = get_logger("release-pipeline")

ReleaseCustomizer = Callable[[dict[str, Any], str, str], dict[str, Any]]


def _release_request(method: str, path: str, pat: str, payload: dict | None = None) -> tuple[int, dict]:
    if not AZDO_ORG or not AZDO_PROJECT or not pat.strip():
        raise RuntimeError("Azure DevOps organization, project and DevOps PAT are required")

    url = (
        f"https://vsrm.dev.azure.com/{urllib.parse.quote(AZDO_ORG)}/"
        f"{urllib.parse.quote(AZDO_PROJECT)}/{path}"
    )
    token = base64.b64encode(f":{pat.strip()}".encode()).decode()
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode() if payload is not None else None,
        method=method,
        headers={"Authorization": f"Basic {token}", "Content-Type": "application/json"},
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
            body = {"message": raw or f"Release API request failed with HTTP {exc.code}"}
        logger.error("Release API request failed method=%s path=%s status=%s", method, path, exc.code)
        return exc.code, body


def _definition_id_from_artifact(artifact: dict[str, Any]) -> str:
    reference = artifact.get("definitionReference") or {}
    definition = reference.get("definition") or {}
    return str(definition.get("id") or "")


def _find_reference_release_definition(reference_repository_name: str, pat: str) -> tuple[dict[str, Any], dict[str, Any]]:
    reference_pipeline = find_pipeline_by_name(reference_repository_name, pat)
    if not reference_pipeline:
        raise RuntimeError(
            f"Reference build pipeline {reference_repository_name} was not found. "
            "The reference repository and build pipeline must have the same name."
        )

    code, body = _release_request("GET", "_apis/release/definitions?api-version=7.1&$top=1000", pat)
    if code != 200:
        raise RuntimeError(body.get("message", f"Unable to list release definitions with HTTP {code}"))

    reference_pipeline_id = str(reference_pipeline.get("id"))
    for summary in body.get("value", []):
        definition_id = summary.get("id")
        if not definition_id:
            continue
        detail_code, detail = _release_request(
            "GET", f"_apis/release/definitions/{definition_id}?api-version=7.1", pat
        )
        if detail_code != 200:
            continue
        if any(_definition_id_from_artifact(artifact) == reference_pipeline_id for artifact in detail.get("artifacts", [])):
            return detail, reference_pipeline

    raise RuntimeError(
        f"No release pipeline was found whose build artifact uses {reference_repository_name} "
        f"(build pipeline ID {reference_pipeline_id})"
    )


def _find_release_by_name(name: str, pat: str) -> dict[str, Any] | None:
    query = urllib.parse.urlencode({"searchText": name, "$top": 100, "api-version": "7.1"})
    code, body = _release_request("GET", f"_apis/release/definitions?{query}", pat)
    if code != 200:
        raise RuntimeError(body.get("message", f"Unable to search release definitions with HTTP {code}"))
    return next((item for item in body.get("value", []) if item.get("name") == name), None)


def _replace_strings(value: Any, replacements: dict[str, str]) -> Any:
    if isinstance(value, dict):
        return {key: _replace_strings(item, replacements) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_strings(item, replacements) for item in value]
    if isinstance(value, str):
        updated = value
        for source, target in replacements.items():
            if source:
                updated = updated.replace(source, target)
        return updated
    return value


def _prepare_cloned_definition(
    reference_definition: dict[str, Any],
    reference_repository_name: str,
    target_repository_name: str,
    target_build_pipeline: dict[str, Any],
) -> dict[str, Any]:
    definition = copy.deepcopy(reference_definition)
    reference_alias = f"_{reference_repository_name}"
    target_alias = f"_{target_repository_name}"

    definition = _replace_strings(
        definition,
        {
            reference_alias: target_alias,
            reference_repository_name: target_repository_name,
        },
    )

    definition["name"] = target_repository_name
    definition.pop("id", None)
    definition.pop("url", None)
    definition.pop("_links", None)
    definition.pop("revision", None)
    definition.pop("createdBy", None)
    definition.pop("createdOn", None)
    definition.pop("modifiedBy", None)
    definition.pop("modifiedOn", None)
    definition.pop("lastRelease", None)

    target_pipeline_id = str(target_build_pipeline.get("id"))
    matched_artifact = False
    for artifact in definition.get("artifacts", []):
        if artifact.get("type") != "Build":
            continue
        reference = artifact.setdefault("definitionReference", {})
        source_definition = reference.setdefault("definition", {})
        source_definition.update({"id": target_pipeline_id, "name": target_repository_name})
        artifact["alias"] = target_alias
        artifact["sourceId"] = target_pipeline_id
        default_version = reference.setdefault("defaultVersionType", {})
        default_version["id"] = "latestType"
        default_version["name"] = "Latest"
        matched_artifact = True
        break

    if not matched_artifact:
        raise RuntimeError("The reference release definition does not contain a Build artifact")

    return definition


def clone_release_pipeline(
    reference_repository_name: str,
    target_repository_name: str,
    target_build_pipeline: dict[str, Any],
    pat: str,
    customizer: ReleaseCustomizer,
) -> dict[str, Any]:
    existing = _find_release_by_name(target_repository_name, pat)
    if existing:
        definition_id = existing.get("id")
        return {
            "status": "Already Exists",
            "message": f"Release pipeline {target_repository_name} already exists",
            "id": definition_id,
            "name": target_repository_name,
            "url": f"https://dev.azure.com/{AZDO_ORG}/{AZDO_PROJECT}/_release?_a=releases&view=mine&definitionId={definition_id}",
        }

    reference_definition, reference_pipeline = _find_reference_release_definition(reference_repository_name, pat)
    definition = _prepare_cloned_definition(
        reference_definition,
        reference_repository_name,
        target_repository_name,
        target_build_pipeline,
    )
    definition = customizer(definition, reference_repository_name, target_repository_name)

    code, body = _release_request("POST", "_apis/release/definitions?api-version=7.1", pat, definition)
    if code not in (200, 201):
        raise RuntimeError(body.get("message", f"Release pipeline creation failed with HTTP {code}"))

    definition_id = body.get("id")
    logger.info(
        "Release pipeline cloned name=%s id=%s reference_definition=%s reference_build_pipeline=%s",
        target_repository_name,
        definition_id,
        reference_definition.get("id"),
        reference_pipeline.get("id"),
    )
    return {
        "status": "Completed",
        "message": (
            f"Release pipeline {target_repository_name} cloned from definition "
            f"{reference_definition.get('id')} and linked to build pipeline {target_build_pipeline.get('id')}"
        ),
        "id": definition_id,
        "name": target_repository_name,
        "reference_definition_id": reference_definition.get("id"),
        "reference_build_pipeline_id": reference_pipeline.get("id"),
        "build_pipeline_id": target_build_pipeline.get("id"),
        "artifact_alias": f"_{target_repository_name}",
        "url": f"https://dev.azure.com/{AZDO_ORG}/{AZDO_PROJECT}/_release?_a=releases&view=mine&definitionId={definition_id}",
    }
