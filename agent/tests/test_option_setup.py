from dataclasses import replace
import unittest

from melee_agent.scenarios import ScenarioPolicy, find_scenario
from test_combat_recenter import scene


class OptionSetupTests(unittest.TestCase):
    def test_option_waits_on_main_ground_until_opponent_shares_the_surface(self):
        for direction,side in ((1,'right'),(-1,'left')):
            for grounded,height in ((False,12.),(True,27.2)):
                policy=ScenarioPolicy(find_scenario('approach-jab-'+side))
                initial=scene(direction,0,-30,-20)
                current=replace(initial,opponent=replace(initial.opponent,
                    x=-30*direction,y=height,grounded=grounded))
                self.assertEqual(policy.decide(current).action,'wait')
                self.assertFalse(policy.combat_crossing)
                self.assertIsNone(policy.measurement_start)
                landed=scene(direction,1,-30,-20)
                self.assertEqual(policy.decide(landed).action,
                    'jump_left' if direction>0 else 'jump_right')

    def test_close_opponent_uses_bounded_hop_spacing_then_observed_neutral(self):
        for direction,side in ((1,'right'),(-1,'left')):
            policy=ScenarioPolicy(find_scenario('approach-jab-'+side))
            away='left' if direction>0 else 'right'
            toward='right' if direction>0 else 'left'
            self.assertEqual(policy.decide(scene(direction,0,-30,-20)).action,'jump_'+away)
            self.assertEqual(policy.decide(scene(direction,1,-30,-20,action_id=24,
                input_jump_held=True,input_neutral_derived=False)).action,away)
            air=scene(direction,2,-38,-20,action_id=26)
            air=replace(air,bot=replace(air.bot,grounded=False,y=8.))
            self.assertEqual(policy.decide(air).action,away)
            air=scene(direction,3,-45,-20,action_id=26)
            air=replace(air,bot=replace(air.bot,grounded=False,y=8.))
            self.assertEqual(policy.decide(air).action,toward)
            self.assertIsNone(policy.measurement_start)
            self.assertEqual(policy.decide(scene(direction,4,-44,-20)).action,'wait')
            self.assertIsNone(policy.measurement_start)
            self.assertEqual(policy.decide(scene(direction,5,-44,-20)).action,'slow_'+toward)
            self.assertEqual(policy.measurement_start,5)

    def test_spacing_does_not_expand_atomic_setup_or_jump_towards_an_edge(self):
        atomic=ScenarioPolicy(find_scenario('jab-right'))
        self.assertEqual(atomic.decide(scene(1,0,-30,-20)).action,'attack')
        edge=ScenarioPolicy(find_scenario('approach-jab-right'))
        self.assertFalse(edge.decide(scene(1,0,-60,-50)).action.startswith('jump'))
        airborne=ScenarioPolicy(find_scenario('approach-jab-right'))
        current=scene(1,0,-30,-20)
        current=replace(current,opponent=replace(current.opponent,grounded=False,y=20.))
        self.assertFalse(airborne.decide(current).action.startswith('jump'))

    def test_damage_and_original_setup_deadline_still_stop_spacing(self):
        policy=ScenarioPolicy(find_scenario('approach-jab-right'))
        self.assertEqual(policy.decide(scene(1,0,-30,-20)).action,'jump_left')
        self.assertEqual(policy.decide(scene(1,1,-30,-20,hitstun_frames_derived=5)).action,'wait')
        for frame in range(2,481):
            policy.decide(scene(1,frame,-30,-20,hitstun_frames_derived=5))
        self.assertEqual(policy.result['status'],'setup_failed')
        self.assertEqual(policy.result['end_frame'],480)
