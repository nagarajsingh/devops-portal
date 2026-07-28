from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .config import AZDO_ORG, AZDO_PAT, AZDO_PROJECT, BOOTSTRAP_BRANCH
from .logging_config import get_logger

logger = get_logger("azure-devops")

PIPELINE_FILE_CANDIDATES = ("/azure-pipelines.yml", "/azure-pipelines.yaml")
DOCKERFILE_PATH = "/Dockerfile"
FOLDER_PREFIXES = ("/manifests/", "/shared-config/")


def azdo_request(method: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
    if not AZDO_ORG or not AZDO_PROJECT or not AZDO_PAT:
        raise RuntimeError("Azure DevOps organization, project or PAT is not configured")
    url = f"https://dev.azure.com/{urllib.parse.quote(AZDO_ORG)}/{urllib.parse.quote(AZDO_PROJECT)}/{path}"
    token = base64.b64encode(f":{AZDO_PAT}".encode()).decode()
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method, headers={"Authorization": f"Basic {token}", "Content-Type": "application/json"})
    logger.debug("Azure DevOps request method=%s path=%s", method, path)
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            raw = response.read().decode()
            try:
                body = json.loads(raw or "{}")
            except json.JSONDecodeError:
                body = {"content": raw}
            logger.debug("Azure DevOps response method=%s path=%s status=%s", method, path, response.status)
            return response.status, body
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            body = json.loads(raw or "{}")
        except json.JSONDecodeError:
            body = {"message": raw or f"Azure DevOps request failed with HTTP {exc.code}"}
        logger.error("Azure DevOps request failed method=%s path=%s status=%s message=%s", method, path, exc.code, body.get("message", ""))
        return exc.code, body


def get_repository(name: str) -> dict | None:
    logger.info("Checking Azure DevOps repository repository=%s", name)
    code, body = azdo_request("GET", f"_apis/git/repositories/{urllib.parse.quote(name)}?api-version=7.1")
    if code == 200:
        logger.info("Repository found repository=%s id=%s", name, body.get("id"))
        return body
    if code == 404:
        logger.info("Repository does not exist repository=%s", name)
        return None
    raise RuntimeError(body.get("message", f"Repository lookup failed with HTTP {code}"))


def create_repository(name: str) -> dict:
    logger.info("Creating Azure DevOps repository repository=%s project=%s", name, AZDO_PROJECT)
    code, body = azdo_request("POST", "_apis/git/repositories?api-version=7.1", {"name": name})
    if code not in (200, 201):
        raise RuntimeError(body.get("message", f"Repository creation failed with HTTP {code}"))
    logger.info("Repository created repository=%s id=%s", name, body.get("id"))
    return body


def get_reference_file_content(repository_id: str, path: str, branch: str) -> str:
    logger.debug("Reading reference file repository_id=%s branch=%s path=%s", repository_id, branch, path)
    query = urllib.parse.urlencode({"path": path, "includeContent": "true", "versionDescriptor.version": branch, "versionDescriptor.versionType": "branch", "api-version": "7.1"})
    code, body = azdo_request("GET", f"_apis/git/repositories/{repository_id}/items?{query}")
    if code != 200:
        raise RuntimeError(body.get("message", f"Unable to read {path} from branch {branch} with HTTP {code}"))
    content = body.get("content")
    if content is None:
        raise RuntimeError(f"Content was not returned for reference file {path} on branch {branch}")
    return content


def reference_files(reference_repository_name: str, reference_branch: str) -> list[dict[str, str]]:
    repository = get_repository(reference_repository_name)
    if not repository:
        raise RuntimeError(f"Reference repository {reference_repository_name} was not found")
    branch = reference_branch.strip().removeprefix("refs/heads/")
    if not branch:
        raise RuntimeError("Reference repository branch must be provided by DevOps")

    repository_id = repository["id"]
    logger.info("Reading reference repository repository=%s branch=%s", reference_repository_name, branch)
    query = urllib.parse.urlencode({"scopePath": "/", "recursionLevel": "Full", "versionDescriptor.version": branch, "versionDescriptor.versionType": "branch", "api-version": "7.1"})
    code, body = azdo_request("GET", f"_apis/git/repositories/{repository_id}/items?{query}")
    if code != 200:
        raise RuntimeError(body.get("message", f"Unable to read reference repository branch {branch} with HTTP {code}"))

    available_paths = {
        item.get("path", "")
        for item in body.get("value", [])
        if not item.get("isFolder")
    }
    pipeline_path = next((path for path in PIPELINE_FILE_CANDIDATES if path in available_paths), None)

    missing: list[str] = []
    if DOCKERFILE_PATH not in available_paths:
        missing.append(DOCKERFILE_PATH)
    if pipeline_path is None:
        missing.append("/azure-pipelines.yml or /azure-pipelines.yaml")
    if missing:
        raise RuntimeError(f"Reference repository branch {branch} is missing required files: {', '.join(missing)}")

    selected_paths = sorted(
        path
        for path in available_paths
        if path == DOCKERFILE_PATH
        or path == pipeline_path
        or path.startswith(FOLDER_PREFIXES)
    )
    logger.info(
        "Reference template matched repository=%s branch=%s pipeline_file=%s selected_files=%s",
        reference_repository_name,
        branch,
        pipeline_path,
        len(selected_paths),
    )

    files = [{"path": path, "content": get_reference_file_content(repository_id, path, branch)} for path in selected_paths]
    if not any(path.startswith("/manifests/") for path in selected_paths):
        files.append({"path": "/manifests/.gitkeep", "content": ""})
    if not any(path.startswith("/shared-config/") for path in selected_paths):
        files.append({"path": "/shared-config/.gitkeep", "content": ""})
    logger.info("Reference files loaded repository=%s branch=%s file_count=%s", reference_repository_name, branch, len(files))
    return files


def bootstrap_repository(target_repository: dict, reference_repository_name: str, reference_branch: str, application_type: str) -> dict[str, Any]:
    if application_type != "H2H":
        raise RuntimeError(f"Template bootstrap is currently configured only for H2H, not {application_type}")
    logger.info("Bootstrapping repository target=%s source=%s branch=%s destination_branch=%s", target_repository.get("name"), reference_repository_name, reference_branch, BOOTSTRAP_BRANCH)
    files = reference_files(reference_repository_name.strip(), reference_branch)
    changes = [{"changeType": "add", "item": {"path": item["path"]}, "newContent": {"content": item["content"], "contentType": "rawtext"}} for item in files]
    payload = {"refUpdates": [{"name": f"refs/heads/{BOOTSTRAP_BRANCH}", "oldObjectId": "0" * 40}], "commits": [{"comment": f"Bootstrap {application_type} DevOps repository structure from {reference_branch}", "changes": changes}]}
    code, body = azdo_request("POST", f"_apis/git/repositories/{target_repository['id']}/pushes?api-version=7.1", payload)
    if code not in (200, 201):
        raise RuntimeError(body.get("message", f"Repository bootstrap failed with HTTP {code}"))
    logger.info("Repository bootstrap completed target=%s destination_branch=%s files=%s", target_repository.get("name"), BOOTSTRAP_BRANCH, len(files))
    return {"status": "Completed", "message": f"Created {BOOTSTRAP_BRANCH} using {reference_repository_name}:{reference_branch}", "branch": BOOTSTRAP_BRANCH, "source_branch": reference_branch, "files": [item["path"] for item in files], "url": target_repository.get("webUrl") or target_repository.get("remoteUrl")}
