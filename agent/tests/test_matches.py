"""Asset-free regression tests for result truth and bounded process ownership."""

import os
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import select
import unittest
from unittest.mock import patch

from melee_agent.matches import artifact_bytes, isolated_environment, locate_run, probe_passed, terminate_child
from melee_agent.replay import expected_settings, summarize_raw
from melee_agent.config import Config
from melee_agent.doctor import runtime_evidence, STOCK_DISC_SHA1


def replay_fixture(method=2, placements=(1, 0, 255, 255), end=True):
    start = bytearray(0xF0)
    start[0] = 0x36
    start[0x5] = 0x20
    start[0x13:0x15] = (31).to_bytes(2, "big")
    start[0x15:0x19] = (480).to_bytes(4, "big")
    start[0x10] = 255
    for i, (character, kind, stocks, level) in enumerate(((2, 0, 4, 0), (8, 1, 4, 3), (0, 3, 0, 0), (0, 3, 0, 0))):
        for offset, value in ((0x65, character), (0x66, kind), (0x67, stocks), (0x74, level)):
            start[offset + 0x24*i] = value
    sizes = bytes([0x35, 7, 0x36, 0, len(start)-1, 0x39, 0, 6])
    ending = bytes([0x39, method, 255, *placements]) if end else b""
    return sizes + start + ending


class ReplayTests(unittest.TestCase):
    def test_actual_end_event_and_placements_determine_winner(self):
        result = summarize_raw(replay_fixture())
        self.assertEqual(result["outcome"], "game")
        self.assertEqual(result["winner_port"], 2)
        self.assertTrue(expected_settings(result["settings"]))

    def test_missing_end_and_no_contest_are_never_wins(self):
        for raw in (replay_fixture(end=False), replay_fixture(method=7)):
            self.assertIsNone(summarize_raw(raw)["winner_port"])
        self.assertEqual(summarize_raw(replay_fixture(end=False))["outcome"], "unknown")

    def test_tied_or_missing_placements_remain_unknown(self):
        for positions in ((0, 0, 255, 255), (255, 255, 255, 255)):
            self.assertIsNone(summarize_raw(replay_fixture(placements=positions))["winner_port"])

    def test_truncation_and_unknown_events_are_rejected(self):
        for raw in (replay_fixture()[:-1], b"\x35", b"\x35\x02", b"\xff"):
            with self.assertRaises(ValueError):
                summarize_raw(raw)

    def test_wrong_level_or_rules_fail_readback(self):
        for key, value in (("game_mode", 0), ("items", 2), ("timer_seconds", 120), ("stage_id", 32), ("teams", True)):
            settings = summarize_raw(replay_fixture())["settings"]
            settings[key] = value
            self.assertFalse(expected_settings(settings))
        settings = summarize_raw(replay_fixture())["settings"]
        settings["players"][1]["cpu_level"] = 9
        self.assertFalse(expected_settings(settings))


class OwnershipTests(unittest.TestCase):
    def test_emulator_grace_allows_a_slow_owned_writer_to_finalize_before_kill(self):
        code = ("import signal,time; "
            "signal.signal(signal.SIGTERM, lambda *_: (time.sleep(3.2), print('finalized', flush=True), exit(0))); "
            "print('ready', flush=True); time.sleep(30)")
        child = subprocess.Popen([sys.executable, "-u", "-c", code], stdout=subprocess.PIPE)
        try:
            self.assertTrue(select.select([child.stdout], [], [], 5)[0])
            self.assertEqual(child.stdout.readline(), b"ready\n")
            terminate_child(child, grace_seconds=8)
            self.assertEqual(child.returncode, 0)
            self.assertEqual(child.stdout.read(), b"finalized\n")
        finally:
            terminate_child(child)
            child.stdout.close()

    def test_shutdown_grace_cannot_be_unbounded(self):
        for value in (0, 9, True, 1.5):
            with self.assertRaises(ValueError):
                terminate_child(None, grace_seconds=value)

    def test_runtime_certificate_requires_distinct_untampered_successful_runs(self):
        root = Path(tempfile.mkdtemp(prefix="jev-certificate-test-")).resolve()
        folder = root / "build/jev/runtime"
        folder.mkdir(parents=True)
        config = Config(runtime_sha256="a" * 64)
        probes = []
        for i in range(3):
            run_id = "match-" + str(i) * 32
            run = root / "build/jev/runs" / run_id
            run.mkdir(parents=True)
            content = json.dumps({"status": "probe_verified", "emulator_stopped": True}).encode()
            (run / "summary.json").write_bytes(content)
            (run / "launch.json").write_text(json.dumps({"runtime_sha256": config.runtime_sha256,
                                                            "disc_sha1": STOCK_DISC_SHA1}))
            probes.append({"run_id": run_id, "summary_sha256": hashlib.sha256(content).hexdigest()})
        certificate = folder / "certification.json"
        certificate.write_text(json.dumps({"runtime_sha256": config.runtime_sha256, "probes": probes}))
        self.assertEqual(runtime_evidence(root, config)["status"], "pass")
        (run / "summary.json").write_text('{}')
        self.assertEqual(runtime_evidence(root, config)["status"], "blocked")
        certificate.write_text(json.dumps({"runtime_sha256": config.runtime_sha256, "probes": [probes[0]] * 3}))
        self.assertEqual(runtime_evidence(root, config)["status"], "blocked")

    def test_shutdown_does_not_signal_unrelated_process(self):
        unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(20)"])
        owned = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(20)"])
        try:
            terminate_child(owned)
            self.assertIsNotNone(owned.poll())
            self.assertIsNone(unrelated.poll())
            terminate_child(owned)  # Already-reaped child cannot become a PID-only kill.
            self.assertIsNone(unrelated.poll())
        finally:
            terminate_child(unrelated)

    def test_emulator_environment_excludes_credentials(self):
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "secret", "OTHER_SECRET": "secret", "UV_ENV_FILE": "private"}):
            env = isolated_environment()
        self.assertNotIn("OPENROUTER_API_KEY", env)
        self.assertNotIn("OTHER_SECRET", env)
        self.assertNotIn("UV_ENV_FILE", env)

    def test_artifact_scan_ignores_fifos_and_symlinks(self):
        root = Path(tempfile.mkdtemp(prefix="jev-budget-test-"))
        (root / "record").write_bytes(b"123")
        (root / "alias").symlink_to(root / "record")
        os.mkfifo(root / "pipe")
        self.assertEqual(artifact_bytes(root), 3)

    def test_invalid_run_ids_cannot_escape(self):
        for run_id in ("../other", "match-../../other", "match-" + "x" * 32):
            with self.assertRaises(ValueError):
                locate_run(Path.cwd(), run_id)

    def test_input_probe_requires_acknowledgement_and_movement(self):
        rows = [{"frame": f, "x": float(f), "main_x": 1.0} for f in range(3, 20)]
        rows += [{"frame": f, "x": float(-f), "main_x": 0.0} for f in range(43, 60)]
        rows += [{"frame": f, "x": 0., "main_x": 0.5} for f in range(75, 101)]
        self.assertTrue(probe_passed(rows))
        for row in rows:
            row["x"] = 0.
        self.assertFalse(probe_passed(rows))


if __name__ == "__main__":
    unittest.main()
