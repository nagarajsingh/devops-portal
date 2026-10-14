from __future__ import annotations

from typing import Any

from .azure_devops import bootstrap_repository, create_repository, get_repository
from .config import LOCAL_KUBERNETES_TARGET
from .kubernetes_ops import ensure_ingress_path, ensure_service
from .logging_config import get_logger
from .pipeline_setup import create_build_pipeline
from .release_pipelines import create_release_pipeline
from .remote_kubernetes_pipeline import provision_through_pipeline

logger = get_logger("provisioning")


def _remote_kubernetes_signature(item: dict) -> dict[str, Any]:
    return {
        "target_cluster": (item.get("target_cluster") or LOCAL_KUBERNETES_TARGET).strip(),
        "namespace": item.get("namespace") or "",
        "create_service": bool(item.get("create_service")),
        "service_name": item.get("service_name") or "",
        "service_port": int(item.get("service_port") or 0),
        "ingress_name": item.get("ingress_name") or "",
        "ingress_path": item.get("ingress_path") or "",
    }


def _previous_remote_kubernetes_result(item: dict) -> dict[str, Any] | None:
    provisioning = item.get("provisioning") or {}
    service = provisioning.get("service") or {}
    ingress = provisioning.get("ingress") or {}
    expected = _remote_kubernetes_signature(item)

    if service.get("status") != "Completed" or ingress.get("status") != "Completed":
        return None
    if service.get("provisioning_signature") != expected:
        return None
    if ingress.get("provisioning_signature") != expected:
        return None

    logger.info(
        "Reusing completed remote Kubernetes provisioning request_id=%s target_cluster=%s run_id=%s",
        item.get("id"),
        expected["target_cluster"],
        service.get("run_id"),
    )
    return service


def _provision_kubernetes(item: dict, azure_devops_pat: str) -> dict[str, dict[str, Any]]:
    request_id = item.get("id")
    target_cluster = (item.get("target_cluster") or LOCAL_KUBERNETES_TARGET).strip()
    steps: dict[str, dict[str, Any]] = {}

    logger.info(
        "Starting Kubernetes provisioning phase request_id=%s target_cluster=%s namespace=%s service=%s ingress=%s create_service=%s",
        request_id,
        target_cluster,
        item.get("namespace"),
        item.get("service_name"),
        item.get("ingress_name"),
        bool(item.get("create_service")),
    )

    if target_cluster == LOCAL_KUBERNETES_TARGET:
        try:
            steps["service"] = {"status": ensure_service(item)}
        except Exception as exc:
            logger.exception(
                "Kubernetes service provisioning failed request_id=%s",
                request_id,
            )
            steps["service"] = {"status": "Failed", "message": str(exc)}
        try:
            steps["ingress"] = ensure_ingress_path(item)
        except Exception as exc:
            logger.exception(
                "Ingress provisioning failed request_id=%s",
                request_id,
            )
            steps["ingress"] = {"status": "Failed", "message": str(exc)}
        return steps

    previous_remote = _previous_remote_kubernetes_result(item)
    if previous_remote:
        reused = {
            **previous_remote,
            "message": "Kubernetes resources were already provisioned successfully; reusing the completed remote pipeline result.",
        }
        steps["service"] = reused
        steps["ingress"] = reused.copy()
        return steps

    try:
        logger.info(
            "Remote Kubernetes provisioning will be queued now request_id=%s target_cluster=%s",
            request_id,
            target_cluster,
        )
        remote_result = provision_through_pipeline(item, azure_devops_pat)
        steps["service"] = {
            **remote_result,
            "message": "Kubernetes service created or validated successfully",
        }
        steps["ingress"] = {
            **remote_result,
            "message": "Ingress path created or updated successfully",
        }
    except Exception as exc:
        logger.exception(
            "Remote Kubernetes provisioning pipeline failed request_id=%s target_cluster=%s",
            request_id,
            target_cluster,
        )
        failed = {
            "status": "Failed",
            "message": str(exc),
            "target_cluster": target_cluster,
            "provisioning_signature": _remote_kubernetes_signature(item),
        }
        steps["service"] = failed
        steps["ingress"] = failed.copy()
    return steps


