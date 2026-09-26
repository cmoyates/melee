from dataclasses import replace
import unittest

from melee_agent import scenarios as module
from test_scenarios import position


def scene(direction, frame, x, other, **details):
    observation = position(frame, x=x*direction, facing_right=direction > 0, **details)
    return replace(observation, opponent=replace(observation.opponent, x=other*direction,
        y=0., grounded=True, details=replace(observation.opponent.details, action_id=14, hurtbox_state=0)))


class RecenterTests(unittest.TestCase):
    def test_mirrored_edge_trap_recenters_waits_for_opponent_and_releases_before_crossing(self):
        for direction, side in ((1, 'right'), (-1, 'left')):
            policy = module.ScenarioPolicy(module.find_scenario('jab-'+side))
            toward, away = ('right','left') if direction == 1 else ('left','right')
            self.assertEqual(policy.decide(scene(direction, 0, -62, -68)).action, toward)
            self.assertEqual(policy.setup_phase, 'recenter_for_crossing')
            self.assertEqual(policy.decide(scene(direction, 1, -30, -65)).action, toward)
            self.assertEqual(policy.decide(scene(direction, 2, -14, -60)).action, 'wait')
            self.assertTrue(policy.combat_recentering)
            self.assertEqual(policy.decide(scene(direction, 3, -14, -25)).action, 'wait')
            self.assertFalse(policy.combat_recentering)
            self.assertEqual(policy.decide(scene(direction, 4, -14, -25)).action, 'jump_'+away)
            self.assertIsNone(policy.measurement_start)

    def test_recenter_cannot_override_damage_inhibition_or_expire_setup_late(self):
        policy = module.ScenarioPolicy(module.find_scenario('jab-right'))
        self.assertEqual(policy.decide(scene(1, 0, -62, -68)).action, 'right')
        self.assertEqual(policy.decide(scene(1, 1, -60, -66, hitstun_frames_derived=3)).action, 'wait')
        for frame in range(2, 481):
            decision = policy.decide(scene(1, frame, -14, -60))
            self.assertEqual(decision.action, 'wait')
        self.assertEqual(policy.result['status'], 'setup_failed')
        self.assertEqual(policy.result['reason'], 'starting_predicate_timeout')
        self.assertEqual(policy.result['end_frame'], 480)

    def test_legal_interior_attack_keeps_same_neutral_measurement_boundary(self):
        for direction, side in ((1,'right'),(-1,'left')):
            policy = module.ScenarioPolicy(module.find_scenario('jab-'+side))
            self.assertEqual(policy.decide(scene(direction, 0, 0, 8)).action, 'attack')
            self.assertEqual(policy.measurement_start, 0)
            self.assertFalse(policy.combat_recentering)


if __name__ == '__main__':
    unittest.main()
