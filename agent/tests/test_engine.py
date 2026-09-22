"""Contract failures and an independent expected-output fixture through the live executor."""

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from melee_agent.engine import Decision, FrameExecutor, Observation, Packet, RunManifest, ScriptedPolicy
from melee_agent.fake import FakeClock, RecordingSink, simulate
from melee_agent.live_control import LibmeleeSink, observe

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
        mutations = [lambda d: d.update(extra=True), lambda d: d.update(schema_version=1),
                        lambda d: d.update(schema_version=True), lambda d: d.update(stage="FINAL_DESTINATION"),
                        lambda d: d["bot"].update(extra=1), lambda d: d["bot"].update(x=float("nan")),
                        lambda d: d["opponent"].update(y=float("inf")), lambda d: d.update(frame=1.2),
                        lambda d: d["bot"].update(grounded=1), lambda d: d["bot"].update(x=10**1000)]
        for mutate in mutations:
            data = deepcopy(self.sample)
            mutate(data)
            with self.assertRaises(ValueError):
                Observation.parse(data)

    def test_invalid_or_missing_match_context_is_rejected(self):
        mutations = [lambda d: d.pop("match"), lambda d: d["bot"].pop("stocks_remaining"),
                        lambda d: d["bot"].update(stocks_remaining=-1),
                        lambda d: d["bot"].update(stocks_remaining=True),
                        lambda d: d["opponent"].update(stocks_remaining=5),
                        lambda d: d["match"].update(starting_stocks=0),
                        lambda d: d["match"].update(time_limit_seconds=True),
                        lambda d: d["match"].update(elapsed_seconds_derived=float("nan")),
                        lambda d: d["match"].update(remaining_seconds_derived=float("inf")),
                        lambda d: d["match"].update(remaining_seconds_derived=481),
                        lambda d: d["match"].update(elapsed_seconds_derived=1, remaining_seconds_derived=479),
                        lambda d: d["match"].update(extra="unknown")]
        for mutate in mutations:
            data = deepcopy(self.sample)
            mutate(data)
            with self.assertRaises(ValueError):
                Observation.parse(data)

    def test_live_match_context_reaches_policy_and_trace_through_stock_loss_and_reset(self):
        def player(stocks):
            return SimpleNamespace(position=SimpleNamespace(x=0, y=0), on_ground=True,
                jumps_left=2, action=SimpleNamespace(name="STANDING", value=14), action_frame=1, stock=stocks,
                percent=0., facing=True, hitlag_left=0, hitstun_frames_left=0, speed_ground_x_self=0.,
                speed_air_x_self=0., speed_y_self=0., speed_x_attack=0., speed_y_attack=0., shield_strength=60.,
                controller_state=SimpleNamespace(button={}, main_stick=(.5,.5), c_stick=(.5,.5), l_shoulder=0., r_shoulder=0.))
        state = SimpleNamespace(stage=SimpleNamespace(name="BATTLEFIELD"), frame=-123,
                                players={1: player(4), 2: player(4)})
        policy, clock = Mock(), FakeClock()
        policy.decide.side_effect = lambda o: Decision(1, o.episode, o.frame, "wait")
        executor = FrameExecutor(policy, RecordingSink(), clock)
        # Sparse observations emulate drops; elapsed time must depend on frame, not rows received.
        cases = [(1, -123, 4, 4, 0, 480), (1, 0, 4, 4, 0, 480),
                    (1, 60, 3, 4, 1, 479), (1, 28740, 1, 2, 479, 1),
                    (1, 28800, 0, 2, 480, 0), (1, 28860, 0, 2, 481, 0),
                    (2, -123, 4, 4, 0, 480)]
        for episode, frame, bot_stock, opponent_stock, elapsed, remaining in cases:
            state.frame = frame
            state.players[1].stock, state.players[2].stock = bot_stock, opponent_stock
            raw = {"state_flags_2": 0, "state_flags_4": 0, "misc_as_raw": -10., "hitlag_raw": 0.,
                    "available": {name: True for name in ("state_flags_2", "state_flags_4", "misc_as_raw", "hitlag_raw")}}
            row = executor.step(observe(state, episode, clock, {str(p): {"raw_post": raw} for p in (1, 2)}))
            received = policy.decide.call_args.args[0]
            self.assertEqual((received.bot.stocks_remaining, received.opponent.stocks_remaining),
                                (bot_stock, opponent_stock))
            # JSON round trip covers the state that a future provider adapter will serialize.
            record = json.loads(json.dumps(row))["observation"]
            self.assertEqual(record["match"], {"time_limit_seconds": 480, "starting_stocks": 4,
                                "elapsed_seconds_derived": elapsed, "remaining_seconds_derived": remaining})
            self.assertEqual(Observation.parse(record), received)

    def test_packet_rejects_invalid_axes_buttons_and_versions(self):
        for changes in ({"main_x": float("nan")}, {"l": 1.1}, {"c_y": -1}, {"schema_version": True},
                        {"held": ("A", "A")}, {"held": ("UNKNOWN",)}, {"main_y": False}):
            with self.assertRaises(ValueError):
                Packet(**changes)

    def test_details_and_life_identity_cannot_be_missing_or_nonfinite(self):
        mutations = [lambda d: d.update(schema_version=2), lambda d: d["bot"].pop("details"),
            lambda d: d["bot"]["details"].update(hitlag_frames_derived=-1),
            lambda d: d["bot"]["details"].update(action_id=65536),
            lambda d: d["bot"]["details"].update(self_velocity_x=float("nan")),
            lambda d: d["bot"]["details"].update(input_neutral_derived=1),
            lambda d: d["bot"]["details"].update(life_generation_derived=2)]
        for mutate in mutations:
            data = deepcopy(self.sample)
            mutate(data)
            with self.assertRaises(ValueError):
                Observation.parse(data)

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
