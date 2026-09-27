from datetime import datetime, timedelta, timezone
import json
import unittest
from unittest.mock import MagicMock, patch

from melee_agent import paid_cohort as paid, policy_batch as batch
from melee_agent.budget import SpendLedger
import test_policy_batch as fixtures


class PaidCohortTests(unittest.TestCase):
    def setUp(self):
        fixtures.PolicyBatchTests.setUp(self)
        self.directory='build/jev/existing-budget'
        self.ledger=SpendLedger.create(self.root,self.directory,
            deadline_utc=(datetime.now(timezone.utc)+timedelta(hours=2)).isoformat(),max_requests=20)
        for item in (patch.dict('os.environ',{'OPENROUTER_API_KEY':'fixture-only'}),
                patch.object(paid,'audit_replay',return_value={'status':'pass','incident_bytes':0}),
                patch.object(paid,'verify_replay_artifacts')):
            item.start();self.addCleanup(item.stop)

    folder=fixtures.PolicyBatchTests.folder

    def child(self,root,folder,manifest,slot):
        fixtures.PolicyBatchTests.child(self,root,folder,manifest,slot)
        if manifest['schedule'][slot]['policy']!='jev':return
        run=root/'build/jev/runs'/('match-'+f'{slot+1:032x}')
        before=self.ledger.report()
        ids=[self.ledger.reserve(cost_nano_usd=2_000_000,input_tokens=2000,payload_sha256='a'*64) for _ in range(2)]
        self.ledger.settle(ids[0],cost_usd='.00001',input_tokens=100)
        launch=batch.read_json(run/'launch.json');summary=batch.read_json(run/'summary.json')
        contract=manifest['provider']
        launch.update(provider_enabled=True,budget_directory=self.directory,
            max_provider_requests=2,provider_budget_before=before)
        summary.update(provider_contacted=True,async_policy={'bridge':{'provider':{
            'budget_before':before,'budget_after':self.ledger.report(),'max_requests':2,
            'config_sha256':contract['config_sha256'],'candidate_profile':contract['profile'],
            'attempts':[{'request_id':ids[0],'status':'validated'},{'request_id':ids[1],'status':'rejected','reason':'deadline_exceeded'}],
            'http_calls':2,'http_active':0,'client_shutdown':{'workers_alive':0,'timers_alive':0}}}})
        (run/'launch.json').write_text(json.dumps(launch));(run/'summary.json').write_text(json.dumps(summary))

    def start(self,**kwargs):
        options={'policies':('random-tactical','jev'),'matches_per_policy':1,
            'duration':1800,'max_new_matches':1,'budget':self.directory,'max_requests':2}
        options.update(kwargs)
        with patch.object(batch,'run_child',side_effect=self.child):
            return batch.start_batch(self.root,**options)

    def test_mixed_checkpoint_reconciles_every_request_and_keeps_unknown_charge(self):
        first=self.start();self.assertEqual(self.ledger.report()['requests'],0)
        with patch.object(batch,'run_child',side_effect=self.child):
            report=batch.resume_batch(self.root,first['batch_id'])
        self.assertEqual(report['status'],'complete');self.assertTrue(report['provider_contacted'])
        self.assertEqual(report['paid_ledger_checkpoint']['report']['accounted_nano_usd'],2_010_000)
        self.assertEqual(report['paid_ledger_checkpoint']['report']['unsettled_requests'],1)
        _,rows,pending=batch.load_batch(self.root,self.folder())
        self.assertIsNone(pending);self.assertEqual(rows[1]['spending']['reserved_requests'],2)
        self.assertEqual(rows[1]['spending']['validated'],1)

    def test_explicit_port_two_keeps_same_paid_budget_and_ledger_chain(self):
        first=self.start(bot_ports=(2,))
        with patch.object(batch,'run_child',side_effect=self.child):
            final=batch.resume_batch(self.root,first['batch_id'])
        self.assertEqual(final['status'],'complete')
        self.assertEqual(final['policies']['jev']['wins'],1)
        self.assertEqual(final['paid_ledger_checkpoint']['report']['accounted_nano_usd'],2_010_000)
        manifest,rows,_=batch.load_batch(self.root,self.folder())
        self.assertEqual(manifest['provider']['budget_directory'],self.directory)
        self.assertEqual([r['bot_port'] for r in rows],[2,2])

    def test_external_ledger_append_blocks_resume_before_launch(self):
        first=self.start()
        self.ledger.reserve(cost_nano_usd=2_000_000,input_tokens=2000,payload_sha256='b'*64)
        with patch.object(batch,'run_child',side_effect=AssertionError('launch forbidden')):
            with self.assertRaisesRegex(ValueError,'Unexpected ledger'):
                batch.resume_batch(self.root,first['batch_id'])

    def test_unexplained_reservation_during_child_is_retained_and_blocks_audit(self):
        def contaminated(*args):
            self.child(*args)
            self.ledger.reserve(cost_nano_usd=2_000_000,input_tokens=2000,payload_sha256='c'*64)
            root,folder,manifest,slot=args
            run=root/'build/jev/runs'/('match-'+f'{slot+1:032x}')
            path=run/'summary.json';summary=batch.read_json(path)
            summary['async_policy']['bridge']['provider']['budget_after']=self.ledger.report()
            path.write_text(json.dumps(summary))
        with patch.object(batch,'run_child',side_effect=contaminated):
            with self.assertRaisesRegex(ValueError,'exactly'):
                batch.start_batch(self.root,policies=('jev',),matches_per_policy=1,duration=1800,
                    budget=self.directory,max_requests=2)
        self.assertEqual(self.ledger.report()['requests'],3)
        _,rows,pending=batch.load_batch(self.root,self.folder())
        self.assertFalse(rows);self.assertIsNotNone(pending)

    def test_completed_paid_child_after_parent_crash_is_adopted_without_respending(self):
        with patch.object(batch,'run_child',side_effect=self.child),patch.object(batch,'record_audit',side_effect=RuntimeError('crash')):
            with self.assertRaises(RuntimeError):
                batch.start_batch(self.root,policies=('jev',),matches_per_policy=1,duration=1800,
                    budget=self.directory,max_requests=2)
        before=paid.checkpoint(self.root,self.directory)
        with patch.object(batch,'run_child',side_effect=AssertionError('retry forbidden')):
            report=batch.resume_batch(self.root,self.folder().name)
        self.assertEqual(report['status'],'complete')
        self.assertEqual(paid.checkpoint(self.root,self.directory),before)

    def test_invalid_paid_admission_does_not_launch_or_reserve(self):
        before=paid.checkpoint(self.root,self.directory)
        cases=({'budget':None},{'max_requests':201},{'duration':8000},
            {'policies':('random-tactical',)})
        for options in cases:
            with self.assertRaises(ValueError):self.start(**options)
        self.assertEqual(paid.checkpoint(self.root,self.directory),before)
        self.assertFalse((self.root/'build/jev/batches').exists())

    def test_exhausted_ledger_is_refused_before_creating_batch(self):
        for _ in range(20):self.ledger.reserve(cost_nano_usd=2_000_000,input_tokens=2000,payload_sha256='d'*64)
        with self.assertRaisesRegex(ValueError,'capacity'):self.start()
        self.assertFalse((self.root/'build/jev/batches').exists())

    def test_missing_credential_and_sealed_ledger_cannot_start_paid_cohort(self):
        with patch.dict('os.environ',{'OPENROUTER_API_KEY':''}):
            with self.assertRaises(ValueError):self.start()
        SpendLedger.continue_experiment(self.root,self.directory,'build/jev/continuation',
            deadline_utc=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),
            max_requests=10,max_input_tokens=100000)
        before=paid.checkpoint(self.root,self.directory)
        with self.assertRaises(ValueError):self.start()
        self.assertEqual(paid.checkpoint(self.root,self.directory),before)
        self.assertFalse((self.root/'build/jev/batches').exists())

    def test_ledger_prefix_change_cannot_hide_behind_unchanged_accounting(self):
        self.ledger.reserve(cost_nano_usd=2_000_000,input_tokens=2000,payload_sha256='a'*64)
        first=self.start()
        self.ledger.path.write_text(self.ledger.path.read_text().replace('a'*64,'b'*64))
        with self.assertRaisesRegex(ValueError,'prefix changed'):
            batch.resume_batch(self.root,first['batch_id'])

    def test_changed_provider_config_blocks_resume_without_spending(self):
        first=self.start();before=paid.checkpoint(self.root,self.directory)
        with patch.object(paid,'policy_config_hash',return_value='changed'):
            with self.assertRaisesRegex(ValueError,'identity or source'):
                batch.resume_batch(self.root,first['batch_id'])
        self.assertEqual(paid.checkpoint(self.root,self.directory),before)

    def test_child_credentials_are_routed_only_to_explicit_paid_supervisor(self):
        first=self.start();manifest,_,_=batch.load_batch(self.root,self.folder())
        child=MagicMock();child.wait.return_value=0
        with patch.object(batch.subprocess,'Popen',return_value=child) as spawn:
            batch.run_child(self.root,self.folder(),manifest,1)
        self.assertEqual(spawn.call_args.kwargs['env']['OPENROUTER_API_KEY'],'fixture-only')
        self.assertIn(self.directory,spawn.call_args.args[0])
        child.stdin.close.assert_called_once()

    def test_no_valid_provider_response_cannot_pass_as_a_paid_match(self):
        original=self.child
        def no_valid(*args):
            original(*args);root,folder,manifest,slot=args
            run=root/'build/jev/runs'/('match-'+f'{slot+1:032x}')
            p=run/'summary.json';s=batch.read_json(p)
            for attempt in s['async_policy']['bridge']['provider']['attempts']:attempt['status']='rejected'
            p.write_text(json.dumps(s))
        with patch.object(batch,'run_child',side_effect=no_valid):
            report=batch.start_batch(self.root,policies=('jev',),matches_per_policy=1,duration=1800,
                budget=self.directory,max_requests=2)
        self.assertEqual(report['status'],'stopped')
        self.assertEqual(report['policies']['jev']['verified_matches'],0)
        self.assertEqual(report['policies']['jev']['failed_attempts'],1)


