from __future__ import annotations

import time
from typing import Any

from .azure_devops import azdo_request
from .config import (
    AZDO_ORG,
    AZDO_PROJECT,
    KUBERNETES_PROVISIONING_PIPELINE_ID,
    KUBERNETES_PROVISIONING_POLL_SECONDS,
    KUBERNETES_PROVISIONING_TIMEOUT_SECONDS,
)
from .logging_config import get_logger

logger = get_logger("remote-kubernetes")


def provision_through_pipeline(item: dict, azure_devops_pat: str) -> dict[str, Any]:
    pipeline_id = KUBERNETES_PROVISIONING_PIPELINE_ID
    if pipeline_id <= 0:
        raise RuntimeError("KUBERNETES_PROVISIONING_PIPELINE_ID is not configured")

    target_cluster = (item.get("target_cluster") or "").strip()
    if not target_cluster:
        raise RuntimeError("Target Kubernetes service connection is required")

    parameters = {
        "requestId": item.get("id") or "devops-portal-request",
        "kubernetesServiceConnection": target_cluster,
        "namespace": item["namespace"],
        "createService": bool(item.get("create_service")),
        "serviceName": item["service_name"],
        "servicePort": int(item["service_port"]),
        "targetPort": int(item["service_port"]),
        "ingressName": item["ingress_name"],
        "ingressPath": item["ingress_path"],
        "ingressPathType": "ImplementationSpecific",
    }
    payload = {"templateParameters": parameters}

    logger.info(
        "Kubernetes target is not directly reachable; triggering provisioning pipeline "
        "request_id=%s target_cluster=%s pipeline_id=%s namespace=%s",
        item.get("id"),
        target_cluster,
        pipeline_id,
        item.get("namespace"),
    )
    code, body = azdo_request(
        "POST",
        f"_apis/pipelines/{pipeline_id}/runs?api-version=7.1",
        azure_devops_pat,
        payload,
    )
    if code not in (200, 201):
        raise RuntimeError(body.get("message", f"Unable to queue Kubernetes provisioning pipeline with HTTP {code}"))

    run_id = body.get("id")
    if not run_id:
        raise RuntimeError("Azure DevOps did not return a run ID for the Kubernetes provisioning pipeline")

    run_url = f"https://dev.azure.com/{AZDO_ORG}/{AZDO_PROJECT}/_build/results?buildId={run_id}"
    logger.info(
        "Kubernetes provisioning pipeline queued request_id=%s target_cluster=%s run_id=%s",
        item.get("id"),
        target_cluster,
        run_id,
    )

    deadline = time.monotonic() + KUBERNETES_PROVISIONING_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        status_code, run = azdo_request(
            "GET",
            f"_apis/pipelines/{pipeline_id}/runs/{run_id}?api-version=7.1",
            azure_devops_pat,
        )
        if status_code != 200:
            raise RuntimeError(run.get("message", f"Unable to read provisioning pipeline run {run_id}"))

        state = str(run.get("state") or "").lower()
        result = str(run.get("result") or "").lower()
        logger.debug(
            "Waiting for Kubernetes provisioning pipeline request_id=%s run_id=%s state=%s result=%s",
            item.get("id"),
            run_id,
            state,
            result,
        )
        if state == "completed":
            if result in {"succeeded", "succeededwithissues"}:
                logger.info(
                    "Kubernetes provisioning pipeline completed request_id=%s target_cluster=%s run_id=%s result=%s",
                    item.get("id"),
                    target_cluster,
                    run_id,
                    result,
                )
                return {
                    "status": "Completed",
                    "message": "Kubernetes resources provisioned successfully",
                    "run_id": run_id,
                    "target_cluster": target_cluster,
                    "url": run_url,
                }
            raise RuntimeError(f"Kubernetes provisioning pipeline run {run_id} completed with result {result or 'unknown'}")

        time.sleep(KUBERNETES_PROVISIONING_POLL_SECONDS)

    raise RuntimeError(
        f"Timed out after {KUBERNETES_PROVISIONING_TIMEOUT_SECONDS} seconds waiting for Kubernetes provisioning pipeline run {run_id}"
    )
