from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .config import AZDO_ORG, AZDO_PROJECT, BOOTSTRAP_BRANCH
from .logging_config import get_logger

logger = get_logger("azure-devops")
PIPELINE_FILE_CANDIDATES = ("/azure-pipelines.yml", "/azure-pipelines.yaml")
DOCKERFILE_PATH = "/Dockerfile"
FOLDER_PREFIXES = ("/manifests/", "/shared-config/")


def azdo_request(method: str, path: str, pat: str, payload: dict | None = None) -> tuple[int, dict]:
    if not AZDO_ORG or not AZDO_PROJECT or not pat.strip():
        raise RuntimeError("Azure DevOps organization, project and DevOps PAT are required")
    url = f"https://dev.azure.com/{urllib.parse.quote(AZDO_ORG)}/{urllib.parse.quote(AZDO_PROJECT)}/{path}"
    token = base64.b64encode(f":{pat.strip()}".encode()).decode()
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
            return response.status, body
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            body = json.loads(raw or "{}")
        except json.JSONDecodeError:
            body = {"message": raw or f"Azure DevOps request failed with HTTP {exc.code}"}
        logger.error("Azure DevOps request failed method=%s path=%s status=%s", method, path, exc.code)
        return exc.code, body


def get_repository(name: str, pat: str) -> dict | None:
    code, body = azdo_request("GET", f"_apis/git/repositories/{urllib.parse.quote(name)}?api-version=7.1", pat)
    if code == 200:
        return body
    if code == 404:
        return None
    raise RuntimeError(body.get("message", f"Repository lookup failed with HTTP {code}"))


def create_repository(name: str, pat: str) -> dict:
    code, body = azdo_request("POST", "_apis/git/repositories?api-version=7.1", pat, {"name": name})
    if code not in (200, 201):
        raise RuntimeError(body.get("message", f"Repository creation failed with HTTP {code}"))
    return body


def get_reference_file_content(repository_id: str, path: str, branch: str, pat: str) -> str:
    query = urllib.parse.urlencode({"path": path, "includeContent": "true", "versionDescriptor.version": branch, "versionDescriptor.versionType": "branch", "api-version": "7.1"})
    code, body = azdo_request("GET", f"_apis/git/repositories/{repository_id}/items?{query}", pat)
    if code != 200:
        raise RuntimeError(body.get("message", f"Unable to read {path} from branch {branch} with HTTP {code}"))
    content = body.get("content")
    if content is None:
        raise RuntimeError(f"Content was not returned for reference file {path} on branch {branch}")
    return content


def list_branch_paths(repository_id: str, branch: str, pat: str) -> set[str]:
    query = urllib.parse.urlencode({"scopePath": "/", "recursionLevel": "Full", "versionDescriptor.version": branch, "versionDescriptor.versionType": "branch", "api-version": "7.1"})
    code, body = azdo_request("GET", f"_apis/git/repositories/{repository_id}/items?{query}", pat)
    if code == 404:
        return set()
    if code != 200:
        raise RuntimeError(body.get("message", f"Unable to read branch {branch} with HTTP {code}"))
    return {item.get("path", "") for item in body.get("value", []) if not item.get("isFolder")}


def get_branch_head(repository_id: str, branch: str, pat: str) -> str | None:
    query = urllib.parse.urlencode({"filter": f"heads/{branch}", "api-version": "7.1"})
    code, body = azdo_request("GET", f"_apis/git/repositories/{repository_id}/refs?{query}", pat)
    if code != 200:
        raise RuntimeError(body.get("message", f"Unable to inspect branch {branch} with HTTP {code}"))
    refs = body.get("value", [])
    return refs[0].get("objectId") if refs else None


