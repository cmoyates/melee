import unittest

from melee_agent.async_policy import AsyncPolicy
from melee_agent.fox_reflex import FoxReflex
from melee_agent.skills import SkillSpec, can_start
from melee_agent.stage import GROUND_EDGE, PLATFORMS, SUPPORT_HORIZONTAL_TOLERANCE, support_surface
from test_async_policy import ManualBridge
from test_scenarios import position


class PlatformBoundaryTests(unittest.TestCase):
    def test_recorded_grounded_wait_positions_and_mirrors_have_estimated_support(self):
        for x, y, surface in ((18.801410675, 54.400100708, 'top'),
                (57.636955261, 27.200099945, 'right')):
            self.assertEqual(support_surface(x, y, True), surface)
            self.assertEqual(support_surface(-x, y, True), 'left' if surface == 'right' else surface)
            self.assertIsNone(support_surface(x, y, False))
            self.assertEqual(support_surface(x, y+0.51, True), 'unknown')

    def test_tolerance_is_bounded_at_each_support_edge_and_requires_grounded_height(self):
        surfaces = ((-GROUND_EDGE, GROUND_EDGE, 0., 'ground'),) + tuple(
            (p['left'], p['right'], p['height'], p['id']) for p in PLATFORMS)
        for left, right, height, name in surfaces:
            for edge, direction in ((left, -1), (right, 1)):
                inside = edge+direction*(SUPPORT_HORIZONTAL_TOLERANCE-1e-6)
                outside = edge+direction*(SUPPORT_HORIZONTAL_TOLERANCE+1e-6)
                self.assertEqual(support_surface(inside, height, True), name)
                self.assertEqual(support_surface(outside, height, True), 'unknown')
                self.assertIsNone(support_surface(inside, height, False))
                self.assertEqual(support_surface(inside, height+0.5, True), 'unknown')

    def test_supported_landing_clears_a_previous_failure_and_resumes_tactical_ownership(self):
        policy = AsyncPolicy('boundary-test', ManualBridge(), clock=lambda: 1_100_000_000)
        unknown = position(0, x=20., y=54.400100708)
        policy.decide(unknown)
        self.assertTrue(policy.recovery.failed)
        self.assertEqual(policy.trace()['input_owner'], 'emergency')
        boundary = position(1, x=18.801410675, y=54.400100708)
        policy.decide(boundary)
        self.assertFalse(policy.recovery.failed)
        self.assertEqual(policy.recovery.phase, 'safe')
        self.assertIsNone(policy.recovery.started_frame)
        self.assertNotEqual(policy.trace()['input_owner'], 'emergency')
        self.assertIsNone(can_start(SkillSpec('jump'), boundary))
        self.assertEqual(can_start(SkillSpec('move', 1), boundary), 'support_edge')

    def test_damage_and_truly_unknown_geometry_still_preempt(self):
        reflex = FoxReflex()
        boundary = position(x=18.801410675, y=54.400100708, hitstun_frames_derived=3)
        self.assertEqual(reflex.reason(boundary), 'hitstun')
        reflex.decide_action(boundary)
        self.assertEqual(reflex.phase, 'defensive_drift')
        unknown = position(1, x=19., y=54.400100708)
        self.assertEqual(reflex.reason(unknown), 'unknown_geometry')
        reflex.decide_action(unknown)
        self.assertTrue(reflex.failed)
        self.assertEqual(reflex.last_action, 'wait')
