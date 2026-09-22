from dataclasses import asdict
import json
from pathlib import Path
import tempfile
import unittest

from melee_agent.async_policy import AsyncPolicy
from melee_agent.policy_evidence import inspect_policy
from test_async_policy import ManualBridge, delivery, state


class PolicyEvidenceTests(unittest.TestCase):
    def fixture(self):
        bridge = ManualBridge()
        policy = AsyncPolicy("test", bridge, clock=lambda: 1_100_000_000)
        policy.next_fallback_ns = 9_000_000_000
        rows = []
        for frame in (10, 11):
            observation = state(frame, 1_000_000_000 + (frame-10)*16_000_000)
            if frame == 11:
                bridge.replies = [delivery()]
            policy.decide(observation)
            rows.append({"menu": "IN_GAME", "run_id": "test", "control": {
                "observation": asdict(observation), "queued_ns": 1_100_000_001},
                "skill": policy.trace(), "input_provenance": {"latest_completed_flush": None}})
        summary = {"run_id": "test", "status": "captured", "episodes": [], "async_policy": {
            "policy": {"accepted": 1}, "bridge": {"workers_alive": 0, "inflight": 0, "worker_limit": 4}}}
        return rows, summary

    def audit(self, rows, summary):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            (run / "launch.json").write_text(json.dumps({"run_id": "test"}))
            (run / "summary.json").write_text(json.dumps(summary))
            (run / "frames.jsonl").write_text("".join(json.dumps(row)+"\n" for row in rows))
            return inspect_policy(run)

    def test_checks_accepted_decision_against_source_and_application_frames(self):
        rows, summary = self.fixture()
        self.assertEqual(self.audit(rows, summary)["status"], "pass")

    def test_rejects_claimed_success_with_forged_source_stock(self):
        rows, summary = self.fixture()
        event = rows[-1]["skill"]["policy_events"][0]
        for key in ("expected",):
            event["delivery"][key]["bot_life"] = 2
        event["delivery"]["reply"]["context"]["bot_life"] = 2
        report = self.audit(rows, summary)
        self.assertEqual(report["status"], "fail")
        self.assertIn("accepted_wrong_life", report["errors"])
        self.assertIn("source_life_mismatch", report["errors"])

    def test_rejects_claimed_success_without_actual_skill_start(self):
        rows, summary = self.fixture()
        rows[-1]["skill"]["active"] = None
        self.assertIn("accepted_skill_not_started", self.audit(rows, summary)["errors"])

    def test_rejects_false_clean_shutdown_and_wrong_summary_counts(self):
        rows, summary = self.fixture()
        summary["async_policy"]["bridge"]["workers_alive"] = 1
        summary["async_policy"]["policy"]["accepted"] = 2
        errors = self.audit(rows, summary)["errors"]
        self.assertIn("worker_bound_or_shutdown", errors)
        self.assertIn("summary_outcome_mismatch", errors)


if __name__ == "__main__":
    unittest.main()
