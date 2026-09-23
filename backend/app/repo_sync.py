from __future__ import annotations

import re
import urllib.parse
from typing import Any

from .azure_devops import azdo_request, get_branch_head, get_reference_file_content, get_repository, list_branch_paths
from .config import AZDO_ORG, AZDO_PROJECT
from .logging_config import get_logger

logger = get_logger("repo-sync")

SOURCE_BRANCH = "develop"
TARGET_BRANCH = "release/uat"
BUILD_FOLDER = "/BuildAndPublish/"
EXPECTED_SIT_FILES = (
    "/BuildAndPublish/chart/templates/configmap-sit.yaml",
    "/BuildAndPublish/chart/templates/secret-sit.yaml",
    "/BuildAndPublish/chart/values-sit.yaml",
)
_ENV_TOKEN = re.compile(r"(?<![A-Za-z0-9])sit(?![A-Za-z0-9])", re.IGNORECASE)


def _replace_env_token(match: re.Match[str]) -> str:
    value = match.group(0)
    if value.isupper():
        return "UAT"
    if value[:1].isupper():
        return "Uat"
    return "uat"


def _replace_environment_tokens(value: str) -> str:
    return _ENV_TOKEN.sub(_replace_env_token, value)


def _replace_repository_name_and_environment(content: str, source_repository: str, target_repository: str) -> str:
    marker = "__DEVOPS_PORTAL_TARGET_REPOSITORY__"
    if source_repository.strip():
        content = re.sub(re.escape(source_repository.strip()), marker, content, flags=re.IGNORECASE)
    content = _replace_environment_tokens(content)
    return content.replace(marker, target_repository.strip())


def _uat_path_from_sit(path: str) -> str:
    return _replace_environment_tokens(path)


def _is_sit_yaml(path: str) -> bool:
    lowered = path.casefold()
    if not lowered.startswith(BUILD_FOLDER.casefold()):
        return False
    if not lowered.endswith((".yaml", ".yml")):
        return False
    return _ENV_TOKEN.search(path.rsplit("/", 1)[-1]) is not None


def _path_map(paths: set[str]) -> dict[str, str]:
    return {path.casefold(): path for path in paths}


def _branch_url(repository_name: str) -> str:
    repo = urllib.parse.quote(repository_name, safe="")
    project = urllib.parse.quote(AZDO_PROJECT, safe="")
    org = urllib.parse.quote(AZDO_ORG, safe="")
    version = urllib.parse.quote(f"GB{TARGET_BRANCH}", safe="")
    return f"https://dev.azure.com/{org}/{project}/_git/{repo}?version={version}"


def _message(body: Any, fallback: str) -> str:
    if isinstance(body, dict):
        return str(body.get("message") or fallback)
    return fallback


def _prepare_plan(target_repository_name: str, reference_repository_name: str, pat: str) -> dict[str, Any]:
    target_name = target_repository_name.strip()
    reference_name = reference_repository_name.strip() or target_name
    if not target_name:
        raise RuntimeError("Target repository name is required")

    target_repository = get_repository(target_name, pat)
    if not target_repository:
        raise RuntimeError(f"Target repository {target_name} was not found")

    reference_repository = get_repository(reference_name, pat)
    if not reference_repository:
        raise RuntimeError(f"SIT reference repository {reference_name} was not found")

    target_id = str(target_repository.get("id") or "")
    reference_id = str(reference_repository.get("id") or "")
    if not target_id or not reference_id:
        raise RuntimeError("Azure DevOps did not return the repository identifier")

    develop_head = get_branch_head(target_id, SOURCE_BRANCH, pat)
    if not develop_head:
        raise RuntimeError(f"Target repository {target_name} does not have a {SOURCE_BRANCH} branch")

    reference_develop_head = get_branch_head(reference_id, SOURCE_BRANCH, pat)
    if not reference_develop_head:
        raise RuntimeError(f"SIT reference repository {reference_name} does not have a {SOURCE_BRANCH} branch")

    release_head = get_branch_head(target_id, TARGET_BRANCH, pat)
    comparison_branch = TARGET_BRANCH if release_head else SOURCE_BRANCH

    source_paths = list_branch_paths(reference_id, SOURCE_BRANCH, pat)
    sit_paths = sorted(path for path in source_paths if _is_sit_yaml(path))
    if not sit_paths:
        raise RuntimeError(
            f"No SIT YAML files were found under BuildAndPublish in {reference_name}:{SOURCE_BRANCH}"
        )

    target_paths = list_branch_paths(target_id, comparison_branch, pat)
    target_map = _path_map(target_paths)
    source_map = _path_map(source_paths)

    files: list[dict[str, Any]] = []
    for source_path in sit_paths:
        generated_path = _uat_path_from_sit(source_path)
        source_content = get_reference_file_content(reference_id, source_path, SOURCE_BRANCH, pat)
        generated_content = _replace_repository_name_and_environment(
            source_content,
            reference_name,
            target_name,
        )

        existing_path = target_map.get(generated_path.casefold())
        action = "add"
        if existing_path:
            current_content = get_reference_file_content(target_id, existing_path, comparison_branch, pat)
            action = "unchanged" if current_content == generated_content else "edit"
            generated_path = existing_path

        files.append(
            {
                "source_path": source_path,
                "target_path": generated_path,
                "action": action,
                "content": generated_content,
            }
        )

    missing_expected = [
        path for path in EXPECTED_SIT_FILES if path.casefold() not in source_map
    ]
    warnings: list[str] = []
    if missing_expected:
        warnings.append(
            "Reference SIT layout is missing: " + ", ".join(missing_expected)
        )
    if release_head:
        warnings.append(
            f"{TARGET_BRANCH} already exists; only generated UAT files that changed will be updated."
        )

    return {
        "repository": target_name,
        "reference_repository": reference_name,
        "source_branch": SOURCE_BRANCH,
        "target_branch": TARGET_BRANCH,
        "branch_action": "update" if release_head else "create",
        "url": _branch_url(target_name),
        "warnings": warnings,
        "files": files,
        "_target_id": target_id,
        "_develop_head": develop_head,
        "_release_head": release_head,
    }


