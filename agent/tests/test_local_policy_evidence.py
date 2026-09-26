from dataclasses import replace
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from melee_agent.engine import FrameExecutor
from melee_agent.fake import RecordingSink
from melee_agent.incidents import RecordedClock, contract_hashes
from melee_agent.local_combat_policy import LocalCombatPolicy
from melee_agent.policy_evidence import inspect_policy
from test_combat_integration import ground


class LocalPolicyEvidenceTests(unittest.TestCase):
    def fixture(self, mode):
        run = Path(tempfile.mkdtemp(prefix='jev-local-replay-'))
        policy, clock = LocalCombatPolicy(mode, seed=7), RecordedClock()
        executor = FrameExecutor(policy, RecordingSink(), clock)
        rows = []
        for frame in range(90):
            observation = replace(ground(frame, 44 if frame in (1,61) else 14),
                observed_ns=1_000_000_000+frame*16_666_667)
            clock.values = [observation.observed_ns+1000, observation.observed_ns+2000]
            control = executor.step(observation)
            rows.append({'menu':'IN_GAME','episode':observation.episode,'frame':frame,
                'control':control,'skill':policy.trace()})
        import melee_agent.local_combat_policy as source
        launch = {'run_id':'synthetic','policy':mode,'source_sha256':{**contract_hashes(),
            'local_combat_policy.py':hashlib.sha256(Path(source.__file__).read_bytes()).hexdigest()}}
        (run/'launch.json').write_text(json.dumps(launch))
        (run/'summary.json').write_text(json.dumps({'policy':mode,'local_policy':policy.close()}))
        (run/'frames.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in rows))
        return run, rows

    def test_seeded_local_trace_replays_without_network_or_emulator(self):
        for mode in ('heuristic-tactical','random-tactical'):
            run, rows = self.fixture(mode)
            with patch('socket.socket', side_effect=AssertionError('network forbidden')), patch(
                    'subprocess.Popen', side_effect=AssertionError('process forbidden')):
                report = inspect_policy(run)
            self.assertEqual(report['status'],'pass',report)
            self.assertEqual(report['replayed_records'],len(rows))
            self.assertEqual(report['seed'],7)
            self.assertTrue(report['summary_matches'])
            self.assertFalse(report['controller_written'])

    def test_changed_candidate_trace_stops_at_first_divergence(self):
        run, rows = self.fixture('random-tactical')
        rows[0]['skill']['local_selection']['legal_candidates'] = ['neutral']
        (run/'frames.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in rows))
        report = inspect_policy(run)
        self.assertEqual(report['status'],'fail')
        self.assertEqual(report['divergence'],{'episode':1,'frame':0})
        self.assertEqual(report['replayed_records'],1)
        self.assertIsNone(report['frames_sha256'])

    def test_catalog_source_or_final_counts_cannot_be_silently_replaced(self):
        run, _ = self.fixture('heuristic-tactical')
        summary = json.loads((run/'summary.json').read_text())
        summary['local_policy']['counts']['selected:jab'] += 1
        (run/'summary.json').write_text(json.dumps(summary))
        self.assertEqual(inspect_policy(run)['status'],'fail')
        launch = json.loads((run/'launch.json').read_text())
        launch['source_sha256']['tactical_choices.py'] = '0'*64
        (run/'launch.json').write_text(json.dumps(launch))
        with self.assertRaisesRegex(ValueError,'launch source checkout'):
            inspect_policy(run)