def reference_files(reference_repository_name: str, reference_branch: str, pat: str) -> list[dict[str, str]]:
    repository = get_repository(reference_repository_name, pat)
    if not repository:
        raise RuntimeError(f"Reference repository {reference_repository_name} was not found")
    branch = reference_branch.strip().removeprefix("refs/heads/")
    if not branch:
        raise RuntimeError("Reference repository branch must be provided by DevOps")
    available_paths = list_branch_paths(repository["id"], branch, pat)
    pipeline_path = next((path for path in PIPELINE_FILE_CANDIDATES if path in available_paths), None)
    missing = []
    if DOCKERFILE_PATH not in available_paths:
        missing.append(DOCKERFILE_PATH)
    if pipeline_path is None:
        missing.append("/azure-pipelines.yml or /azure-pipelines.yaml")
    if missing:
        raise RuntimeError(f"Reference repository branch {branch} is missing required files: {', '.join(missing)}")
    selected_paths = sorted(path for path in available_paths if path == DOCKERFILE_PATH or path == pipeline_path or path.startswith(FOLDER_PREFIXES))
    files = [{"path": path, "content": get_reference_file_content(repository["id"], path, branch, pat)} for path in selected_paths]
    if not any(path.startswith("/manifests/") for path in selected_paths):
        files.append({"path": "/manifests/.gitkeep", "content": ""})
    if not any(path.startswith("/shared-config/") for path in selected_paths):
        files.append({"path": "/shared-config/.gitkeep", "content": ""})
    return files


def bootstrap_repository(target_repository: dict, reference_repository_name: str, reference_branch: str, application_type: str, pat: str) -> dict[str, Any]:
    if application_type != "H2H":
        raise RuntimeError(f"Template bootstrap is currently configured only for H2H, not {application_type}")
    files = reference_files(reference_repository_name.strip(), reference_branch, pat)
    repository_id = target_repository["id"]
    head = get_branch_head(repository_id, BOOTSTRAP_BRANCH, pat)
    existing_paths = list_branch_paths(repository_id, BOOTSTRAP_BRANCH, pat) if head else set()
    changes = [{"changeType": "edit" if item["path"] in existing_paths else "add", "item": {"path": item["path"]}, "newContent": {"content": item["content"], "contentType": "rawtext"}} for item in files]
    payload = {"refUpdates": [{"name": f"refs/heads/{BOOTSTRAP_BRANCH}", "oldObjectId": head or "0" * 40}], "commits": [{"comment": f"Bootstrap {application_type} DevOps repository structure from {reference_branch}", "changes": changes}]}
    code, body = azdo_request("POST", f"_apis/git/repositories/{repository_id}/pushes?api-version=7.1", pat, payload)
    if code not in (200, 201):
        raise RuntimeError(body.get("message", f"Repository bootstrap failed with HTTP {code}"))
    action = "Updated" if head else "Created"
    return {"status": "Completed", "message": f"{action} {BOOTSTRAP_BRANCH} using {reference_repository_name}:{reference_branch}", "branch": BOOTSTRAP_BRANCH, "source_branch": reference_branch, "files": [item["path"] for item in files], "url": target_repository.get("webUrl") or target_repository.get("remoteUrl")}


def find_pipeline_by_name(name: str, pat: str) -> dict | None:
    code, body = azdo_request("GET", "_apis/pipelines?api-version=7.1", pat)
    if code != 200:
        raise RuntimeError(body.get("message", f"Unable to list pipelines with HTTP {code}"))
    return next((item for item in body.get("value", []) if item.get("name") == name), None)


def create_build_pipeline(repository: dict, yaml_path: str, pat: str) -> dict[str, Any]:
    pipeline_name = repository["name"]
    existing = find_pipeline_by_name(pipeline_name, pat)
    if existing:
        pipeline_id = existing.get("id")
        return {"status": "Already Exists", "message": f"Pipeline {pipeline_name} already exists", "id": pipeline_id, "name": pipeline_name, "yaml_path": yaml_path, "branch": BOOTSTRAP_BRANCH, "url": f"https://dev.azure.com/{AZDO_ORG}/{AZDO_PROJECT}/_build?definitionId={pipeline_id}"}
    payload = {"name": pipeline_name, "folder": "\\DevOps-Portal", "configuration": {"type": "yaml", "path": yaml_path, "repository": {"id": repository["id"], "name": pipeline_name, "type": "azureReposGit"}}}
    code, body = azdo_request("POST", "_apis/pipelines?api-version=7.1", pat, payload)
    if code not in (200, 201):
        raise RuntimeError(body.get("message", f"Pipeline creation failed with HTTP {code}"))
    pipeline_id = body.get("id")
    logger.info("Azure DevOps pipeline created pipeline=%s id=%s", pipeline_name, pipeline_id)
    return {"status": "Completed", "message": f"Pipeline {pipeline_name} created using {yaml_path}", "id": pipeline_id, "name": pipeline_name, "yaml_path": yaml_path, "branch": BOOTSTRAP_BRANCH, "url": f"https://dev.azure.com/{AZDO_ORG}/{AZDO_PROJECT}/_build?definitionId={pipeline_id}"}
