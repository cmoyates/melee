from dataclasses import replace
from types import SimpleNamespace
import unittest

from melee_agent.async_policy import AsyncPolicy
from melee_agent.engine import ACTION_PACKETS, FrameExecutor
from melee_agent.fake import RecordingSink
from melee_agent.fox_reflex import FoxReflex, aim_action, occupied_ledge
from melee_agent.skills import SkillSpec
from test_async_policy import ManualBridge
from test_scenarios import position


def air(frame=0, x=-72., y=-1., jumps=1, **details):
    return position(frame, x=x, y=y, grounded=False, jumps=jumps,
        **{"action_id": 29, "self_velocity_y": -.23, **details})


class FoxReflexTests(unittest.TestCase):
    def test_shared_executor_emits_one_start_press_then_button_free_aim_packets(self):
        sink = RecordingSink()
        executor = FrameExecutor(FoxReflex(), sink, SimpleNamespace(now_ns=lambda: 1_100_000_000))
        executor.step(air(y=-25., jumps=0))
        executor.step(air(1, y=-25., jumps=0, action_id=354))
        self.assertEqual(sink.packets, [ACTION_PACKETS["special_up"].wire(), ACTION_PACKETS["aim_up"].wire()])
        self.assertTrue(sink.packets[0]["buttons"]["B"])
        self.assertFalse(any(sink.packets[1]["buttons"].values()))
        for name, packet in ACTION_PACKETS.items():
            if name.startswith("aim_"):
                self.assertEqual(packet.held, ())
                self.assertEqual(packet.l+packet.r, 0.)

    def test_reflex_preempts_tactical_commitment_through_one_controller_writer(self):
        policy = AsyncPolicy("test", ManualBridge(), clock=lambda: 1_100_000_000)
        policy.next_fallback_ns = 9_000_000_000
        sink = RecordingSink()
        executor = FrameExecutor(policy, sink, SimpleNamespace(now_ns=lambda: 1_100_000_000))
        executor.step(position())
        self.assertIsNone(policy.arbiter.request(SkillSpec("jump"), position()))
        executor.step(air(1))
        self.assertEqual(sink.packets[-1], ACTION_PACKETS["jump_right"].wire())
        self.assertEqual(len(sink.packets), 2)
        self.assertIsNone(policy.arbiter.active)
        self.assertEqual(policy.arbiter.last_event["status"], "aborted")
        self.assertEqual(policy.trace()["input_owner"], "emergency")
        executor.step(position(2))
        self.assertIsNone(policy.recovery.started_frame)
        executor.step(air(3, x=0., y=20., action_id=25, self_velocity_y=3.))
        self.assertEqual(policy.trace()["input_owner"], "idle")
        self.assertEqual(policy.recovery.phase, "idle")

    def test_mirrored_double_jump_is_acknowledged_by_resource_and_motion(self):
        for x, inward in ((-72., "right"), (72., "left")):
            policy = FoxReflex()
            self.assertEqual(policy.decide_action(air(x=x)), "jump_"+inward)
            self.assertEqual(policy.decide_action(air(1, x=x, y=3., jumps=0, action_id=27,
                self_velocity_y=4., input_jump_held=True, input_neutral_derived=False)), inward)
            self.assertEqual(policy.counts["observed_double_jumps"], 1)
            self.assertEqual(policy.decide_action(air(2, x=x, y=7., jumps=0, action_id=27, self_velocity_y=3.)), inward)
            self.assertEqual(policy.counts["jump_attempts"], 1)

    def test_held_jump_is_released_before_a_new_press(self):
        policy = FoxReflex()
        self.assertEqual(policy.decide_action(air(input_jump_held=True, input_neutral_derived=False)), "right")
        self.assertEqual(policy.phase, "release_jump")
        self.assertEqual(policy.decide_action(air(1)), "jump_right")

    def test_firefox_start_charge_travel_and_freefall_are_distinct(self):
        policy = FoxReflex()
        self.assertEqual(policy.decide_action(air(y=-25., jumps=0)), "special_up")
        charge = air(1, y=-25., jumps=0, action_id=354)
        charge = replace(charge, bot=replace(charge.bot, action="SWORD_DANCE_3_LOW"))
        self.assertEqual(policy.decide_action(charge), "aim_up")
        self.assertEqual(policy.phase, "charge_aim")
        self.assertEqual(policy.decide_action(air(2, y=-10., jumps=0, action_id=356, self_velocity_y=5.)), "right")
        self.assertEqual(policy.counts["observed_firefox_launches"], 1)
        self.assertEqual(policy.decide_action(air(3, y=35., jumps=0, action_id=35)), "right")
        self.assertEqual(policy.phase, "special_fall_drift")
        self.assertEqual(policy.counts["special_attempts"], 1)

    def test_missing_special_acknowledgement_does_not_loop_or_repress_b(self):
        policy = FoxReflex()
        actions = [policy.decide_action(air(frame, y=-25., jumps=0)) for frame in range(30)]
        self.assertEqual(actions.count("special_up"), 1)
        self.assertEqual(actions[8:], ["wait"]*22)
        self.assertEqual(policy.event["reason"], "special_start_unacknowledged")

    def test_stuck_charge_reaches_its_bounded_failure(self):
        policy = FoxReflex()
        for frame in range(181):
            action = policy.decide_action(air(frame, y=-25., jumps=0, action_id=354))
        self.assertEqual(action, "wait")
        self.assertEqual(policy.event["reason"], "recovery_deadline")

    def test_death_and_respawn_release_inputs_and_allow_fresh_observed_resources(self):
        policy = FoxReflex()
        policy.decide_action(air())
        self.assertEqual(policy.decide_action(air(1, action_id=0)), "wait")
        self.assertEqual(policy.decide_action(air(2, action_id=12, life_generation_derived=2)), "wait")
        policy.decide_action(position(3, life_generation_derived=2))
        self.assertEqual(policy.decide_action(air(4, life_generation_derived=2)), "jump_right")
        self.assertEqual(policy.counts["jump_attempts"], 2)

    def test_damage_cancels_the_old_special_commitment_before_a_fresh_attempt(self):
        policy = FoxReflex()
        policy.decide_action(air(y=-25., jumps=0))
        policy.decide_action(air(1, y=-25., jumps=0, action_id=354))
        self.assertNotEqual(policy.decide_action(air(2, y=-25., jumps=0, action_id=88,
            hitstun_frames_derived=4, attack_velocity_x=1.)), "special_up")
        self.assertEqual(policy.decide_action(air(3, y=-25., jumps=0)), "special_up")
        self.assertEqual(policy.counts["special_attempts"], 2)

    def test_ledge_getup_needs_neutral_in_wait_state_not_just_catch(self):
        policy = FoxReflex()
        self.assertEqual(policy.decide_action(air(action_id=252)), "wait")
        self.assertEqual(policy.decide_action(air(1, action_id=253)), "wait")
        self.assertEqual(policy.decide_action(air(2, action_id=253)), "right")
        self.assertEqual(policy.decide_action(air(3, action_id=255)), "wait")
        self.assertEqual(policy.decide_action(position(4, x=-60.)), "wait")
        self.assertEqual(policy.phase, "safe")
        self.assertEqual(policy.counts["observed_stage_returns"], 1)

    def test_unknown_support_and_outside_envelope_never_report_recovery(self):
        for observation in (position(x=-100., y=-30.), air(y=-90., jumps=0)):
            policy = FoxReflex()
            self.assertEqual(policy.decide_action(observation), "wait")
            self.assertTrue(policy.failed)
            self.assertEqual(policy.counts["observed_stage_returns"], 0)

    def test_landing_clears_engagement_before_an_ordinary_in_stage_jump(self):
        policy = FoxReflex()
        policy.decide_action(air())
        policy.decide_action(position(1, x=-40., y=27.2001))
        self.assertIsNone(policy.started_frame)
        ordinary = air(2, x=0., y=20., action_id=25, self_velocity_y=3.)
        self.assertIsNone(policy.reason(ordinary))
        self.assertEqual(policy.decide_action(ordinary), "wait")

    def test_tech_is_one_pulse_only_in_hitstun_near_known_floor(self):
        policy = FoxReflex()
        first = air(x=0., y=3., hitstun_frames_derived=4, self_velocity_y=-2., attack_velocity_y=-1.)
        self.assertEqual(policy.decide_action(first), "shield")
        second = air(1, x=0., y=2., hitstun_frames_derived=3, self_velocity_y=-2.,
            attack_velocity_y=-1., input_shield_held=True)
        self.assertNotEqual(policy.decide_action(second), "shield")
        self.assertNotEqual(policy.decide_action(air(2, x=0., y=1., hitstun_frames_derived=2,
            self_velocity_y=-2., attack_velocity_y=-1.)), "shield")
        self.assertEqual(policy.counts["tech_attempts"], 1)
        for changed in (air(x=120., y=3., hitstun_frames_derived=4, self_velocity_y=-2.),
                air(x=0., y=3., hitstun_frames_derived=4, hitlag_frames_derived=1, self_velocity_y=-2.),
                air(x=0., y=3., self_velocity_y=-2.)):
            self.assertNotEqual(FoxReflex().decide_action(changed), "shield")

    def test_occupied_ledge_changes_the_target_and_close_low_recovery_avoids_wall_crossing(self):
        observation = air(x=-90., y=8., jumps=0)
        occupied = replace(observation, opponent=replace(observation.opponent, x=-68.,
            details=replace(observation.opponent.details, action_id=253)))
        self.assertTrue(occupied_ledge(occupied))
        self.assertNotEqual(aim_action(observation), aim_action(occupied))
        self.assertEqual(aim_action(air(x=-72., y=-25., jumps=0)), "aim_up")
        self.assertEqual(aim_action(air(x=72., y=-25., jumps=0)), "aim_up")
        self.assertEqual(aim_action(air(x=-100., y=-40., jumps=0)), "aim_steep_right")

    def test_unknown_knockback_vector_gets_neutral_instead_of_guessed_di(self):
        policy = FoxReflex()
        self.assertEqual(policy.decide_action(air(hitlag_frames_derived=4)), "wait")

    def test_frame_loss_releases_inputs_without_extending_the_recovery_deadline(self):
        policy = FoxReflex()
        policy.decide_action(air(y=-25., jumps=0))
        self.assertEqual(policy.decide_action(air(100, y=-25., jumps=0)), "wait")
        self.assertEqual(policy.started_frame, 0)
        for frame in range(101, 181):
            policy.decide_action(air(frame, y=-25., jumps=0, action_id=354))
        self.assertTrue(policy.failed)
        self.assertEqual(policy.event["reason"], "recovery_deadline")


if __name__ == "__main__":
    unittest.main()
