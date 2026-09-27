from copy import deepcopy
from dataclasses import replace
import unittest
from unittest.mock import patch

from melee_agent.cli import main
from melee_agent.scenario_runner import combat_acceptance
from melee_agent.scenarios import ScenarioPolicy, find_scenario, find_suite, scenario_suite, starting_predicate, suite_hash
from test_scenarios import position


SUITE = 'ground-combat-calibration-v1'


def trials():
    return [{'scenario':spec.name, 'status':'pass', 'trial_status':'succeeded',
        'opponent_control':'neutral-human-v1', 'combat':{'motion_acknowledged':True,
            'completed':True, 'capture_observed':spec.kind == 'combat_grab', 'contact_events':1}}
        for spec in find_suite(SUITE) for _ in range(20)]


def platform_state(frame=0, direction=1, *, x=None, y=0., grounded=True, jumps=2, **details):
    value=position(frame,x=38.8-6*direction if x is None else x,y=y,grounded=grounded,jumps=jumps,
        facing_right=direction>0,hurtbox_state=0,**details)
    opponent=replace(value.opponent,x=38.8,y=27.2001,grounded=True,jumps=2,
        details=replace(value.opponent.details,action_id=14,self_velocity_x=0.,self_velocity_y=0.,
            input_neutral_derived=True,hurtbox_state=0))
    return replace(value,opponent=opponent)


