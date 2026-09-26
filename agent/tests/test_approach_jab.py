from dataclasses import replace
from collections import Counter
from copy import deepcopy
from types import SimpleNamespace
import unittest

from melee_agent.approach_jab import ApproachJab, MAX_FRAMES
from melee_agent.engine import FrameExecutor, ACTION_PACKETS
from melee_agent.fake import RecordingSink
from melee_agent.skills import SkillArbiter, SkillSpec, can_start
from melee_agent.option_evidence import audit_option
from melee_agent.scenarios import ScenarioPolicy, find_scenario
from test_combat_integration import ground


def sample(frame=0,x=0.,motion=14,direction=1,opponent_x=24.,**details):
    observation = ground(frame,motion,**details)
    return replace(observation,bot=replace(observation.bot,x=x*direction,
        details=replace(observation.bot.details,facing_right=direction>0,
            self_velocity_x=observation.bot.details.self_velocity_x*direction)),
        opponent=replace(observation.opponent,x=opponent_x*direction))


class ApproachJabTests(unittest.TestCase):
    def test_two_moves_then_one_fresh_jab_share_the_single_packet_writer(self):
        for direction in (-1,1):
            arbiter,sink = SkillArbiter(),RecordingSink()
            executor = FrameExecutor(SimpleNamespace(decide=arbiter.step),sink,
                SimpleNamespace(now_ns=lambda:1_100_000_000))
            states = [sample(0,direction=direction),
                sample(1,7.,20,direction,self_velocity_x=2.,input_neutral_derived=False),
                sample(2,9.,20,direction),sample(3,10.,14,direction),
                sample(4,17.,20,direction,self_velocity_x=2.,input_neutral_derived=False),
                sample(5,19.,20,direction),sample(6,19.,14,direction),
                sample(7,19.,44,direction),sample(8,19.,14,direction)]
            self.assertIsNone(arbiter.request(SkillSpec('approach_jab',direction),states[0]))
            for state in states:
                executor.step(state)
            terminal = arbiter.last_event
            self.assertEqual(terminal['status'],'succeeded')
            self.assertEqual(terminal['ack_frame'],7)
            option = terminal['option']
            self.assertEqual(option['movement_count'],2)
            self.assertEqual([c['skill'] for c in option['children']],['move','move','jab'])
            self.assertEqual(option['combat']['press_frame'],6)
            self.assertEqual(option['combat']['contact_frames'],[])
            self.assertEqual(len(sink.packets),len(states))
            self.assertEqual(sum(p['buttons']['A'] for p in sink.packets),1)
            self.assertEqual(sink.packets[-1],ACTION_PACKETS['wait'].wire())

    def test_start_refuses_unsupported_geometry_and_target_state(self):
        initial=sample()
        invalid = [replace(initial,opponent=replace(initial.opponent,grounded=False)),
            sample(opponent_x=35),sample(opponent_x=-4),
            replace(initial,bot=replace(initial.bot,details=replace(initial.bot.details,facing_right=False))),
            replace(initial,opponent=replace(initial.opponent,details=replace(initial.opponent.details,hurtbox_state=None))),
            replace(initial,opponent=replace(initial.opponent,details=replace(initial.opponent.details,action_id=179)))]
        for state in invalid:
            self.assertIsNotNone(can_start(SkillSpec('approach_jab',1),state))

    def test_changed_opportunity_never_issues_the_jab(self):
        for change in ('range','crossed','airborne','invulnerable','shield','hitstun','episode','gap'):
            option = ApproachJab(1,sample())
            self.assertEqual(option.step(sample()),'right')
            current=sample(1,7.,20,self_velocity_x=2.)
            if change=='range':current=replace(current,opponent=replace(current.opponent,x=60.))
            if change=='crossed':current=replace(current,opponent=replace(current.opponent,x=0.))
            if change=='airborne':current=replace(current,opponent=replace(current.opponent,grounded=False))
            if change=='invulnerable':current=replace(current,opponent=replace(current.opponent,details=replace(current.opponent.details,hurtbox_state=2)))
            if change=='shield':current=replace(current,opponent=replace(current.opponent,details=replace(current.opponent.details,action_id=179)))
            if change=='hitstun':current=replace(current,bot=replace(current.bot,details=replace(current.bot.details,hitstun_frames_derived=5)))
            if change=='episode':current=replace(current,episode=2)
            if change=='gap':current=sample(2,7.,20,self_velocity_x=2.)
            self.assertEqual(option.step(current),'wait',change)
            self.assertEqual(option.status,'aborted',change)
            self.assertIsNone(option.combat,change)
            self.assertIsNone(option.child.active,change)

    def test_facing_and_input_are_rechecked_after_movement_release(self):
        option=ApproachJab(1,sample(opponent_x=18.))
        option.step(sample(opponent_x=18.))
        option.step(sample(1,7.,20,opponent_x=18.,self_velocity_x=2.))
        option.step(sample(2,9.,20,opponent_x=18.))
        settling=sample(3,9.,14,opponent_x=18.,input_neutral_derived=False)
        self.assertEqual(option.step(settling),'wait')
        self.assertIsNone(option.combat)
        reversed_facing=sample(4,9.,14,opponent_x=18.)
        reversed_facing=replace(reversed_facing,bot=replace(reversed_facing.bot,
            details=replace(reversed_facing.bot.details,facing_right=False)))
        self.assertEqual(option.step(reversed_facing),'wait')
        self.assertEqual(option.reason,'facing_changed')

    def test_jab_hitlag_retains_commitment_and_damage_preempts(self):
        arbiter=SkillArbiter()
        start=sample(opponent_x=8.)
        arbiter.request(SkillSpec('approach_jab',1),start)
        self.assertEqual(arbiter.step(start).action,'attack')
        hitlag=sample(1,motion=44,opponent_x=8.,hitlag_frames_derived=3)
        self.assertTrue(arbiter.retains_attack_hitlag(hitlag))
        self.assertEqual(arbiter.step(hitlag).action,'wait')
        damage=sample(2,motion=75,opponent_x=8.,hitstun_frames_derived=4)
        self.assertFalse(arbiter.retains_attack_hitlag(damage))
        self.assertEqual(arbiter.step(damage).action,'wait')
        self.assertEqual(arbiter.last_event['option']['reason'],'own_hitstun')
        self.assertEqual(arbiter.last_event['option']['combat']['ack_frame'],1)

    def test_settling_and_chasing_have_independent_hard_bounds(self):
        option=ApproachJab(1,sample(motion=20))
        for frame in range(MAX_FRAMES):
            self.assertEqual(option.step(sample(frame,motion=20)),'wait')
        self.assertEqual(option.step(sample(MAX_FRAMES,motion=20)),'wait')
        self.assertEqual((option.status,option.reason),('timeout','option_deadline'))
        travel=ApproachJab(1,sample())
        travel.step(sample())
        self.assertEqual(travel.step(sample(1,31.,20,opponent_x=50.)),'wait')
        self.assertEqual(travel.reason,'travel_bound')

    def test_movement_count_and_stock_change_end_without_an_attack(self):
        option=ApproachJab(1,sample())
        for index in range(4):
            frame,x=index*3,index*6.
            self.assertEqual(option.step(sample(frame,x,opponent_x=x+24)),'right')
            self.assertEqual(option.step(sample(frame+1,x+6,20,opponent_x=x+30,self_velocity_x=2.)),'wait')
            self.assertEqual(option.step(sample(frame+2,x+6,20,opponent_x=x+30)),'wait')
        self.assertEqual(option.step(sample(12,24,opponent_x=48)),'wait')
        self.assertEqual(option.reason,'movement_count_bound')
        fresh=ApproachJab(1,sample())
        fresh.step(sample())
        changed=sample(1,life_generation_derived=2)
        self.assertEqual(fresh.step(changed),'wait')
        self.assertEqual(fresh.reason,'life_or_episode_changed')

    def test_scenario_and_raw_auditor_require_actual_child_motion_and_packets(self):
        policy=ScenarioPolicy(find_scenario('approach-jab-right'))
        executor=FrameExecutor(policy,RecordingSink(),SimpleNamespace(now_ns=lambda:1_100_000_000))
        states=[sample(0),sample(1,7,20,self_velocity_x=2.),sample(2,9,20),
            sample(3,10),sample(4,17,20,self_velocity_x=2.),sample(5,19,20),
            sample(6,19),sample(7,19,44),sample(8,19)]
        rows=[]
        for state in states:
            control=executor.step(state)
            players={}
            for port,fighter in (('1',state.bot),('2',state.opponent)):
                d=fighter.details
                players[port]={'raw_post':{'action_id':d.action_id,'x':fighter.x,'y':fighter.y,
                    'airborne':int(not fighter.grounded),'speed_ground_x_self':d.self_velocity_x,
                    'percent':d.percent,'hurtbox_state':d.hurtbox_state,'state_flags_2':0,
                    'state_flags_4':0,'hitlag_raw':0.,'misc_as_raw':0.,'available':{
                        k:True for k in ('hurtbox_state','state_flags_2','state_flags_4','hitlag_raw','misc_as_raw')}}}
            rows.append({'frame':state.frame,'control':control,'scenario':deepcopy(policy.trace()),
                'raw_observation':{'players':players}})
        report=policy.report()
        errors=Counter()
        evidence=audit_option(report,rows,errors)
        self.assertEqual(errors,{})
        self.assertEqual(evidence,{'moves_acknowledged':2,'jab_acknowledged':True,'completed':True,'contacts':0})
        for change in ('movement','packet','jab'):
            altered=deepcopy(rows)
            if change=='movement':altered[1]['raw_observation']['players']['1']['raw_post']['x']=1.
            if change=='packet':altered[0]['control']['packet']=ACTION_PACKETS['wait'].wire()
            if change=='jab':altered[7]['raw_observation']['players']['1']['raw_post']['action_id']=14
            errors=Counter()
            audit_option(report,altered,errors)
            self.assertTrue(errors,change)
