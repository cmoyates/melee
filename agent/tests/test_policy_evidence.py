from dataclasses import asdict, replace
import json
from pathlib import Path
import tempfile
import unittest

from melee_agent.async_policy import AsyncPolicy, Delivery, Reply, bind
from melee_agent.engine import ACTION_PACKETS
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

    def test_terminal_record_supplement_accounts_for_last_packet_after_logger_failure(self):
        rows, summary = self.fixture()
        summary["last_unrecorded_record"] = rows.pop()
        report = self.audit(rows, summary)
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["supplemental_records"], 1)
        self.assertEqual(report["outcomes"], {"accepted": 1})

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

    def test_observed_acknowledgement_checks_motion_instead_of_success_label(self):
        bridge = ManualBridge()
        clock = [1_000_000_000]
        policy = AsyncPolicy("test", bridge, clock=lambda: clock[0]+10_000)
        policy.next_fallback_ns = 9_000_000_000
        candidates = ("neutral", "approach")
        context = bind("test", state(), 1, 0, candidates)
        rows = []
        for frame, x in ((10,0.), (11,0.), (12,3.), (13,6.), (14,7.)):
            clock[0] = 1_000_000_000 + (frame-10)*16_000_000
            observation = state(frame, clock[0], action_id=20 if frame in (12,13) else 14,
                self_velocity_x=2. if frame in (12,13) else 0., input_neutral_derived=frame not in (12,13))
            observation = replace(observation, bot=replace(observation.bot, x=x))
            if frame == 11:
                bridge.replies = [Delivery(context, candidates, Reply(context, "approach", clock[0]))]
            decision = policy.decide(observation)
            rows.append({"menu": "IN_GAME", "run_id": "test", "control": {"observation": asdict(observation),
                "queued_ns": clock[0]+20_000, "packet": ACTION_PACKETS[decision.action].wire()},
                "skill": policy.trace(), "raw_observation": {"players": {"1": {"raw_post": {
                    "x": x, "airborne": False, "speed_ground_x_self": observation.bot.details.self_velocity_x}}}},
                "input_provenance": {"latest_completed_flush": None, "observed": ACTION_PACKETS["wait"].wire()}})
        _, summary = self.fixture()
        report = self.audit(rows, summary)
        self.assertEqual(report["errors"], {})
        self.assertEqual(report["acknowledgements"], {"observed:move": 1})
        rows[3]["raw_observation"]["players"]["1"]["raw_post"]["x"] = 1.
        self.assertIn("unverified_provider_skill_success", self.audit(rows, summary)["errors"])


if __name__ == "__main__":
    unittest.main()
