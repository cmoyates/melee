from collections import Counter
from copy import deepcopy
from dataclasses import asdict,replace
import unittest
from unittest.mock import patch

from melee_agent.cli import main
from melee_agent.engine import ACTION_PACKETS
from melee_agent.platform_jump import PlatformJump,can_start_platform_jump
from melee_agent.platform_audit import audit_platform,platform_acceptance
from melee_agent.scenarios import ScenarioPolicy,find_scenario,find_suite,suite_hash,verified_trial
from melee_agent.skills import SkillArbiter,SkillSpec,relative_skill
from test_scenarios import position


def state(frame=0,direction=1,*,y=0.,grounded=True,jumps=2,**details):
    return position(frame,x=45.*direction,y=y,grounded=grounded,jumps=jumps,**details)


def flight(direction=1):
    return [state(direction=direction)]+[state(f,direction,action_id=24,
        input_jump_held=True,input_neutral_derived=False) for f in (1,2,3)]+[
        state(4,direction,y=3.68,grounded=False,jumps=1,action_id=25,self_velocity_y=3.68,
            input_jump_held=True,input_neutral_derived=False),
        state(5,direction,y=20.,grounded=False,jumps=1,action_id=25,self_velocity_y=1.),
        state(6,direction,y=31.28,grounded=False,jumps=1,action_id=29,self_velocity_y=-.5),
        state(7,direction,y=27.2001,action_id=42),state(8,direction,y=27.2001)]


def recorded(direction=1):
    arbiter=SkillArbiter();arbiter.request(SkillSpec('platform_jump',direction),state(direction=direction))
    rows=[];previous=ACTION_PACKETS['wait'].wire()
    for value in flight(direction):
        action=arbiter.step(value).action;a,d=value.bot,value.bot.details
        raw={'action_id':d.action_id,'x':a.x,'y':a.y,'airborne':int(not a.grounded),
            'jumps':a.jumps,'speed_y_self':d.self_velocity_y,'speed_ground_x_self':d.self_velocity_x,
            'state_flags_2':0,'state_flags_4':0,'hitlag_raw':0.,'misc_as_raw':0.,
            'available':{k:True for k in ('state_flags_2','state_flags_4','hitlag_raw','misc_as_raw')}}
        packet=ACTION_PACKETS[action].wire()
        rows.append({'frame':value.frame,'raw_observation':{'players':{'1':{'raw_post':raw}}},
            'control':{'packet':packet,'observation':asdict(value)},
            'input_provenance':{'observed':previous},'scenario':{'skill':deepcopy(arbiter.trace())}})
        previous=packet
    return {'skill':arbiter.trace(),'result':{'status':'succeeded'}},rows


