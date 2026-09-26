from copy import deepcopy
import unittest
from unittest.mock import patch

from melee_agent.cli import main
from melee_agent.scenario_runner import combat_acceptance
from melee_agent.scenarios import find_scenario, find_suite, scenario_suite, suite_hash


SUITE = 'ground-combat-calibration-v1'


def trials():
    return [{'scenario':spec.name, 'status':'pass', 'trial_status':'succeeded',
        'opponent_control':'neutral-human-v1', 'combat':{'motion_acknowledged':True,
            'completed':True, 'capture_observed':spec.kind == 'combat_grab', 'contact_events':1}}
        for spec in find_suite(SUITE) for _ in range(20)]


class GroundCalibrationTests(unittest.TestCase):
    def test_fixed_six_cases_preserve_original_geometry_timing_and_cpu3_identity(self):
        original=find_suite('ground-combat-v1')
        calibration=find_suite(SUITE)
        self.assertEqual(len(calibration),6)
        for a,b in zip(original,calibration):
            expected=a.manifest()
            expected.update(name='calibration-'+a.name,cpu_level=0,opponent_control='neutral-human-v1')
            self.assertEqual(b.manifest(),expected)
            self.assertEqual(find_scenario(b.name),b)
            self.assertEqual(scenario_suite(b),SUITE)
            self.assertEqual(scenario_suite(a),'ground-combat-v1')
        self.assertEqual(suite_hash('ground-combat-v1'),'04298ca511a8f188e547686782f30e061ad12386e40c7d6e8fa500d4c57375b0')
        self.assertNotEqual(suite_hash(SUITE),suite_hash('ground-combat-v1'))

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
