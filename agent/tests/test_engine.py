"""Contract failures and an independent expected-output fixture through the live executor."""

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock

from melee_agent.engine import Decision, FrameExecutor, Observation, Packet, RunManifest, ScriptedPolicy
from melee_agent.fake import FakeClock, RecordingSink, simulate
from melee_agent.live_control import LibmeleeSink

FIXTURE = Path(__file__).parent / "fixtures/battlefield.json"


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.fixture = json.loads(FIXTURE.read_text())
        self.sample = self.fixture["cases"][0]["observation"]

    def test_fixture_repeats_identically_and_covers_all_support_surfaces(self):
        first = simulate(self.fixture)
        self.assertEqual(first, simulate(self.fixture))
        self.assertEqual({r["support_surface_derived"] for r in first}, {None, "ground", "left", "right", "top"})
        self.assertEqual(first[-1]["decision"]["episode"], 2)

    def test_intentionally_wrong_controller_output_fails_cli(self):
        self.fixture["cases"][1]["expected_packet"]["main"] = [0., .5]
        path = Path(tempfile.mkdtemp(prefix="jev-wrong-output-")) / "fixture.json"
        path.write_text(json.dumps(self.fixture))
        result = subprocess.run([sys.executable, "-B", "-m", "melee_agent.cli", "smoke", "--backend", "fake", "--fixture", str(path)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["status"], "fail")

    def test_unknown_fields_versions_and_nonfinite_values_fail(self):
        mutations = [lambda d: d.update(extra=True), lambda d: d.update(schema_version=2),
                        lambda d: d.update(schema_version=True), lambda d: d.update(stage="FINAL_DESTINATION"),
                        lambda d: d["bot"].update(extra=1), lambda d: d["bot"].update(x=float("nan")),
                        lambda d: d["opponent"].update(y=float("inf")), lambda d: d.update(frame=1.2),
                        lambda d: d["bot"].update(grounded=1), lambda d: d["bot"].update(x=10**1000)]
        for mutate in mutations:
            data = deepcopy(self.sample)
            mutate(data)
            with self.assertRaises(ValueError):
                Observation.parse(data)

    def test_packet_rejects_invalid_axes_buttons_and_versions(self):
        for changes in ({"main_x": float("nan")}, {"l": 1.1}, {"c_y": -1}, {"schema_version": True},
                        {"held": ("A", "A")}, {"held": ("UNKNOWN",)}, {"main_y": False}):
            with self.assertRaises(ValueError):
                Packet(**changes)

    def test_stale_decision_cannot_reach_sink(self):
        observation = Observation.parse(self.sample)
        policy = Mock()
        policy.decide.return_value = Decision(1, 2, observation.frame, "right")
        sink = RecordingSink()
        with self.assertRaises(ValueError):
            FrameExecutor(policy, sink, FakeClock()).step(observation)
        self.assertEqual(sink.packets, [])

    def test_duplicate_or_old_episode_cannot_send_another_packet(self):
        observation = Observation.parse(self.sample)
        sink = RecordingSink()
        executor = FrameExecutor(ScriptedPolicy(), sink, FakeClock())
        executor.step(observation)
        with self.assertRaises(ValueError):
            executor.step(observation)
        executor.step(replace(observation, episode=2))
        with self.assertRaises(ValueError):
            executor.step(replace(observation, frame=0))
        self.assertEqual(len(sink.packets), 2)

    def test_clock_rollback_and_future_observation_fail_before_send(self):
        sink = RecordingSink()
        observation = Observation.parse(self.sample)
        clock = Mock()
        clock.now_ns.side_effect = [10, 9]
        with self.assertRaises(ValueError):
            FrameExecutor(ScriptedPolicy(), sink, clock).step(observation)
        with self.assertRaises(ValueError):
            FrameExecutor(ScriptedPolicy(), sink, FakeClock()).step(replace(observation, observed_ns=10**20))
        self.assertEqual(sink.packets, [])

    def test_complete_packet_clears_previous_buttons_and_axes_in_live_adapter(self):
        controller, buttons = Mock(), Mock()
        buttons.__getitem__ = Mock(side_effect=lambda name: name)
        sink = LibmeleeSink(controller, buttons)
        sink.send(Packet(main_x=1., held=("A",)))
        controller.reset_mock()
        sink.send(Packet())
        controller.release_all.assert_called_once()
        self.assertEqual(controller.tilt_analog.call_count, 2)
        controller.press_button.assert_not_called()
        controller.press_shoulder.assert_any_call(buttons.BUTTON_L, 0.)
        controller.press_shoulder.assert_any_call(buttons.BUTTON_R, 0.)

    def test_fake_manifest_cannot_claim_live_validation(self):
        with self.assertRaises(ValueError):
            RunManifest(1, "fake", "BATTLEFIELD", "a" * 64, 9, "pass")


if __name__ == "__main__":
    unittest.main()
