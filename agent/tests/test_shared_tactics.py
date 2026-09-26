from dataclasses import replace
import unittest

from melee_agent.async_policy import AsyncPolicy
from melee_agent.engine import ACTION_PACKETS
from melee_agent.local_combat_policy import LocalCombatPolicy
from melee_agent.tactical_choices import LABELS, PROFILE, legal_candidates
from test_async_policy import ManualBridge
from test_combat_integration import ground


class SharedTacticalTests(unittest.TestCase):
    def test_live_and_local_candidates_match_across_spacing_shield_and_invulnerability(self):
        base = ground()
        cases = [base, replace(base, opponent=replace(base.opponent, x=40.)),
            replace(base, opponent=replace(base.opponent, details=replace(base.opponent.details, action_id=179))),
            replace(base, opponent=replace(base.opponent, details=replace(base.opponent.details, hurtbox_state=1))),
            replace(base, bot=replace(base.bot, details=replace(base.bot.details, facing_right=False)),
                opponent=replace(base.opponent, x=-8.))]
        for observation in cases:
            live = AsyncPolicy('fixture', ManualBridge(), clock=lambda: observation.observed_ns+1000)
            live.decide(observation)
            offered = live.trace()['semantic_state']['mechanical']['legal_candidates']
            self.assertEqual(offered, list(legal_candidates(observation)))
            for mode in ('heuristic-tactical', 'random-tactical'):
                local = LocalCombatPolicy(mode, seed=7)
                local.decide(observation)
                selection = local.trace()['local_selection']
                self.assertEqual(selection['legal_candidates'], offered)
                self.assertIn(selection['selected'], offered)
                self.assertIsNone(selection['refusal'])
                self.assertEqual(selection['source_frame'], selection['applied_frame'])
                self.assertEqual(local.close()['profile'], PROFILE)

    def test_random_profile_can_choose_all_legal_tactics_and_preserves_seed(self):
        seen = set()
        for seed in range(64):
            choices = []
            for _ in range(2):
                policy = LocalCombatPolicy('random-tactical', seed=seed)
                policy.decide(ground())
                choices.append(policy.trace()['local_selection']['selected'])
                self.assertEqual(policy.close()['seed'], seed)
                self.assertFalse(policy.close()['provider_contacted'])
            self.assertEqual(*choices)
            seen.add(choices[0])
        self.assertEqual(seen, set(LABELS))

    def test_shared_executor_retains_hitlag_and_preempts_damage_without_another_selection(self):
        policy = LocalCombatPolicy('heuristic-tactical')
        self.assertEqual(policy.decide(ground()).action, 'attack')
        policy.decide(ground(1, 44, hitlag_frames_derived=2))
        self.assertIsNotNone(policy.arbiter.active)
        self.assertIsNone(policy.selection)
        decision = policy.decide(ground(2, 79, hitstun_frames_derived=5))
        self.assertIsNone(policy.arbiter.active)
        self.assertEqual(policy.owner, 'emergency')
        self.assertIsNone(policy.selection)
        self.assertFalse(ACTION_PACKETS[decision.action].wire()['buttons']['A'])

    def test_historical_modes_keep_attack_only_random_and_old_trace_contract(self):
        for mode, selected in (('heuristic', 'jab'), ('random-legal', 'dtilt')):
            policy = LocalCombatPolicy(mode, seed=7)
            policy.decide(ground())
            self.assertEqual(policy.selection['selected'], selected)
            self.assertNotIn('legal_candidates', policy.selection)
            self.assertNotIn('profile', policy.close())
