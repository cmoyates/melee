from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

from melee_agent.engine import ACTION_PACKETS, FrameExecutor, MatchProgress, Observation
from melee_agent.fake import FakeClock, RecordingSink
from melee_agent.skills import SkillArbiter, SkillSpec, can_start, relative_skill
from melee_agent.skill_check import SkillCheckPolicy, SUITE, verified_report

BASE = Observation.parse(json.loads((Path(__file__).parent / "fixtures/battlefield.json").read_text())["cases"][1]["observation"])


def observation(frame, *, x=0., grounded=True, stocks=4, episode=1, **details):
    state = replace(BASE.bot.details, life_generation_derived=5-stocks, **details)
    return replace(BASE, episode=episode, frame=frame, observed_ns=0,
        bot=replace(BASE.bot, x=x, y=0. if grounded else 10., grounded=grounded, stocks_remaining=stocks, details=state),
        match=MatchProgress.from_frame(frame, 480, 4))


class SkillTests(unittest.TestCase):
    def test_toward_away_labels_resolve_from_current_opponent_side(self):
        for x, toward in ((-20., -1), (20., 1)):
            state = observation(0)
            state = replace(state, opponent=replace(state.opponent, x=x))
            self.assertEqual(relative_skill("approach", state), SkillSpec("move", toward))
            self.assertEqual(relative_skill("retreat", state), SkillSpec("move", -toward))
            self.assertEqual(relative_skill("jump_away", state), SkillSpec("jump", -toward))

    def exercise(self, spec, rows):
        arbiter, sink = SkillArbiter(), RecordingSink()
        self.assertIsNone(arbiter.request(spec, rows[0]))
        executor = FrameExecutor(SimpleNamespace(decide=arbiter.step), sink, FakeClock())
        for row in rows:
            executor.step(row)
        return arbiter, sink

    def test_twenty_observed_movements_each_direction_release_all_inputs(self):
        for direction in (-1, 1):
            for repetition in range(20):
                rows = [observation(0), observation(1, x=3.*direction, action_id=20, self_velocity_x=2.*direction, input_neutral_derived=False),
                    observation(2, x=6.*direction, action_id=20, self_velocity_x=2.*direction, input_neutral_derived=False),
                    observation(3, x=7.*direction)]
                arbiter, sink = self.exercise(SkillSpec("move", direction), rows)
                self.assertEqual(arbiter.last_event["status"], "succeeded")
                self.assertEqual(arbiter.last_event["ack_frame"], 2)
                self.assertEqual(sink.packets[-1], ACTION_PACKETS["wait"].wire())
                self.assertEqual(len(sink.packets), len(rows))

    def test_twenty_jumps_each_direction_require_squat_takeoff_and_release(self):
        for direction in (-1, 0, 1):
            for repetition in range(20):
                rows = [observation(0)] + [observation(f, action_id=24, input_jump_held=True, input_neutral_derived=False) for f in (1,2,3)]
                rows += [observation(4, grounded=False, action_id=25, self_velocity_y=2., input_jump_held=True, input_neutral_derived=False),
                            observation(5, grounded=False, action_id=25, self_velocity_y=2.)]
                arbiter, sink = self.exercise(SkillSpec("jump", direction), rows)
                self.assertEqual(arbiter.last_event["status"], "succeeded")
                self.assertEqual(arbiter.last_event["jumpsquat_observed_frames"], 3)
                self.assertTrue(sink.packets[0]["buttons"]["X"])
                self.assertEqual(sink.packets[-1], ACTION_PACKETS["wait"].wire())

    def test_twenty_shields_wait_for_observed_hold_and_release(self):
        for repetition in range(20):
            rows = [observation(0), observation(1, action_id=178, input_shield_held=True, input_neutral_derived=False)]
            rows += [observation(f, action_id=179, input_shield_held=True, input_neutral_derived=False) for f in range(2,11)]
            rows += [observation(11, action_id=180)]
            arbiter, sink = self.exercise(SkillSpec("shield"), rows)
            self.assertEqual(arbiter.last_event["status"], "succeeded")
            self.assertEqual(arbiter.last_event["ack_frame"], 2)
            self.assertEqual(sink.packets[-1], ACTION_PACKETS["wait"].wire())

    def test_twenty_neutral_repetitions_require_observed_release(self):
        for repetition in range(20):
            arbiter, sink = self.exercise(SkillSpec("neutral"), [observation(0), observation(1)])
            self.assertEqual(arbiter.last_event["status"], "succeeded")
            self.assertTrue(all(p == ACTION_PACKETS["wait"].wire() for p in sink.packets))

    def test_sending_jump_without_observed_squat_never_succeeds(self):
        arbiter, sink = self.exercise(SkillSpec("jump"), [observation(0), observation(1, grounded=False, action_id=25, self_velocity_y=2.)])
        self.assertEqual(arbiter.last_event["reason"], "unconfirmed_takeoff")
        self.assertEqual(sink.packets[-1], ACTION_PACKETS["wait"].wire())

    def test_hitlag_hitstun_and_life_change_abort_without_latched_input(self):
        for changed in (observation(1, hitlag_frames_derived=2), observation(1, hitstun_frames_derived=10),
                        observation(1, stocks=3, action_id=12), observation(1, action_id=0)):
            arbiter, sink = self.exercise(SkillSpec("shield"), [observation(0), changed])
            self.assertEqual(arbiter.last_event["status"], "aborted")
            self.assertEqual(sink.packets[-1], ACTION_PACKETS["wait"].wire())

    def test_missing_frame_cannot_advance_a_jump_sequence(self):
        arbiter, sink = self.exercise(SkillSpec("jump"), [observation(0), observation(2, action_id=24)])
        self.assertEqual(arbiter.last_event["reason"], "observation_discontinuity")
        self.assertEqual(sink.packets[-1], ACTION_PACKETS["wait"].wire())

    def test_active_skill_cannot_be_replaced_by_another_request(self):
        arbiter = SkillArbiter()
        arbiter.request(SkillSpec("jump"), observation(0))
        self.assertEqual(arbiter.request(SkillSpec("shield"), observation(1)), "skill_committed")
        self.assertEqual(arbiter.active["spec"].name, "jump")
        self.assertEqual(arbiter.abort(observation(1), "emergency").action, "wait")
        self.assertEqual(arbiter.last_event["reason"], "emergency")

    def test_timeout_releases_without_claiming_acknowledgement(self):
        arbiter, sink = self.exercise(SkillSpec("move", 1), [observation(f) for f in range(41)])
        self.assertEqual(arbiter.last_event["status"], "timeout")
        self.assertIsNone(arbiter.last_event["ack_frame"])
        self.assertEqual(sink.packets[-1], ACTION_PACKETS["wait"].wire())

    def test_state_dependent_refusals_are_explicit(self):
        cases = [(SkillSpec("jump"), observation(-1), "countdown"),
            (SkillSpec("jump"), observation(0, grounded=False), "requires_ground"),
            (SkillSpec("jump"), observation(0, input_jump_held=True), "jump_unavailable_or_held"),
            (SkillSpec("shield"), observation(0, shield_strength=5.), "shield_low"),
            (SkillSpec("move", 1), observation(0, x=60.), "support_edge"),
            (SkillSpec("move", 1), observation(0, action_id=600), "motion_not_interruptible")]
        cases.append((SkillSpec("jump"), observation(0, action_id=42), "motion_not_interruptible"))
        for spec, state, reason in cases:
            self.assertEqual(can_start(spec, state), reason)

    def test_report_recomputes_attempts_and_cannot_count_interruptions_as_success(self):
        policy = SkillCheckPolicy(1)
        policy.results = [{"skill": s.name, "direction": s.direction, "status": "succeeded"} for s in SUITE]
        report = policy.report()
        self.assertTrue(verified_report(report, 1))
        report["groups"][0]["succeeded"] = 20
        self.assertFalse(verified_report(report, 1))
        policy.results[0]["status"] = "aborted"
        self.assertFalse(policy.complete)
        self.assertFalse(verified_report(policy.report(), 1))


if __name__ == "__main__":
    unittest.main()
