from __future__ import annotations

from typing import Any

from .azure_devops import bootstrap_repository, create_repository, get_repository
from .config import BOOTSTRAP_BRANCH
from .kubernetes_ops import ensure_ingress_path, ensure_service


def provision(item: dict) -> tuple[str, dict[str, Any]]:
    steps: dict[str, Any] = {}
    target_repo: dict | None = None

    try:
        existing_repo = get_repository(item["repository_name"])
        previous_repo_id = item.get("provisioning", {}).get("repository", {}).get("id")
        if existing_repo and previous_repo_id != existing_repo.get("id"):
            steps["repository"] = {
                "status": "Warning",
                "message": "Repository already exists",
                "id": existing_repo.get("id"),
                "url": existing_repo.get("webUrl") or existing_repo.get("remoteUrl"),
            }
            return "Pending Action", steps
        if existing_repo:
            target_repo = existing_repo
            steps["repository"] = {
                "status": "Already Exists",
                "message": "Reusing repository created during the earlier provisioning attempt",
                "id": existing_repo.get("id"),
                "url": existing_repo.get("webUrl") or existing_repo.get("remoteUrl"),
            }
        else:
            target_repo = create_repository(item["repository_name"])
            steps["repository"] = {
                "status": "Completed",
                "id": target_repo.get("id"),
                "url": target_repo.get("webUrl") or target_repo.get("remoteUrl"),
            }
    except Exception as exc:
        steps["repository"] = {"status": "Failed", "message": str(exc)}

    if target_repo:
        try:
            steps["repository_bootstrap"] = bootstrap_repository(
                target_repo,
                item.get("reference_repository_name", ""),
                item.get("reference_branch", ""),
                item.get("application_type", "H2H"),
            )
            steps["pipeline"] = {
                "status": "Completed",
                "message": f"azure-pipelines.yaml committed to {BOOTSTRAP_BRANCH}",
            }
        except Exception as exc:
            steps["repository_bootstrap"] = {"status": "Failed", "message": str(exc)}
            steps["pipeline"] = {"status": "Failed", "message": "Pipeline file could not be bootstrapped"}
    else:
        steps["repository_bootstrap"] = {"status": "Pending", "message": "Waiting for repository creation"}
        steps["pipeline"] = {"status": "Pending", "message": "Waiting for repository bootstrap"}

    try:
        steps["service"] = {"status": ensure_service(item)}
    except Exception as exc:
        steps["service"] = {"status": "Failed", "message": str(exc)}

    try:
        steps["ingress"] = ensure_ingress_path(item)
    except Exception as exc:
        steps["ingress"] = {"status": "Failed", "message": str(exc)}

    statuses = [step["status"] for step in steps.values()]
    if statuses and all(value in ("Completed", "Skipped", "Already Exists") for value in statuses):
        return "Completed", steps
    if any(value == "Failed" for value in statuses):
        return "Partially Completed", steps
    return "Pending Action", steps
