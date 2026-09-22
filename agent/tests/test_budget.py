"""Persistent spend limits under crashes, restarts and competing workers."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from melee_agent.budget import BudgetError, SpendLedger, cost_units


class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="jev-spend-test-")).resolve()
        self.options = {"deadline_utc": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
                        "limit_usd": "0.01", "max_requests": 100, "max_input_tokens": 1000}
        self.ledger = SpendLedger.create(self.root, "build/jev/test-budget", **self.options)

    def reserve(self, ledger=None, **values):
        return (ledger or self.ledger).reserve(**{"cost_nano_usd": 2_000_000, "input_tokens": 100,
                                                    "payload_sha256": "a" * 64, **values})

    def test_restart_keeps_unknown_reservations_and_known_costs(self):
        known, unknown = self.reserve(), self.reserve()
        self.ledger.settle(known, cost_usd="0.0001", input_tokens=10)
        restored = SpendLedger.create(self.root, "build/jev/test-budget", **self.options)
        report = restored.report()
        self.assertEqual(report["requests"], 2)
        self.assertEqual(report["unsettled_requests"], 1)
        self.assertEqual(report["accounted_nano_usd"], 2_100_000)
        self.assertEqual(report["reported_nano_usd"], 100_000)
        self.assertEqual(report["accounted_input_tokens"], 110)
        self.assertNotEqual(known, unknown)

    def test_competing_file_descriptors_cannot_overspend(self):
        def reserve_once(_):
            try:
                return self.reserve(SpendLedger(self.ledger.path))
            except BudgetError:
                return None
        with ThreadPoolExecutor(max_workers=8) as workers:
            results = list(workers.map(reserve_once, range(20)))
        self.assertEqual(sum(r is not None for r in results), 5)
        self.assertEqual(self.ledger.report()["accounted_nano_usd"], 10_000_000)

    def test_limits_cannot_be_increased_on_restart(self):
        self.reserve()
        for change in ({"limit_usd": "1"}, {"max_requests": 200}, {"max_input_tokens": 2000},
                        {"deadline_utc": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()}):
            with self.assertRaises(BudgetError):
                SpendLedger.create(self.root, "build/jev/test-budget", **{**self.options, **change})

    def test_duplicate_settlement_or_refund_is_rejected(self):
        request = self.reserve()
        self.ledger.settle(request, cost_usd="0.001", input_tokens=25)
        for identity in (request, "unknown"):
            with self.assertRaises(BudgetError):
                self.ledger.settle(identity, cost_usd="0", input_tokens=0)
        self.assertEqual(self.ledger.report()["accounted_nano_usd"], 1_000_000)

    def test_provider_exceeding_reservation_blocks_further_spend(self):
        request = self.reserve()
        self.ledger.settle(request, cost_usd="0.003", input_tokens=100)
        self.assertTrue(self.ledger.report()["reservation_exceeded"])
        with self.assertRaises(BudgetError):
            self.reserve()

    def test_deadline_request_and_token_caps_are_independent(self):
        for i, change in enumerate(({"max_requests": 1}, {"max_input_tokens": 100})):
            ledger = SpendLedger.create(self.root, f"build/jev/cap-{i}", **{**self.options, **change})
            self.reserve(ledger)
            with self.assertRaises(BudgetError):
                self.reserve(ledger)
        ledger = SpendLedger.create(self.root, "build/jev/expired", **{**self.options,
                                    "deadline_utc": "2000-01-01T00:00:00+00:00"})
        with self.assertRaises(BudgetError):
            self.reserve(ledger)

    def test_corrupt_tail_and_empty_existing_ledger_fail_closed(self):
        with self.ledger.path.open("ab") as handle:
            handle.write(b'{"kind": "reserve"')
        with self.assertRaises(BudgetError):
            self.reserve()
        with self.assertRaises(BudgetError):
            SpendLedger.create(self.root, "build/jev/test-budget", **self.options)
        empty = self.root / "build/jev/empty"
        empty.mkdir()
        (empty / "spend.jsonl").touch()
        with self.assertRaises(BudgetError):
            SpendLedger.create(self.root, "build/jev/empty", **self.options)

    def test_paths_and_invalid_money_cannot_bypass_limits(self):
        for amount in (True, -1, float("nan"), "Infinity", {}, "invalid"):
            with self.assertRaises(BudgetError):
                cost_units(amount)
        self.assertEqual(cost_units("0.0000000001"), 1)
        with self.assertRaises(ValueError):
            SpendLedger.create(self.root, "../escape", **self.options)
        alias = self.root / "build/jev/alias"
        alias.mkdir()
        (alias / "spend.jsonl").symlink_to(self.ledger.path)
        with self.assertRaises(OSError):
            SpendLedger.create(self.root, "build/jev/alias", **self.options)
