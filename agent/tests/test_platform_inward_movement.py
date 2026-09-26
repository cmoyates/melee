from dataclasses import replace
import unittest

from melee_agent.async_policy import AsyncPolicy
from melee_agent.local_combat_policy import LocalCombatPolicy
from melee_agent.skills import SkillSpec, can_start
from melee_agent.stage import PLATFORMS
from melee_agent.tactical_choices import legal_candidates
from test_async_policy import ManualBridge
from test_combat_integration import ground


def edge_state(platform, edge, frame=0):
    state = ground(frame)
    x = platform[edge] + (-.004 if edge == 'left' else .004)
    return replace(state, bot=replace(state.bot, x=x, y=platform['height']),
        opponent=replace(state.opponent, x=x+(-20 if edge == 'left' else 20), y=platform['height']))


class PlatformInwardMovementTests(unittest.TestCase):
    def test_all_six_platform_edges_allow_only_the_inward_escape(self):
        for platform in PLATFORMS:
            for edge, inward in (('left',1),('right',-1)):
                state = edge_state(platform,edge)
                self.assertIsNone(can_start(SkillSpec('move',inward),state))
                self.assertEqual(can_start(SkillSpec('move',-inward),state),'support_edge')
                self.assertIn('retreat',legal_candidates(state))
                self.assertNotIn('approach',legal_candidates(state))

    def test_normal_interior_destination_margin_is_not_relaxed(self):
        for platform in PLATFORMS:
            state = edge_state(platform,'right')
            state = replace(state,bot=replace(state.bot,x=platform['right']-9))
            self.assertEqual(can_start(SkillSpec('move',1),state),'support_edge')
            self.assertIsNone(can_start(SkillSpec('move',-1),state))

    def test_unknown_airborne_and_damage_states_still_refuse(self):
        state = edge_state(PLATFORMS[0],'right')
        for bot in (replace(state.bot,y=30.),replace(state.bot,grounded=False),
                replace(state.bot,details=replace(state.bot.details,hitstun_frames_derived=3))):
            self.assertIsNotNone(can_start(SkillSpec('move',-1),replace(state,bot=bot)))

    def test_fallback_and_heuristic_escape_the_retained_inner_edge_sample(self):
        state = edge_state(PLATFORMS[0],'right')
        state = replace(state,bot=replace(state.bot,x=-19.995738983154297))
        policy = AsyncPolicy('fixture',ManualBridge(),clock=lambda:state.observed_ns+1000)
        policy.decide(state)
        self.assertEqual(policy.arbiter.trace()['active']['direction'],-1)
        self.assertEqual(policy.arbiter.trace()['active']['skill'],'move')
        local = LocalCombatPolicy('heuristic-tactical')
        self.assertEqual(local.decide(state).action,'left')
        self.assertEqual(local.selection['selected'],'retreat')
        # Returning into the ordinary interior restores the normal destination rule.
        interior = replace(state,bot=replace(state.bot,x=-36.))
        self.assertIn('approach',legal_candidates(interior))
