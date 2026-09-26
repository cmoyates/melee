from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from melee_agent.async_policy import AsyncPolicy, Delivery, Reply, bind, rejection
from melee_agent.engine import ACTION_PACKETS, FrameExecutor, Observation
from melee_agent.budget import SpendLedger
from melee_agent.cli import main
from melee_agent.corpus import choose_sources, generate_cases
from melee_agent.fake import RecordingSink
from melee_agent.incidents import RecordedClock, canonical, contract_hashes, export_incident, replay_incident, sha
from melee_agent.live_provider import descriptions, policy_config_hash, ProviderBackend
from melee_agent.provider import VERIFIED_MODEL
from melee_agent.semantic import compact_observation
from melee_agent.local_combat_policy import LocalCombatPolicy
from melee_agent.policy_evidence import inspect_policy
from melee_agent.tactical_choices import PROFILE, OPTION_PROFILE, legal_candidates
from test_approach_jab import sample
from test_async_policy import ManualBridge


class OptionProfileTests(unittest.TestCase):
    def fixture(self):
        bridge,clock,now = ManualBridge(),RecordedClock(),[0]
        policy=AsyncPolicy('synthetic',bridge,clock=lambda:now[0]+1000,profile=OPTION_PROFILE)
        executor=FrameExecutor(policy,RecordingSink(),clock)
        rows=[]
        for frame in range(43):
            now[0]=1_000_000_000+frame*16_666_667
            x,motion,velocity = (0.,14,0.) if frame==0 else (1.,20,2.) if frame==1 else (7.,20,2.) if frame==2 else (9.,14,0.)
            if frame>=34:
                x,motion,velocity={34:(9.,14,0.),35:(16.,20,2.),36:(18.,20,0.),37:(19.,14,0.),
                    38:(26.,20,2.),39:(28.,20,0.),40:(28.,14,0.),41:(28.,44,0.),42:(28.,14,0.)}[frame]
            observation=replace(sample(frame,x,motion,opponent_x=33.,self_velocity_x=velocity),observed_ns=now[0])
            if frame==34:
                source=rows[4]
                candidates=tuple(source['skill']['semantic_state']['mechanical']['legal_candidates'])
                context=bind('synthetic',source_observation,1,source['skill']['generation'],candidates,
                    sha(source['skill']['semantic_state']))
                bridge.replies=[Delivery(context,candidates,Reply(context,'approach_jab',now[0]-1))]
            clock.values=[now[0]+500,now[0]+2000]
            control=executor.step(observation)
            players={}
            for port,fighter in (('1',observation.bot),('2',observation.opponent)):
                d=fighter.details
                players[port]={'raw_post':{'action_id':d.action_id,'x':fighter.x,'y':fighter.y,
                    'airborne':int(not fighter.grounded),'speed_ground_x_self':d.self_velocity_x,
                    'percent':d.percent,'hurtbox_state':d.hurtbox_state,'state_flags_2':0,
                    'state_flags_4':0,'hitlag_raw':0.,'misc_as_raw':0.,'available':{
                        k:True for k in ('hurtbox_state','state_flags_2','state_flags_4','hitlag_raw','misc_as_raw')}}}
            rows.append({'schema_version':4,'run_id':'synthetic','menu':'IN_GAME','episode':1,'frame':frame,
                'control':control,'skill':deepcopy(policy.trace()),'raw_observation':{'players':players},
                'input_provenance':{'observed':ACTION_PACKETS['wait'].wire(),'latest_completed_flush':None}})
            if frame==4:source_observation=observation
        root=Path(tempfile.mkdtemp(prefix='jev-option-profile-')).resolve()
        run=root/'build/jev/runs/synthetic';run.mkdir(parents=True)
        launch={'run_id':'synthetic','policy':'delayed-fake','synthetic_fixture':True,'candidate_profile':OPTION_PROFILE,
            'stage_id':31,'starting_stocks':4,'match_time_limit_seconds':480,'source_sha256':contract_hashes()}
        summary={'schema_version':1,'run_id':'synthetic','status':'captured','episodes':[],
            'candidate_profile':OPTION_PROFILE,'async_policy':{'candidate_profile':OPTION_PROFILE,
                'policy':dict(policy.counts),'bridge':{'workers_alive':0,'inflight':0,'worker_limit':1}}}
        (run/'launch.json').write_bytes(canonical(launch))
        (run/'summary.json').write_bytes(canonical(summary))
        (run/'frames.jsonl').write_bytes(b''.join(canonical(row)+b'\n' for row in rows))
        return root,run,rows

    def test_half_second_reply_drives_observed_option_and_exact_sealed_replay(self):
        root,run,rows=self.fixture()
        report=inspect_policy(run)
        self.assertEqual(report['status'],'pass',report)
        self.assertEqual(report['accepted_age_ms']['count'],1)
        self.assertGreaterEqual(report['accepted_age_ms']['p50'],500.)
        self.assertEqual(report['acknowledgements']['observed:approach_jab'],1)
        self.assertEqual(report['option_outcomes'],{'moves_acknowledged':2,'jab_acknowledged':1,'completed':1,'contacts':0})
        with patch('socket.socket',side_effect=AssertionError('network forbidden')),patch('subprocess.Popen',side_effect=AssertionError('process forbidden')):
            incident=export_incident(root,run,frame=42,after_frames=0)
            replay=replay_incident(root,root/'build/jev/incidents'/incident['incident_id'])
        self.assertEqual(replay['status'],'pass',replay)
        self.assertEqual(replay['replayed_records'],43)

    def test_profiles_share_candidates_and_atomic_mode_rejects_option(self):
        state=sample()
        labels=legal_candidates(state,OPTION_PROFILE)
        self.assertIn('approach_jab',labels)
        self.assertNotIn('approach_jab',legal_candidates(state))
        for mode in ('heuristic-tactical','random-tactical'):
            policy=LocalCombatPolicy(mode,seed=3,profile=OPTION_PROFILE)
            policy.decide(state)
            self.assertEqual(policy.selection['legal_candidates'],list(labels))
            self.assertEqual(policy.close()['profile'],OPTION_PROFILE)
            if mode=='heuristic-tactical':self.assertEqual(policy.selection['selected'],'approach_jab')
        context=bind('test',state,1,0,labels)
        delivery=Delivery(context,labels,Reply(context,'approach_jab',state.observed_ns+1))
        self.assertEqual(rejection(delivery,state,'test',0,0,state.observed_ns+2,False),'invalid_candidate')
        self.assertIsNone(rejection(delivery,state,'test',0,0,state.observed_ns+2,False,profile=OPTION_PROFILE))
        self.assertNotEqual(policy_config_hash(PROFILE),policy_config_hash(OPTION_PROFILE))
        self.assertIn('approach_jab',descriptions(OPTION_PROFILE))
        self.assertNotIn('approach_jab',descriptions())

    def test_wrong_profile_or_forged_raw_child_evidence_cannot_pass(self):
        _,run,rows=self.fixture()
        altered=deepcopy(rows)
        altered[35]['raw_observation']['players']['1']['raw_post']['x']=10.
        (run/'frames.jsonl').write_bytes(b''.join(canonical(row)+b'\n' for row in altered))
        self.assertEqual(inspect_policy(run)['status'],'fail')
        summary=json.loads((run/'summary.json').read_text())
        summary['candidate_profile']=PROFILE
        (run/'summary.json').write_bytes(canonical(summary))
        with self.assertRaisesRegex(ValueError,'profile mismatch'):inspect_policy(run)

    def test_local_option_execution_replays_with_its_declared_profile(self):
        root,_,source_rows=self.fixture()
        run=root/'local';run.mkdir()
        policy,clock=LocalCombatPolicy('heuristic-tactical',profile=OPTION_PROFILE),RecordedClock()
        executor=FrameExecutor(policy,RecordingSink(),clock)
        rows=[]
        for source in source_rows[34:]:
            observation=Observation.parse(source['control']['observation'])
            clock.values=[observation.observed_ns+500,observation.observed_ns+2000]
            control=executor.step(observation)
            rows.append({'menu':'IN_GAME','episode':1,'frame':observation.frame,
                'control':control,'skill':deepcopy(policy.trace())})
        self.assertEqual(policy.arbiter.last_event['skill'],'approach_jab')
        self.assertEqual(policy.arbiter.last_event['status'],'succeeded')
        import melee_agent.local_combat_policy as module
        launch={'run_id':'local','policy':'heuristic-tactical','candidate_profile':OPTION_PROFILE,
            'source_sha256':{**contract_hashes(),'local_combat_policy.py':hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()}}
        (run/'launch.json').write_bytes(canonical(launch))
        (run/'summary.json').write_bytes(canonical({'policy':'heuristic-tactical','candidate_profile':OPTION_PROFILE,'local_policy':policy.close()}))
        (run/'frames.jsonl').write_bytes(b''.join(canonical(row)+b'\n' for row in rows))
        report=inspect_policy(run)
        self.assertEqual(report['status'],'pass',report)
        self.assertEqual(report['candidate_profile'],OPTION_PROFILE)

    def test_provider_and_cli_carry_the_explicit_profile_without_real_network(self):
        with patch('melee_agent.matches.launch',return_value=0) as launch:
            self.assertEqual(main(['match','--policy','jev','--profile',OPTION_PROFILE,
                '--budget','build/jev/existing','--max-requests','10']),0)
        self.assertEqual(launch.call_args.kwargs['candidate_profile'],OPTION_PROFILE)
        root=Path(tempfile.mkdtemp(prefix='jev-option-provider-')).resolve()
        SpendLedger.create(root,'build/jev/budget',deadline_utc=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat())
        observation=replace(sample(),observed_ns=time.monotonic_ns())
        labels=('neutral','approach_jab')
        semantic=compact_observation(observation,labels)
        context=bind('test',observation,1,0,labels,semantic.sha256)
        def transport(payload,timeout):
            request=json.loads(payload)
            self.assertEqual(request['questions']['action']['criteria'],{label:descriptions(OPTION_PROFILE)[label] for label in labels})
            self.assertEqual(request['state'],semantic.wire())
            return 200,{},json.dumps({'model':VERIFIED_MODEL,'provider':'TypeSafe','answers':{
                'action':{'type':'choice','choice':'approach_jab','probabilities':{'neutral':0.,'approach_jab':1.}}},
                'usage':{'cost':.00001,'input_tokens':100,'output_tokens':10}}).encode()
        backend=ProviderBackend(root,'build/jev/budget',1,time.monotonic_ns()+10_000_000_000,
            transport=transport,profile=OPTION_PROFILE)
        try:
            self.assertEqual(backend.call(observation,context,labels,threading.Event(),semantic=semantic)[0].action,'approach_jab')
        finally:
            report=backend.close()
        self.assertEqual(report['candidate_profile'],OPTION_PROFILE)
        self.assertEqual(report['http_calls'],1)

    def test_atomic_corpus_does_not_silently_relabel_option_runs(self):
        root,_,_=self.fixture()
        name='match-'+'a'*32
        run=root/'build/jev/runs'/name;run.mkdir()
        (run/'summary.json').write_bytes(canonical({'candidate_profile':OPTION_PROFILE}))
        self.assertEqual(choose_sources(root,3),[])
        with self.assertRaisesRegex(ValueError,'cannot relabel'):
            next(generate_cases(root,[name],1))
