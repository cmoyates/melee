from dataclasses import replace
from types import SimpleNamespace
import unittest

from melee_agent.async_policy import AsyncPolicy
from melee_agent.engine import ACTION_PACKETS, FrameExecutor
from melee_agent.fake import RecordingSink
from melee_agent.scenarios import ScenarioPolicy, find_scenario
from melee_agent.skills import SkillArbiter, SkillSpec
from test_aerial import aerial_state
from test_async_policy import ManualBridge


class AerialIntegrationTests(unittest.TestCase):
    def test_setup_walks_out_of_recorded_dash_oscillation_and_releases_before_jump(self):
        from test_scenarios import position
        for direction in (-1, 1):
            side = "left" if direction < 0 else "right"
            policy = ScenarioPolicy(find_scenario("sh_nair-"+side))
            # The failed live setup kept redashing between x 30.9 and 41.4.
            # Both sides approach with a walking packet, then observe release.
            outside = position(x=-41.41*direction, action_id=18, self_velocity_x=-.23*direction)
            self.assertEqual(policy.decide(outside).action, "slow_right" if direction > 0 else "slow_left")
            settled = position(1, x=-35.*direction)
            self.assertEqual(policy.decide(settled).action, "wait")
            self.assertIsNone(policy.measurement_start)
            self.assertEqual(policy.decide(position(2, x=-35.*direction)).action, "jump")
            self.assertEqual(policy.measurement_start, 2)

    def test_arbiter_has_one_packet_writer_through_jump_attack_and_landing(self):
        arbiter, sink = SkillArbiter(), RecordingSink()
        executor = FrameExecutor(SimpleNamespace(decide=arbiter.step), sink,
            SimpleNamespace(now_ns=lambda: 1_100_000_000))
        self.assertIsNone(arbiter.request(SkillSpec("sh_nair", -1), aerial_state()))
        observations = [aerial_state(), aerial_state(1, 24, input_jump_held=True), aerial_state(2, 24),
            aerial_state(3, 25, y=3., airborne=True, self_velocity_y=2.5),
            aerial_state(4, 65, y=5., airborne=True, self_velocity_y=-1.),
            aerial_state(5, 65, y=3., airborne=True, self_velocity_y=-1.5),
            aerial_state(6, 70), aerial_state(7, 70), aerial_state(8)]
        for observation in observations:
            executor.step(observation)
        self.assertEqual(sink.packets, [ACTION_PACKETS[action].wire() for action in
            ("jump", "wait", "wait", "attack", "left", "shield", "wait", "wait", "wait")])
        self.assertEqual(arbiter.last_event["status"], "succeeded")
        self.assertEqual(arbiter.last_event["aerial"]["observed_nair_landing_frames"], 2)

    def test_async_ownership_preserves_air_attack_hitlag_then_aborts_on_damage(self):
        policy = AsyncPolicy("aerial-test", ManualBridge(), clock=lambda: 1_100_000_000)
        policy.next_fallback_ns = 9_000_000_000
        policy.decide(aerial_state())
        policy.arbiter.request(SkillSpec("sh_nair", 1), aerial_state())
        for observation in (aerial_state(1), aerial_state(2, 24, input_jump_held=True), aerial_state(3, 24),
                aerial_state(4, 25, y=3., airborne=True, self_velocity_y=2.5),
                aerial_state(5, 65, y=3., airborne=True, hitlag_frames_derived=3)):
            policy.decide(observation)
        self.assertIsNotNone(policy.arbiter.active)
        self.assertEqual(policy.arbiter.active["ack_frame"], 5)
        policy.decide(aerial_state(6, 75, y=3., airborne=True, hitstun_frames_derived=4, attack_velocity_x=1.))
        self.assertIsNone(policy.arbiter.active)
        self.assertEqual(policy.arbiter.last_event["aerial"]["reason"], "hitstun")
        self.assertEqual(policy.last_owner, "emergency")

    def test_scenario_crosses_a_released_setup_boundary_in_each_direction(self):
        for name in ("sh_nair", "sh_nair_no_lcancel"):
            for direction in (-1, 1):
                scenario = ScenarioPolicy(find_scenario(name+("-left" if direction < 0 else "-right")))
                observation = aerial_state()
                observation = replace(observation, bot=replace(observation.bot, x=-35.*direction))
                decision = scenario.decide(observation)
                self.assertEqual(scenario.measurement_start, 0)
                self.assertEqual(decision.action, "jump")
                self.assertEqual(scenario.trace()["input_owner"], "measured")
                self.assertEqual(scenario.arbiter.active["spec"], SkillSpec(name, direction))
