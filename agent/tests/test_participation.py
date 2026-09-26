from dataclasses import replace
import json
import unittest

from melee_agent.participation import Participation, opportunity_phase
from melee_agent.policy_evidence import inspect_policy
from melee_agent.incidents import canonical
from melee_agent.tactical_choices import PROFILE, OPTION_PROFILE
from test_approach_jab import sample
import test_option_profile as fixtures


class ParticipationTests(unittest.TestCase):
    def test_opportunity_bins_respect_motion_and_candidate_profile(self):
        self.assertEqual(opportunity_phase(sample(),OPTION_PROFILE),'grounded_option_only')
        self.assertEqual(opportunity_phase(sample(),PROFILE),'grounded_other')
        self.assertEqual(opportunity_phase(sample(opponent_x=8),OPTION_PROFILE),'grounded_atomic_combat')
        self.assertEqual(opportunity_phase(sample(hitlag_frames_derived=2),OPTION_PROFILE),'own_hitlag')
        self.assertEqual(opportunity_phase(sample(hitstun_frames_derived=3,hitlag_frames_derived=2),OPTION_PROFILE),'own_hitstun')
        self.assertEqual(opportunity_phase(sample(motion=5),OPTION_PROFILE),'inactive')
        current=sample()
        current=replace(current,bot=replace(current.bot,grounded=False,y=5.))
        self.assertEqual(opportunity_phase(current,OPTION_PROFILE),'airborne')

    def test_actual_delayed_option_audit_attributes_selection_and_completion_to_source(self):
        _,run,rows=fixtures.OptionProfileTests().fixture()
        summary=json.loads((run/'summary.json').read_text())
        result={'action':'approach_jab'}
        rows[34]['skill']['policy_events'][0]['delivery']['reply']['metadata']=result
        summary['async_policy']['bridge']['provider']={'max_requests':1,'http_active':0,
            'client_shutdown':{'workers_alive':0,'timers_alive':0},'attempts':[
                {'episode':1,'source_frame':4,'sequence':1,'status':'validated','result':result}]}
        (run/'summary.json').write_bytes(canonical(summary))
        (run/'frames.jsonl').write_bytes(b''.join(canonical(r)+b'\n' for r in rows))
        audited=inspect_policy(run)
        self.assertEqual(audited['status'],'pass',audited)
        report=audited['participation']
        self.assertTrue(report['backend_attempts_available'])
        self.assertEqual(sum(r['observed'] for r in report['frames'].values()),43)
        self.assertEqual(sum(r['provider_owned'] for r in report['frames'].values()),
            audited['input_owner_frames']['provider'])
        source=report['request_sources']['grounded_option_only']
        self.assertEqual(source,{'backend_attempts':1,'validated_responses':1,
            'selected:approach_jab':1,'delivered_responses':1,'accepted_choices':1,
            'completed:approach_jab':1})
        self.assertEqual(report['applications']['grounded_option_only'],
            {'accepted_choices':1,'completed:approach_jab':1})

    def test_episode_cancellation_never_credits_a_completion_or_new_episode_source(self):
        _,run,_=fixtures.OptionProfileTests().fixture(episode_boundary=True)
        audited=inspect_policy(run)
        self.assertEqual(audited['status'],'pass',audited)
        report=audited['participation']
        self.assertFalse(report['backend_attempts_available'])
        self.assertEqual(report['frames']['inactive']['observed'],7)
        source=report['request_sources']['grounded_option_only']
        self.assertEqual(source,{'delivered_responses':1,'accepted_choices':1,
            'cancelled:episode_boundary':1})
        self.assertNotIn('inactive',report['request_sources'])

    def test_source_application_and_current_frame_are_separate_and_missing_attempts_stay_unknown(self):
        report=Participation({'attempts':[{'episode':9,'source_frame':7,'status':'rejected'}]})
        report.observe(sample(),'grounded_atomic_combat','provider')
        report.delivery('grounded_option_only','grounded_atomic_combat',True)
        report.terminal({'source_phase':'grounded_option_only','application_phase':'grounded_atomic_combat'},
            'completed:approach_jab')
        first=report.report()
        self.assertEqual(first,report.report())
        self.assertEqual(first['request_sources']['unavailable_source'],{'backend_attempts':1})
        self.assertNotIn('grounded_atomic_combat',first['request_sources'])
        self.assertNotIn('grounded_option_only',first['applications'])
        self.assertEqual(first['frames']['grounded_atomic_combat'],{'observed':1,'provider_owned':1})
