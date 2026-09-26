from copy import deepcopy
import unittest

from melee_agent.engine import ACTION_PACKETS
from melee_agent.horizontal_recovery_evidence import audit_rows


def rows(side=1,port=1):
    start={'episode':1,'frame':0,'life':1,'x':side*140.,'y':45.,'jumps':1,'motion':38}
    records=[]
    for frame,motion,jumps,y,airborne in ((0,38,1,45.,1),(1,27,0,48.,1),(2,14,0,0.,0)):
        raw={'x':side*(140. if frame<2 else 55.),'y':y,'action_id':motion,'jumps':jumps,
            'airborne':airborne,'stocks':4,'speed_y_self':-2.8 if frame==0 else 3.,
            'state_flags_2':0,'state_flags_4':0,'hitlag_raw':0.,'misc_as_raw':0.,
            'available':{key:True for key in ('state_flags_2','state_flags_4','hitlag_raw','misc_as_raw')}}
        reflex={'failed':False,'phase':'safe' if frame==2 else 'jump_press' if frame==0 else 'jump_release'}
        if frame<2:reflex['horizontal_start']=deepcopy(start)
        action=('jump_right' if side<0 else 'jump_left') if frame==0 else 'wait'
        records.append({'schema_version':5,'bot_port':port,'menu':'IN_GAME','episode':1,'frame':frame,
            'control':{'packet':ACTION_PACKETS[action].wire()},'skill':{'reflex':reflex},
            'raw_observation':{'players':{str(port):{'raw_post':raw,'life_generation_derived':1},
                str(3-port):{'raw_post':{'action_id':0},'life_generation_derived':1}}},
            'input_provenance':{'observed':ACTION_PACKETS['wait'].wire()}})
    return records


class HorizontalRecoveryEvidenceTests(unittest.TestCase):
    def test_both_sides_and_native_ports_require_raw_jump_and_return(self):
        for side in (-1,1):
            for port in (1,2):
                report=audit_rows(rows(side,port))
                self.assertEqual(report['status'],'pass',report)
                trial,=report['trials']
                self.assertTrue(trial['admission_verified'])
                self.assertEqual(trial['jump_ack_frame'],1)
                self.assertEqual(trial['outcome'],'observed_stage_return')

    def test_a_reported_jump_is_not_a_raw_acknowledgement(self):
        for field,value in (('jumps',1),('action_id',38),('speed_y_self',0.)):
            records=rows()
            records[1]['raw_observation']['players']['1']['raw_post'][field]=value
            report=audit_rows(records)
            self.assertIsNone(report['trials'][0]['jump_ack_frame'])
            self.assertEqual(report['sides']['right']['jump_acknowledgements'],0)

    def test_landing_observation_ends_recovery_before_the_next_skill_input(self):
        records=rows()
        records[2]['control']['packet']=ACTION_PACKETS['jump_left'].wire()
        report=audit_rows(records)
        self.assertEqual(report['status'],'pass',report)
        self.assertEqual(report['trials'][0]['outcome'],'observed_stage_return')

    def test_forged_admission_or_missing_fresh_input_is_rejected(self):
        for change in ('motion','bound','jump','held','packet','source'):
            records=rows()
            first=records[0]
            raw=first['raw_observation']['players']['1']['raw_post']
            if change=='motion':raw['action_id']=29
            elif change=='bound':raw['x']=190.
            elif change=='jump':raw['jumps']=0
            elif change=='held':first['input_provenance']['observed']['buttons']['X']=True
            elif change=='packet':first['control']['packet']=ACTION_PACKETS['wait'].wire()
            else:first['skill']['reflex']['horizontal_start']['frame']=-1
            self.assertIn('horizontal_admission_not_observed',audit_rows(records)['errors'],change)

    def test_repress_and_disappearing_admission_are_not_clean_trials(self):
        records=rows()
        records[1]['control']['packet']=ACTION_PACKETS['jump_left'].wire()
        self.assertIn('horizontal_repeated_jump_input',audit_rows(records)['errors'])
        records=rows()
        records[1]['skill']['reflex'].pop('horizontal_start')
        self.assertIn('horizontal_admission_disappeared',audit_rows(records)['errors'])

    def test_damage_gap_and_controller_failure_remain_separate_from_returns(self):
        for cause in ('damage','gap','failure'):
            records=rows()[:2]
            if cause=='damage':
                raw=records[1]['raw_observation']['players']['1']['raw_post']
                raw.update(state_flags_4=2,misc_as_raw=8.)
            elif cause=='gap':records[1]['frame']=3
            else:records[1]['skill']['reflex'].update(failed=True,event={'reason':'outside_declared_recovery_envelope'})
            report=audit_rows(records)
            trial,=report['trials']
            self.assertEqual(trial['outcome'],{'damage':'hitstun_interruption',
                'gap':'identity_or_frame_interruption','failure':'reported_failure'}[cause])
            self.assertFalse(any('return' in key for key in report['sides']['right']['outcomes']))

    def test_no_encounters_and_partial_encounters_are_not_successes(self):
        self.assertEqual(audit_rows([])['sides']['left']['admissions'],0)
        report=audit_rows(rows()[:1])
        self.assertEqual(report['trials'][0]['outcome'],'pending')
        self.assertEqual(report['sides']['right']['jump_acknowledgements'],0)


if __name__=='__main__':
    unittest.main()