class PaidReplayPointerTests(unittest.TestCase):
    def test_crash_adoption_reuses_sealed_bundle_and_detects_changed_artifacts(self):
        import tempfile
        from pathlib import Path
        root=Path(tempfile.mkdtemp(prefix='jev-paid-replay-')).resolve()
        folder=root/'batch';folder.mkdir();run=root/'match-fixture';run.mkdir()
        incident_id='incident-'+'a'*32;incident=root/'build/jev/incidents'/incident_id;incident.mkdir(parents=True)
        for name in ('manifest.json','focus.json','prefix.jsonl'):
            (incident/name).write_text(json.dumps({'run_id':run.name}))
        summary={'episodes':[{'episode':1,'last_frame':50,'observations':51}]}
        with patch.object(paid,'export_incident',return_value={'incident_id':incident_id}) as export,\
                patch.object(paid,'replay_incident',return_value={'status':'pass','replayed_records':51,'incident_id':incident_id}),\
                patch.object(paid,'inspect_policy',return_value={'status':'pass','outcomes':{'accepted':1}}):
            first=paid.audit_replay(root,folder,0,run,summary)
            second=paid.audit_replay(root,folder,0,run,summary)
        self.assertEqual(first,second);export.assert_called_once()
        paid.verify_replay_artifacts(root,first)
        (incident/'prefix.jsonl').write_text('changed')
        with self.assertRaisesRegex(ValueError,'artifacts changed'):paid.verify_replay_artifacts(root,first)


if __name__=='__main__':unittest.main()
