"""Reviewable delivery plans derived from Collections-Dashboard contracts.

Planning is side-effect free: this module never queues a pipeline, merges a PR,
creates a release or changes a pipeline definition.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .auth import require_devops
from .models import UserContext

router = APIRouter(prefix="/gtb-agent/delivery", tags=["GTB delivery planner"])
MAPPINGS = Path(__file__).with_name("gtb_reference")
ENV_BRANCHES = {"R2": "release/r2", "R2UAT": "release/uat", "PREPRD": "release/ppr", "R2TRAIN": "release/train", "PROD": "release/prod", "GOLD": "release/gold"}
PR_ENVS = {"R2UAT": "r2uat", "PREPRD": "ppr", "PROD": "prod"}


def mapping(name: str) -> dict:
    return json.loads((MAPPINGS / f"{name}_mapping.json").read_text())


class DeliveryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    application: Literal["GTB-Applications", "Collections"]
    component: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9-]+$")
    environment: Literal["R2", "R2UAT", "PREPRD", "R2TRAIN", "PROD", "GOLD"] = "R2UAT"
    country: Literal["Egypt", "UAE"] = "Egypt"
    vendor_branch: str = Field(default="", max_length=200)
    build_branch: str = Field(default="release/uat", min_length=1, max_length=200)
    war_files: str = Field(default="None", max_length=2000)
    jar_files: str = Field(default="None", max_length=2000)
    deploy_type: str = Field(default="Regular", min_length=1, max_length=80)
    vendor_image: str = Field(default="", max_length=500)
    use_vendor_image: bool = True
    list_only: bool = False

    @field_validator("vendor_branch", "build_branch", "deploy_type", "vendor_image")
    @classmethod
    def clean(cls, value):
        if any(ord(c) < 32 for c in value):
            raise ValueError("Control characters are not allowed")
        return value.strip()


def artifact_names(value: str) -> str:
    # Same normalization as reference azure_devops.normalize_artifact_names.
    normalized = value.replace(";", ",").replace(":", ",").replace("\n", ",").replace("\t", ",")
    parts = []
    for item in normalized.split(","):
        item = item.strip().replace(".war", "").replace(".jar", "").replace(".WAR", "").replace(".JAR", "").strip()
        if item and item.lower() not in {"none", "no", "na", "n/a"}:
            parts.append(item)
    return " ".join(parts) or "None"


def pipeline_payload(ref, parameters):
    return {"resources": {"repositories": {"self": {"refName": ref if ref.startswith("refs/heads/") else f"refs/heads/{ref}"}}}, "templateParameters": parameters}


def delivery_plan(p: DeliveryInput) -> dict:
    steps, blockers = [], []
    reference = "nagarajsingh/Collections-Dashboard@feature/ui-enhancements"
    if p.application == "Collections":
        pipelines = mapping("pipeline").get(p.country, {})
        pipeline = pipelines.get(p.component)
        if not pipeline:
            raise HTTPException(422, "No Collections pipeline mapping for this country and component")
        if p.use_vendor_image and not p.vendor_image:
            blockers.append("A vendor image is required when useVendorImage is enabled.")
        steps.append({"id": "build", "title": "Run the existing Collections service pipeline", "depends_on": [],
                      "pipeline": pipeline, "payload": pipeline_payload(os.getenv("AZDO_BRANCH", "refs/heads/master"), {"vendorImage": p.vendor_image, "useVendorImage": p.use_vendor_image}),
                      "gate": "Review the selected country, service and vendor image in Deployment Management."})
    else:
        build = mapping("build_pipeline").get(p.component)
        repo = mapping("repo").get(p.component)
        if not repo:
            raise HTTPException(422, "No GTB repository mapping for this component")
        if not p.vendor_branch:
            blockers.append("A vendor branch is required for code pull.")
        code_pull = os.getenv("CODE_PULL_PIPELINE_ID") or os.getenv("CODE_PULL_PIPELINE_NAME", "")
        if not code_pull:
            blockers.append("Configure CODE_PULL_PIPELINE_ID or CODE_PULL_PIPELINE_NAME; no pipeline name is guessed.")
        steps.append({"id": "code-pull", "title": "Run the existing vendor code-pull pipeline", "depends_on": [], "pipeline": code_pull,
                      "payload": pipeline_payload(os.getenv("AZDO_BRANCH", "refs/heads/master"), {
                          os.getenv("CODE_PULL_PARAM_APPLICATION", "APP"): p.component,
                          os.getenv("CODE_PULL_PARAM_BRANCH", "PROFINCH_BRANCH"): p.vendor_branch,
                          os.getenv("CODE_PULL_PARAM_LIST_ONLY", "LIST_ONLY"): p.list_only}),
                      "gate": "Review the vendor branch and list-only setting before execution."})
        if p.list_only:
            return {"mode": "plan-only", "reference": reference, "application": p.application, "component": p.component,
                    "blockers": blockers, "steps": steps, "notes": ["List-only stops after code pull; no PR, build or release is planned."]}
        target = mapping("pr_branch").get(p.component, {}).get(PR_ENVS.get(p.environment, p.environment.lower()))
        if not target:
            blockers.append(f"No reference PR target mapping for {p.component}/{p.environment}; an administrator must define it.")
        steps.append({"id": "pull-request", "title": "Review and merge the vendor-code pull request", "depends_on": ["code-pull"],
                      "repository": repo, "target_branch": target,
                      "source_branch_template": f"profinch/{p.vendor_branch}-{{successful_code_pull_build_number}}-{p.component}",
                      "gate": "Verify the successful code-pull result and actual source branch, reuse any existing PR, and require repository branch policies. Never auto-merge."})
        if build:
            context = {"build_branch": p.build_branch, "environment": p.environment, "war_files": artifact_names(p.war_files), "jar_files": artifact_names(p.jar_files), "deploy_type": p.deploy_type}
            params = {key: value.format_map(context) if isinstance(value, str) else value for key, value in build["parameters"].items()}
            if "branch" in params and target and p.build_branch.removeprefix("refs/heads/") != target:
                blockers.append("Build source branch differs from the mapped PR target; reconcile the branches before execution.")
            # Reference sitecustomize.py overrides these three pipeline refs at runtime.
            ref = ENV_BRANCHES[p.environment] if p.component in {"obp", "obtf", "obdx"} else build["pipeline_version_ref"]
            steps.append({"id": "build", "title": "Run the mapped GTB build pipeline", "depends_on": ["pull-request"], "pipeline": build["pipeline_name"],
                          "payload": pipeline_payload(ref, params), "gate": "Verify the reviewed PR is merged and the build branch contains the intended changes. YAML branch and source branch are separate settings."})
        else:
            blockers.append("No standalone build mapping exists for this component; use its parent application workflow after code-pull and PR review.")
    if any(step["id"] == "build" for step in steps):
        steps.append({"id": "release", "title": "Discover the release for the successful build", "depends_on": ["build"],
                      "match": "artifact build ID must equal the successful build run ID", "gate": "Respect existing release triggers and environment approvals. If no exact artifact match is found, stop and investigate; do not substitute the latest release."})
    return {"mode": "plan-only", "reference": reference, "application": p.application, "component": p.component,
            "blockers": blockers, "steps": steps, "notes": ["No pipeline was queued and no release was created.", "Existing Deployment Management remains the execution surface. Compare these payloads before execution; its generic GTB adapter has not been replaced.", "Pipeline completion alone is not deployment success; verify the intended release environment and application health."]}


@router.get("/catalog")
def catalog(_: UserContext = Depends(require_devops)):
    return {"gtb_components": sorted(mapping("repo")), "collections_components": {country: sorted(rows) for country, rows in mapping("pipeline").items()}, "environments": list(ENV_BRANCHES)}


@router.post("/plan")
def plan(payload: DeliveryInput, _: UserContext = Depends(require_devops)):
    return delivery_plan(payload)
