from __future__ import annotations

import base64
import io
import json
import time
import urllib.request
import zipfile
from typing import Any

from .azure_devops import azdo_request
from .config import (
    AZDO_ORG,
    DATASOURCE_AZURE_DEVOPS_PROJECT,
    DATASOURCE_PIPELINE_ID,
    DATASOURCE_PIPELINE_POLL_SECONDS,
    DATASOURCE_PIPELINE_TIMEOUT_SECONDS,
    DATASOURCE_PREVIEW_ARTIFACT_NAME,
    DATASOURCE_RUNTIME_API_URL,
)
from .logging_config import get_logger

logger = get_logger("datasource-pipeline")


def _download_bytes(url: str, pat: str) -> bytes:
    token = base64.b64encode(f":{pat.strip()}".encode()).decode()
    request = urllib.request.Request(
        url,
        method="GET",
        headers={"Authorization": f"Basic {token}"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def _download_plan(run_id: int, pat: str) -> dict[str, Any]:
    code, body = azdo_request(
        "GET",
        f"_apis/build/builds/{run_id}/artifacts?artifactName={DATASOURCE_PREVIEW_ARTIFACT_NAME}&api-version=7.1",
        pat,
        project=DATASOURCE_AZURE_DEVOPS_PROJECT,
    )
    if code != 200:
        raise RuntimeError(
            body.get(
                "message",
                f"Unable to read datasource preview artifact with HTTP {code}",
            )
        )

    download_url = ((body.get("resource") or {}).get("downloadUrl") or "").strip()
    if not download_url:
        raise RuntimeError(
            f"Datasource artifact {DATASOURCE_PREVIEW_ARTIFACT_NAME} does not contain a download URL"
        )

    archive_bytes = _download_bytes(download_url, pat)
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        candidates = [
            name
            for name in archive.namelist()
            if name.endswith("datasource-plan.json")
        ]
        if not candidates:
            raise RuntimeError("datasource-plan.json was not found in the Azure DevOps artifact")
        return json.loads(archive.read(candidates[0]).decode("utf-8"))


def run_datasource_pipeline(
    *,
    action: str,
    request_id: str,
    environment: dict[str, Any],
    operation: dict[str, Any],
    azure_devops_pat: str,
) -> dict[str, Any]:
    pipeline_id = DATASOURCE_PIPELINE_ID
    if pipeline_id <= 0:
        raise RuntimeError(
            "DATASOURCE_PIPELINE_ID is not configured. Create the datasource-management Azure DevOps pipeline and configure its ID."
        )

    if action not in {"preview", "apply"}:
        raise RuntimeError(f"Unsupported datasource pipeline action: {action}")

    parameters = {
        "action": action,
        "requestId": request_id,
        "application": environment["application"],
        "environment": environment["environment"],
        "instanceName": environment["instance_name"],
        "agentPool": environment["agent_pool"],
        "adminHost": environment["admin_host"],
        "adminPort": str(environment["admin_port"]),
        "sshPort": str(environment["ssh_port"]),
        "basePath": environment.get("base_path") or "",
        "domainName": environment["domain_name"],
        "wlstPath": environment["wlst_path"],
        "sshUsername": environment["ssh_username"],
        "weblogicUsername": environment["weblogic_username"],
        "referenceEntity": operation["reference_entity"],
        "targetEntity": operation["target_entity"],
        "datasourceType": operation["datasource_type"],
        "dbHost": operation["db_host"],
        "dbPort": str(operation["db_port"]),
        "serviceId": operation["service_id"],
        "schemaUsername": operation["schema_username"],
        "runtimeApiUrl": DATASOURCE_RUNTIME_API_URL,
    }

    if operation["datasource_type"] == "gridlink":
        parameters["onsNodes"] = str(operation.get("ons_nodes") or "")

    logger.info(
        "Queueing datasource pipeline action=%s request_id=%s application=%s environment=%s reference_entity=%s target_entity=%s project=%s pipeline_id=%s",
        action,
        request_id,
        environment["application"],
        environment["environment"],
        operation["reference_entity"],
        operation["target_entity"],
        DATASOURCE_AZURE_DEVOPS_PROJECT,
        pipeline_id,
    )
    code, body = azdo_request(
        "POST",
        f"_apis/pipelines/{pipeline_id}/runs?api-version=7.1",
        azure_devops_pat,
        {"templateParameters": parameters},
        project=DATASOURCE_AZURE_DEVOPS_PROJECT,
    )
    if code not in (200, 201):
        raise RuntimeError(
            body.get(
                "message",
                f"Unable to queue datasource pipeline with HTTP {code}",
            )
        )

    run_id = body.get("id")
    if not run_id:
        raise RuntimeError("Azure DevOps did not return a run ID for the datasource pipeline")

    run_url = (
        f"https://dev.azure.com/{AZDO_ORG}/{DATASOURCE_AZURE_DEVOPS_PROJECT}/_build/results?buildId={run_id}"
    )
    deadline = time.monotonic() + DATASOURCE_PIPELINE_TIMEOUT_SECONDS

    while time.monotonic() < deadline:
        status_code, run = azdo_request(
            "GET",
            f"_apis/pipelines/{pipeline_id}/runs/{run_id}?api-version=7.1",
            azure_devops_pat,
            project=DATASOURCE_AZURE_DEVOPS_PROJECT,
        )
        if status_code != 200:
            raise RuntimeError(
                run.get(
                    "message",
                    f"Unable to read datasource pipeline run {run_id}",
                )
            )

        state = str(run.get("state") or "").lower()
        result = str(run.get("result") or "").lower()
        if state == "completed":
            if result not in {"succeeded", "succeededwithissues"}:
                raise RuntimeError(
                    f"Datasource pipeline run {run_id} completed with result {result or 'unknown'}"
                )
            plan = _download_plan(run_id, azure_devops_pat)
            logger.info(
                "Datasource pipeline completed action=%s request_id=%s run_id=%s result=%s",
                action,
                request_id,
                run_id,
                result,
            )
            return {
                "pipeline_id": pipeline_id,
                "run_id": run_id,
                "run_url": run_url,
                "plan": plan,
                "result": result,
            }

        time.sleep(DATASOURCE_PIPELINE_POLL_SECONDS)

    raise RuntimeError(
        f"Timed out after {DATASOURCE_PIPELINE_TIMEOUT_SECONDS} seconds waiting for datasource pipeline run {run_id}"
    )
