from __future__ import annotations

from typing import Any

from .azure_devops import azdo_request, find_pipeline_by_name
from .config import AZDO_ORG, AZDO_PROJECT
from .logging_config import get_logger

logger = get_logger("pipeline-setup")

PIPELINE_FOLDERS = {
    "Native-Mobile": "\\Native-Mobile",
    "H2H": "\\H2H",
    "Collections": "\\Collections",
    "Safenet": "\\Safenet",
}


def pipeline_folder(application_type: str) -> str:
    return PIPELINE_FOLDERS.get(application_type, "\\DevOps-Portal")


def create_build_pipeline(
    repository: dict,
    yaml_path: str,
    target_branch: str,
    pat: str,
    application_type: str,
) -> dict[str, Any]:
    pipeline_name = repository["name"]
    folder = pipeline_folder(application_type)
    existing = find_pipeline_by_name(pipeline_name, pat)
    if existing:
        pipeline_id = existing.get("id")
        logger.info(
            "Azure DevOps pipeline already exists pipeline=%s id=%s application=%s requested_folder=%s",
            pipeline_name,
            pipeline_id,
            application_type,
            folder,
        )
        return {
            "status": "Already Exists",
            "message": f"Pipeline {pipeline_name} already exists",
            "id": pipeline_id,
            "name": pipeline_name,
            "yaml_path": yaml_path,
            "branch": target_branch,
            "folder": folder,
            "url": f"https://dev.azure.com/{AZDO_ORG}/{AZDO_PROJECT}/_build?definitionId={pipeline_id}",
        }

    payload = {
        "name": pipeline_name,
        "folder": folder,
        "configuration": {
            "type": "yaml",
            "path": yaml_path,
            "repository": {
                "id": repository["id"],
                "name": pipeline_name,
                "type": "azureReposGit",
                "defaultBranch": f"refs/heads/{target_branch}",
            },
        },
    }
    code, body = azdo_request("POST", "_apis/pipelines?api-version=7.1", pat, payload)
    if code not in (200, 201):
        raise RuntimeError(body.get("message", f"Pipeline creation failed with HTTP {code}"))

    pipeline_id = body.get("id")
    logger.info(
        "Azure DevOps pipeline created pipeline=%s id=%s branch=%s application=%s folder=%s",
        pipeline_name,
        pipeline_id,
        target_branch,
        application_type,
        folder,
    )
    return {
        "status": "Completed",
        "message": f"Pipeline {pipeline_name} created in {folder} using {yaml_path} from {target_branch}",
        "id": pipeline_id,
        "name": pipeline_name,
        "yaml_path": yaml_path,
        "branch": target_branch,
        "folder": folder,
        "url": f"https://dev.azure.com/{AZDO_ORG}/{AZDO_PROJECT}/_build?definitionId={pipeline_id}",
    }
