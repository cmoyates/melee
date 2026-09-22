"""Provider failures cannot bypass schema, deadline, concurrency or spend limits."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import tempfile
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import patch

from melee_agent.budget import SpendLedger
from melee_agent.engine import Observation
from melee_agent.provider import DecisionsClient, OpenRouterTransport, ProviderError, VERIFIED_MODEL, decode_response

FIXTURE = Path(__file__).parent / "fixtures/battlefield.json"


def response():
    return {"model": VERIFIED_MODEL, "provider": "TypeSafe", "answers": {
        "action": {"type": "choice", "choice": "right", "probabilities": {"left": .1, "right": .9}, "confidence": .8}},
        "usage": {"cost": .00002, "input_tokens": 500, "output_tokens": 20}}


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="jev-provider-test-")).resolve()
        self.ledger = SpendLedger.create(self.root, "build/jev/spend",
            deadline_utc=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat())
        self.observation = Observation.parse(json.loads(FIXTURE.read_text())["cases"][1]["observation"])
        self.candidates = {"left": "Move left", "right": "Move right"}

    def submit(self, client, seconds=2):
        return client.submit(self.observation, self.candidates, deadline_ns=time.monotonic_ns() + int(seconds * 1e9))

    def test_valid_response_preserves_identity_state_prices_and_usage(self):
        captured = []
        def transport(payload, timeout):
            captured.append(json.loads(payload))
            return 200, {}, json.dumps(response()).encode()
        client = DecisionsClient(self.ledger, transport)
        result = self.submit(client).result(timeout=3)
        self.assertEqual((result.episode, result.frame), (1, 0))
        self.assertEqual(result.action, "right")
        self.assertEqual(result.resolved_model, VERIFIED_MODEL)
        self.assertEqual(captured[0]["state"]["match"]["time_limit_seconds"], 480)
        self.assertEqual(captured[0]["state"]["bot"]["stocks_remaining"], 4)
        self.assertEqual(captured[0]["provider"], {"only": ["TypeSafe"], "allow_fallbacks": False,
                                                    "max_price": {"prompt": .042, "completion": 0}})
        self.assertEqual(self.ledger.report()["reported_nano_usd"], 20000)

    def test_deadline_fires_while_transport_stalls_and_slot_stays_occupied(self):
        entered, release, ended = threading.Event(), threading.Event(), threading.Event()
        def transport(payload, timeout):
            entered.set()
            release.wait(2)
            ended.set()
            return 200, {}, json.dumps(response()).encode()
        client = DecisionsClient(self.ledger, transport)
        try:
            future = self.submit(client, .05)
            self.assertTrue(entered.wait(1))
            with self.assertRaisesRegex(ProviderError, "deadline_exceeded"):
                future.result(timeout=.5)
            with self.assertRaisesRegex(ProviderError, "in_flight_limit"):
                self.submit(client)
            self.assertEqual(self.ledger.report()["unsettled_requests"], 1)
        finally:
            release.set()
            ended.wait(1)
            client.close()

    def test_http_backoff_does_not_retry_or_refund_unknown_cost(self):
        calls = []
        def transport(payload, timeout):
            calls.append(1)
            return 429, {"Retry-After": "60"}, b"private server text"
        client = DecisionsClient(self.ledger, transport)
        with self.assertRaisesRegex(ProviderError, "rate_limited"):
            self.submit(client).result(timeout=1)
        with self.assertRaisesRegex(ProviderError, "provider_backoff"):
            self.submit(client)
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.ledger.report()["accounted_nano_usd"], 2_000_000)

    def test_invalid_answers_are_rejected_but_reported_billing_is_retained(self):
        mutations = [lambda d: d.update(model="different-model"),
            lambda d: d.pop("model"),
            lambda d: d["answers"]["action"].update(type="score"),
            lambda d: d["answers"]["action"].update(choice="invented"),
            lambda d: d["answers"]["action"].update(probabilities={"right": 1}),
            lambda d: d["answers"]["action"].update(probabilities={"left": .5, "right": .9}),
            lambda d: d["answers"]["action"].update(confidence=True),
            lambda d: d["answers"]["action"].update(probabilities={"left": -1, "right": 2}),
            lambda d: d["answers"]["action"].update(extra=1)]
        for mutate in mutations:
            data = response()
            mutate(data)
            client = DecisionsClient(self.ledger, lambda p, t: (200, {}, json.dumps(data).encode()))
            with self.assertRaises(ProviderError):
                self.submit(client).result(timeout=1)
            client.close()
        self.assertEqual(self.ledger.report()["reported_nano_usd"], len(mutations) * 20000)

    def test_auth_and_server_errors_preserve_reservations_without_retry(self):
        for status in (401, 403, 529):
            calls = []
            def transport(payload, timeout):
                calls.append(1)
                return status, {}, b"server secret"
            client = DecisionsClient(self.ledger, transport)
            with self.assertRaisesRegex(ProviderError, "http_error"):
                self.submit(client).result(timeout=1)
            self.assertEqual(len(calls), 1)
            client.close()
        self.assertEqual(self.ledger.report()["unsettled_requests"], 3)

    def test_live_transport_hard_timeout_reaps_its_exact_child(self):
        real_popen = subprocess.Popen
        children = []
        def stalled_process(*args, **kwargs):
            child = real_popen([sys.executable, "-c", "import time; time.sleep(20)"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            children.append(child)
            return child
        with patch("melee_agent.provider.subprocess.Popen", side_effect=stalled_process):
            with self.assertRaisesRegex(ProviderError, "transport_timeout"):
                OpenRouterTransport("synthetic-credential")(b"{}", .05)
        self.assertIsNotNone(children[0].poll())

    def test_missing_confidence_is_explicitly_unavailable(self):
        data = response()
        data["answers"]["action"].pop("confidence")
        client = DecisionsClient(self.ledger, lambda p, t: (200, {}, json.dumps(data).encode()))
        self.assertIsNone(self.submit(client).result(timeout=1).confidence)

    def test_schema_and_deadline_fail_before_spending(self):
        client = DecisionsClient(self.ledger, lambda p, t: self.fail("No request expected"))
        for candidates in ({"left": "one option"}, {"bad label": "bad", "right": "good"}, {"left": 3, "right": "ok"}):
            with self.assertRaises(ProviderError):
                client.submit(self.observation, candidates, deadline_ns=time.monotonic_ns() + 1_000_000_000)
        with self.assertRaises(ProviderError):
            client.submit(self.observation, self.candidates, deadline_ns=0)
        self.assertEqual(self.ledger.report()["requests"], 0)
        with self.assertRaisesRegex(ProviderError, "missing_credential"):
            OpenRouterTransport("")

    def test_caller_candidate_mutation_cannot_change_in_flight_contract(self):
        entered, release = threading.Event(), threading.Event()
        def transport(payload, timeout):
            entered.set()
            release.wait(1)
            return 200, {}, json.dumps(response()).encode()
        client = DecisionsClient(self.ledger, transport)
        future = self.submit(client)
        self.assertTrue(entered.wait(1))
        self.candidates.clear()
        release.set()
        self.assertEqual(future.result(timeout=2).action, "right")

    def test_close_and_completion_callbacks_are_reentrant(self):
        entered, release = threading.Event(), threading.Event()
        def transport(payload, timeout):
            entered.set()
            release.wait(1)
            return 200, {}, json.dumps(response()).encode()
        client = DecisionsClient(self.ledger, transport)
        future = self.submit(client)
        self.assertTrue(entered.wait(1))
        future.add_done_callback(lambda f: client.close())
        client.close()
        with self.assertRaisesRegex(ProviderError, "client_closed"):
            future.result(timeout=1)
        release.set()
        with self.assertRaisesRegex(ProviderError, "client_closed"):
            self.submit(client)

    def test_transport_exception_messages_and_invalid_json_do_not_leak(self):
        def transport(payload, timeout):
            raise RuntimeError("secret credential or private response")
        client = DecisionsClient(self.ledger, transport)
        with self.assertRaisesRegex(ProviderError, "^transport_or_accounting_error$"):
            self.submit(client).result(timeout=1)
        for raw in (b'{"x":1,"x":2}', b'{"x":NaN}', b'not json'):
            with self.assertRaises(ProviderError):
                decode_response(raw)
