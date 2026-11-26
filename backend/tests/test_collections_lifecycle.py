"""Regression tests for non-destructive extraction and early release discovery."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from app import azure_releases as releases
from app import deployment_runtime as runtime


class CollectionsLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.row = {
            "id": "DM-lifecycle-test", "application_type": "Collections",
            "country": "UAE", "deployment_environment": "UAT",
            "status": "Build Running", "progress_percent": 60, "extracted": True,
            "collections_items": [{"service": "vtmaster", "vendor_image": "reviewed:original", "selected": True}],
            "steps": {
                "owner_approval": {"status": "Approved"},
                "devops_review": {"status": "Completed"},
                "build": {"status": "Running", "runs": [
                    {"run_id": 11, "pipeline_id": 101, "service": "vtmaster", "status": "Succeeded"},
                    {"run_id": 12, "pipeline_id": 102, "service": "vtcustomer", "status": "Running"},
                ]},
                "deployment": {"status": "Waiting", "runs": []},
            },
        }

    def release(self, build_id=11):
        return {"release_id": 111, "url": "https://example.test/release/111",
                "source_build": {"run_id": build_id, "pipeline_id": 101},
                "environments": [{"name": "UAT", "status": "succeeded"}],
                "status": "Succeeded"}

    def test_reextract_preserves_reviewed_inputs_and_all_lifecycle_steps(self):
        self.row["steps"]["deployment"] = {"status": "Partial", "runs": [self.release()]}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "release.txt"
            path.write_text("release document", encoding="utf-8")
            self.row["document_path"] = str(path)
            original = copy.deepcopy(self.row)
            with patch.object(runtime.dm, "_load", return_value=[self.row]), patch.object(runtime.dm, "_save"), patch.object(runtime.dm, "_structured_extract", return_value={"collections_items": [{"service": "vtmaster", "vendor_image": "fresh:tag"}]}):
                result = runtime.reextract_document(self.row["id"], "tester")
            for step in ("owner_approval", "devops_review", "build", "deployment"):
                self.assertEqual(result["steps"][step], original["steps"][step])
            self.assertEqual(result["status"], original["status"])
            self.assertEqual(result["progress_percent"], 60)
            self.assertEqual(result["collections_items"], original["collections_items"])
            self.assertEqual(result["latest_extraction"]["data"]["collections_items"][0]["vendor_image"], "fresh:tag")

    def test_partial_release_discovered_before_all_builds_finish(self):
        with patch.object(runtime.dm, "_load", return_value=[self.row]), patch.object(runtime.dm, "_save"), patch.object(runtime, "_refresh_build_run", return_value=True), patch.object(runtime, "discover_collections_releases", return_value=([self.release()], [])) as discover:
            result = runtime.refresh_status(self.row["id"], "mock-pat", "tester")
            discover.assert_called_once()
        self.assertEqual(result["steps"]["deployment"]["runs"][0]["source_build"]["run_id"], 11)
        self.assertEqual(result["steps"]["deployment"]["status"], "Partial")
        self.assertEqual(result["status"], "Build Running")
        self.assertEqual(result["progress_percent"], 60)

    def test_missing_second_release_prevents_completion(self):
        self.row["steps"]["build"]["runs"][1]["status"] = "Succeeded"
        with patch.object(runtime, "discover_collections_releases", return_value=([self.release()], [])):
            runtime._sync_collections_releases(self.row, "mock-pat")
        self.assertEqual(self.row["steps"]["deployment"]["status"], "Discovering")

    def test_completed_target_for_every_build_allows_completion(self):
        self.row["steps"]["build"]["runs"][1]["status"] = "Succeeded"
        second = {**self.release(12), "release_id": 112}
        with patch.object(runtime, "discover_collections_releases", return_value=([self.release(), second], [])):
            runtime._sync_collections_releases(self.row, "mock-pat")
        self.assertEqual(self.row["steps"]["deployment"]["status"], "Succeeded")

    def test_existing_release_link_survives_api_failure(self):
        self.row["steps"]["deployment"]["runs"] = [self.release()]
        with patch.object(releases, "azdo_release_request", return_value=(503, {})), patch.object(releases, "discover_release_for_build") as search:
            runs, missing = releases.discover_collections_releases(self.row, "mock-pat")
        search.assert_not_called()
        self.assertEqual(runs[0]["url"], self.release()["url"])
        self.assertTrue(runs[0]["refresh_stale"])
        self.assertEqual(len(missing), 1)

    def test_retry_allowed_when_other_service_has_release(self):
        self.row["steps"]["build"]["runs"][1].update(status="Failed", pipeline_name="customer", parameters={"vendorImage": "customer:tag", "useVendorImage": True})
        self.row["steps"]["deployment"] = {"status": "Partial", "runs": [self.release()]}
        with patch.object(runtime.dm, "_load", return_value=[self.row]), patch.object(runtime.dm, "_save"), patch.object(runtime, "_refresh_build_run", return_value=True), patch.object(runtime.dm, "_pipeline_run", return_value={"run_id": 13, "status": "Queued"}):
            result = runtime.retry_collections_builds(self.row["id"], "tester", "mock-pat", {"run_ids": [12]})
        self.assertEqual(result["steps"]["build"]["runs"][1]["run_id"], 13)
        self.assertEqual(result["steps"]["deployment"]["runs"][0]["release_id"], 111)

    def test_completion_blocked_if_builds_still_running(self):
        self.row["steps"]["deployment"]["status"] = "Succeeded"
        with patch.object(runtime.dm, "_load", return_value=[self.row]):
            with self.assertRaises(HTTPException):
                runtime.complete_deployment_request(self.row["id"], "tester", {"comment": "done"})


if __name__ == "__main__":
    unittest.main()
