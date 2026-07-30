from __future__ import annotations

from typing import Any

from .azure_devops import bootstrap_repository, create_build_pipeline, create_repository, get_repository
from .kubernetes_ops import ensure_ingress_path, ensure_service
from .logging_config import get_logger
from .release_pipelines import create_release_pipeline

logger = get_logger("provisioning")


def provision(item: dict, azure_devops_pat: str) -> tuple[str, dict[str, Any]]:
    steps: dict[str, Any] = {}
    target_repo: dict | None = None
    request_id = item.get("id")
    logger.info("Provisioning started request_id=%s repository=%s namespace=%s", request_id, item.get("repository_name"), item.get("namespace"))

    try:
        existing_repo = get_repository(item["repository_name"], azure_devops_pat)
        previous_repo_id = item.get("provisioning", {}).get("repository", {}).get("id")
        if existing_repo and previous_repo_id != existing_repo.get("id"):
            steps["repository"] = {"status": "Warning", "message": "Repository already exists", "id": existing_repo.get("id"), "url": existing_repo.get("webUrl") or existing_repo.get("remoteUrl")}
            return "Pending Action", steps
        if existing_repo:
            target_repo = existing_repo
            steps["repository"] = {"status": "Already Exists", "message": "Reusing repository created during an earlier provisioning attempt", "id": existing_repo.get("id"), "url": existing_repo.get("webUrl") or existing_repo.get("remoteUrl")}
        else:
            target_repo = create_repository(item["repository_name"], azure_devops_pat)
            steps["repository"] = {"status": "Completed", "id": target_repo.get("id"), "url": target_repo.get("webUrl") or target_repo.get("remoteUrl")}
    except Exception as exc:
        logger.exception("Repository provisioning failed request_id=%s repository=%s", request_id, item.get("repository_name"))
        steps["repository"] = {"status": "Failed", "message": str(exc)}

    bootstrap_result: dict[str, Any] | None = None
    reference_repo = (item.get("reference_repository_name") or "").strip()
    if target_repo and reference_repo:
        try:
            bootstrap_result = bootstrap_repository(target_repo, reference_repo, item.get("reference_branch", ""), item.get("application_type", "H2H"), azure_devops_pat)
            steps["repository_bootstrap"] = bootstrap_result
        except Exception as exc:
            logger.exception("Repository bootstrap failed request_id=%s repository=%s", request_id, item.get("repository_name"))
            steps["repository_bootstrap"] = {"status": "Failed", "message": str(exc)}
    elif target_repo:
        steps["repository_bootstrap"] = {"status": "Skipped", "message": "No reference repository was selected"}
    else:
        steps["repository_bootstrap"] = {"status": "Pending", "message": "Waiting for repository creation"}

    build_pipeline_result: dict[str, Any] | None = None
    if item.get("setup_pipeline"):
        try:
            if not target_repo:
                raise RuntimeError("Repository must be created before pipeline setup")
            if not bootstrap_result:
                raise RuntimeError("Pipeline setup requires a reference repository containing azure-pipelines.yml or azure-pipelines.yaml")
            yaml_path = next((path for path in bootstrap_result.get("files", []) if path.lower() in ("/azure-pipelines.yml", "/azure-pipelines.yaml")), None)
            if not yaml_path:
                raise RuntimeError("Pipeline YAML file was not found in the bootstrapped repository")
            target_branch = bootstrap_result.get("branch") or "feature/devops"
            build_pipeline_result = create_build_pipeline(target_repo, yaml_path, target_branch, azure_devops_pat)
            steps["pipeline"] = build_pipeline_result
        except Exception as exc:
            logger.exception("Pipeline creation failed request_id=%s repository=%s", request_id, item.get("repository_name"))
            steps["pipeline"] = {"status": "Failed", "message": str(exc)}
    else:
        steps["pipeline"] = {"status": "Skipped", "message": "Pipeline setup was disabled by DevOps"}

    if item.get("setup_pipeline") and reference_repo:
        try:
            if not build_pipeline_result or not build_pipeline_result.get("id"):
                raise RuntimeError("Build pipeline must be created or found before release pipeline cloning")
            steps["release_pipeline"] = create_release_pipeline(
                item.get("application_type", "H2H"),
                reference_repo,
                item["repository_name"],
                build_pipeline_result,
                azure_devops_pat,
            )
        except Exception as exc:
            logger.exception("Release pipeline creation failed request_id=%s repository=%s", request_id, item.get("repository_name"))
            steps["release_pipeline"] = {"status": "Failed", "message": str(exc)}
    elif item.get("setup_pipeline"):
        steps["release_pipeline"] = {"status": "Skipped", "message": "No reference repository was selected for release pipeline cloning"}
    else:
        steps["release_pipeline"] = {"status": "Skipped", "message": "Pipeline setup was disabled by DevOps"}

    try:
        steps["service"] = {"status": ensure_service(item)}
    except Exception as exc:
        logger.exception("Kubernetes service provisioning failed request_id=%s", request_id)
        steps["service"] = {"status": "Failed", "message": str(exc)}
    try:
        steps["ingress"] = ensure_ingress_path(item)
    except Exception as exc:
        logger.exception("Ingress provisioning failed request_id=%s", request_id)
        steps["ingress"] = {"status": "Failed", "message": str(exc)}

    statuses = [step["status"] for step in steps.values()]
    final_status = "Completed" if statuses and all(value in ("Completed", "Skipped", "Already Exists") for value in statuses) else "Partially Completed" if any(value == "Failed" for value in statuses) else "Pending Action"
    logger.info("Provisioning finished request_id=%s status=%s steps=%s", request_id, final_status, statuses)
    return final_status, steps
