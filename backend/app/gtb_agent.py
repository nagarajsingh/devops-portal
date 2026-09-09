"""Bounded, read-only GTB operations agent. No model or shell execution."""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from kubernetes import client
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import String, Text, select
from sqlalchemy.orm import Mapped, mapped_column

from .auth import require_devops
from .config import KUBERNETES_TARGETS, LOCAL_KUBERNETES_TARGET, NAMESPACE_ALLOWLIST
from .kubernetes_ops import load_k8s
from .models import UserContext
from .user_store import Base, session_factory

router = APIRouter(prefix="/gtb-agent", tags=["GTB operations agent"])
DNS = r"^[a-z0-9](?:[-a-z0-9]*[a-z0-9])?$"


class Scope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=80, pattern=DNS)
    application: Literal["GTB-Applications", "H2H", "Collections", "Native-Mobile", "Safenet"]
    cluster: str = Field(min_length=1, max_length=120)
    namespace: str = Field(min_length=1, max_length=63, pattern=DNS)
    environment: str = Field(min_length=1, max_length=40)


class RunInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope_id: str = Field(min_length=1, max_length=80, pattern=DNS)
    objective: Literal["health", "connectivity", "readiness"] = "health"


class AgentRun(Base):
    __tablename__ = "gtb_agent_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_by: Mapped[str] = mapped_column(String(255), index=True)
    created_at: Mapped[str] = mapped_column(String(40), index=True)
    report: Mapped[str] = mapped_column(Text)


def scopes() -> list[Scope]:
    try:
        raw = json.loads(os.getenv("GTB_AGENT_SCOPES", "[]"))
        if not isinstance(raw, list):
            raise ValueError("Expected list")
        values = [Scope.model_validate(row) for row in raw]
        if len({s.id for s in values}) != len(values):
            raise ValueError("Duplicate scope IDs")
        for scope in values:
            if scope.cluster not in KUBERNETES_TARGETS:
                raise ValueError("Unknown cluster")
            if "all" not in [n.lower() for n in NAMESPACE_ALLOWLIST] and scope.namespace not in NAMESPACE_ALLOWLIST:
                raise ValueError("Namespace outside allowlist")
        return values
    except (ValueError, TypeError, ValidationError) as exc:
        raise HTTPException(503, "GTB_AGENT_SCOPES is invalid; verify configured clusters and allowed namespaces") from exc


def collect(tool: str, scope: Scope) -> dict:
    """Return only allowlisted status fields; never secrets, logs, env or messages."""
    if scope.cluster != LOCAL_KUBERNETES_TARGET:
        raise RuntimeError("Live diagnostics are not configured for this remote cluster")
    load_k8s()
    configuration = client.Configuration.get_default_copy()
    configuration.retries = 0
    with client.ApiClient(configuration) as api_client:
        core, apps = client.CoreV1Api(api_client), client.AppsV1Api(api_client)
        operations = {
            "pods": core.list_namespaced_pod,
            "deployments": apps.list_namespaced_deployment,
            "storage": core.list_namespaced_persistent_volume_claim,
            "services": core.list_namespaced_service,
            "endpoints": client.DiscoveryV1Api(api_client).list_namespaced_endpoint_slice,
        }
        response = operations[tool](scope.namespace, limit=200, _request_timeout=(3, 8))
        rows = []
        for item in response.items:
            row = {"name": item.metadata.name}
            if tool == "pods":
                statuses = (item.status.init_container_statuses or []) + (item.status.container_statuses or [])
                reasons = []
                for status in statuses:
                    for state in (status.state, status.last_state):
                        if state:
                            for detail in (state.waiting, state.terminated):
                                if detail and detail.reason and (state is status.state or detail.reason == "OOMKilled"):
                                    reasons.append(detail.reason)
                row.update(phase=item.status.phase, ready=any(c.type == "Ready" and c.status == "True" for c in item.status.conditions or []),
                           restarts=sum(s.restart_count or 0 for s in statuses), reasons=sorted(set(reasons)))
            elif tool == "deployments":
                row.update(desired=item.spec.replicas if item.spec.replicas is not None else 1,
                           available=item.status.available_replicas or 0, updated=item.status.updated_replicas or 0,
                           generation=item.metadata.generation or 0, observed=item.status.observed_generation or 0)
            elif tool == "storage":
                row.update(phase=item.status.phase)
            elif tool == "services":
                row.update(type=item.spec.type, selector=bool(item.spec.selector))
            elif tool == "endpoints":
                row.update(service=(item.metadata.labels or {}).get("kubernetes.io/service-name", ""),
                           ready=sum(e.conditions is not None and e.conditions.ready is True for e in item.endpoints or []))
            rows.append(row)
        return {"rows": rows, "truncated": bool(response.metadata and response.metadata._continue)}


