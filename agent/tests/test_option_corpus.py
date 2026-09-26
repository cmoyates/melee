import json
import unittest
from unittest.mock import patch

from melee_agent.cli import main
from melee_agent.corpus import build_corpus, choose_sources, digest, generate_cases, validate_corpus
from melee_agent.corpus_evaluation import evaluate_corpus, select_cases
from melee_agent.live_provider import descriptions
from melee_agent.tactical_choices import PROFILE, OPTION_PROFILE, profile_labels
import test_corpus
import test_corpus_evaluation


class OptionCorpusTests(unittest.TestCase):
    def setUp(self):
        self.fixture=test_corpus.CorpusTests()
        self.fixture.setUp()
        self.root,self.runs=self.fixture.root,self.fixture.runs
        for run in self.runs:
            p=self.root/'build/jev/runs'/run/'summary.json'
            s=json.loads(p.read_text());s.update(candidate_profile=OPTION_PROFILE,policy='heuristic-tactical')
            p.write_text(json.dumps(s))

    def build(self):
        with patch('socket.socket',side_effect=AssertionError('network forbidden')),patch('subprocess.Popen',side_effect=AssertionError('runtime forbidden')):
            result=build_corpus(self.root,1000,3,profile=OPTION_PROFILE)
            self.assertEqual(validate_corpus(self.root,result['corpus_id'])['recompiled_states'],1000)
        return self.root/'build/jev/corpora'/result['corpus_id'],result

    def test_explicit_profile_selects_only_matching_sources_and_recompiles_option_labels(self):
        self.assertEqual(choose_sources(self.root,3),[])
        self.assertEqual(choose_sources(self.root,3,profile=OPTION_PROFILE),self.runs)
        with self.assertRaisesRegex(ValueError,'cannot relabel'):
            next(generate_cases(self.root,self.runs,1000))
        folder,result=self.build()
        self.assertEqual(result['candidate_profile'],OPTION_PROFILE)
        manifest=json.loads((folder/'manifest.json').read_text())
        self.assertEqual(manifest['candidate_order'],list(profile_labels(OPTION_PROFILE)))
        rows=[json.loads(line) for line in (folder/'states.jsonl').read_text().splitlines()]
        self.assertTrue(all(r['candidate_profile']==OPTION_PROFILE for r in rows))
        self.assertTrue(all('approach_jab' in r['state']['mechanical']['legal_candidates'] for r in rows))
        self.assertNotIn('forbidden',(folder/'states.jsonl').read_text())
        with self.assertRaisesRegex(ValueError,'profile mismatch'):select_cases(rows,1)
        self.assertEqual(len(select_cases(rows,3,profile=OPTION_PROFILE)),3)

    def test_insufficient_matching_sources_cannot_be_filled_with_atomic_runs(self):
        p=self.root/'build/jev/runs'/self.runs[0]/'summary.json'
        s=json.loads(p.read_text());s['candidate_profile']=PROFILE;p.write_text(json.dumps(s))
        with self.assertRaisesRegex(ValueError,'at least three'):
            build_corpus(self.root,1000,3,profile=OPTION_PROFILE)

    def test_forged_case_or_manifest_profile_fails_even_with_rehashed_states(self):
        folder,result=self.build();p=folder/'states.jsonl';rows=[json.loads(x) for x in p.read_text().splitlines()]
        rows[0]['candidate_profile']=PROFILE;p.write_text(''.join(json.dumps(r)+'\n' for r in rows))
        manifest=json.loads((folder/'manifest.json').read_text());manifest['state_file_sha256']=digest(p)
        (folder/'manifest.json').write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError,'no longer matches'):validate_corpus(self.root,result['corpus_id'])
        manifest['candidate_profile']=PROFILE
        (folder/'manifest.json').write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError,'manifest'):validate_corpus(self.root,result['corpus_id'])

    def test_mock_evaluation_uses_option_criteria_and_cli_keeps_profile_explicit(self):
        fixture=test_corpus_evaluation.CorpusEvaluationTests();fixture.setUp()
        # Reuse its counted mock transport and bounded simulated ledger, but
        # explicitly replace the corpus with sources declaring the option profile.
        for run in fixture.fixture.runs:
            p=fixture.root/'build/jev/runs'/run/'summary.json';s=json.loads(p.read_text())
            s.update(candidate_profile=OPTION_PROFILE,policy='heuristic-tactical');p.write_text(json.dumps(s))
        corpus=build_corpus(fixture.root,1000,3,profile=OPTION_PROFILE)
        with patch('socket.socket',side_effect=AssertionError('network forbidden')),patch('subprocess.Popen',side_effect=AssertionError('runtime forbidden')):
            result=evaluate_corpus(fixture.root,corpus['corpus_id'],'build/jev/test-budget',1,
                transport=fixture.transport,sleep=lambda _:None)
        self.assertEqual(result['candidate_profile'],OPTION_PROFILE)
        self.assertEqual(result['validated_responses'],1)
        self.assertFalse(result['emulator_launched'])
        criteria=fixture.calls[0]['questions']['action']['criteria']
        self.assertEqual(criteria['approach_jab'],descriptions(OPTION_PROFILE)['approach_jab'])
        with patch('melee_agent.corpus.build_corpus',return_value={}) as build:
            self.assertEqual(main(['corpus','build','--profile',OPTION_PROFILE]),0)
        self.assertEqual(build.call_args.kwargs['profile'],OPTION_PROFILE)