def provision(item: dict, azure_devops_pat: str) -> tuple[str, dict[str, Any]]:
    steps: dict[str, Any] = {}
    target_repo: dict | None = None
    request_id = item.get("id")
    pending_pipeline_confirmation = False
    logger.info(
        "Provisioning started request_id=%s repository=%s namespace=%s target_cluster=%s",
        request_id,
        item.get("repository_name"),
        item.get("namespace"),
        item.get("target_cluster") or LOCAL_KUBERNETES_TARGET,
    )

    # Kubernetes provisioning is intentionally executed first. Repository/build/release
    # confirmations must never prevent Service or Ingress provisioning on a selected
    # remote cluster.
    steps.update(_provision_kubernetes(item, azure_devops_pat))

    try:
        existing_repo = get_repository(item["repository_name"], azure_devops_pat)
        previous_repo_id = item.get("provisioning", {}).get("repository", {}).get("id")
        allow_existing_repo = bool(item.get("allow_existing_repo_bootstrap"))
        if existing_repo and previous_repo_id != existing_repo.get("id") and not allow_existing_repo:
            steps["repository"] = {
                "status": "Warning",
                "message": "Repository already exists",
                "id": existing_repo.get("id"),
                "url": existing_repo.get("webUrl") or existing_repo.get("remoteUrl"),
                "requires_confirmation": True,
                "confirmation_action": "create_pipeline_branch",
            }
            return "Pending Action", steps
        if existing_repo:
            target_repo = existing_repo
            steps["repository"] = {
                "status": "Already Exists",
                "message": "Using the existing repository without modifying its current branches or code",
                "id": existing_repo.get("id"),
                "url": existing_repo.get("webUrl") or existing_repo.get("remoteUrl"),
            }
        else:
            target_repo = create_repository(item["repository_name"], azure_devops_pat)
            steps["repository"] = {
                "status": "Completed",
                "id": target_repo.get("id"),
                "url": target_repo.get("webUrl") or target_repo.get("remoteUrl"),
            }
    except Exception as exc:
        logger.exception(
            "Repository provisioning failed request_id=%s repository=%s",
            request_id,
            item.get("repository_name"),
        )
        steps["repository"] = {"status": "Failed", "message": str(exc)}

    bootstrap_result: dict[str, Any] | None = None
    reference_repo = (item.get("reference_repository_name") or "").strip()
    if target_repo and reference_repo:
        try:
            bootstrap_result = bootstrap_repository(
                target_repo,
                reference_repo,
                item.get("reference_branch", ""),
                item.get("application_type", "H2H"),
                azure_devops_pat,
            )
            steps["repository_bootstrap"] = bootstrap_result
        except Exception as exc:
            logger.exception(
                "Repository bootstrap failed request_id=%s repository=%s",
                request_id,
                item.get("repository_name"),
            )
            steps["repository_bootstrap"] = {"status": "Failed", "message": str(exc)}
    elif target_repo:
        steps["repository_bootstrap"] = {
            "status": "Skipped",
            "message": "No reference repository was selected",
        }
    else:
        steps["repository_bootstrap"] = {
            "status": "Pending",
            "message": "Waiting for repository creation",
        }

    build_pipeline_result: dict[str, Any] | None = None
    if item.get("setup_pipeline"):
        try:
            if not target_repo:
                raise RuntimeError("Repository must be created before pipeline setup")
            if not bootstrap_result:
                raise RuntimeError(
                    "Pipeline setup requires a reference repository containing azure-pipelines.yml or azure-pipelines.yaml"
                )
            yaml_path = next(
                (
                    path
                    for path in bootstrap_result.get("files", [])
                    if path.lower() in ("/azure-pipelines.yml", "/azure-pipelines.yaml")
                ),
                None,
            )
            if not yaml_path:
                raise RuntimeError("Pipeline YAML file was not found in the bootstrapped repository")
            target_branch = bootstrap_result.get("branch") or "feature/devops"
            application_type = item.get("application_type", "H2H")
            build_pipeline_result = create_build_pipeline(
                target_repo,
                yaml_path,
                target_branch,
                azure_devops_pat,
                application_type,
            )
            steps["pipeline"] = build_pipeline_result
            if (
                build_pipeline_result.get("status") == "Already Exists"
                and not item.get("allow_existing_pipeline_release")
            ):
                pending_pipeline_confirmation = True
                steps["pipeline"] = {
                    **build_pipeline_result,
                    "requires_confirmation": True,
                    "confirmation_action": "reuse_build_pipeline_for_release",
                    "message": (
                        f"Build pipeline {build_pipeline_result.get('name') or item.get('repository_name')} "
                        "already exists. Kubernetes provisioning will continue, but DevOps confirmation is "
                        "required before the release pipeline is created."
                    ),
                }
                logger.info(
                    "Existing build pipeline requires confirmation; continuing Kubernetes provisioning "
                    "request_id=%s pipeline_id=%s",
                    request_id,
                    build_pipeline_result.get("id"),
                )
            else:
                logger.info(
                    "Build pipeline resolved request_id=%s pipeline_id=%s status=%s",
                    request_id,
                    build_pipeline_result.get("id"),
                    build_pipeline_result.get("status"),
                )
        except Exception as exc:
            logger.exception(
                "Pipeline creation failed request_id=%s repository=%s",
                request_id,
                item.get("repository_name"),
            )
            steps["pipeline"] = {"status": "Failed", "message": str(exc)}
    else:
        steps["pipeline"] = {
            "status": "Skipped",
            "message": "Pipeline setup was disabled by DevOps",
        }

    if pending_pipeline_confirmation:
        steps["release_pipeline"] = {
            "status": "Pending",
            "message": "Waiting for DevOps confirmation to reuse the existing build pipeline.",
        }
    elif item.get("setup_pipeline") and reference_repo:
        try:
            pipeline_id = build_pipeline_result.get("id") if build_pipeline_result else None
            if not pipeline_id:
                raise RuntimeError(
                    "Build pipeline must be created or found before release pipeline cloning"
                )
            logger.info(
                "Starting release pipeline setup request_id=%s build_pipeline_id=%s build_pipeline_status=%s",
                request_id,
                pipeline_id,
                build_pipeline_result.get("status"),
            )
            steps["release_pipeline"] = create_release_pipeline(
                item.get("application_type", "H2H"),
                reference_repo,
                item["repository_name"],
                build_pipeline_result,
                azure_devops_pat,
            )
        except Exception as exc:
            logger.exception(
                "Release pipeline creation failed request_id=%s repository=%s",
                request_id,
                item.get("repository_name"),
            )
            steps["release_pipeline"] = {"status": "Failed", "message": str(exc)}
    elif item.get("setup_pipeline"):
        steps["release_pipeline"] = {
            "status": "Skipped",
            "message": "No reference repository was selected for release pipeline cloning",
        }
    else:
        steps["release_pipeline"] = {
            "status": "Skipped",
            "message": "Pipeline setup was disabled by DevOps",
        }

    statuses = [str(step.get("status") or "") for step in steps.values()]
    requires_confirmation = any(
        bool(step.get("requires_confirmation")) for step in steps.values()
    )
    if any(value == "Failed" for value in statuses):
        final_status = "Partially Completed"
    elif requires_confirmation or any(value in ("Pending", "Warning") for value in statuses):
        final_status = "Pending Action"
    elif statuses and all(
        value in ("Completed", "Skipped", "Already Exists") for value in statuses
    ):
        final_status = "Completed"
    else:
        final_status = "Pending Action"

    logger.info(
        "Provisioning finished request_id=%s status=%s steps=%s confirmation_required=%s",
        request_id,
        final_status,
        statuses,
        requires_confirmation,
    )
    return final_status, steps
