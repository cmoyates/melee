from dataclasses import replace
from types import SimpleNamespace
import unittest

from melee_agent.fox_reflex import FoxReflex, horizontal_recovery_entry
from test_fox_reflex import air
from test_scenarios import position


def displaced(frame=0, side=1, **changes):
    return air(frame,x=side*134.2,y=45.1,jumps=1,action_id=38,self_velocity_y=-2.8,**changes)


class HorizontalRecoveryTests(unittest.TestCase):
    def test_local_and_async_players_share_one_preempting_recovery_writer(self):
        from melee_agent.async_policy import AsyncPolicy
        from melee_agent.engine import ACTION_PACKETS, FrameExecutor
        from melee_agent.fake import RecordingSink
        from melee_agent.local_combat_policy import LocalCombatPolicy
        from melee_agent.skills import SkillSpec
        from test_async_policy import ManualBridge
        for policy in (LocalCombatPolicy('heuristic-tactical'),
                AsyncPolicy('test',ManualBridge(),clock=lambda:1_100_000_000)):
            sink=RecordingSink()
            executor=FrameExecutor(policy,sink,SimpleNamespace(now_ns=lambda:1_100_000_000))
            executor.step(position())
            policy.arbiter.request(SkillSpec('jump'),position())
            executor.step(displaced(1))
            self.assertEqual(len(sink.packets),2)
            self.assertEqual(sink.packets[-1],ACTION_PACKETS['jump_left'].wire())
            self.assertIsNone(policy.arbiter.active)
            self.assertEqual(policy.trace()['input_owner'],'emergency')
            self.assertEqual(policy.trace()['reflex']['horizontal_start']['frame'],1)

    def test_retained_damagefall_geometry_gets_one_inward_jump_and_observed_ack(self):
        # Development cohort slot9/frame15207: x134.2/y45.1, one jump,
        # DamageFall38. This test proves emitted input, not recoverability.
        for side,inward in ((-1,'right'),(1,'left')):
            policy=FoxReflex()
            self.assertEqual(policy.decide_action(displaced(side=side)),'jump_'+inward)
            self.assertEqual(policy.trace()['horizontal_start']['x'],side*134.2)
            self.assertEqual(policy.counts['horizontal_admissions'],1)
            self.assertEqual(policy.decide_action(air(1,x=side*135,y=48,jumps=0,
                action_id=27,self_velocity_y=3.,input_jump_held=True)),inward)
            self.assertEqual(policy.counts['observed_double_jumps'],1)
            for frame in range(2,10):
                self.assertEqual(policy.decide_action(air(frame,x=side*134,y=55,jumps=0,
                    action_id=27,self_velocity_y=1.)),inward)
            self.assertEqual(policy.counts['jump_attempts'],1)
            self.assertFalse(policy.failed)

    def test_only_declared_airborne_damagefall_resource_and_geometry_are_admitted(self):
        base=displaced()
        changes=[{'x':130.},{'x':180.01},{'y':-.01},{'y':140.01},{'jumps':0},{'jumps':2},
            {'grounded':True}]
        observations=[replace(base,bot=replace(base.bot,**c)) for c in changes]
        observations.append(replace(base,bot=replace(base.bot,stocks_remaining=0,
            details=replace(base.bot.details,life_generation_derived=5))))
        observations.extend(replace(base,bot=replace(base.bot,details=replace(base.bot.details,**c))) for c in
            ({'action_id':29},{'hitlag_frames_derived':1},{'hitstun_frames_derived':1},
            {'input_jump_held':True},{'self_velocity_y':.01}))
        observations.append(replace(base,frame=-1))
        for value in observations:
            self.assertFalse(horizontal_recovery_entry(value),value)
            policy=FoxReflex()
            policy.decide_action(value)
            self.assertNotIn('horizontal_start',policy.trace())

    def test_missing_jump_ack_is_terminal_without_second_jump_or_special(self):
        policy=FoxReflex()
        actions=[policy.decide_action(displaced(frame)) for frame in range(30)]
        self.assertEqual(actions.count('jump_left'),1)
        self.assertNotIn('special_up',actions)
        self.assertEqual(actions[8:],['wait']*22)
        self.assertEqual(policy.event['reason'],'horizontal_jump_unacknowledged')

    def test_frame_gap_does_not_readmit_the_same_knockback_or_extend_deadline(self):
        policy=FoxReflex()
        policy.decide_action(displaced())
        self.assertEqual(policy.decide_action(displaced(3)),'wait')
        self.assertEqual(policy.decide_action(displaced(4)),'wait')
        self.assertTrue(policy.failed)
        self.assertEqual(policy.started_frame,0)
        self.assertEqual(policy.counts['horizontal_admissions'],1)

    def test_damage_interrupts_extended_envelope_and_uses_fresh_resources(self):
        policy=FoxReflex()
        policy.decide_action(displaced())
        policy.decide_action(air(1,x=140,y=50,jumps=0,action_id=27,self_velocity_y=3.))
        policy.decide_action(air(2,x=145,y=50,jumps=0,action_id=88,hitstun_frames_derived=4))
        self.assertNotIn('horizontal_start',policy.trace())
        self.assertEqual(policy.counts['horizontal_interruptions'],1)
        self.assertEqual(policy.decide_action(air(3,x=145,y=50,jumps=0,action_id=38)),'wait')
        self.assertTrue(policy.failed)
        self.assertEqual(policy.counts['horizontal_admissions'],1)

    def test_outer_bound_and_original_deadline_still_terminate(self):
        for value in (air(1,x=180.1,y=60,jumps=0,action_id=27),air(1,x=140,y=-85.1,jumps=0,action_id=27)):
            policy=FoxReflex()
            policy.decide_action(displaced())
            self.assertEqual(policy.decide_action(value),'wait')
            self.assertTrue(policy.failed)
        policy=FoxReflex()
        policy.decide_action(displaced())
        policy.decide_action(air(1,x=140,y=60,jumps=0,action_id=27,self_velocity_y=3.))
        for frame in range(2,181):
            policy.decide_action(air(frame,x=140,y=60,jumps=0,action_id=27,self_velocity_y=1.))
        self.assertTrue(policy.failed)
        self.assertEqual(policy.event['reason'],'recovery_deadline')

    def test_observed_stage_return_and_new_life_clear_the_admission(self):
        policy=FoxReflex()
        policy.decide_action(displaced())
        policy.decide_action(position(1,x=40.))
        self.assertNotIn('horizontal_start',policy.trace())
        self.assertEqual(policy.counts['observed_stage_returns'],1)
        self.assertFalse(policy.horizontal_used)
        policy.decide_action(displaced(2))
        policy.decide_action(air(3,x=140,y=50,action_id=0))
        self.assertNotIn('horizontal_start',policy.trace())
        self.assertEqual(policy.decide_action(displaced(4,life_generation_derived=2)),'jump_left')


if __name__=='__main__':
    unittest.main()