class PlatformJumpTests(unittest.TestCase):
    def test_both_targets_hold_existing_jump_then_release_through_landing(self):
        for direction in (-1,1):
            report,rows=recorded(direction)
            event=report['skill']['event']
            self.assertEqual(event['status'],'succeeded')
            self.assertEqual(event['ack_frame'],4)
            self.assertEqual(event['platform']['target'],'left' if direction<0 else 'right')
            self.assertEqual([r['control']['packet'] for r in rows],
                [ACTION_PACKETS['jump'].wire()]*4+[ACTION_PACKETS['wait'].wire()]*5)
            self.assertEqual(len(event['platform']['children']),1)

    def test_admission_rejects_motion_input_resource_and_geometry_changes(self):
        invalid=[state(action_id=15),state(input_jump_held=True),state(jumps=1),
            state(input_neutral_derived=False),state(self_velocity_x=.05),state(y=27.2001),
            state(hitstun_frames_derived=1),state(-1),replace(state(),bot=replace(state().bot,x=0.))]
        for value in invalid:self.assertIsNotNone(can_start_platform_jump(1,value))
        self.assertIsNotNone(can_start_platform_jump(True,state()))
        self.assertIsNotNone(can_start_platform_jump(-1,state()))

    def test_missing_takeoff_has_eight_frame_deadline_and_no_retry(self):
        skill=PlatformJump(1,state())
        for f in range(8):self.assertEqual(skill.step(state(f)),'jump')
        self.assertEqual(skill.step(state(8)),'wait')
        self.assertEqual(skill.reason,'takeoff_not_observed')
        self.assertEqual(skill.step(state(9)),'wait')
        self.assertEqual(len(skill.children),1)

    def test_missing_knee_or_consumed_resource_cannot_acknowledge_full_jump(self):
        for missing_knee in (True,False):
            skill=PlatformJump(1,state());skill.step(state())
            if not missing_knee:skill.step(flight()[1])
            f=1 if missing_knee else 2
            value=state(f,y=3.,grounded=False,jumps=1 if missing_knee else 0,
                action_id=25,self_velocity_y=3.68)
            self.assertEqual(skill.step(value),'wait')
            self.assertEqual(skill.reason,'unconfirmed_full_jump')

    def test_early_release_and_unexpected_ground_motion_stop_child(self):
        for value,reason in ((state(1,action_id=24),'jump_released_before_takeoff'),
                (state(1,action_id=15),'unexpected_jumpsquat_motion')):
            skill=PlatformJump(1,state());skill.step(state())
            self.assertEqual(skill.step(value),'wait');self.assertEqual(skill.reason,reason)

    def test_damage_gap_and_life_change_abort_and_never_follow_up(self):
        for value in (state(1,hitstun_frames_derived=1),state(1,hitlag_frames_derived=1),
                state(2),state(1,life_generation_derived=state().bot.details.life_generation_derived+1)):
            arbiter=SkillArbiter();arbiter.request(SkillSpec('platform_jump',1),state());arbiter.step(state())
            self.assertEqual(arbiter.step(value).action,'wait')
            self.assertIsNone(arbiter.active)
            self.assertEqual(arbiter.last_event['status'],'aborted')
            self.assertEqual(arbiter.step(state(value.frame+1)).action,'wait')

    def test_wrong_surface_drift_and_airborne_resource_end_transfer(self):
        for value in (state(6),replace(flight()[6],bot=replace(flight()[6].bot,x=49.)),
                state(6,y=30.,grounded=False,jumps=0,action_id=29)):
            skill=PlatformJump(1,state())
            for v in flight()[:6]:skill.step(v)
            self.assertEqual(skill.step(value),'wait');self.assertEqual(skill.status,'aborted')

    def test_landing_requires_standing_neutral_and_air_wait_is_bounded(self):
        skill=PlatformJump(1,state())
        for v in flight()[:8]:skill.step(v)
        self.assertEqual(skill.step(state(8,y=27.2001,input_neutral_derived=False)),'wait')
        self.assertIsNone(skill.status)
        skill.step(state(9,y=27.2001));self.assertEqual(skill.status,'succeeded')
        skill=PlatformJump(1,state())
        for v in flight()[:6]:skill.step(v)
        for f in range(6,91):self.assertEqual(skill.step(state(f,y=30.,grounded=False,jumps=1,action_id=29)),'wait')
        self.assertEqual(skill.reason,'platform_completion_deadline')

    def test_raw_audit_verifies_both_targets_and_rejects_forged_motion_or_input(self):
        for direction,side in ((-1,'left'),(1,'right')):
            spec=find_scenario('calibration-platform-jump-'+side)
            report,rows=recorded(direction);errors=Counter()
            result=audit_platform(spec,report,rows,errors)
            self.assertFalse(errors);self.assertTrue(result['completed'])
            for mode in ('knee','resource','extra_jump','landing','neutral','incomplete_input','drift','midair_resource'):
                altered=deepcopy(rows)
                if mode=='knee':altered[2]['input_provenance']['observed']['buttons']['X']=False
                if mode=='resource':altered[4]['raw_observation']['players']['1']['raw_post']['jumps']=0
                if mode=='extra_jump':altered[6]['control']['packet']=ACTION_PACKETS['jump'].wire()
                if mode=='landing':altered[-1]['raw_observation']['players']['1']['raw_post']['y']=0.
                if mode=='neutral':altered[-1]['input_provenance']['observed']['buttons']['X']=True
                if mode=='incomplete_input':altered[-1]['input_provenance']['observed']['buttons'].pop('Y')
                if mode=='drift':altered[6]['raw_observation']['players']['1']['raw_post']['x']+=3
                if mode=='midair_resource':altered[6]['raw_observation']['players']['1']['raw_post']['jumps']=0
                errors=Counter();audit_platform(spec,report,altered,errors)
                self.assertTrue(errors,mode)

    def test_acceptance_retains_missing_failed_and_wrong_fixture_trials(self):
        rows=[{'scenario':s.name,'status':'pass','opponent_control':'neutral-human-v1',
            'trial_status':'succeeded','platform':{'full_jump_observed':True,'completed':True}}
            for s in find_suite('platform-jump-calibration-v1') for _ in range(20)]
        self.assertTrue(platform_acceptance(rows,20)['passed'])
        for key,value in (('status','fail'),('trial_status','skill_failed'),('opponent_control','cpu3')):
            changed=deepcopy(rows);changed[0][key]=value
            self.assertFalse(platform_acceptance(changed,20)['passed'])
        self.assertFalse(platform_acceptance(rows[:-1],20)['passed'])
        self.assertFalse(platform_acceptance(rows,1)['passed'])
        changed=deepcopy(rows);changed.append({**rows[0],'scenario':'unrecognized'})
        self.assertFalse(platform_acceptance(changed,20)['passed'])

    def test_scenario_retains_target_and_observes_terminal_release(self):
        for direction,side in ((-1,'left'),(1,'right')):
            spec=find_scenario('calibration-platform-jump-'+side);policy=ScenarioPolicy(spec)
            for value in flight(direction):
                value=replace(value,opponent=replace(value.opponent,x=-100.*direction))
                policy.decide(value)
            self.assertEqual(policy.result['status'],'succeeded')
            self.assertFalse(policy.ready_to_stop)
            policy.decide(state(9,direction,y=27.2001))
            self.assertTrue(policy.ready_to_stop)
            self.assertTrue(verified_trial(policy.report(),spec.name))

    def test_new_suite_stays_separate_and_does_not_expose_a_tactical_label(self):
        for spec in find_suite('platform-jump-calibration-v1'):
            self.assertEqual(spec.opponent_control,'neutral-human-v1')
            policy=ScenarioPolicy(spec)
            self.assertEqual(policy.decide(position(x=-38.8,y=27.2001)).action,'right')
        with self.assertRaises(ValueError):relative_skill('platform_jump',state())
        self.assertEqual(suite_hash('ground-combat-v1'),'04298ca511a8f188e547686782f30e061ad12386e40c7d6e8fa500d4c57375b0')
        self.assertEqual(suite_hash('aerial-calibration-v1'),'dae29e2c78568ca550ab258037852e3cb702f66e8401db40f25b636cb57ca745')
        self.assertEqual(suite_hash('ground-combat-calibration-v1'),'706e35aa7264cbcc724dcabc80f2b4649b0621aadd09f0189611db1dee43f0bf')
        with patch('melee_agent.scenario_runner.run_suite',return_value=0) as run:
            self.assertEqual(main(['skill-check','--suite','platform-jump-calibration-v1','--repeats','20']),0)
        self.assertEqual(run.call_args.kwargs['suite'],'platform-jump-calibration-v1')
