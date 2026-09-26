import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from melee_agent.async_policy import AsyncPolicy, Delivery, LABELS, Reply, bind
from melee_agent.engine import FrameExecutor
from melee_agent.fake import RecordingSink
from melee_agent.incidents import (IncidentError, RecordedClock, canonical, contract_hashes,
    export_incident, replay_incident, sha, verify_bundle)
from test_async_policy import ManualBridge, state


class IncidentTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="jev-incident-test-")).resolve()
        self.run = self.root / "build/jev/runs/synthetic"
        self.run.mkdir(parents=True)
        self.rows = []
        bridge, clock, sink = ManualBridge(), RecordedClock(), RecordingSink()
        moment = [0]
        policy = AsyncPolicy("synthetic", bridge, clock=lambda: moment[0]+1000)
        executor = FrameExecutor(policy, sink, clock)
        source = None
        for frame in range(67):
            moment[0] = 1_000_000_000+frame*16_666_667
            observation = state(frame, moment[0])
            if frame == 1:
                source = bind("synthetic", observation, 1, policy.arbiter.generation, LABELS)
            if frame == 65:
                bridge.replies = [Delivery(source, LABELS, Reply(source, "shield", moment[0]))]
            clock.values = [moment[0]+500, moment[0]+2000]
            control = executor.step(observation)
            trace = policy.trace()
            self.rows.append({"schema_version": 4, "run_id": "synthetic", "menu": "IN_GAME",
                "episode": observation.episode, "frame": frame, "control": control, "skill": trace,
                "input_provenance": {"latest_completed_flush": None}})
        launch = {"schema_version": 2, "run_id": "synthetic", "policy": "delayed-fake", "synthetic_fixture": True,
            "stage_id": 31, "starting_stocks": 4, "match_time_limit_seconds": 480,
            "source_sha256": contract_hashes()}
        (self.run / "launch.json").write_bytes(canonical(launch))
        (self.run / "summary.json").write_bytes(canonical({"schema_version": 1, "run_id": "synthetic"}))
        self.write_rows()
        self.explanation = export_incident(self.root, self.run, frame=65, after_frames=1)
        self.folder = self.root / "build/jev/incidents" / self.explanation["incident_id"]

    def write_rows(self):
        (self.run / "frames.jsonl").write_bytes(b"".join(canonical(row)+b"\n" for row in self.rows))

    def reseal(self, transform):
        path = self.folder / "manifest.json"
        manifest = json.loads(path.read_bytes())
        transform(manifest)
        manifest.pop("manifest_sha256")
        manifest["manifest_sha256"] = sha(manifest)
        path.write_bytes(canonical(manifest)+b"\n")

    def test_two_replays_are_identical_without_network_assets_or_controller_access(self):
        with patch("socket.socket", side_effect=AssertionError("network forbidden")), patch("subprocess.Popen", side_effect=AssertionError("process forbidden")):
            first = replay_incident(self.root, self.folder)
            second = replay_incident(self.root, self.folder)
        self.assertEqual(first, second)
        self.assertEqual(first["status"], "pass")
        self.assertEqual(first["replayed_records"], 67)
        self.assertFalse(first["controller_written"])
        self.assertFalse(first["provider_contacted"])

    def test_seeded_missing_freshness_bug_diverges_then_fixed_guard_passes(self):
        with patch("melee_agent.async_policy.MAX_AGE_NS", 10_000_000_000), patch("melee_agent.async_policy.MAX_FRAME_AGE", 600):
            broken = replay_incident(self.root, self.folder)
        self.assertEqual(broken["status"], "fail")
        self.assertEqual(broken["divergence"]["frame"], 65)
        self.assertIn("packet", broken["divergence"]["different_fields"])
        self.assertEqual(broken["replayed_records"], 66)  # Stops before using the counterfactual next frame.
        self.assertEqual(replay_incident(self.root, self.folder)["status"], "pass")

    def test_changed_reflex_state_is_detected_even_before_it_changes_a_packet(self):
        from melee_agent.fox_reflex import FoxReflex
        original = FoxReflex.trace
        with patch.object(FoxReflex, "trace", lambda policy: {**original(policy), "phase": "wrong_phase"}):
            broken = replay_incident(self.root, self.folder)
        self.assertEqual(broken["status"], "fail")
        self.assertEqual(broken["divergence"]["frame"], 0)
        self.assertEqual(broken["divergence"]["different_fields"], ["reflex"])

    def test_tampered_or_truncated_prefix_fails_integrity(self):
        path = self.folder / "prefix.jsonl"
        original = path.read_bytes()
        path.write_bytes(original[:-3])
        with self.assertRaises(IncidentError):
            verify_bundle(self.root, self.folder)
        path.write_bytes(original.replace(b'"shield"', b'"neutral"', 1))
        with self.assertRaises(IncidentError):
            verify_bundle(self.root, self.folder)

    def test_changed_semantic_state_diverges_before_any_controller_difference(self):
        from dataclasses import replace
        from melee_agent.semantic import canonical as semantic_json, compact_observation
        def wrong_state(*args, **kwargs):
            compact = compact_observation(*args, **kwargs)
            payload = compact.wire()
            payload["bot"]["native_motion_name"] = "InventedMotion"
            return replace(compact, payload_json=semantic_json(payload))
        with patch("melee_agent.async_policy.compact_observation", side_effect=wrong_state):
            report = replay_incident(self.root, self.folder)
        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["divergence"]["frame"], 0)
        self.assertEqual(report["divergence"]["different_fields"], ["semantic_state"])

    def test_wrong_episode_fails_even_after_recomputing_file_hash(self):
        path = self.folder / "prefix.jsonl"
        rows = [json.loads(line) for line in path.read_bytes().splitlines()]
        rows[5]["observation"]["episode"] = 2
        raw = b"".join(canonical(row)+b"\n" for row in rows)
        path.write_bytes(raw)
        self.reseal(lambda m: m.update(prefix_sha256=hashlib.sha256(raw).hexdigest(), prefix_bytes=len(raw)))
        with self.assertRaisesRegex(IncidentError, "episode_or_frame"):
            verify_bundle(self.root, self.folder)

    def test_binary_and_policy_provenance_cannot_be_changed(self):
        self.reseal(lambda m: m["declared_provenance"].update(runtime_sha256="0"*64))
        with self.assertRaisesRegex(IncidentError, "provenance_mismatch"):
            verify_bundle(self.root, self.folder)

    def test_changed_policy_hash_is_rejected_even_when_manifest_is_resealed(self):
        def changed(manifest):
            for key in ("declared_provenance", "expected_provenance"):
                manifest[key]["source_sha256"]["async_policy.py"] = "0"*64
        self.reseal(changed)
        with self.assertRaisesRegex(IncidentError, "policy_contract_mismatch"):
            verify_bundle(self.root, self.folder)

    def test_provider_configuration_is_checked_without_constructing_a_provider(self):
        from melee_agent.live_provider import policy_config_hash
        def configure(manifest):
            for key in ("declared_provenance", "expected_provenance"):
                manifest[key]["provider_config_sha256"] = policy_config_hash()
        self.reseal(configure)
        with patch("melee_agent.live_provider.ProviderBackend", side_effect=AssertionError("provider forbidden")):
            self.assertEqual(replay_incident(self.root, self.folder)["status"], "pass")
            with patch("melee_agent.live_provider.INSTRUCTIONS", "changed policy"):
                with self.assertRaisesRegex(IncidentError, "provider_config_mismatch"):
                    verify_bundle(self.root, self.folder)

    def test_focus_cannot_disagree_with_the_replay_prefix(self):
        path = self.folder / "focus.json"
        focus = json.loads(path.read_bytes())
        focus["control"]["decision"]["action"] = "shield"
        raw = canonical(focus)+b"\n"
        path.write_bytes(raw)
        self.reseal(lambda m: m.update(focus_sha256=hashlib.sha256(raw).hexdigest()))
        with self.assertRaisesRegex(IncidentError, "focus_prefix_mismatch"):
            verify_bundle(self.root, self.folder)

    def test_observation_schema_mismatch_is_not_silently_upgraded(self):
        path = self.folder / "prefix.jsonl"
        rows = [json.loads(line) for line in path.read_bytes().splitlines()]
        rows[0]["observation"]["schema_version"] = 2
        raw = b"".join(canonical(row)+b"\n" for row in rows)
        path.write_bytes(raw)
        self.reseal(lambda m: m.update(prefix_sha256=hashlib.sha256(raw).hexdigest(), prefix_bytes=len(raw)))
        with self.assertRaises(ValueError):
            verify_bundle(self.root, self.folder)

    def test_historical_trace_without_exact_clock_is_explainable_but_not_replay_certified(self):
        self.rows[0]["skill"].pop("decision_ns")
        self.write_rows()
        explanation = export_incident(self.root, self.run, frame=65)
        self.assertFalse(explanation["replay_supported"])
        self.assertIn("missing_exact_clock_or_mailbox_provenance", explanation["replay_blockers"])
        folder = self.root / "build/jev/incidents" / explanation["incident_id"]
        with self.assertRaisesRegex(IncidentError, "missing_exact_replay"):
            replay_incident(self.root, folder)

    def test_request_selector_and_statuses_do_not_claim_contact_or_outcome(self):
        self.assertEqual(self.explanation["contact"], "not_measured")
        self.assertEqual(self.explanation["outcome_attribution"], "not_established")
        self.assertEqual(self.explanation["provider_decisions"][0]["reason"], "monotonic_age")
        with self.assertRaisesRegex(IncidentError, "not_found"):
            export_incident(self.root, self.run, request_id="missing-request")

    def test_request_selection_retains_the_exact_response_and_candidate_binding(self):
        event = self.rows[65]["skill"]["policy_events"][0]
        event["delivery"]["reply"]["metadata"] = {"request_id": "recorded-request", "confidence": .7}
        self.write_rows()
        result = export_incident(self.root, self.run, request_id="recorded-request", after_frames=0)
        folder = self.root / "build/jev/incidents" / result["incident_id"]
        focus = json.loads((folder / "focus.json").read_bytes())
        self.assertEqual(canonical(focus["skill"]["policy_events"][0]), canonical(event))
        self.assertEqual(result["focus"], [1, 65])
        self.assertEqual(replay_incident(self.root, folder)["status"], "pass")

    def test_invalid_clock_is_refused_before_policy_execution(self):
        path = self.folder / "prefix.jsonl"
        rows = [json.loads(line) for line in path.read_bytes().splitlines()]
        rows[0]["times"]["policy_ns"] = rows[0]["times"]["queued_ns"] + 1
        raw = b"".join(canonical(row)+b"\n" for row in rows)
        path.write_bytes(raw)
        self.reseal(lambda m: m.update(prefix_sha256=hashlib.sha256(raw).hexdigest(), prefix_bytes=len(raw)))
        with patch.object(AsyncPolicy, "decide", side_effect=AssertionError("invalid clock reached policy")):
            with self.assertRaisesRegex(IncidentError, "invalid_recorded_clock"):
                replay_incident(self.root, self.folder)

    def test_symlinked_incident_file_is_not_followed(self):
        original = self.folder / "prefix.jsonl"
        saved = self.folder / "saved-prefix.jsonl"
        original.rename(saved)
        original.symlink_to(saved)
        with self.assertRaises(OSError):
            verify_bundle(self.root, self.folder)


if __name__ == "__main__":
    unittest.main()
