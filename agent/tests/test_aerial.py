from dataclasses import replace
import unittest

from melee_agent.aerial import ShortHopAerial, can_start_aerial
from test_combat_integration import ground


def aerial_state(frame=0, motion=14, y=0., airborne=False, **details):
    observation = ground(frame, motion, **details)
    return replace(observation, bot=replace(observation.bot, y=y, grounded=not airborne, jumps=1 if airborne else 2))


def takeoff(skill):
    actions = [skill.step(aerial_state()),
        skill.step(aerial_state(1, 24, input_jump_held=True, input_neutral_derived=False)),
        skill.step(aerial_state(2, 24)),
        skill.step(aerial_state(3, 25, y=2.5, airborne=True, self_velocity_y=2.5))]
    return actions


class AerialTests(unittest.TestCase):
    def test_one_fresh_jump_release_in_kneebend_then_neutral_stick_attack(self):
        for direction in (-1, 1):
            skill = ShortHopAerial("sh_nair", direction, aerial_state())
            self.assertEqual(takeoff(skill), ["jump", "wait", "wait", "attack"])
            self.assertEqual(skill.jump_release_frame, 2)
            self.assertEqual(skill.takeoff_frame, 3)
            drift = skill.step(aerial_state(4, 65, y=5., airborne=True, self_velocity_y=2.))
            self.assertEqual(drift, "left" if direction < 0 else "right")
            self.assertEqual(skill.ack_frame, 4)

    def test_lcancel_is_one_pulse_and_landing_frames_are_measured_without_success_inference(self):
        for enabled in (False, True):
            name = "sh_nair" if enabled else "sh_nair_no_lcancel"
            skill = ShortHopAerial(name, 1, aerial_state())
            takeoff(skill)
            skill.step(aerial_state(4, 65, y=5., airborne=True, self_velocity_y=-1.))
            self.assertEqual(skill.step(aerial_state(5, 65, y=3., airborne=True, self_velocity_y=-1.5)),
                "shield" if enabled else "right")
            self.assertEqual(skill.step(aerial_state(6, 65, y=1., airborne=True, self_velocity_y=-2.)), "right")
            for frame in range(7, 14):
                self.assertEqual(skill.step(aerial_state(frame, 70, action_frame=(frame-7)*2+1)), "wait")
                self.assertIsNone(skill.status)
            skill.step(aerial_state(14))
            self.assertEqual(skill.status, "succeeded")
            trace = skill.trace()
            self.assertEqual(trace["observed_nair_landing_frames"], 7)
            self.assertEqual(trace["lcancel_attempt_frame"], 5 if enabled else None)
            self.assertIsNone(trace["reduced_landing_lag"])

    def test_hitlag_acknowledges_aerial_but_never_triggers_lcancel(self):
        skill = ShortHopAerial("sh_nair", 1, aerial_state())
        takeoff(skill)
        self.assertEqual(skill.step(aerial_state(4, 65, y=2., airborne=True,
            self_velocity_y=-1., hitlag_frames_derived=3)), "wait")
        self.assertEqual(skill.ack_frame, 4)
        self.assertIsNone(skill.lcancel_attempt_frame)
        self.assertEqual(skill.step(aerial_state(5, 65, y=2., airborne=True, self_velocity_y=-1.)), "shield")

    def test_missing_kneebend_or_release_never_sends_air_attack(self):
        for missing in ("knee", "release"):
            skill = ShortHopAerial("sh_nair", 1, aerial_state())
            skill.step(aerial_state())
            skill.step(aerial_state(1, 14 if missing == "knee" else 24, input_jump_held=True))
            result = skill.step(aerial_state(2, 25, y=2., airborne=True, self_velocity_y=2.))
            self.assertEqual(result, "wait")
            self.assertEqual(skill.reason, "unconfirmed_short_hop")
            self.assertIsNone(skill.attack_press_frame)

    def test_failed_jumpsquat_and_early_landing_are_terminal_without_followup(self):
        skill = ShortHopAerial("sh_nair", 1, aerial_state())
        actions = [skill.step(aerial_state(frame)) for frame in range(15)]
        self.assertEqual(actions.count("jump"), 1)
        self.assertNotIn("attack", actions)
        self.assertEqual(skill.reason, "takeoff_not_observed")
        skill = ShortHopAerial("sh_nair", 1, aerial_state())
        takeoff(skill)
        self.assertEqual(skill.step(aerial_state(4, 42)), "wait")
        self.assertEqual(skill.reason, "landed_before_aerial_ack")
        self.assertEqual(skill.step(aerial_state(5, 65, y=2., airborne=True, self_velocity_y=-1.)), "wait")
        self.assertIsNone(skill.lcancel_attempt_frame)

    def test_hitstun_gap_or_life_change_cancels_followups(self):
        for changed in (aerial_state(4, 75, hitstun_frames_derived=2), aerial_state(7, 65, y=5., airborne=True),
                aerial_state(4, life_generation_derived=2)):
            skill = ShortHopAerial("sh_nair", 1, aerial_state())
            takeoff(skill)
            self.assertEqual(skill.step(changed), "wait")
            self.assertEqual(skill.status, "aborted")
            self.assertIsNone(skill.lcancel_attempt_frame)
            self.assertIsNone(skill.trace()["observed_nair_landing_frames"])

    def test_unsupported_geometry_and_states_refuse_or_abort_with_reason(self):
        for changed in (aerial_state(0, 65, y=10., airborne=True), aerial_state(0, 42),
                replace(aerial_state(), bot=replace(aerial_state().bot, x=60.)),
                aerial_state(0, self_velocity_x=1.), aerial_state(0, input_jump_held=True)):
            self.assertIsNotNone(can_start_aerial("sh_nair", 1, changed))
        skill = ShortHopAerial("sh_nair", 1, aerial_state())
        takeoff(skill)
        self.assertEqual(skill.step(aerial_state(4, 65, y=27., airborne=True)), "wait")
        self.assertEqual(skill.reason, "unsupported_air_geometry")

    def test_late_autocancel_and_deadline_do_not_manufacture_reduced_lag(self):
        skill = ShortHopAerial("sh_nair_no_lcancel", 1, aerial_state())
        takeoff(skill)
        skill.step(aerial_state(4, 65, y=5., airborne=True))
        skill.step(aerial_state(5, 29, y=3., airborne=True))
        skill.step(aerial_state(6, 42))
        skill.step(aerial_state(7))
        self.assertEqual(skill.status, "succeeded")
        self.assertEqual(skill.trace()["observed_nair_landing_frames"], 0)
        self.assertIsNone(skill.trace()["reduced_landing_lag"])
        skill = ShortHopAerial("sh_nair", 1, aerial_state())
        takeoff(skill)
        for frame in range(4, 181):
            skill.step(aerial_state(frame, 65, y=5., airborne=True))
        self.assertEqual(skill.status, "timeout")
        self.assertIsNone(skill.trace()["observed_nair_landing_frames"])