class GroundCalibrationTests(unittest.TestCase):
    def test_fixed_six_cases_preserve_combat_legality_timing_and_cpu3_identity(self):
        original=find_suite('ground-combat-v1')
        calibration=find_suite(SUITE)
        self.assertEqual(len(calibration),6)
        for a,b in zip(original,calibration):
            expected=a.manifest()
            expected.update(name='calibration-'+a.name,cpu_level=0,opponent_control='neutral-human-v1')
            expected.update(setup_variant='right-platform-full-jump-v1',
                starting_predicate='settled right platform; '+expected['starting_predicate'])
            self.assertEqual(b.manifest(),expected)
            self.assertEqual(find_scenario(b.name),b)
            self.assertEqual(scenario_suite(b),SUITE)
            self.assertEqual(scenario_suite(a),'ground-combat-v1')
        self.assertEqual(suite_hash('ground-combat-v1'),'04298ca511a8f188e547686782f30e061ad12386e40c7d6e8fa500d4c57375b0')
        self.assertNotEqual(suite_hash(SUITE),suite_hash('ground-combat-v1'))
        self.assertEqual(suite_hash('aerial-calibration-v1'),'dae29e2c78568ca550ab258037852e3cb702f66e8401db40f25b636cb57ca745')

    def test_mirrored_route_holds_one_full_jump_then_releases_before_platform_attack(self):
        for direction,side in ((-1,'left'),(1,'right')):
            policy=ScenarioPolicy(find_scenario('calibration-jab-'+side))
            self.assertEqual(policy.decide(platform_state(0,direction,x=-38.8,y=27.2001)).action,'right')
            self.assertEqual(policy.decide(platform_state(1,direction,x=-18.,y=26.,grounded=False,action_id=29)).action,'wait')
            self.assertEqual(policy.decide(platform_state(2,direction,x=0.)).action,'slow_right')
            self.assertEqual(policy.decide(platform_state(3,direction,self_velocity_x=.2)).action,'wait')
            self.assertEqual(policy.decide(platform_state(4,direction)).action,'jump')
            for frame in (5,6):
                self.assertEqual(policy.decide(platform_state(frame,direction,action_id=24,
                    input_jump_held=True,input_neutral_derived=False)).action,'jump')
            self.assertEqual(policy.decide(platform_state(7,direction,y=4.,grounded=False,jumps=1,
                action_id=25,self_velocity_y=4.,input_jump_held=True,input_neutral_derived=False)).action,'wait')
            self.assertEqual(policy.decide(platform_state(8,direction,y=32.,grounded=False,jumps=1,
                action_id=25,self_velocity_y=-1.)).action,'wait')
            self.assertEqual(policy.decide(platform_state(9,direction,y=27.2001,action_id=42)).action,'wait')
            self.assertEqual(policy.decide(platform_state(10,direction,y=27.2001)).action,'attack')
            self.assertEqual(policy.phase,'measured')
            self.assertEqual(policy.measurement_start,10)
            self.assertTrue(policy.calibration_jump_airborne)

    def test_calibration_start_requires_fixed_platform_and_settled_observed_state(self):
        spec=find_scenario('calibration-jab-right')
        valid=platform_state(y=27.2001)
        self.assertTrue(starting_predicate(spec,valid))
        self.assertFalse(starting_predicate(spec,platform_state()))
        for observation in (platform_state(y=27.2001,self_velocity_x=.1),
                platform_state(y=27.2001,input_neutral_derived=False),
                replace(valid,opponent=replace(valid.opponent,x=52.))):
            self.assertFalse(starting_predicate(spec,observation))
        floor=replace(platform_state(),opponent=replace(valid.opponent,y=0.))
        self.assertTrue(starting_predicate(find_scenario('jab-right'),floor))
        self.assertFalse(starting_predicate(spec,floor))

    def test_missing_takeoff_releases_without_retry_then_records_explicit_setup_failure(self):
        policy=ScenarioPolicy(find_scenario('calibration-grab-right'))
        for frame in range(8):
            self.assertEqual(policy.decide(platform_state(frame)).action,'jump')
        self.assertEqual(policy.decide(platform_state(8)).action,'wait')
        self.assertEqual(policy.decide(platform_state(9)).action,'wait')
        self.assertEqual(policy.result['status'],'setup_failed')
        self.assertEqual(policy.result['reason'],'calibration_jump_unacknowledged')
        self.assertEqual(policy.decide(platform_state(10)).action,'wait')
        self.assertTrue(policy.ready_to_stop)

    def test_unexpected_takeoff_or_missed_platform_does_not_issue_another_jump(self):
        for missed in (False,True):
            policy=ScenarioPolicy(find_scenario('calibration-grab-right'))
            policy.decide(platform_state())
            policy.decide(platform_state(1,y=4.,grounded=False,jumps=1,
                action_id=25 if missed else 29,self_velocity_y=4.))
            self.assertEqual(policy.decide(platform_state(2)).action,'wait')
            policy.decide(platform_state(3))
            self.assertEqual(policy.result['reason'],'calibration_missed_platform' if missed else 'calibration_takeoff_unacknowledged')

    def test_airborne_wait_has_a_deadline_and_never_represses_jump(self):
        policy=ScenarioPolicy(find_scenario('calibration-jab-right'))
        policy.decide(platform_state())
        policy.decide(platform_state(1,y=4.,grounded=False,jumps=1,action_id=25,self_velocity_y=4.))
        for frame in range(2,122):
            self.assertEqual(policy.decide(platform_state(frame,y=35.,grounded=False,jumps=1,action_id=29)).action,'wait')
        self.assertEqual(policy.result['reason'],'calibration_landing_timeout')

    def test_opponent_departure_and_unknown_routes_fail_neutrally(self):
        for observation in (platform_state(x=65.),platform_state(y=-13.),
                replace(platform_state(),opponent=replace(platform_state().opponent,y=0.))):
            policy=ScenarioPolicy(find_scenario('calibration-jab-right'))
            self.assertEqual(policy.decide(observation).action,'wait')
            self.assertIsNotNone(policy.calibration_setup_failure)

    def test_observed_landing_origin_dip_waits_for_floor_without_starting_jump(self):
        for direction,side in ((-1,'left'),(1,'right')):
            policy=ScenarioPolicy(find_scenario('calibration-jab-'+side))
            value=platform_state(26,direction,x=-5.959995269775391,y=-1.9398987293243408,
                grounded=False,action_id=29)
            self.assertEqual(policy.decide(value).action,'wait')
            self.assertIsNone(policy.calibration_setup_failure)
            self.assertIsNone(policy.calibration_jump_started)
            self.assertEqual(policy.decide(platform_state(27,direction,x=-5.959995269775391)).action,'slow_right')

    def test_gap_after_setup_jump_releases_and_preserves_existing_continuity_guard(self):
        policy=ScenarioPolicy(find_scenario('calibration-jab-right'))
        self.assertEqual(policy.decide(platform_state()).action,'jump')
        self.assertEqual(policy.decide(platform_state(2)).action,'wait')
        self.assertEqual(policy.result['reason'],'observation_discontinuity')

    def test_calibration_and_cpu3_results_cannot_satisfy_each_other(self):
        rows=trials()
        self.assertTrue(combat_acceptance(rows,20,suite=SUITE)['passed'])
        self.assertFalse(combat_acceptance(rows,20)['passed'])
        cpu=deepcopy(rows)
        for row in cpu:
            row['scenario']=row['scenario'].removeprefix('calibration-')
            row['opponent_control']='cpu3'
        self.assertTrue(combat_acceptance(cpu,20)['passed'])
        self.assertFalse(combat_acceptance(cpu,20,suite=SUITE)['passed'])
        cpu[0]['opponent_control']='neutral-human-v1'
        self.assertFalse(combat_acceptance(cpu,20)['passed'])
        for wrong in ('cpu3',None):
            changed=deepcopy(rows)
            if wrong is None:changed[0].pop('opponent_control')
            else:changed[0]['opponent_control']=wrong
            self.assertFalse(combat_acceptance(changed,20,suite=SUITE)['passed'])

    def test_failed_motion_completion_and_missing_trials_keep_the_strict_gate(self):
        for failure in ('audit','motion','completion','missing','extra'):
            rows=trials()
            if failure=='audit':rows[0]['status']='fail'
            elif failure=='motion':rows[0]['combat']['motion_acknowledged']=False
            elif failure=='completion':
                rows[0]['combat']['completed']=False
                rows[0]['trial_status']='skill_failed'
            elif failure=='missing':rows.pop(0)
            else:rows.append(deepcopy(rows[0]))
            report=combat_acceptance(rows,20,suite=SUITE)
            self.assertFalse(report['passed'],failure)
            self.assertEqual(sum(group['trials'] for group in report['scenarios'].values()),len(rows))

    def test_grab_motion_is_not_actual_capture_and_contacts_stay_separate(self):
        rows=trials()
        grab=[r for r in rows if 'grab' in r['scenario']]
        for row in grab:row['combat']['capture_observed']=False
        report=combat_acceptance(rows,20,suite=SUITE)
        self.assertFalse(report['passed'])
        for group in report['scenarios'].values():
            self.assertEqual(group['motion_acknowledged'],20)
            self.assertEqual(group['completed'],20)
            self.assertEqual(group['contacts'],20)
        for direction in ('left','right'):
            next(r for r in grab if r['scenario'].endswith(direction))['combat']['capture_observed']=True
        self.assertTrue(combat_acceptance(rows,20,suite=SUITE)['passed'])

    def test_pilot_and_unknown_suite_cannot_claim_acceptance(self):
        self.assertFalse(combat_acceptance(trials(),1,suite=SUITE)['passed'])
        with self.assertRaises(ValueError):combat_acceptance(trials(),20,suite='aerial-calibration-v1')

    def test_cli_routes_calibration_through_bounded_scenario_supervisor(self):
        with patch('melee_agent.scenario_runner.run_suite',return_value=0) as run:
            self.assertEqual(main(['skill-check','--suite',SUITE,'--repeats','20']),0)
        self.assertEqual(run.call_args.args[1:3],(20,3000))
        self.assertTrue(run.call_args.kwargs['require_acceptance'])
        self.assertEqual(run.call_args.kwargs['suite'],SUITE)


if __name__=='__main__':
    unittest.main()
