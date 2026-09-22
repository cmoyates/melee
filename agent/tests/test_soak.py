import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from melee_agent.soak import assess_run, run_soak


class SoakTests(unittest.TestCase):
    def assess(self, mode, **changes):
        root = Path(tempfile.mkdtemp(prefix="jev-soak-test-"))
        summary = {"run_id": "fixture", "status": "captured", "reason": "timeout", "worker_stopped": True,
            "emulator_stopped": True, "neutralized": True, "provider_contacted": False,
            "processes": {"worker": {"exit_code": 0}}, "fault_injection": {"counts": {mode: 1}, "events": []},
            "async_policy": {"bridge": {"provider": {"simulation_only": True, "external_http_calls": 0,
                "attempts": [], "max_requests": 6, "health_events": []}}}}
        summary.update(changes)
        (root / "summary.json").write_text(json.dumps(summary))
        if mode != "network":
            (root / "fault-injected.json").write_text(json.dumps({"fault": mode, "monotonic_ns": 1_000_000_000}))
        with patch("melee_agent.soak.inspect_policy", return_value={"status": "pass", "game_frames": 100}):
            return assess_run(root, mode, 2_000_000_000)

    def test_terminal_watchdog_requires_actual_owned_process_cleanup(self):
        passing = self.assess("controller_stall", status="incomplete", reason="state_stalled")
        self.assertEqual(passing["status"], "pass")
        failed = self.assess("controller_stall", status="incomplete", reason="state_stalled", emulator_stopped=False)
        self.assertIn("owned_process_not_stopped", failed["errors"])
        failed = self.assess("controller_stall", status="incomplete", reason="timeout")
        self.assertIn("watchdog_did_not_stop_stall", failed["errors"])

    def test_worker_death_preserves_unknown_neutralization_instead_of_claiming_success(self):
        report = self.assess("worker_death", status="incomplete", reason="worker_error", neutralized=False,
            processes={"worker": {"exit_code": -9}}, async_policy={})
        self.assertEqual(report["status"], "pass")
        self.assertFalse(report["neutralized"])
        self.assertTrue(report["neutralization_unavailable_due_to_worker_death"])

    def test_logger_failure_requires_supplement_and_drain(self):
        report = self.assess("logger_stall", status="incomplete", reason="worker_error",
            failure_reason="recorder_queue_full", recorder={"unwritten": 0}, last_unrecorded_record={"fixture": True})
        self.assertEqual(report["status"], "pass")
        failed = self.assess("logger_stall", status="incomplete", reason="worker_error",
            failure_reason="recorder_queue_full", recorder={"unwritten": 1})
        self.assertIn("logger_failure_not_accounted", failed["errors"])
        self.assertIn("logger_drain_incomplete", failed["errors"])

    def test_external_calls_and_changed_limits_cannot_pass_as_simulation(self):
        report = self.assess("network", provider_contacted=True)
        self.assertIn("unexpected_external_provider", report["errors"])
        report = self.assess("rate_cap", async_policy={"bridge": {"provider": {"simulation_only": True,
            "external_http_calls": 0, "attempts": [{}, {}], "max_requests": 1}}})
        self.assertIn("run_request_limit_exceeded", report["errors"])

    def test_short_run_cannot_claim_thirty_minute_certification(self):
        with self.assertRaises(ValueError):
            run_soak(Path("/tmp"), "build/jev/fixture", 60)


if __name__ == "__main__":
    unittest.main()
