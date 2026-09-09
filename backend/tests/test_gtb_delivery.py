import unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.gtb_delivery import DeliveryInput, artifact_names, delivery_plan, router
from app.auth import current_user
from app.models import UserContext

class DeliveryTests(unittest.TestCase):
    def gtb(self, component="obp", **kwargs):
        return delivery_plan(DeliveryInput(application="GTB-Applications", component=component, vendor_branch="vendor-42", **kwargs))

    def test_obp_environment_parameter_and_runtime_branch(self):
        plan = self.gtb(environment="PREPRD")
        build = next(s for s in plan["steps"] if s["id"] == "build")
        self.assertEqual(build["pipeline"], "r2-obp-build-pipeline")
        self.assertEqual(build["payload"]["templateParameters"], {"Environment": "PREPRD"})
        self.assertEqual(build["payload"]["resources"]["repositories"]["self"]["refName"], "refs/heads/release/ppr")

    def test_obdx_runtime_override_and_moc_develop_ref(self):
        for component, ref in [("obdx", "refs/heads/release/prod"), ("moc", "refs/heads/develop")]:
            plan = self.gtb(component, environment="PROD", war_files="api.war;ui.WAR")
            build = next(s for s in plan["steps"] if s["id"] == "build")
            self.assertEqual(build["payload"]["resources"]["repositories"]["self"]["refName"], ref)
            self.assertEqual(build["payload"]["templateParameters"]["war_files"], "api ui")

    def test_code_pull_contract_and_list_only_stops(self):
        with patch.dict("os.environ", {"CODE_PULL_PIPELINE_NAME": "working-code-pull", "CODE_PULL_PIPELINE_ID": ""}):
            plan = self.gtb(list_only=True)
        self.assertEqual(len(plan["steps"]), 1)
        self.assertEqual(plan["steps"][0]["payload"]["templateParameters"], {"APP": "obp", "PROFINCH_BRANCH": "vendor-42", "LIST_ONLY": True})

    def test_collections_pipeline_mapping_and_boolean_contract(self):
        for country, suffix in [("Egypt", "-egypt"), ("UAE", "")]:
            plan = delivery_plan(DeliveryInput(application="Collections", component="vtcustomer", country=country, use_vendor_image=False))
            build = plan["steps"][0]
            self.assertEqual(build["pipeline"], "collections-customer-service"+suffix)
            self.assertIs(build["payload"]["templateParameters"]["useVendorImage"], False)
            self.assertFalse(plan["blockers"])
            self.assertEqual(plan["steps"][1]["id"], "release")

    def test_unknown_mapping_and_missing_image_block(self):
        with self.assertRaises(Exception): self.gtb("nonexistent")
        plan = delivery_plan(DeliveryInput(application="Collections", component="vtcustomer"))
        self.assertTrue(plan["blockers"])
        self.assertTrue(any("PR target" in b for b in self.gtb(environment="GOLD")["blockers"]))

    def test_artifact_none_and_kernel_no_invented_build(self):
        self.assertEqual(artifact_names("N/A"), "None")
        plan = self.gtb("obp-kernel")
        self.assertNotIn("build", [s["id"] for s in plan["steps"]])
        self.assertTrue(any("standalone" in b for b in plan["blockers"]))

    def test_api_authorization_and_schema(self):
        app = FastAPI(); app.include_router(router); client = TestClient(app)
        self.assertEqual(client.get("/gtb-agent/delivery/catalog").status_code, 401)
        app.dependency_overrides[current_user] = lambda: UserContext(username="ops@mashreq.com", role="devops")
        self.assertEqual(client.get("/gtb-agent/delivery/catalog").status_code, 200)
        self.assertEqual(client.post("/gtb-agent/delivery/plan", json={"application":"Collections", "component":"vtcustomer", "unknown":True}).status_code, 422)

if __name__ == "__main__": unittest.main()
