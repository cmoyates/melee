from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from melee_agent.async_policy import AsyncPolicy, Delivery, Reply, bind, rejection
from melee_agent.cli import main
from melee_agent.budget import SpendLedger
from melee_agent.engine import FrameExecutor, MatchProgress, Observation
from melee_agent.fake import RecordingSink
from melee_agent.incidents import RecordedClock, canonical, contract_hashes, export_incident, replay_incident, sha
from melee_agent.live_provider import descriptions, policy_config_hash, ProviderBackend
from melee_agent.local_combat_policy import LocalCombatPolicy
from melee_agent.participation import opportunity_phase
from melee_agent.policy_evidence import inspect_policy
from melee_agent.provider import VERIFIED_MODEL
from melee_agent.semantic import compact_observation
from melee_agent.tactical_choices import AERIAL_PROFILE, OPTION_PROFILE, PROFILE, legal_candidates
from test_aerial_audit import recorded_aerial
from test_async_policy import ManualBridge
from test_combat_integration import ground
import test_option_profile


class AerialProfileTests(unittest.TestCase):
    def fixture(self, *, interrupted=False):
        _,_,prefix = test_option_profile.OptionProfileTests().fixture()
        _,air = recorded_aerial()
        bridge,clock,now = ManualBridge(),RecordedClock(),[0]
        policy = AsyncPolicy('synthetic',bridge,clock=lambda:now[0]+1000,profile=AERIAL_PROFILE)
        executor = FrameExecutor(policy,RecordingSink(),clock)
        rows = []
        for frame in range(49):
            now[0] = 1_000_000_000+frame*16_666_667
            source = deepcopy(prefix[frame] if frame < 34 else air[frame-34])
            source['input_provenance']['latest_completed_flush'] = None
            observation = Observation.parse(source['control']['observation'])
            if frame >= 34:
                observation = replace(observation,frame=frame,observed_ns=now[0],
                    match=MatchProgress.from_frame(frame,480,4),
                    bot=replace(observation.bot,x=9.),opponent=replace(observation.opponent,x=33.))
                source['raw_observation']['players']['1']['raw_post']['x'] = 9.
                if interrupted and frame == 39:
                    observation = replace(observation,bot=replace(observation.bot,
                        details=replace(observation.bot.details,action_id=75,hitstun_frames_derived=3)))
                    source['raw_observation']['players']['1']['raw_post'].update(
                        action_id=75,state_flags_4=2,misc_as_raw=3.)
            if frame == 34:
                prior = rows[4]
                labels = tuple(prior['skill']['semantic_state']['mechanical']['legal_candidates'])
                context = bind('synthetic',Observation.parse(prior['control']['observation']),1,
                    prior['skill']['generation'],labels,sha(prior['skill']['semantic_state']))
                bridge.replies = [Delivery(context,labels,Reply(context,'sh_nair',now[0]-1))]
            clock.values = [now[0]+500,now[0]+2000]
            control = executor.step(observation)
            rows.append({**source,'schema_version':4,'run_id':'synthetic','menu':'IN_GAME',
                'episode':1,'frame':frame,'control':control,'skill':deepcopy(policy.trace())})
        root = Path(tempfile.mkdtemp(prefix='jev-aerial-profile-')).resolve()
        run = root/'build/jev/runs/synthetic';run.mkdir(parents=True)
        launch = {'run_id':'synthetic','policy':'delayed-fake','synthetic_fixture':True,
            'candidate_profile':AERIAL_PROFILE,'stage_id':31,'starting_stocks':4,
            'match_time_limit_seconds':480,'source_sha256':contract_hashes()}
        summary = {'schema_version':1,'run_id':'synthetic','status':'captured','episodes':[],
            'candidate_profile':AERIAL_PROFILE,'async_policy':{'candidate_profile':AERIAL_PROFILE,
                'policy':dict(policy.counts),'bridge':{'workers_alive':0,'inflight':0,'worker_limit':1}}}
        (run/'launch.json').write_bytes(canonical(launch))
        (run/'summary.json').write_bytes(canonical(summary))
        (run/'frames.jsonl').write_bytes(b''.join(canonical(row)+b'\n' for row in rows))
        return root,run,rows

    def test_delayed_aerial_observes_takeoff_motion_and_landing_and_replays_without_network(self):
        root,run,rows = self.fixture()
        report = inspect_policy(run)
        self.assertEqual(report['status'],'pass',report)
        self.assertGreaterEqual(report['accepted_age_ms']['p50'],500.)
        self.assertEqual(report['acknowledgements'],{'observed:sh_nair':1})
        self.assertEqual(report['aerial_outcomes'],{'short_hop_observed':1,'aerial_acknowledged':1,
            'completed':1,'lcancel_attempt_observed':1})
        self.assertEqual(report['aerial_landing_duration_counts'],{7:1})
        with patch('socket.socket',side_effect=AssertionError('network forbidden')), patch('subprocess.Popen',side_effect=AssertionError('process forbidden')):
            incident = export_incident(root,run,frame=48,after_frames=0)
            replay = replay_incident(root,root/'build/jev/incidents'/incident['incident_id'])
        self.assertEqual(replay['status'],'pass',replay)
        self.assertEqual(replay['replayed_records'],49)

    def test_wrong_raw_aerial_or_landing_duration_or_identity_cannot_pass(self):
        for change in ('motion','duration','direction','claim'):
            _,run,rows = self.fixture()
            if change == 'motion':
                rows[38]['raw_observation']['players']['1']['raw_post']['action_id'] = 29
            else:
                details = rows[-1]['skill']['transitions'][0]['aerial']
                details[{'duration':'observed_nair_landing_frames','direction':'direction',
                    'claim':'reduced_landing_lag'}[change]] = {'duration':1,'direction':-1,'claim':True}[change]
            (run/'frames.jsonl').write_bytes(b''.join(canonical(row)+b'\n' for row in rows))
            self.assertEqual(inspect_policy(run)['status'],'fail',change)

    def test_damage_cancels_aerial_without_a_lcancel_followup_or_completion_claim(self):
        _,run,rows = self.fixture(interrupted=True)
        report = inspect_policy(run)
        self.assertEqual(report['status'],'pass',report)
        self.assertEqual(report['acknowledgements'],{'aborted':1})
        self.assertEqual(report['aerial_outcomes'],{'short_hop_observed':1,'aerial_acknowledged':1,
            'completed':0,'lcancel_attempt_observed':0})
        self.assertEqual(report['aerial_landing_duration_counts'],{})
        for row in rows[39:]:
            self.assertFalse(any(row['control']['packet']['buttons'][button] for button in ('A','X','Y')))
            self.assertNotEqual(row['skill']['input_owner'],'provider')
            if row['control']['packet']['buttons']['L']:
                self.assertEqual(row['skill']['input_owner'],'emergency')
                self.assertEqual(row['skill']['reflex']['phase'],'tech_pulse')

    def test_profile_is_explicit_and_rejects_old_catalog_or_unsupported_application(self):
        state = ground()
        labels = legal_candidates(state,AERIAL_PROFILE)
        self.assertIn('sh_nair',labels)
        for profile in (PROFILE,OPTION_PROFILE):
            self.assertNotIn('sh_nair',legal_candidates(state,profile))
            self.assertNotIn('sh_nair',descriptions(profile))
            self.assertNotEqual(policy_config_hash(profile),policy_config_hash(AERIAL_PROFILE))
        context = bind('test',state,1,0,labels)
        reply = Delivery(context,labels,Reply(context,'sh_nair',state.observed_ns+1))
        self.assertEqual(rejection(reply,state,'test',0,0,state.observed_ns+2,False),'invalid_candidate')
        airborne = replace(state,bot=replace(state.bot,grounded=False))
        self.assertIsNotNone(rejection(reply,airborne,'test',0,0,state.observed_ns+2,False,profile=AERIAL_PROFILE))
        self.assertIsNone(rejection(reply,state,'test',0,0,state.observed_ns+2,False,profile=AERIAL_PROFILE))

    def test_local_anti_air_and_cli_use_the_same_explicit_profile(self):
        state = ground()
        state = replace(state,opponent=replace(state.opponent,x=15.,y=10.,grounded=False))
        local = LocalCombatPolicy('heuristic-tactical',profile=AERIAL_PROFILE)
        self.assertEqual(local.decide(state).action,'jump')
        self.assertEqual(local.selection['selected'],'sh_nair')
        self.assertEqual(opportunity_phase(state,AERIAL_PROFILE),'grounded_aerial_only')
        with patch('melee_agent.matches.launch',return_value=0) as launch:
            self.assertEqual(main(['match','--policy','delayed-fake','--profile',AERIAL_PROFILE]),0)
        self.assertEqual(launch.call_args.kwargs['candidate_profile'],AERIAL_PROFILE)
        with patch('melee_agent.corpus.build_corpus',return_value={}) as build:
            self.assertEqual(main(['corpus','build','--profile',AERIAL_PROFILE]),0)
        self.assertEqual(build.call_args.kwargs['profile'],AERIAL_PROFILE)

    def test_provider_payload_and_paid_incident_bind_the_aerial_profile_without_network(self):
        root,run,_ = self.fixture()
        SpendLedger.create(root,'build/jev/mock-budget',deadline_utc=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat())
        state = replace(ground(),observed_ns=time.monotonic_ns())
        labels = ('neutral','sh_nair')
        semantic = compact_observation(state,labels)
        context = bind('synthetic',state,1,0,labels,semantic.sha256)
        def transport(payload,timeout):
            request = json.loads(payload)
            self.assertEqual(request['questions']['action']['criteria'],{k:descriptions(AERIAL_PROFILE)[k] for k in labels})
            return 200,{},json.dumps({'model':VERIFIED_MODEL,'provider':'TypeSafe','answers':{
                'action':{'type':'choice','choice':'sh_nair','probabilities':{'neutral':0.,'sh_nair':1.}}},
                'usage':{'cost':.00001,'input_tokens':100,'output_tokens':10}}).encode()
        with patch('socket.socket',side_effect=AssertionError('network forbidden')):
            backend = ProviderBackend(root,'build/jev/mock-budget',1,time.monotonic_ns()+10_000_000_000,
                transport=transport,profile=AERIAL_PROFILE)
            try:
                replies = backend.call(state,context,labels,threading.Event(),semantic=semantic)
                self.assertEqual(replies[0].action,'sh_nair',replies)
            finally:
                backend.close()
            launch = json.loads((run/'launch.json').read_text());launch['policy']='jev'
            (run/'launch.json').write_bytes(canonical(launch))
            summary = json.loads((run/'summary.json').read_text())
            summary['async_policy']['bridge']['provider']={'config_sha256':policy_config_hash(AERIAL_PROFILE)}
            (run/'summary.json').write_bytes(canonical(summary))
            with patch('subprocess.Popen',side_effect=AssertionError('process forbidden')):
                incident = export_incident(root,run,frame=48,after_frames=0)
                replay = replay_incident(root,root/'build/jev/incidents'/incident['incident_id'])
            self.assertEqual(replay['status'],'pass',replay)
