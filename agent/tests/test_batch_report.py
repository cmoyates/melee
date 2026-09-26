import contextlib
import io
import json
from pathlib import Path
import socket
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import ubjson

from melee_agent import batch_report as report, policy_batch as batch
from melee_agent.budget import SpendLedger
from melee_agent.cli import main
from melee_agent.paid_cohort import checkpoint


class BatchReportTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='jev-report-')).resolve()
        self.batch_id = 'batch-'+'a'*32
        self.folder = self.root/'build/jev/batches'/self.batch_id
        self.folder.mkdir(parents=True)
        source = {'fixture.py':'1'*64}
        self.manifest = {'schema_version':1, 'batch_id':self.batch_id,
            'policies':['jev','random-tactical','heuristic-tactical'], 'matches_per_policy':1,
            'match_seconds':600, 'duration_seconds':3000, 'candidate_profile':'fox-aerial-v1',
            'provider_enabled':True, 'source_identity':{'modules':source,'local_config':'2'*64},
            'runtime_sha256':'3'*64}
        self.manifest['schedule'] = batch.validate_plan(self.manifest['policies'],1,600,3000,'fox-aerial-v1')
        ledger = SpendLedger.create(self.root,'build/jev/budget',deadline_utc='2099-01-01T00:00:00Z')
        self.ledger = ledger
        self.initial = checkpoint(self.root,'build/jev/budget')
        self.manifest['provider'] = {'initial_ledger':self.initial, 'budget_directory':'build/jev/budget',
            'profile':'fox-aerial-v1','config_sha256':'4'*64,'max_requests':1}
        batch.write_new(self.folder/'manifest.json', self.manifest)
        batch.append_event(self.folder,{'kind':'created','manifest_sha256':batch.file_hash(self.folder/'manifest.json')})
        self.latest = self.initial

    def add(self, slot, passed=True):
        batch.append_event(self.folder,{'kind':'launch','slot':slot,'ledger_before':self.latest})
        before = self.latest
        if slot == 0:
            self.ledger.reserve(cost_nano_usd=2_000_000,input_tokens=100,payload_sha256='5'*64)
            self.latest = checkpoint(self.root,'build/jev/budget')
        run_id = 'match-'+f'{slot+1:032x}'
        run = self.root/'build/jev/runs'/run_id
        (run/'replays').mkdir(parents=True)
        # Minimal real UBJSON event container, with a big-endian GameStart RNG seed.
        event = bytearray(0x141); event[0] = 0x36; event[1:5] = bytes([3,19,1,0])
        event[0x13D:0x141] = (12345+slot).to_bytes(4,'big')
        replay = run/'replays/game.slp'
        replay.write_bytes(ubjson.dumpb({'raw':bytes([0x35,4,0x36,1,0x40])+event}))
        summary = {'run_id':run_id,'policy':self.manifest['schedule'][slot]['policy'],
            'status':'complete' if passed else 'incomplete','completed_matches':int(passed),
            'elapsed_seconds':12.5,'episodes':[{'winner_port':2,'last_stocks':[0,3],'observations':100}],
            'replays':[{'file':'game.slp','sha256':batch.file_hash(replay)}],
            'private_prompt':'NEVER_PUBLIC_SECRET','asset_path':'/private/NEVER_PUBLIC_SECRET'}
        launch = {'run_id':run_id,'policy':summary['policy'],
            'source_sha256':self.manifest['source_identity']['modules'],
            'runtime_sha256':self.manifest['runtime_sha256'],'candidate_profile':'fox-aerial-v1'}
        batch.write_new(run/'summary.json',summary);batch.write_new(run/'launch.json',launch)
        (run/'frames.jsonl').write_text('private frame payload\n')
        control = {'status':'pass' if passed else 'fail','packets_sha256':'6'*64}
        spending = {'before':before,'after':self.latest,'reserved_requests':int(slot==0)}
        if slot == 0:
            incident_id = 'incident-'+'b'*32
            incident = self.root/'build/jev/incidents'/incident_id;incident.mkdir(parents=True)
            for name in ('manifest.json','focus.json','prefix.jsonl'):
                (incident/name).write_text('private sealed fixture\n')
            control.update(sealed_replay={'incident_id':incident_id,'packets_sha256':'6'*64},
                incident_sha256={p.name:batch.file_hash(p) for p in incident.iterdir()},
                policy_evidence={'outcomes':{'accepted':1},'acknowledgements':{'observed:move':1},
                    'input_owner_frames':{'provider':12,'idle':88},
                    'source_to_reply_ms':{'count':1,'p50':400,'p95':400,'p99':400,'max':400}})
            spending.update(accounted_cost_nano_usd=2_000_000, attempts=1, http_calls=1, validated=1)
        audit = {'schema_version':1,'slot':slot,'run_id':run_id,'policy':summary['policy'],'passed':passed,
            'summary':summary,'control_replay':control,'spending':spending,
            'integrity':{'status':'pass'},'rules_and_result':passed,
            'artifact_sha256':{n:batch.file_hash(run/n) for n in
                ('summary.json','launch.json','frames.jsonl','replays/game.slp')}}
        path = self.folder/f'audit-{slot:02}.json'
        batch.write_new(path,audit)
        batch.append_event(self.folder,{'kind':'audited','slot':slot,'audit_sha256':batch.file_hash(path)})

    def render(self):
        return report.build_report(self.root,self.batch_id)

    def rewrite_audit(self, mutate):
        path=self.folder/'audit-00.json';audit=json.loads(path.read_text());mutate(audit)
        path.write_text(json.dumps(audit))
        journal=self.folder/'events.jsonl';events=[json.loads(l) for l in journal.read_text().splitlines()]
        events[2]['audit_sha256']=batch.file_hash(path)
        journal.write_text(''.join(json.dumps(e)+'\n' for e in events))

    def test_complete_report_has_exact_counts_seeds_reservations_and_safe_markdown(self):
        for slot in range(3): self.add(slot)
        with patch.object(socket,'socket',side_effect=AssertionError('network forbidden')), \
                patch.object(subprocess,'Popen',side_effect=AssertionError('launch forbidden')):
            value = self.render()
        self.assertEqual(value['status'],'complete')
        self.assertEqual(value['spending']['accounted_nano_usd'],2_000_000)
        self.assertEqual(value['spending']['reported_nano_usd'],0)
        self.assertEqual(value['spending']['uncertain_reserved_nano_usd'],2_000_000)
        self.assertEqual(value['matches'][0]['replays'][0]['observed_rng_seed'],12345)
        self.assertIsNone(value['matches'][1]['provider'])
        self.assertIsNone(value['matches'][0]['provider']['phases'])
        self.assertEqual(value['policies']['jev']['wilson_95'][0],0)
        text = report.markdown(value)
        self.assertNotIn('NEVER_PUBLIC_SECRET',text)
        self.assertNotIn(str(self.root),text)
        self.assertEqual(json.loads(text.split('```json\n')[1].split('\n```')[0]),value)

    def test_failed_attempt_is_visible_but_not_scored_as_loss(self):
        self.add(0);self.add(1,passed=False)
        value = self.render();group=value['policies']['random-tactical']
        self.assertEqual(value['status'],'failed')
        self.assertEqual(group['failed_attempts'],1)
        self.assertEqual(group['losses'],0)
        self.assertIsNone(group['wilson_95'])
        self.assertEqual(value['unattempted_slots'],1)

    def test_pending_identity_and_spending_are_not_claimed_audited(self):
        self.add(0)
        batch.append_event(self.folder,{'kind':'launch','slot':1,'ledger_before':self.latest})
        self.ledger.reserve(cost_nano_usd=2_000_000,input_tokens=100,payload_sha256='7'*64)
        value = self.render()
        self.assertEqual(value['pending_slot'],1)
        self.assertEqual(value['audited_matches'],1)
        self.assertEqual(value['spending']['requests'],1)
        self.assertFalse(value['spending']['includes_pending_spending'])

    def test_historical_report_ignores_current_source_and_later_ledger_suffix(self):
        self.add(0)
        p=self.root/'agent/src/melee_agent/fixture.py';p.parent.mkdir(parents=True);p.write_text('changed')
        self.ledger.reserve(cost_nano_usd=2_000_000,input_tokens=100,payload_sha256='7'*64)
        self.assertEqual(self.render()['spending']['requests'],1)
        with self.assertRaisesRegex(ValueError,'source changed'):
            batch.load_batch(self.root,self.folder)

    def test_tampered_frame_audit_manifest_and_ledger_each_refuse(self):
        self.add(0)
        paths = [next((self.root/'build/jev/runs').glob('*/frames.jsonl')),
            self.folder/'audit-00.json',self.folder/'manifest.json',self.ledger.path]
        for path in paths:
            original=path.read_bytes()
            path.write_bytes(original.replace(b'private',b'changed') if b'private' in original else b'{}\n')
            with self.assertRaises((ValueError,KeyError,TypeError)):
                self.render()
            path.write_bytes(original)

    def test_journal_change_during_report_is_refused(self):
        self.add(0)
        original=report.match_row
        def concurrent(root,audit):
            value=original(root,audit)
            batch.append_event(self.folder,{'kind':'launch','slot':1,'ledger_before':self.latest})
            return value
        with patch.object(report,'match_row',side_effect=concurrent),self.assertRaises(ValueError):
            self.render()

    def test_partial_journal_and_out_of_order_slot_refuse(self):
        self.add(0);path=self.folder/'events.jsonl';original=path.read_bytes()
        path.write_bytes(original+b'{')
        with self.assertRaises(ValueError): self.render()
        path.write_bytes(original)
        batch.append_event(self.folder,{'kind':'launch','slot':2,'ledger_before':self.latest})
        with self.assertRaises(ValueError): self.render()

    def test_unsafe_artifact_paths_refuse_even_when_audit_rehashed(self):
        self.add(0);path=self.folder/'audit-00.json';audit=json.loads(path.read_text())
        audit['artifact_sha256']['../../outside']='1'*64
        path.write_text(json.dumps(audit))
        journal=self.folder/'events.jsonl';events=[json.loads(l) for l in journal.read_text().splitlines()]
        events[-1]['audit_sha256']=batch.file_hash(path)
        journal.write_text(''.join(json.dumps(e)+'\n' for e in events))
        with self.assertRaises(ValueError): self.render()

    def test_rehashed_false_accounting_and_changed_sealed_prefix_refuse(self):
        self.add(0)
        def mutate(audit):
            audit['spending']['after']['report']['accounted_nano_usd']=0
        self.rewrite_audit(mutate)
        with self.assertRaises(ValueError): self.render()
        self.rewrite_audit(lambda a: a['spending']['after']['report'].update(accounted_nano_usd=2_000_000))
        p=next((self.root/'build/jev/incidents').glob('*/prefix.jsonl'));p.write_text('changed')
        with self.assertRaises(ValueError): self.render()

    def test_invalid_phase_keys_are_not_exported(self):
        self.add(0)
        def mutate(audit):
            audit['control_replay']['policy_evidence']['participation']={
                'frames':{'private secret':{'observed':1}},'request_sources':{},'applications':{}}
        self.rewrite_audit(mutate)
        with self.assertRaises(ValueError): self.render()

    def test_provider_identity_exports_only_validated_identity_fields(self):
        summary={'async_policy':{'bridge':{'provider':{'attempts':[
            {'status':'rejected','reason':'NEVER_PUBLIC_SECRET'},
            {'status':'validated','result':{'requested_model':'~typesafe/jev-latest',
                'resolved_model':'typesafe/jev-fixture','provider':'TypeSafe',
                'answers':{'private':'NEVER_PUBLIC_SECRET'}}}]}}}}
        result=report.provider_identity(summary)
        self.assertEqual(result[0]['validated_responses'],1)
        self.assertEqual(result[0]['resolved_model'],'typesafe/jev-fixture')
        self.assertNotIn('NEVER_PUBLIC_SECRET',json.dumps(result))

    def test_unscored_empty_cohort_and_cli_workspace_route(self):
        value=self.render()
        self.assertEqual(value['status'],'checkpointed')
        self.assertTrue(all(v['win_fraction'] is None for v in value['policies'].values()))
        output=io.StringIO()
        with contextlib.redirect_stdout(output):
            code=main(['batch','report',self.batch_id,'--workspace',str(self.root),'--format','markdown'])
        self.assertEqual(code,0)
        self.assertIn('0/3 audited',output.getvalue())


if __name__ == '__main__':
    unittest.main()
