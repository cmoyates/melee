import json
import subprocess
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from melee_agent import policy_batch as batch
from melee_agent.cli import main


class PolicyBatchTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='jev-batch-')).resolve()
        (self.root/'agent/src/melee_agent').mkdir(parents=True)
        (self.root/'agent/src/melee_agent/fixture.py').write_text('version = 1\n')
        (self.root/'agent/local.toml').write_text('[limits]\nmax_run_seconds = 600\n')
        self.launched = []
        self.failed = False
        self.patches = [patch.object(batch,'inspect_integrity',return_value={'status':'pass'}),
            patch.object(batch,'inspect_local_policy',return_value={'status':'pass'}),
            patch.object(batch,'replay_layout_valid',return_value=True)]
        for item in self.patches:
            item.start();self.addCleanup(item.stop)

    def child(self, root, folder, manifest, slot):
        self.launched.append(slot)
        run_id = 'match-'+f'{slot+1:032x}'
        run = root/'build/jev/runs'/run_id;run.mkdir(parents=True)
        policy = manifest['schedule'][slot]['policy']
        role = {'bot_port':batch.child_port(manifest,slot)} if manifest['schema_version'] == 2 else {}
        batch.write_new(run/'launch.json',{'run_id':run_id,'policy':policy,
            **role,
            'candidate_profile':manifest['candidate_profile'], 'source_sha256':manifest['source_identity']['modules'],
            'duration_seconds':manifest['match_seconds'],'episodes':1,'provider_enabled':False,
            'budget_directory':None,'runtime_sha256':manifest['runtime_sha256']})
        batch.write_new(run/'summary.json',{'run_id':run_id,'policy':policy,
            **role,
            'status':'incomplete' if self.failed else 'complete','completed_matches':0 if self.failed else 1,
            'episodes':[{'winner_port':2}], 'replays':[], 'provider_contacted':False,
            'neutralized':True,'worker_stopped':True,'emulator_stopped':True,'state_receiver':{'stopped':True}})
        (run/'frames.jsonl').write_text('{}\n')
        batch.write_new(folder/f'match-{slot:02}.log',{'event':'started','run_id':run_id})

    def start(self, **kwargs):
        with patch.object(batch,'run_child',side_effect=self.child):
            return batch.start_batch(self.root,matches_per_policy=2,max_new_matches=1,**kwargs)

    def folder(self):
        return next((self.root/'build/jev/batches').glob('batch-*'))

    def test_round_robin_checkpoint_resume_retains_exact_prior_artifacts(self):
        first = self.start()
        self.assertEqual(first['status'],'checkpointed')
        self.assertEqual(self.launched,[0])
        manifest,rows,pending = batch.load_batch(self.root,self.folder())
        self.assertEqual([s['policy'] for s in manifest['schedule']],list(batch.MODES)*2)
        self.assertIsNone(pending)
        with patch.object(batch,'run_child',side_effect=self.child):
            final = batch.resume_batch(self.root,first['batch_id'])
        self.assertEqual(self.launched,[0,1,2,3])
        self.assertEqual(final['status'],'complete')
        self.assertTrue(all(g['verified_matches']==g['losses']==2 for g in final['policies'].values()))

    def test_failed_match_is_retained_and_never_retried_or_hidden_by_resume(self):
        self.failed = True
        first = self.start()
        self.assertEqual(first['status'],'stopped')
        with patch.object(batch,'run_child',side_effect=AssertionError('retry forbidden')):
            final = batch.resume_batch(self.root,first['batch_id'])
        self.assertEqual(final['audited_attempts'],1)
        self.assertEqual(final['policies']['random-tactical']['failed_attempts'],1)
        self.assertEqual(final['policies']['random-tactical']['losses'],0)

    def test_changed_source_and_changed_artifact_block_resume_before_processes(self):
        first = self.start()
        with patch.object(batch,'run_child',side_effect=AssertionError('launch forbidden')):
            source = self.root/'agent/src/melee_agent/fixture.py'
            source.write_text('version = 2\n')
            with self.assertRaisesRegex(ValueError,'source changed'):
                batch.resume_batch(self.root,first['batch_id'])
            source.write_text('version = 1\n')
            next((self.root/'build/jev/runs').glob('*/frames.jsonl')).write_text('changed\n')
            with self.assertRaisesRegex(ValueError,'artifacts changed'):
                batch.resume_batch(self.root,first['batch_id'])

    def test_crash_before_recorded_child_identity_is_ambiguous_without_retry(self):
        with patch.object(batch,'run_child',side_effect=RuntimeError('simulated crash')):
            with self.assertRaises(RuntimeError):
                batch.start_batch(self.root,max_new_matches=1)
        with patch.object(batch,'run_child',side_effect=AssertionError('launch forbidden')):
            with self.assertRaisesRegex(ValueError,'child log'):
                batch.resume_batch(self.root,self.folder().name)
        _,rows,pending = batch.load_batch(self.root,self.folder())
        self.assertEqual(rows,[])
        self.assertIsNotNone(pending)

    def test_finished_child_is_adopted_once_after_parent_crash(self):
        with patch.object(batch,'run_child',side_effect=self.child), patch.object(batch,'record_audit',side_effect=RuntimeError('simulated crash')):
            with self.assertRaises(RuntimeError):
                batch.start_batch(self.root,matches_per_policy=1,max_new_matches=1)
        with batch.batch_lock(self.root/'build/jev',name='match.lock'):
            with self.assertRaisesRegex(ValueError,'owner'):
                batch.resume_batch(self.root,self.folder().name)
        with patch.object(batch,'run_child',side_effect=self.child):
            final = batch.resume_batch(self.root,self.folder().name,max_new_matches=1)
        self.assertEqual(self.launched,[0,1])
        self.assertEqual(final['status'],'complete')

    def test_unjournaled_audit_is_rechecked_and_adopted_after_crash(self):
        original = batch.append_event
        def crash(folder,event):
            if event['kind']=='audited':
                raise RuntimeError('simulated crash')
            original(folder,event)
        with patch.object(batch,'run_child',side_effect=self.child), patch.object(batch,'append_event',side_effect=crash):
            with self.assertRaises(RuntimeError):
                batch.start_batch(self.root,policies=('random-tactical',),matches_per_policy=1)
        self.assertTrue((self.folder()/'audit-00.json').exists())
        with patch.object(batch,'run_child',side_effect=AssertionError('launch forbidden')):
            final = batch.resume_batch(self.root,self.folder().name)
        self.assertEqual(final['status'],'complete')
        self.assertEqual(final['audited_attempts'],1)

    def test_manifest_edit_and_partial_journal_are_not_silently_repaired(self):
        first = self.start();folder=self.folder()
        saved = (folder/'manifest.json').read_text()
        manifest = json.loads(saved);manifest['deadline_unix']+=100
        (folder/'manifest.json').write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError,'manifest changed'):
            batch.resume_batch(self.root,first['batch_id'])
        (folder/'manifest.json').write_text(saved)
        with (folder/'events.jsonl').open('a') as handle:handle.write('{')
        with self.assertRaises(ValueError):
            batch.resume_batch(self.root,first['batch_id'])

    def test_bounds_reject_paid_modes_and_invalid_counts_before_files_or_processes(self):
        for options in ({'policies':('jev',)}, {'matches_per_policy':11}, {'match_seconds':601},
                {'duration':600}, {'max_new_matches':True}, {'policies':('random-tactical','random-tactical')}):
            with self.assertRaises(ValueError):
                batch.start_batch(self.root,**options)
        self.assertFalse((self.root/'build').exists())

    def test_deadline_is_not_reset_on_resume(self):
        first = self.start()
        manifest,_,_ = batch.load_batch(self.root,self.folder())
        with patch.object(batch.time,'time',return_value=manifest['deadline_unix']), patch.object(batch,'run_child',side_effect=AssertionError('launch forbidden')):
            report = batch.resume_batch(self.root,first['batch_id'])
        self.assertEqual(report['audited_attempts'],1)
        self.assertEqual(report['stop_reason'],'batch_deadline')

    def test_child_gets_no_provider_credentials_and_parent_closes_watchdog_pipe(self):
        first=self.start();folder=self.folder();manifest,_,_=batch.load_batch(self.root,folder)
        child=MagicMock();child.wait.return_value=0
        with patch.dict('os.environ',{'OPENROUTER_API_KEY':'fixture-secret'}), patch.object(batch.subprocess,'Popen',return_value=child) as spawn:
            batch.run_child(self.root,folder,manifest,1)
        self.assertNotIn('OPENROUTER_API_KEY',spawn.call_args.kwargs['env'])
        self.assertEqual(spawn.call_args.args[0][3],'melee_agent.matches')
        child.stdin.close.assert_called_once()

    def test_cli_routes_the_explicit_free_profile_and_checkpoint(self):
        with patch('melee_agent.policy_batch.start_batch',return_value={'status':'checkpointed'}) as start:
            self.assertEqual(main(['batch','start','--matches-per-policy','1','--profile','fox-aerial-v1','--max-new-matches','1']),0)
        self.assertEqual(start.call_args.kwargs['profile'],'fox-aerial-v1')
        self.assertEqual(start.call_args.kwargs['max_new_matches'],1)

    def test_deadline_closes_watchdog_pipe_before_cleanup_wait(self):
        self.start();folder=self.folder();manifest,_,_=batch.load_batch(self.root,folder)
        child=MagicMock();child.wait.side_effect=[subprocess.TimeoutExpired('fixture',615),0]
        with patch.object(batch.subprocess,'Popen',return_value=child):
            batch.run_child(self.root,folder,manifest,1)
        child.stdin.close.assert_called_once()
        self.assertEqual(child.wait.call_count,2)

    def test_previous_cohort_link_does_not_mix_revised_results(self):
        first=self.start()
        (self.root/'agent/src/melee_agent/fixture.py').write_text('version = 2\n')
        with patch.object(batch,'run_child',side_effect=RuntimeError('planned checkpoint')):
            with self.assertRaises(RuntimeError):
                batch.start_batch(self.root,previous_batch=first['batch_id'])
        manifests=[batch.read_json(p) for p in (self.root/'build/jev/batches').glob('*/manifest.json')]
        current=next(m for m in manifests if m['batch_id'] != first['batch_id'])
        self.assertEqual(current['previous_cohort']['batch_id'],first['batch_id'])
        self.assertEqual(current['previous_cohort']['manifest_sha256'],batch.file_hash(
            batch.locate_batch(self.root,first['batch_id'])/'manifest.json'))

    def test_audit_artifact_paths_cannot_escape_owned_recording(self):
        run=self.root/'build/jev/runs/fixture';run.mkdir(parents=True)
        for name in ('../outside','/tmp/outside'):
            with self.assertRaisesRegex(ValueError,'escapes'):
                batch.artifact_path(run,name)

    def test_unknown_child_does_not_claim_no_provider_contact(self):
        first=self.start();manifest,rows,_=batch.load_batch(self.root,self.folder())
        self.assertIsNone(batch.report_batch(manifest,rows,{'slot':1})['provider_contacted'])
        rows[0]['summary']['provider_contacted']=True
        self.assertTrue(batch.report_batch(manifest,rows)['provider_contacted'])

    def test_both_ports_resume_exact_schedule_and_score_native_winners_by_role(self):
        first=self.start(bot_ports=(1,2))
        manifest,_,_=batch.load_batch(self.root,self.folder())
        self.assertEqual(manifest['schema_version'],2)
        self.assertEqual([(r['round'],r['bot_port'],r['policy']) for r in manifest['schedule']],
            [(n,p,policy) for n in (1,2) for p in (1,2) for policy in batch.MODES])
        with patch.object(batch,'run_child',side_effect=self.child):
            final=batch.resume_batch(self.root,first['batch_id'])
        self.assertEqual(self.launched,list(range(8)))
        self.assertTrue(all(g['wins']==g['losses']==2 for g in final['policies'].values()))
        self.assertTrue(all(g['by_port']['2']['wins']==2 and g['by_port']['1']['losses']==2
            for g in final['policies'].values()))
        self.assertEqual(batch.replay_layout_valid.call_args.kwargs['bot_port'],2)

    def test_port_two_child_command_is_explicit_and_still_has_no_secret(self):
        self.start(bot_ports=(2,));folder=self.folder();manifest,_,_=batch.load_batch(self.root,folder)
        child=MagicMock();child.wait.return_value=0
        with patch.dict('os.environ',{'OPENROUTER_API_KEY':'fixture-secret'}),patch.object(batch.subprocess,'Popen',return_value=child) as spawn:
            batch.run_child(self.root,folder,manifest,1)
        self.assertEqual(spawn.call_args.args[0][-2:],['grounded-tactical-v1','2'])
        self.assertNotIn('OPENROUTER_API_KEY',spawn.call_args.kwargs['env'])
        child.stdin.close.assert_called_once()

    def test_wrong_child_port_is_retained_pending_without_retry(self):
        def wrong(root,folder,manifest,slot):
            self.child(root,folder,manifest,slot)
            path=root/'build/jev/runs'/('match-'+f'{slot+1:032x}')/'launch.json'
            value=batch.read_json(path);value['bot_port']=1
            path.write_text(json.dumps(value))
        with patch.object(batch,'run_child',side_effect=wrong):
            with self.assertRaisesRegex(ValueError,'Child differs'):
                batch.start_batch(self.root,bot_ports=(2,),max_new_matches=1)
        with patch.object(batch,'run_child',side_effect=AssertionError('retry forbidden')):
            with self.assertRaisesRegex(ValueError,'Child differs'):
                batch.resume_batch(self.root,self.folder().name)
        self.assertEqual(self.launched,[0])

    def test_invalid_ports_and_version_disagreement_cannot_launch(self):
        for ports in ((),(True,),(3,),(1,1),'12',(1,2,1)):
            with self.assertRaises(ValueError):
                batch.start_batch(self.root,bot_ports=ports)
        self.assertFalse((self.root/'build').exists())
        self.start();manifest,_,_=batch.load_batch(self.root,self.folder())
        manifest['bot_ports']=[2]
        with self.assertRaises(ValueError):batch.manifest_plan(manifest)
        manifest['schema_version']=2;manifest['bot_ports']=None
        with self.assertRaises(ValueError):batch.manifest_plan(manifest)

    def test_explicit_port_one_cannot_adopt_a_child_with_missing_role(self):
        def missing(root,folder,manifest,slot):
            self.child(root,folder,manifest,slot)
            path=root/'build/jev/runs'/('match-'+f'{slot+1:032x}')/'summary.json'
            value=batch.read_json(path);value.pop('bot_port');path.write_text(json.dumps(value))
        with patch.object(batch,'run_child',side_effect=missing):
            with self.assertRaisesRegex(ValueError,'Child differs'):
                batch.start_batch(self.root,bot_ports=(1,),max_new_matches=1)

    def test_cli_routes_explicit_port_order_and_count(self):
        with patch('melee_agent.policy_batch.start_batch',return_value={'status':'checkpointed'}) as start:
            self.assertEqual(main(['batch','start','--bot-ports','2','1','--matches-per-policy','3']),0)
        self.assertEqual(start.call_args.kwargs['bot_ports'],[2,1])
        self.assertEqual(start.call_args.kwargs['matches_per_policy'],3)