def investigate(scope: Scope, objective: str, collector=collect) -> dict:
    report = {"mode": "rule-based", "scope": scope.model_dump(), "objective": objective,
              "status": "completed", "assessment": "no_findings", "trace": [], "findings": [],
              "limitations": ["Point-in-time infrastructure checks do not prove transaction health or authorize a release."]}
    evidence = {}

    def run(tool):
        at = datetime.now(timezone.utc).isoformat()
        try:
            result = collector(tool, scope)
            evidence[tool] = result["rows"]
            report["trace"].append({"tool": tool, "at": at, "status": "completed", "evidence": result["rows"]})
            if result["truncated"]:
                report["limitations"].append(f"{tool}: first 200 resources only; evidence is incomplete.")
                report["status"] = "partial"
        except Exception:
            # Exception bodies may contain credentials or infrastructure details.
            report["trace"].append({"tool": tool, "at": at, "status": "unavailable", "evidence": []})
            report["limitations"].append(f"{tool}: unavailable; verify cluster connectivity and read permissions.")
            report["status"] = "partial"

    def finding(code, severity, resource, detail, recommendation, tool):
        report["findings"].append({"code": code, "severity": severity, "resource": resource,
                                   "detail": detail, "recommendation": recommendation, "evidence_tool": tool})

    run("pods")
    run("deployments")
    pods = evidence.get("pods", [])
    if "pods" in evidence and not pods:
        finding("no-pods", "warning", scope.namespace, "No pods were observed.", "Confirm the intended workload and namespace before proceeding.", "pods")
    for pod in pods:
        reasons = set(pod["reasons"])
        if "OOMKilled" in reasons:
            finding("oom", "warning", pod["name"], "Current or previous container termination was OOMKilled.", "Compare memory usage with container limits and JVM heap; review workload growth before changing limits.", "pods")
        if reasons & {"ImagePullBackOff", "ErrImagePull"}:
            finding("image-pull", "critical", pod["name"], "A container image could not be pulled.", "Check the image tag, registry availability and image-pull credential configuration through the approved workflow.", "pods")
        if "CrashLoopBackOff" in reasons:
            finding("crash-loop", "critical", pod["name"], "A container is repeatedly failing to start.", "Review previous container logs in the approved logging tool, startup configuration and probes.", "pods")
        if pod["phase"] not in {"Succeeded"} and not pod["ready"]:
            finding("pod-not-ready", "warning", pod["name"], f"Pod is not ready (phase: {pod['phase']}).", "Inspect scheduling and readiness probes; correlate with the deployment rollout.", "pods")
    for deployment in evidence.get("deployments", []):
        if deployment["available"] < deployment["desired"] or deployment["updated"] < deployment["desired"] or deployment["observed"] < deployment["generation"]:
            finding("rollout-incomplete", "critical", deployment["name"], "Deployment has not reached its desired rollout state.", "Review rollout events and the deployed image. Use Deployment Management for any approved rollback.", "deployments")
    # Follow-up tool choice depends on observations and the operator's objective.
    if any(p["phase"] == "Pending" for p in pods) or objective == "readiness":
        run("storage")
        for pvc in evidence.get("storage", []):
            if pvc["phase"] != "Bound":
                finding("pvc-unbound", "critical", pvc["name"], f"PVC phase: {pvc['phase']}.", "Check StorageClass, PV availability, CSI health and binding events; do not delete the claim.", "storage")
    if objective in {"connectivity", "readiness"}:
        run("services")
        run("endpoints")
        if "services" in evidence and "endpoints" in evidence:
            for service in evidence["services"]:
                if service["type"] != "ExternalName" and service["selector"]:
                    ready = sum(e["ready"] for e in evidence["endpoints"] if e["service"] == service["name"])
                    if not ready:
                        finding("no-ready-endpoints", "critical", service["name"], "No explicitly ready EndpointSlice endpoints were observed.", "Check Service selectors, pod readiness and target ports before investigating ingress or cross-cluster routing.", "endpoints")
    if report["findings"]:
        report["assessment"] = "attention_required"
    elif report["status"] == "partial":
        report["assessment"] = "unknown"
    if not any(t["status"] == "completed" for t in report["trace"]):
        report["status"] = "unavailable"
    return report


@router.get("/scopes")
def list_scopes(_: UserContext = Depends(require_devops)):
    return [scope.model_dump() for scope in scopes()]


@router.post("/runs", status_code=201)
def create_run(payload: RunInput, user: UserContext = Depends(require_devops)):
    scope = next((s for s in scopes() if s.id == payload.scope_id), None)
    if not scope:
        raise HTTPException(404, "Configured application scope not found")
    # Verify persistence before collecting evidence. No Kubernetes writes occur.
    factory = session_factory()
    with factory() as db:
        db.execute(select(AgentRun.id).limit(1))
    report = investigate(scope, payload.objective)
    report.update(id=str(uuid.uuid4()), created_by=user.username, created_at=datetime.now(timezone.utc).isoformat())
    with factory() as db:
        db.add(AgentRun(id=report["id"], created_by=user.username, created_at=report["created_at"], report=json.dumps(report)))
        db.commit()
    return report


@router.get("/runs")
def history(user: UserContext = Depends(require_devops)):
    factory = session_factory()
    with factory() as db:
        query = select(AgentRun).where(AgentRun.created_by == user.username).order_by(AgentRun.created_at.desc()).limit(25)
        return [json.loads(row.report) for row in db.scalars(query)]
