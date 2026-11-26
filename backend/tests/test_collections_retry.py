"""Regression tests for Collections retry orchestration (no Azure DevOps calls)."""
import copy
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app import deployment_runtime as runtime


class CollectionsRetryTests(unittest.TestCase):
    def setUp(self):
        self.row = {
            "id": "DM-test",
            "application_type": "Collections",
            "status": "Build Failed",
            "steps": {
                "owner_approval": {"status": "Approved"},
                "build": {"status": "Failed", "runs": [
                    {"run_id": 11, "pipeline_id": 101, "pipeline_name": "batch", "service": "vtbatch-01", "status": "Failed", "source_branch": "refs/heads/main", "parameters": {"vendorImage": "batch:original", "useVendorImage": True}},
                    {"run_id": 12, "pipeline_id": 102, "pipeline_name": "master", "service": "vtmaster", "status": "Running"},
                    {"run_id": 13, "pipeline_id": 103, "pipeline_name": "archival", "service": "vtarchival", "status": "Succeeded"},
                    {"run_id": 14, "pipeline_id": 104, "pipeline_name": "customer", "service": "vtcustomer", "status": "Failed", "parameters": {"vendorImage": "customer:original", "useVendorImage": True}},
                ]},
                "deployment": {"status": "Waiting", "runs": []},
            },
        }

    def test_running_takes_precedence_over_failed(self):
        runtime._update_build_status(self.row)
        self.assertEqual(self.row["steps"]["build"]["status"], "Running")

    def test_retry_only_selected_failed_run(self):
        original = copy.deepcopy(self.row["steps"]["build"]["runs"])
        with patch.object(runtime.dm, "_load", return_value=[self.row]), patch.object(runtime.dm, "_save"), patch.object(runtime.dm, "_update_progress"), patch.object(runtime, "_refresh_build_run", return_value=True), patch.object(runtime.dm, "_pipeline_run", return_value={"run_id": 21, "status": "Queued", "pipeline_id": 101, "pipeline_name": "batch"}) as queue:
            result = runtime.retry_collections_builds("DM-test", "tester", "mock-pat", {"run_ids": [11]})
            queue.assert_called_once_with("batch", original[0]["parameters"], "mock-pat", ref="refs/heads/main", pipeline_id=101)
            runs = result["steps"]["build"]["runs"]
            self.assertEqual(runs[0]["run_id"], 21)
            self.assertEqual(runs[0]["attempt_history"][0]["run_id"], 11)
            self.assertEqual(runs[1:], original[1:])
            self.assertEqual(result["steps"]["build"]["status"], "Running")
            self.assertEqual(len(result["retry_result"]["queued"]), 1)
            with self.assertRaises(HTTPException):
                runtime.retry_collections_builds("DM-test", "tester", "mock-pat", {"run_ids": [11]})
            self.assertEqual(queue.call_count, 1)

    def test_partial_queue_failure_preserves_accepted_retry(self):
        with patch.object(runtime.dm, "_load", return_value=[self.row]), patch.object(runtime.dm, "_save"), patch.object(runtime.dm, "_update_progress"), patch.object(runtime, "_refresh_build_run", return_value=True), patch.object(runtime.dm, "_pipeline_run", side_effect=[{"run_id": 21, "status": "Queued"}, HTTPException(502, "Queue rejected")]):
            result = runtime.retry_collections_builds("DM-test", "tester", "mock-pat", {"run_ids": [11, 14]})
            self.assertEqual(len(result["retry_result"]["queued"]), 1)
            self.assertEqual(len(result["retry_result"]["errors"]), 1)
            self.assertEqual(result["steps"]["build"]["runs"][0]["run_id"], 21)
            self.assertEqual(result["steps"]["build"]["runs"][3]["run_id"], 14)

    def test_running_run_cannot_be_retried(self):
        with patch.object(runtime.dm, "_load", return_value=[self.row]), patch.object(runtime.dm, "_pipeline_run") as queue:
            with self.assertRaises(HTTPException):
                runtime.retry_collections_builds("DM-test", "tester", "mock-pat", {"run_ids": [12]})
            queue.assert_not_called()

    def test_refresh_failure_prevents_queue(self):
        with patch.object(runtime.dm, "_load", return_value=[self.row]), patch.object(runtime.dm, "_save"), patch.object(runtime.dm, "_update_progress"), patch.object(runtime, "_refresh_build_run", return_value=False), patch.object(runtime.dm, "_pipeline_run") as queue:
            result = runtime.retry_collections_builds("DM-test", "tester", "mock-pat", {"run_ids": [11]})
            queue.assert_not_called()
            self.assertEqual(len(result["retry_result"]["errors"]), 1)


if __name__ == "__main__":
    unittest.main()
