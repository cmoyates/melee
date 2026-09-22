from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from melee_agent.async_policy import bind
from melee_agent.budget import SpendLedger
from melee_agent.live_provider import ProviderBackend, preflight, provider_environment
from melee_agent.provider import MODEL_ALIAS, VERIFIED_MODEL
from test_async_policy import state


class LiveProviderTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="jev-live-provider-test-")).resolve()
        self.ledger = SpendLedger.create(self.root, "build/jev/budget", deadline_utc=
            (datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(), max_requests=20)
        self.candidates = ("neutral", "jump", "shield")

    def response(self, payload, timeout):
        value = json.loads(payload)
        self.payload = value
        labels = value["questions"]["action"]["criteria"]
        return 200, {}, json.dumps({"model": VERIFIED_MODEL, "provider": "TypeSafe", "answers": {
            "action": {"type": "choice", "choice": "shield", "probabilities": {k: int(k=="shield") for k in labels}}},
            "usage": {"cost": .00001, "input_tokens": 100, "output_tokens": 10}}).encode()

    def call(self, backend, sequence=1):
        observation = state(ns=time.monotonic_ns())
        context = bind("test", observation, sequence, 0, self.candidates)
        return backend.call(observation, context, self.candidates, threading.Event())

    def test_real_backend_seam_keeps_context_usage_and_model_identity(self):
        backend = ProviderBackend(self.root, "build/jev/budget", 2, time.monotonic_ns()+10_000_000_000, transport=self.response)
        try:
            reply = self.call(backend)[0]
            self.assertEqual(reply.action, "shield")
            self.assertEqual(reply.metadata["requested_model"], MODEL_ALIAS)
            self.assertEqual(reply.metadata["resolved_model"], VERIFIED_MODEL)
            self.assertEqual(reply.context.sequence, 1)
            self.assertEqual(self.payload["state"]["bot"]["stocks_remaining"], 4)
            self.assertEqual(self.payload["state"]["match"]["time_limit_seconds"], 480)
            self.assertEqual(set(self.payload["questions"]), {"action"})
            self.assertEqual(set(self.payload["questions"]["action"]["criteria"]), set(self.candidates))
        finally:
            report = backend.close()
        self.assertEqual(report["http_calls"], 1)
        self.assertEqual(report["http_active"], 0)
        self.assertEqual(report["client_shutdown"], {"workers_alive": 0, "timers_alive": 0})
        self.assertEqual(report["budget_after"]["requests"], 1)

    def test_run_cap_does_not_reset_shared_ledger(self):
        backend = ProviderBackend(self.root, "build/jev/budget", 1, time.monotonic_ns()+10_000_000_000, transport=self.response)
        try:
            self.assertEqual(len(self.call(backend)), 1)
            self.assertEqual(self.call(backend, 2), [])
            self.assertTrue(backend.exhausted)
        finally:
            report = backend.close()
        self.assertEqual(report["http_calls"], 1)
        next_backend = ProviderBackend(self.root, "build/jev/budget", 1, time.monotonic_ns()+10_000_000_000, transport=self.response)
        try:
            self.call(next_backend)
        finally:
            second = next_backend.close()
        self.assertEqual(second["budget_before"]["requests"], 1)
        self.assertEqual(second["budget_after"]["requests"], 2)

    def test_shutdown_margin_prevents_new_paid_request(self):
        backend = ProviderBackend(self.root, "build/jev/budget", 1, time.monotonic_ns()+2_000_000_000, transport=self.response)
        self.assertEqual(self.call(backend), [])
        self.assertEqual(backend.close()["http_calls"], 0)
        self.assertEqual(self.ledger.report()["requests"], 0)

    def test_malformed_response_is_accounted_and_never_becomes_a_choice(self):
        def invalid(payload, timeout):
            status, headers, raw = self.response(payload, timeout)
            data = json.loads(raw)
            data["answers"]["action"]["probabilities"]["shield"] = .99
            return status, headers, json.dumps(data).encode()
        backend = ProviderBackend(self.root, "build/jev/budget", 1, time.monotonic_ns()+10_000_000_000, transport=invalid)
        try:
            reply = self.call(backend)[0]
            self.assertEqual(reply.error, "invalid_distribution_sum")
            self.assertEqual(reply.action, "")
        finally:
            report = backend.close()
        self.assertEqual(report["counts"], {"errors:invalid_distribution_sum": 1})
        self.assertEqual(report["budget_after"]["unsettled_requests"], 0)

    def test_budget_refusal_makes_no_http_call(self):
        backend = ProviderBackend(self.root, "build/jev/budget", 1, time.monotonic_ns()+10_000_000_000, transport=self.response)
        from melee_agent.budget import BudgetError
        with patch.object(backend.ledger, "reserve", side_effect=BudgetError("fixture")):
            reply = self.call(backend)[0]
        self.assertEqual(reply.error, "budget_refused")
        self.assertTrue(backend.exhausted)
        self.assertEqual(backend.close()["http_calls"], 0)

    def test_credentials_only_cross_explicit_jev_boundary_and_never_emulator_environment(self):
        from melee_agent.matches import isolated_environment
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "private-test-key", "OPENROUTER_MODEL": MODEL_ALIAS}):
            self.assertNotIn("OPENROUTER_API_KEY", isolated_environment())
            for policy in ("smoke", "scripted", "delayed-fake"):
                self.assertNotIn("OPENROUTER_API_KEY", provider_environment(policy))
            self.assertEqual(provider_environment("jev")["OPENROUTER_API_KEY"], "private-test-key")
            self.assertEqual(preflight(self.root, "jev", "build/jev/budget", 1)["requests"], 0)
            with self.assertRaises(ValueError):
                preflight(self.root, "scripted", "build/jev/budget", 1)
            with self.assertRaises(ValueError):
                preflight(self.root, "jev", "build/jev/budget", 201)

    def test_circuit_opens_then_recovers_on_a_fresh_request(self):
        calls = []
        def transport(payload, timeout):
            calls.append(payload)
            if len(calls) <= 3:
                raise OSError("disconnect")
            return self.response(payload, timeout)
        backend = ProviderBackend(self.root, "build/jev/budget", 10, time.monotonic_ns()+10_000_000_000, transport=transport)
        try:
            for sequence in (1,2,3):
                self.assertEqual(self.call(backend, sequence)[0].error, "transport_or_accounting_error")
            self.assertEqual(self.call(backend, 4)[0].error, "circuit_open")
            self.assertEqual(len(calls), 3)
            backend.open_until_ns = 0
            reply = self.call(backend, 5)[0]
            self.assertIsNone(reply.error)
            self.assertEqual(reply.context.sequence, 5)
            self.assertEqual([event["state"] for event in backend.health_events], ["open", "recovered"])
        finally:
            self.assertEqual(backend.close()["client_shutdown"]["workers_alive"], 0)

    def test_client_shutdown_reports_stalled_worker_instead_of_claiming_it_stopped(self):
        from melee_agent.provider import DecisionsClient, ProviderError
        entered, release = threading.Event(), threading.Event()
        def stalled(payload, timeout):
            entered.set()
            release.wait(3)
            return self.response(payload, timeout)
        client = DecisionsClient(self.ledger, stalled)
        observation = state(ns=time.monotonic_ns())
        future = client.submit(observation, {k: k for k in self.candidates}, deadline_ns=time.monotonic_ns()+2_000_000_000)
        try:
            self.assertTrue(entered.wait(1))
            started = time.monotonic()
            report = client.close(timeout=.02)
            self.assertLess(time.monotonic()-started, .2)
            self.assertEqual(report["workers_alive"], 1)
            with self.assertRaisesRegex(ProviderError, "client_closed"):
                future.result()
        finally:
            release.set()
            report = client.close(timeout=1)
        self.assertEqual(report, {"workers_alive": 0, "timers_alive": 0})
        self.assertEqual(self.ledger.report()["unsettled_requests"], 0)


if __name__ == "__main__":
    unittest.main()
