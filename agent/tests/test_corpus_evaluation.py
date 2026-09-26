from datetime import datetime, timedelta, timezone
import json
import unittest
from unittest.mock import patch

from melee_agent.budget import SpendLedger
from melee_agent.corpus_evaluation import evaluate_corpus, select_cases
from melee_agent.provider import VERIFIED_MODEL
import test_corpus


class CorpusEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_corpus.CorpusTests()
        self.fixture.setUp()
        self.root = self.fixture.root
        self.folder, self.corpus = self.fixture.build()
        self.ledger = SpendLedger.create(self.root, "build/jev/test-budget",
            deadline_utc=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(), max_requests=2)
        self.calls = []

    def transport(self, payload, timeout):
        request = json.loads(payload)
        self.calls.append(request)
        candidates = request["questions"]["action"]["criteria"]
        self.assertEqual(list(candidates), request["state"]["mechanical"]["legal_candidates"])
        self.assertEqual(request["state"]["kind"], "CompactObservationV2")
        choice = next(iter(candidates))
        return 200, {}, json.dumps({"model": VERIFIED_MODEL, "provider": "TypeSafe",
            "answers": {"action": {"type": "choice", "choice": choice,
                "probabilities": {key: int(key == choice) for key in candidates}}},
            "usage": {"cost": .00002, "input_tokens": 800, "output_tokens": 20}}).encode()

    def test_paid_corpus_path_preserves_states_and_stops_at_shared_request_bound(self):
        with patch("socket.socket", side_effect=AssertionError("network forbidden")), patch("subprocess.Popen", side_effect=AssertionError("runtime forbidden")):
            result = evaluate_corpus(self.root, self.corpus["corpus_id"], "build/jev/test-budget", 10,
                transport=self.transport, sleep=lambda seconds: None)
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(result["validated_responses"], 2)
        self.assertEqual(result["refusals"], {"budget_refused": 1})
        self.assertEqual(result["controller_inputs_sent"], 0)
        self.assertFalse(result["emulator_launched"])
        self.assertEqual(result["client_closed"], {"workers_alive": 0, "timers_alive": 0})
        self.assertEqual(result["budget_after"]["requests"], 2)
        artifact = self.folder/result["evaluation_id"]
        records = [json.loads(line) for line in (artifact/"responses.jsonl").read_text().splitlines()]
        manifest = json.loads((artifact/"manifest.json").read_text())
        self.assertEqual(records[0]["source"], manifest["selected"][0]["source"])
        self.assertEqual(records[0]["state_sha256"], manifest["selected"][0]["state_sha256"])

    def test_changed_corpus_is_rejected_before_any_transport_or_spend(self):
        path = self.folder/"states.jsonl"
        path.write_text(path.read_text()+"\n")
        with self.assertRaises(ValueError):
            evaluate_corpus(self.root, self.corpus["corpus_id"], "build/jev/test-budget", 1,
                transport=self.transport, sleep=lambda seconds: None)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.ledger.report()["requests"], 0)

    def test_selection_spans_eligible_order_without_duplicates(self):
        rows = [{"state": {"mechanical": {"legal_candidates": ["neutral", "approach"]}}, "index": i} for i in range(21)]
        selected = select_cases(rows, 4)
        self.assertEqual([row["index"] for row in selected], [0, 6, 13, 20])
        self.assertEqual(len(select_cases(rows, 30)), 21)
