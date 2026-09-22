from dataclasses import replace
import unittest
from unittest.mock import patch

from melee_agent.scenarios import ScenarioPolicy, SUITE, find_scenario, starting_predicate, verified_trial
from melee_agent.scenario_runner import recovery_acceptance
from test_async_policy import state


def position(frame=0, x=-35., y=0., grounded=True, jumps=2, **details):
    observation = state(frame, action_id=14, self_velocity_x=0., self_velocity_y=0.,
        input_neutral_derived=True)
    return replace(observation, bot=replace(observation.bot, x=x, y=y, grounded=grounded, jumps=jumps,
        stocks_remaining=5-details.get("life_generation_derived", 1),
        details=replace(observation.bot.details, **details)))


class ScenarioTests(unittest.TestCase):
    def test_combat_crossing_releases_jump_then_neutralizes_before_measurement(self):
        policy = ScenarioPolicy(find_scenario("grab-left"))
        def opponent(observation):
            return replace(observation, opponent=replace(observation.opponent, x=8., y=0., grounded=True,
                details=replace(observation.opponent.details, action_id=14, hurtbox_state=0)))
        self.assertEqual(policy.decide(opponent(position(x=0., facing_right=True))).action, "jump_right")
        self.assertEqual(policy.decide(opponent(position(1, x=1., action_id=24,
            input_jump_held=True, input_neutral_derived=False))).action, "right")
        self.assertEqual(policy.decide(opponent(position(2, x=12., y=5., grounded=False,
            jumps=1, action_id=25))).action, "right")
        self.assertEqual(policy.decide(opponent(position(3, x=20., y=4., grounded=False,
            jumps=1, action_id=25))).action, "left")
        self.assertEqual(policy.decide(opponent(position(4, x=19., facing_right=False))).action, "wait")
        self.assertEqual(policy.phase, "setup")
        self.assertEqual(policy.decide(opponent(position(5, x=17., facing_right=False))).action, "grab")
        self.assertEqual(policy.measurement_start, 5)

    def test_recovery_acceptance_counts_setup_and_audit_failures_against_each_side(self):
        names = ("recovery-high-left", "recovery-high-right", "recovery-low-left", "recovery-low-right")
        rows = [{"scenario": name, "status": "pass", "trial_status": "succeeded"}
            for name in names for _ in range(20)]
        self.assertTrue(recovery_acceptance(rows, 20)["passed"])
        for index in (0, 1):
            rows[index]["trial_status"] = "setup_failed"
        self.assertTrue(recovery_acceptance(rows, 20)["passed"])
        rows[2]["status"] = "fail"
        self.assertFalse(recovery_acceptance(rows, 20)["passed"])
        self.assertFalse(recovery_acceptance(rows[20:], 20)["passed"])
        self.assertFalse(recovery_acceptance([rows[40]], 1)["passed"])

    def test_low_recovery_predicate_requires_consumed_jump_and_neutral_setup_boundary(self):
        for direction, side in ((-1, "left"), (1, "right")):
            spec = find_scenario("recovery-low-"+side)
            valid = position(x=95*direction, y=-25., grounded=False, jumps=0, action_id=29, self_velocity_y=-2.)
            self.assertTrue(starting_predicate(spec, valid))
            self.assertFalse(starting_predicate(spec, replace(valid, bot=replace(valid.bot, jumps=1))))
            self.assertFalse(starting_predicate(spec, replace(valid, bot=replace(valid.bot, y=-10.))))
            policy = ScenarioPolicy(spec)
            self.assertEqual(policy.decide(valid).action, "special_up")
            self.assertEqual(policy.phase, "measured")
            policy.decide(position(1, x=95*direction, y=-25., grounded=False, jumps=0,
                action_id=88, hitstun_frames_derived=3, attack_velocity_x=float(direction)))
            self.assertFalse(policy.complete)
            self.assertEqual(policy.reflex.phase, "defensive_drift")
            policy.decide(position(2, x=40*direction, y=27.2001, action_id=42))
            self.assertEqual(policy.result["status"], "succeeded")
            self.assertTrue(verified_trial(policy.report(), spec.name))

    def test_mirrored_predicates_require_the_declared_side_and_resources(self):
        for direction, name in ((-1, "left"), (1, "right")):
            spec = find_scenario("offstage-"+name)
            valid = position(x=72*direction, y=-1., grounded=False, jumps=1, action_id=29, self_velocity_y=-.23)
            self.assertTrue(starting_predicate(spec, valid))
            self.assertFalse(starting_predicate(spec, replace(valid, bot=replace(valid.bot, jumps=0))))
            self.assertFalse(starting_predicate(spec, replace(valid, bot=replace(valid.bot, x=-valid.bot.x))))
            self.assertFalse(starting_predicate(spec, replace(valid, bot=replace(valid.bot,
                details=replace(valid.bot.details, hitstun_frames_derived=1)))))

    def test_setup_must_release_before_measurement_even_if_observation_is_neutral(self):
        policy = ScenarioPolicy(find_scenario("grounded-left"))
        self.assertEqual(policy.decide(position(x=0.)).action, "left")
        self.assertEqual(policy.decide(position(1)).action, "wait")
        self.assertEqual(policy.phase, "setup")
        self.assertEqual(policy.decide(position(2)).action, "right")
        self.assertEqual(policy.phase, "measured")
        self.assertEqual(policy.report()["setup_stopped_frame"], 1)
        self.assertEqual(policy.report()["measurement_start_frame"], 2)

    def test_airborne_setup_waits_for_observed_jump_release_then_measures_landing(self):
        policy = ScenarioPolicy(find_scenario("airborne-left"))
        self.assertEqual(policy.decide(position()).action, "jump")
        self.assertEqual(policy.decide(position(1, action_id=24, input_neutral_derived=False, input_jump_held=True)).action, "jump")
        airborne = position(2, y=2., grounded=False, jumps=1, action_id=25,
            self_velocity_y=3., input_neutral_derived=False, input_jump_held=True)
        self.assertEqual(policy.decide(airborne).action, "wait")
        self.assertEqual(policy.phase, "setup")
        policy.decide(position(3, y=5., grounded=False, jumps=1, action_id=25, self_velocity_y=3.))
        self.assertEqual(policy.phase, "measured")
        policy.decide(position(4, action_id=42))
        self.assertEqual(policy.result["status"], "succeeded")
        self.assertTrue(verified_trial(policy.report(), "airborne-left"))

    def test_returning_to_a_battlefield_platform_counts_as_recovered_stage(self):
        policy = ScenarioPolicy(find_scenario("offstage-left"))
        policy.decide(position(x=-72., y=-1., grounded=False, jumps=1, action_id=29, self_velocity_y=-1.))
        policy.decide(position(1, x=-45., y=27.2001, action_id=42))
        self.assertEqual(policy.result["status"], "succeeded")

    def test_unknown_ground_collision_is_not_a_known_stage_return(self):
        policy = ScenarioPolicy(find_scenario("offstage-left"))
        policy.decide(position(x=-72., y=-1., grounded=False, jumps=1, action_id=29, self_velocity_y=-1.))
        policy.decide(position(1, x=-72., y=-10., grounded=True, action_id=42))
        self.assertFalse(policy.complete)

    def test_setup_failure_does_not_run_measured_controller(self):
        policy = ScenarioPolicy(find_scenario("shielded-opponent"))
        with patch.object(policy.arbiter, "request", side_effect=AssertionError("measurement forbidden")):
            for frame in range(481):
                policy.decide(position(frame))
        self.assertEqual(policy.result["status"], "setup_failed")
        self.assertIsNone(policy.initial)
        self.assertTrue(verified_trial(policy.report(), "shielded-opponent"))
        early = policy.report()
        early["setup_started_frame"] = 1
        self.assertFalse(verified_trial(early, "shielded-opponent"))

    def test_skill_failure_and_measurement_timeout_are_distinct_from_setup_failure(self):
        spec = find_scenario("offstage-left")
        policy = ScenarioPolicy(spec)
        policy.decide(position(x=-72., y=-1., grounded=False, jumps=1, action_id=29, self_velocity_y=-1.))
        policy.decide(position(1, x=-72., y=-2., grounded=False, jumps=1, action_id=29, hitlag_frames_derived=3))
        self.assertEqual(policy.result["status"], "skill_failed")
        policy = ScenarioPolicy(spec)
        for frame in range(181):
            policy.decide(position(frame, x=-72., y=-1., grounded=False, jumps=1, action_id=29, self_velocity_y=-1.))
        self.assertEqual(policy.result["status"], "timeout")
        self.assertTrue(verified_trial(policy.report(), "offstage-left"))

    def test_life_change_and_frame_loss_end_the_trial_without_retrying_setup(self):
        policy = ScenarioPolicy(find_scenario("grounded-right"))
        policy.decide(position())
        policy.decide(position(2))
        self.assertEqual(policy.result["reason"], "observation_discontinuity")
        self.assertEqual(policy.result["status"], "setup_failed")
        policy = ScenarioPolicy(find_scenario("offstage-left"))
        policy.decide(position(x=-72., y=-1., grounded=False, jumps=1, action_id=29))
        policy.decide(position(1, life_generation_derived=2))
        self.assertEqual(policy.result["status"], "skill_failed")
        self.assertEqual(policy.decide(position(2)).action, "wait")

    def test_no_savestate_or_alternate_rules_can_be_smuggled_into_a_report(self):
        policy = ScenarioPolicy(find_scenario("offstage-left"))
        policy.decide(position(x=-72., y=-1., grounded=False, jumps=1, action_id=29))
        policy.decide(position(1))
        report = policy.report()
        report["scenario"]["savestate"] = "wrong-build.sav"
        self.assertFalse(verified_trial(report, "offstage-left"))
        self.assertEqual(len(SUITE), 9)
        with self.assertRaises(ValueError):
            find_scenario("wrong-build.sav")


if __name__ == "__main__":
    unittest.main()
