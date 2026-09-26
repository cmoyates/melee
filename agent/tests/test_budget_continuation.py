from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from melee_agent.budget import BudgetError, SpendLedger
from melee_agent.live_provider import preflight


class BudgetContinuationTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="jev-continuation-test-")).resolve()
        self.deadline = (datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()
        self.parent_directory = "build/jev/parent"
        self.parent = SpendLedger.create(self.root, self.parent_directory, deadline_utc=self.deadline,
            limit_usd="0.01", max_requests=100, max_input_tokens=10000)
        self.options = {"deadline_utc": self.deadline, "max_requests": 1000, "max_input_tokens": 1000000}

    def reserve(self, ledger):
        return ledger.reserve(cost_nano_usd=2000000, input_tokens=100, payload_sha256="a"*64)

    def continue_to(self, target="build/jev/child", **options):
        return SpendLedger.continue_experiment(self.root, self.parent_directory, target,
            **{**self.options, **options})

    def test_only_unspent_money_transfers_and_unknown_reservations_cannot_be_refunded(self):
        known, unknown = self.reserve(self.parent), self.reserve(self.parent)
        self.parent.settle(known, cost_usd="0.0001", input_tokens=10)
        prefix = self.parent.path.read_bytes()
        child = self.continue_to()
        self.assertTrue(self.parent.path.read_bytes().startswith(prefix))
        self.assertEqual(child.report()["limit_nano_usd"], 7900000)
        self.assertTrue(self.parent.report()["sealed"])
        with self.assertRaisesRegex(BudgetError, "sealed"):
            self.reserve(self.parent)
        with self.assertRaisesRegex(BudgetError, "sealed"):
            self.parent.settle(unknown, cost_usd="0", input_tokens=0)
        for _ in range(3):
            self.reserve(child)
        with self.assertRaises(BudgetError):
            self.reserve(child)
        self.assertEqual(self.parent.report()["accounted_nano_usd"]+child.report()["limit_nano_usd"], 10000000)
        funding = json.loads((child.path.parent/"funding.json").read_text())
        self.assertEqual(funding["parent_accounted_nano_usd"], 2100000)

    def test_identical_retry_preserves_child_spend_and_altered_config_cannot_fork(self):
        child = self.continue_to()
        self.reserve(child)
        before = child.path.read_bytes()
        self.assertEqual(self.continue_to().path.read_bytes(), before)
        for options in ({"max_requests": 1001}, {"max_input_tokens": 2000000},
                {"deadline_utc": (datetime.now(timezone.utc)+timedelta(hours=2)).isoformat()}):
            with self.assertRaisesRegex(BudgetError, "reconfigured"):
                self.continue_to(**options)
        with self.assertRaisesRegex(BudgetError, "reconfigured"):
            self.continue_to("build/jev/other")
        self.assertFalse((self.root/"build/jev/other").exists())

    def test_competing_destinations_authorize_only_one_child(self):
        def attempt(number):
            try:
                return self.continue_to("build/jev/child-"+str(number))
            except BudgetError:
                return None
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(attempt, range(8)))
        self.assertEqual(sum(result is not None for result in results), 1)
        self.assertEqual(len(list((self.root/"build/jev").glob("child-*"))), 1)

    def test_live_preflight_refuses_a_sealed_parent_before_runtime_start(self):
        self.continue_to()
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test", "OPENROUTER_MODEL": "~typesafe/jev-latest"}):
            with self.assertRaisesRegex(BudgetError, "sealed"):
                preflight(self.root, "jev", self.parent_directory, 1)

    def test_multiple_generations_conserve_the_original_dollar_allowance(self):
        self.reserve(self.parent)
        child = self.continue_to()
        self.reserve(child)
        final = SpendLedger.continue_experiment(self.root, "build/jev/child", "build/jev/grandchild", **self.options)
        self.assertEqual(final.report()["limit_nano_usd"], 6000000)
        total = sum(ledger.report()["accounted_nano_usd"] for ledger in (self.parent, child))
        self.assertEqual(total+final.report()["limit_nano_usd"], 10000000)
        for sealed in (self.parent, child):
            with self.assertRaisesRegex(BudgetError, "sealed"):
                self.reserve(sealed)

    def test_competing_reservation_is_either_accounted_before_seal_or_refused(self):
        def reserve():
            try:
                return self.reserve(SpendLedger(self.parent.path))
            except BudgetError:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            pending = pool.submit(reserve)
            child = self.continue_to()
            pending.result()
        self.assertEqual(self.parent.report()["accounted_nano_usd"]+child.report()["limit_nano_usd"], 10000000)
        with self.assertRaises(BudgetError):
            self.reserve(self.parent)

    def test_interrupted_initialization_and_missing_child_fail_closed(self):
        with patch.object(SpendLedger, "create", side_effect=OSError("interrupted before child")):
            with self.assertRaises(OSError):
                self.continue_to()
        self.assertTrue(self.parent.report()["sealed"])
        with self.assertRaisesRegex(BudgetError, "missing"):
            self.continue_to()
        with self.assertRaisesRegex(BudgetError, "sealed"):
            self.reserve(self.parent)
        self.assertFalse((self.root/"build/jev/child").exists())

    def test_existing_destination_invalid_limits_and_overrun_do_not_seal(self):
        (self.root/"build/jev/occupied").mkdir()
        for target, options in (("build/jev/occupied", {}), (self.parent_directory, {}),
                ("../escape", {}), ("build/jev/child", {"max_requests": 0}),
                ("build/jev/child", {"deadline_utc": "2000-01-01T00:00:00Z"})):
            with self.assertRaises(ValueError):
                self.continue_to(target, **options)
            self.assertFalse(self.parent.report().get("sealed", False))
        request = self.reserve(self.parent)
        self.parent.settle(request, cost_usd="0.003", input_tokens=100)
        with self.assertRaisesRegex(BudgetError, "unspent"):
            self.continue_to()
        self.assertFalse(self.parent.report().get("sealed", False))

    def test_appending_to_a_sealed_journal_or_forging_transfer_amount_is_invalid(self):
        self.continue_to()
        original = self.parent.path.read_bytes()
        rows = [json.loads(line) for line in original.splitlines()]
        rows[-1]["limit_nano_usd"] += 1
        self.parent.path.write_text("".join(json.dumps(row)+"\n" for row in rows))
        with self.assertRaises(BudgetError):
            self.parent.report()
        self.parent.path.write_bytes(original+original.splitlines()[0]+b"\n")
        with self.assertRaises(BudgetError):
            self.parent.report()
