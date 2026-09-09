import json
import unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app import gtb_agent as agent
from app.auth import current_user
from app.models import UserContext

SCOPE = agent.Scope(id="gtb-uat", application="GTB-Applications", cluster="local", namespace="gtb-uat", environment="UAT")
POD = dict(name="api-1", phase="Running", ready=True, restarts=0, reasons=[])
DEPLOYMENT = dict(name="api", desired=1, available=1, updated=1, generation=1, observed=1)

class AgentTests(unittest.TestCase):
    def collector(self, rows):
        return lambda tool, scope: {"rows": rows.get(tool, []), "truncated": False}

    def test_pending_pod_triggers_storage_followup(self):
        rows = {"pods": [{**POD, "phase": "Pending", "ready": False}], "storage": [{"name": "data", "phase": "Pending"}]}
        result = agent.investigate(SCOPE, "health", self.collector(rows))
        self.assertEqual([t["tool"] for t in result["trace"]], ["pods", "deployments", "storage"])
        self.assertIn("pvc-unbound", [f["code"] for f in result["findings"]])

    def test_healthy_does_not_run_unnecessary_tools(self):
        result = agent.investigate(SCOPE, "health", self.collector({"pods": [POD], "deployments": [DEPLOYMENT]}))
        self.assertEqual(result["assessment"], "no_findings")
        self.assertEqual(len(result["trace"]), 2)

    def test_failed_tools_are_unknown_and_do_not_leak_errors(self):
        def failed(*args): raise RuntimeError("secret-token")
        result = agent.investigate(SCOPE, "readiness", failed)
        self.assertEqual(result["assessment"], "unknown")
        self.assertEqual(result["status"], "unavailable")
        self.assertNotIn("secret-token", json.dumps(result))
        self.assertFalse(result["findings"])

    def test_failed_endpoints_do_not_invent_connectivity_failure(self):
        def collector(tool, scope):
            if tool == "endpoints": raise RuntimeError()
            return {"rows": {"pods": [POD], "services": [{"name": "api", "selector": True, "type": "ClusterIP"}]}.get(tool, []), "truncated": False}
        result = agent.investigate(SCOPE, "connectivity", collector)
        self.assertEqual(result["assessment"], "unknown")
        self.assertFalse(result["findings"])

    def test_zero_ready_endpoints(self):
        rows = {"pods": [POD], "services": [{"name": "api", "selector": True, "type": "ClusterIP"}]}
        result = agent.investigate(SCOPE, "connectivity", self.collector(rows))
        self.assertIn("no-ready-endpoints", [f["code"] for f in result["findings"]])

    def test_unobserved_generation_is_incomplete_rollout(self):
        result = agent.investigate(SCOPE, "health", self.collector({"pods": [POD], "deployments": [{**DEPLOYMENT, "observed": 0}]}))
        self.assertIn("rollout-incomplete", [f["code"] for f in result["findings"]])

    def test_namespace_allowlist_fails_closed(self):
        with patch.dict("os.environ", {"GTB_AGENT_SCOPES": json.dumps([SCOPE.model_dump()])}), patch.object(agent, "KUBERNETES_TARGETS", ["local"]), patch.object(agent, "NAMESPACE_ALLOWLIST", ["other"]):
            with self.assertRaises(agent.HTTPException): agent.scopes()

    def test_truncated_evidence_is_not_healthy(self):
        result = agent.investigate(SCOPE, "health", lambda *a: {"rows": [POD] if a[0] == "pods" else [], "truncated": True})
        self.assertEqual(result["assessment"], "unknown")

    def test_remote_never_uses_local_credentials(self):
        with patch.object(agent, "load_k8s") as load, patch.object(agent, "LOCAL_KUBERNETES_TARGET", "different"):
            with self.assertRaises(RuntimeError): agent.collect("pods", SCOPE)
            load.assert_not_called()

    def test_api_authorization_persistence_and_history_isolation(self):
        app = FastAPI(); app.include_router(agent.router)
        client = TestClient(app)
        self.assertEqual(client.get("/gtb-agent/runs").status_code, 401)
        user = UserContext(username="dev@mashreq.com", role="developer")
        app.dependency_overrides[current_user] = lambda: user
        self.assertEqual(client.get("/gtb-agent/scopes").status_code, 403)
        user = UserContext(username="ops@mashreq.com", role="devops")
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        agent.AgentRun.__table__.create(engine)
        with patch.object(agent, "session_factory", return_value=sessionmaker(bind=engine)), patch.object(agent, "scopes", return_value=[SCOPE]), patch.object(agent, "investigate", return_value={"assessment": "unknown"}):
            self.assertEqual(client.post("/gtb-agent/runs", json={"scope_id":"unconfigured"}).status_code, 404)
            self.assertEqual(client.post("/gtb-agent/runs", json={"scope_id":SCOPE.id}).status_code, 201)
            self.assertEqual(len(client.get("/gtb-agent/runs").json()), 1)
            user = UserContext(username="other@mashreq.com", role="devops")
            self.assertEqual(client.get("/gtb-agent/runs").json(), [])
        engine.dispose()

if __name__ == "__main__": unittest.main()
