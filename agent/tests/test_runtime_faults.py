from dataclasses import replace
from pathlib import Path
import tempfile
import threading
import time
import unittest

from melee_agent.async_policy import rejection
from melee_agent.runtime_faults import RuntimeFaults, FaultBackend
from test_async_policy import delivery, state


class RuntimeFaultTests(unittest.TestCase):
    def test_low_confidence_cannot_start_a_skill(self):
        original = delivery()
        low = replace(original, reply=replace(original.reply, metadata={"confidence": .01}))
        self.assertEqual(rejection(low, state(11), "test", 0, 0, 1_100_000_000, False), "low_confidence")

    def test_frame_gap_occurs_once_and_persists_a_boundary(self):
        root = Path(tempfile.mkdtemp(prefix="jev-fault-test-"))
        faults = RuntimeFaults(root, "frame_gap")
        self.assertFalse(faults.drop_state(599))
        self.assertTrue(faults.drop_state(600))
        self.assertFalse(faults.drop_state(601))
        self.assertEqual(faults.report()["counts"], {"frame_gap": 1})
        self.assertTrue((root / "fault-injected.json").exists())

    def test_frame_stall_keeps_dropping_until_supervisor_stops_worker(self):
        root = Path(tempfile.mkdtemp(prefix="jev-fault-test-"))
        faults = RuntimeFaults(root, "frame_stall")
        self.assertTrue(faults.drop_state(600))
        self.assertTrue(faults.drop_state(601))
        self.assertEqual(len(faults.events), 1)

    def test_mock_budget_and_transport_are_explicitly_separate_from_external_spend(self):
        root = Path(tempfile.mkdtemp(prefix="jev-fault-test-")).resolve()
        run = root / "build/jev/runs/fixture"
        run.mkdir(parents=True)
        faults = RuntimeFaults(run, "network")
        backend = FaultBackend(root, run, faults, time.monotonic_ns()+10_000_000_000)
        original = delivery(state(ns=time.monotonic_ns()))
        try:
            replies = backend.call(state(ns=original.expected.observed_ns), original.expected,
                original.candidates, threading.Event())
            self.assertEqual(len(replies), 1)
        finally:
            report = backend.close()
        self.assertTrue(report["simulation_only"])
        self.assertEqual(report["external_http_calls"], 0)
        self.assertEqual(report["http_calls"], 1)
        self.assertEqual(report["budget_after"]["reported_nano_usd"], 0)
        self.assertEqual(report["client_shutdown"]["workers_alive"], 0)


if __name__ == "__main__":
    unittest.main()
