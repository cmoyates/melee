from collections import Counter
from copy import deepcopy
import unittest

from melee_agent.aerial_audit import aerial_acceptance
from melee_agent.engine import BUTTONS
from melee_agent.match_lifecycle import MatchBoundaryError, start_segment
from melee_agent.replay import expected_settings
from melee_agent.scenario_runner import audit_opponent_fixture
from melee_agent.scenarios import find_scenario, find_suite, scenario_suite, suite_hash
from test_match_lifecycle import settings


def fixture_row(frame=0):
    return {'frame':frame, 'players':{'2':{'observed_main':[.5,.5]}},
        'opponent_fixture':{'mode':'neutral-human-v1', 'port':2, 'queued':'release_all',
            'observed':{'main':[.5,.5], 'c':[.5,.5], 'l':0., 'r':0.,
                'buttons':{key:False for key in BUTTONS}}}}


class AerialCalibrationTests(unittest.TestCase):
    def test_new_names_preserve_original_cpu3_manifests_and_starting_predicates(self):
        old=find_suite('aerial-v1')
        new=find_suite('aerial-calibration-v1')
        self.assertEqual(len(new),4)
        for a,b in zip(old,new):
            self.assertEqual((a.kind,a.direction,a.measured_policy),(b.kind,b.direction,b.measured_policy))
            self.assertNotIn('opponent_control',a.manifest())
            self.assertEqual(a.manifest()['cpu_level'],3)
            self.assertEqual(b.manifest()['cpu_level'],0)
            self.assertEqual(b.manifest()['opponent_control'],'neutral-human-v1')
            self.assertEqual(a.manifest()['starting_predicate'],b.manifest()['starting_predicate'])
            self.assertEqual(scenario_suite(b),'aerial-calibration-v1')
            self.assertEqual(find_scenario(b.name),b)
        self.assertNotEqual(suite_hash('aerial-v1'),suite_hash('aerial-calibration-v1'))
        self.assertEqual(suite_hash('aerial-v1'),'a40053a9f26b414a259fcc8cab245f92f20c6137e61b5bc07e979bd445da0a9e')

    def test_replay_rules_require_explicit_human_mode_and_refuse_it_in_normal_matches(self):
        cpu=settings()
        human=deepcopy(cpu)
        human['players'][1]['type']=0
        self.assertTrue(expected_settings(cpu))
        self.assertFalse(expected_settings(human))
        self.assertFalse(expected_settings(cpu,opponent_control='neutral-human-v1'))
        self.assertTrue(expected_settings(human,opponent_control='neutral-human-v1'))
        self.assertFalse(expected_settings(human,opponent_control='unknown'))
        self.assertFalse(expected_settings(human,opponent_control='neutral-human-v1',bot_port=2))
        self.assertFalse(expected_settings(human,opponent_control='neutral-human-v1',phase='sudden_death'))
        segment=start_segment(1,1,'regulation',-123,0.,1,human,opponent_control='neutral-human-v1')
        self.assertEqual(segment['opponent_control'],'neutral-human-v1')
        with self.assertRaises(MatchBoundaryError):
            start_segment(1,1,'regulation',-123,0.,1,human)

    def test_neutral_command_does_not_substitute_for_observed_neutral_input(self):
        for change in ('button','main','c','l','r','nan'):
            row=fixture_row()
            packet=row['opponent_fixture']['observed']
            if change=='button':packet['buttons']['A']=True
            elif change in ('main','c'):
                packet[change]=[.6,.5]
                if change=='main':row['players']['2']['observed_main']=[.6,.5]
            else:packet['l' if change=='nan' else change]=float('nan') if change=='nan' else .1
            errors=Counter()
            audit_opponent_fixture(row,'neutral-human-v1',errors)
            self.assertEqual(errors['opponent_input_not_neutral'],1,change)

    def test_missing_wrong_or_unreported_fixture_fails(self):
        for change in ('missing','port','mode','buttons','main'):
            row=fixture_row()
            if change=='missing':row.pop('opponent_fixture')
            elif change=='buttons':row['opponent_fixture']['observed']['buttons'].pop('A')
            elif change=='main':row['players']['2']['observed_main']=[1.,.5]
            else:row['opponent_fixture'][change]=1 if change=='port' else 'cpu3'
            errors=Counter()
            audit_opponent_fixture(row,'neutral-human-v1',errors)
            self.assertEqual(errors['opponent_fixture_evidence_invalid'],1,change)
        errors=Counter()
        audit_opponent_fixture(fixture_row(),'cpu3',errors)
        self.assertEqual(errors['unexpected_opponent_fixture'],1)

    def test_countdown_menu_input_is_retained_but_live_setup_must_be_released(self):
        row=fixture_row(-123)
        row['opponent_fixture']['observed']['buttons']['A']=True
        errors=Counter()
        audit_opponent_fixture(row,'neutral-human-v1',errors)
        self.assertFalse(errors)
        row['frame']=0
        audit_opponent_fixture(row,'neutral-human-v1',errors)
        self.assertEqual(errors['opponent_input_not_neutral'],1)

    def test_calibration_trials_cannot_satisfy_cpu3_acceptance_or_vice_versa(self):
        results=[]
        for spec in find_suite('aerial-calibration-v1'):
            enabled='no_lcancel' not in spec.name
            results.extend({'scenario':spec.name, 'status':'pass', 'opponent_control':'neutral-human-v1',
                'aerial':{'completed':True, 'aerial_acknowledged':True,
                    'lcancel_attempt_observed':enabled, 'nair_landing_frames':7 if enabled else 15}}
                for _ in range(20))
        report=aerial_acceptance(results,20,scenario_prefix='calibration-')
        self.assertTrue(report['passed'])
        self.assertTrue(all(r['reduced_landing_lag_observed'] for r in report['landing_calibration'].values()))
        self.assertFalse(aerial_acceptance(results,20)['passed'])
        results[0].pop('opponent_control')
        self.assertFalse(aerial_acceptance(results,20,scenario_prefix='calibration-')['passed'])
        results[0]['opponent_control']='neutral-human-v1'
        results[0]['status']='fail'
        failed=aerial_acceptance(results,20,scenario_prefix='calibration-')
        self.assertFalse(failed['passed'])
        self.assertEqual(sum(g['trials'] for g in failed['scenarios'].values()),80)


if __name__=='__main__':
    unittest.main()
