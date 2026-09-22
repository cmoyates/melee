from dataclasses import asdict
import random
from types import SimpleNamespace
import unittest

from melee_agent.ground_combat import GroundCombat, can_start_combat, combat_candidates, select_combat
from test_scenarios import position


def combat_state(frame=0, direction=1, own_motion=14, opponent_motion=14, **changes):
    source = asdict(position(frame, x=0.))
    for key in ("bot", "opponent"):
        source[key]["details"] = SimpleNamespace(**{**source[key]["details"], "hurtbox_state": 0})
        source[key] = SimpleNamespace(**source[key])
    source["bot"].details.facing_right = direction > 0
    source["bot"].details.action_id = own_motion
    source["opponent"].x = 8.*direction
    source["opponent"].y = 0.
    source["opponent"].grounded = True
    source["opponent"].details.action_id = opponent_motion
    source["opponent"].details.percent = 0.
    result = SimpleNamespace(**source)
    for path, value in changes.items():
        target = result
        parts = path.split("__")
        for part in parts[:-1]:
            target = getattr(target, part)
        setattr(target, parts[-1], value)
    return result


class GroundCombatTests(unittest.TestCase):
    def test_down_tilt_squat_reversal_is_endlag_not_a_new_attack_or_completed_skill(self):
        skill = GroundCombat("dtilt", 1, combat_state())
        skill.step(combat_state())
        skill.step(combat_state(1, own_motion=57))
        self.assertEqual(skill.step(combat_state(2, own_motion=41)), "wait")
        self.assertIsNone(skill.status)
        skill.step(combat_state(3))
        self.assertEqual(skill.status, "succeeded")

    def test_delayed_first_step_rechecks_legality_before_the_actual_press(self):
        skill = GroundCombat("jab", 1, combat_state())
        self.assertEqual(skill.step(combat_state(1, opponent__x=30.)), "wait")
        self.assertEqual(skill.reason, "prepress:out_of_range")
        self.assertIsNone(skill.press_frame)
        skill = GroundCombat("jab", 1, combat_state())
        self.assertEqual(skill.step(combat_state(1)), "attack")
        self.assertEqual(skill.press_frame, 1)
        self.assertEqual(skill.step(combat_state(2, own_motion=44)), "wait")
        self.assertEqual(skill.ack_frame, 2)

    def test_each_direction_and_action_needs_one_press_observed_motion_and_actionable_release(self):
        for name, motion, action in (("jab", 44, "attack"), ("dtilt", 57, "down_tilt"), ("grab", 212, "grab")):
            for direction in (-1, 1):
                skill = GroundCombat(name, direction, combat_state(direction=direction))
                self.assertEqual(skill.step(combat_state(direction=direction)), action)
                self.assertEqual(skill.step(combat_state(1, direction, own_motion=motion)), "wait")
                self.assertEqual(skill.ack_frame, 1)
                self.assertIsNone(skill.status)
                skill.step(combat_state(2, direction, own_motion=motion))
                self.assertIsNone(skill.status)
                skill.step(combat_state(3, direction))
                self.assertEqual(skill.status, "succeeded")
                self.assertFalse(skill.contact_frames)
                self.assertIsNone(skill.capture_frame)

    def test_invulnerability_shield_range_facing_and_input_guards_refuse_before_a_press(self):
        cases = (({"opponent__details__hurtbox_state": 1}, "opponent_invulnerable_or_unknown"),
            ({"opponent__details__hurtbox_state": None}, "opponent_invulnerable_or_unknown"),
            ({"opponent_motion": 179}, "opponent_shielded"),
            ({"opponent__x": 20.}, "out_of_range"),
            ({"bot__details__facing_right": False}, "wrong_facing"),
            ({"bot__details__input_neutral_derived": False}, "requires_released_input"),
            ({"bot__details__hitstun_frames_derived": 3}, "own_damage_or_hitlag"))
        for changes, expected in cases:
            observation = combat_state(**changes)
            self.assertEqual(can_start_combat("jab", 1, observation), expected)
            with self.assertRaisesRegex(ValueError, expected):
                GroundCombat("jab", 1, observation)
        self.assertIsNone(can_start_combat("grab", 1, combat_state(opponent_motion=179)))

    def test_hitlag_preserves_commitment_and_paired_damage_is_separate_contact_evidence(self):
        skill = GroundCombat("jab", 1, combat_state())
        skill.step(combat_state())
        skill.step(combat_state(1, own_motion=44))
        skill.step(combat_state(2, own_motion=44, opponent_motion=75,
            bot__details__hitlag_frames_derived=3, opponent__details__hitlag_frames_derived=3,
            opponent__details__percent=4.))
        self.assertIsNone(skill.status)
        self.assertEqual(skill.contact_frames, [2])
        skill.step(combat_state(3, own_motion=44, opponent_motion=75,
            bot__details__hitlag_frames_derived=2, opponent__details__hitlag_frames_derived=2,
            opponent__details__percent=4.))
        self.assertEqual(skill.contact_frames, [2])

    def test_shield_contact_and_opponent_escape_do_not_become_damage_or_capture(self):
        skill = GroundCombat("jab", 1, combat_state())
        skill.step(combat_state())
        skill.step(combat_state(1, own_motion=44))
        skill.step(combat_state(2, own_motion=44, opponent_motion=181, bot__details__hitlag_frames_derived=2))
        self.assertEqual(skill.shield_contact_frames, [2])
        skill.step(combat_state(3, own_motion=44, opponent__x=35.))
        skill.step(combat_state(4, opponent__x=35.))
        self.assertEqual(skill.status, "succeeded")
        self.assertEqual(skill.contact_frames, [])
        self.assertIsNone(skill.capture_frame)

    def test_grab_motion_alone_does_not_assert_capture_or_endlag_completion(self):
        skill = GroundCombat("grab", 1, combat_state())
        skill.step(combat_state())
        skill.step(combat_state(1, own_motion=212))
        self.assertIsNone(skill.capture_frame)
        skill.step(combat_state(2, own_motion=213, opponent_motion=223))
        self.assertEqual(skill.capture_frame, 2)
        self.assertIsNone(skill.status)
        skill.step(combat_state(3, own_motion=216, opponent_motion=224))
        self.assertIsNone(skill.status)
        skill.step(combat_state(4, own_motion=218, opponent_motion=229))
        skill.step(combat_state(5))
        self.assertEqual(skill.status, "succeeded")
        self.assertEqual(skill.end_frame, 5)

    def test_hitstun_life_change_and_frame_loss_abort_with_neutral(self):
        for changed in (combat_state(2, own_motion=75, bot__details__hitstun_frames_derived=4),
                combat_state(2, bot__details__life_generation_derived=2), combat_state(4)):
            skill = GroundCombat("dtilt", 1, combat_state())
            skill.step(combat_state())
            skill.step(combat_state(1, own_motion=57))
            self.assertEqual(skill.step(changed), "wait")
            self.assertEqual(skill.status, "aborted")

    def test_missing_ack_and_stuck_capture_are_bounded(self):
        skill = GroundCombat("jab", 1, combat_state())
        actions = [skill.step(combat_state(frame)) for frame in range(30)]
        self.assertEqual(actions.count("attack"), 1)
        self.assertEqual(skill.status, "timeout")
        self.assertEqual(skill.end_frame, 8)
        skill = GroundCombat("grab", 1, combat_state())
        skill.step(combat_state())
        skill.step(combat_state(1, own_motion=212))
        for frame in range(2, 181):
            skill.step(combat_state(frame, own_motion=216, opponent_motion=224))
        self.assertEqual(skill.status, "timeout")
        self.assertEqual(skill.end_frame, 180)
        self.assertEqual(skill.capture_frame, 2)

    def test_both_selectors_use_the_exact_same_legal_candidate_set(self):
        for observation in (combat_state(), combat_state(opponent_motion=179),
                combat_state(opponent__x=14.), combat_state(opponent__details__hurtbox_state=2)):
            candidates = combat_candidates(observation)
            heuristic = select_combat(observation)
            random_choice = select_combat(observation, "random-legal", random.Random(3))
            if candidates:
                self.assertIn(heuristic, candidates)
                self.assertIn(random_choice, candidates)
            else:
                self.assertIsNone(heuristic)
                self.assertIsNone(random_choice)


if __name__ == "__main__":
    unittest.main()