def _public_plan(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "repository": plan["repository"],
        "reference_repository": plan["reference_repository"],
        "source_branch": plan["source_branch"],
        "target_branch": plan["target_branch"],
        "branch_action": plan["branch_action"],
        "url": plan["url"],
        "warnings": list(plan["warnings"]),
        "files": [
            {
                "source_path": item["source_path"],
                "target_path": item["target_path"],
                "action": item["action"],
            }
            for item in plan["files"]
        ],
    }


def preview_uat_repository_sync(
    target_repository_name: str,
    reference_repository_name: str,
    pat: str,
) -> dict[str, Any]:
    return _public_plan(_prepare_plan(target_repository_name, reference_repository_name, pat))


def _create_branch_without_changes(repository_id: str, develop_head: str, pat: str) -> None:
    payload = [
        {
            "name": f"refs/heads/{TARGET_BRANCH}",
            "oldObjectId": "0" * 40,
            "newObjectId": develop_head,
        }
    ]
    code, body = azdo_request(
        "POST",
        f"_apis/git/repositories/{repository_id}/refs?api-version=7.1",
        pat,
        payload,  # type: ignore[arg-type]
    )
    if code not in (200, 201):
        raise RuntimeError(_message(body, f"Unable to create {TARGET_BRANCH} with HTTP {code}"))


def execute_uat_repository_sync(
    target_repository_name: str,
    reference_repository_name: str,
    pat: str,
    actor: str,
) -> dict[str, Any]:
    plan = _prepare_plan(target_repository_name, reference_repository_name, pat)
    changes = []
    for item in plan["files"]:
        if item["action"] == "unchanged":
            continue
        changes.append(
            {
                "changeType": item["action"],
                "item": {"path": item["target_path"]},
                "newContent": {
                    "content": item["content"],
                    "contentType": "rawtext",
                },
            }
        )

    repository_id = plan["_target_id"]
    release_head = plan["_release_head"]
    develop_head = plan["_develop_head"]

    if not changes:
        if not release_head:
            _create_branch_without_changes(repository_id, develop_head, pat)
            status = "Created"
            detail = f"Created {TARGET_BRANCH} from {SOURCE_BRANCH}; generated UAT files were already present in the base branch."
        else:
            status = "No Changes"
            detail = f"{TARGET_BRANCH} is already synchronized with the selected SIT configuration."
    else:
        parent = release_head or develop_head
        commit = {
            "comment": f"Sync UAT configuration from SIT via DevOps Portal ({actor})",
            "parents": [parent],
            "changes": changes,
        }
        payload = {
            "refUpdates": [
                {
                    "name": f"refs/heads/{TARGET_BRANCH}",
                    "oldObjectId": release_head or "0" * 40,
                }
            ],
            "commits": [commit],
        }
        code, body = azdo_request(
            "POST",
            f"_apis/git/repositories/{repository_id}/pushes?api-version=7.1",
            pat,
            payload,
        )
        if code not in (200, 201):
            raise RuntimeError(_message(body, f"UAT repository sync failed with HTTP {code}"))
        status = "Updated" if release_head else "Created"
        detail = (
            f"{status} {TARGET_BRANCH} from {SOURCE_BRANCH} and applied "
            f"{len(changes)} UAT file change(s) using SIT configuration from "
            f"{plan['reference_repository']}:{SOURCE_BRANCH}."
        )

    logger.info(
        "UAT repo sync completed actor=%s repository=%s reference=%s branch_action=%s changed_files=%s",
        actor,
        plan["repository"],
        plan["reference_repository"],
        plan["branch_action"],
        len(changes),
    )
    result = _public_plan(plan)
    result.update(
        {
            "status": status,
            "message": detail,
            "changed_files": len(changes),
        }
    )
    return result
