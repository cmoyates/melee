"""Exercise failure reports and ownership through the real supervisor boundary."""

from contextlib import ExitStack, redirect_stdout
import errno
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from melee_agent.config import Config, Limits
from melee_agent import matches


class SupervisorTests(unittest.TestCase):
    def exercise(self, *, worker_text=None, start_error=False, scan_error=False,
                summary_error=False, artifact_limit=False, fake_replay=False):
        root = Path(tempfile.mkdtemp(prefix="jev-supervisor-test-")).resolve()
        config = Config(slippi_port=0, limits=Limits(max_artifact_bytes=1 if artifact_limit else 1_000_000))
        children = []
        real_popen = subprocess.Popen
        real_write = matches.write_json
        output = io.StringIO()

        def spawn(command, **kwargs):
            if len(command) > 3 and command[3] == "melee_agent.match_worker":
                run = Path(command[-1])
                (run / "ready.json").write_text('{}')
                if worker_text is not None:
                    (run / "worker-result.json").write_text(worker_text)
                if fake_replay:
                    (run / "replays/a.slp").write_bytes(b"fixture")
                delay = 0.2 if worker_text is not None else 10
                child = real_popen([sys.executable, "-c", f"import time; time.sleep({delay})"], **kwargs)
            else:
                if start_error:
                    raise OSError(errno.ENOEXEC, "private runtime path")
                child = real_popen([sys.executable, "-c", "import time; time.sleep(10)"], **kwargs)
            children.append(child)
            return child

        def write(path, value):
            if path.name == "summary.json" and summary_error:
                raise OSError(errno.ENOSPC, "private artifact path")
            return real_write(path, value)

        unrelated = real_popen([sys.executable, "-c", "import time; time.sleep(10)"])
        try:
            with ExitStack() as stack:
                stack.enter_context(patch.object(matches, "preflight", return_value=(config, Path("fixture"), Path("disc"))))
                stack.enter_context(patch.object(matches.subprocess, "run", return_value=subprocess.CompletedProcess([], 1)))
                stack.enter_context(patch.object(matches.subprocess, "Popen", side_effect=spawn))
                stack.enter_context(patch.object(matches.select, "select", return_value=([], [], [])))
                stack.enter_context(patch("socket.socket"))  # Port availability belongs to doctor coverage.
                stack.enter_context(patch.object(matches, "write_json", side_effect=write))
                if scan_error:
                    stack.enter_context(patch.object(matches, "artifact_bytes", side_effect=PermissionError("private path")))
                if fake_replay:
                    stack.enter_context(patch("melee_agent.replay.summarize_file", return_value={"outcome": "game", "settings": {}}))
                    stack.enter_context(patch("melee_agent.replay.expected_settings", return_value=True))
                with redirect_stdout(output):
                    code = matches.supervise(root, 2, 1, "smoke")
            summary = json.loads(output.getvalue().splitlines()[-1])
            self.assertTrue(all(child.poll() is not None for child in children))
            self.assertIsNone(unrelated.poll())
            self.assertNotIn("private", output.getvalue())
            self.assertTrue(summary["worker_stopped"])
            self.assertTrue(summary["emulator_stopped"])
            return code, summary
        finally:
            for child in [*children, unrelated]:
                matches.terminate_child(child)

    def test_emulator_launch_failure_reaps_worker_and_reports_error(self):
        code, summary = self.exercise(start_error=True)
        self.assertEqual(code, 2)
        self.assertEqual(summary["reason"], "supervisor_error")
        self.assertEqual(summary["supervisor_error_type"], "OSError")

    def test_artifact_scan_failure_reaps_both_children(self):
        code, summary = self.exercise(scan_error=True)
        self.assertEqual(code, 2)
        self.assertEqual(summary["supervisor_error_type"], "PermissionError")

    def test_artifact_budget_stops_owned_processes(self):
        code, summary = self.exercise(artifact_limit=True)
        self.assertEqual(code, 2)
        self.assertEqual(summary["reason"], "artifact_limit")

    def test_partial_and_wrong_shape_worker_results_are_incomplete(self):
        for value in ('{"episodes":', '[]', '{"episodes": [], "neutralized": 1}', '{}'):
            with self.subTest(value=value):
                code, summary = self.exercise(worker_text=value)
                self.assertEqual(code, 2)
                self.assertEqual(summary["reason"], "worker_result_invalid")

    def test_worker_success_without_verified_episode_is_incomplete(self):
        for episodes in ([], [{}], [{"result_event_verified": False}]):
            code, summary = self.exercise(worker_text=json.dumps({"episodes": episodes,
                "neutralized": True, "status": "matches_complete"}), fake_replay=True)
            self.assertEqual(code, 2)
            self.assertEqual(summary["status"], "incomplete")

    def test_full_disk_keeps_incomplete_report_on_stdout(self):
        code, summary = self.exercise(start_error=True, summary_error=True)
        self.assertEqual(code, 2)
        self.assertEqual(summary["reason"], "summary_write_failed")
        self.assertEqual(summary["prior_reason"], "supervisor_error")

    def test_malformed_probe_cannot_escape_completion_report(self):
        code, summary = self.exercise(worker_text=json.dumps({"episodes": [],
            "neutralized": True, "status": "probe_complete", "probe_samples": [None]}))
        self.assertEqual(code, 2)
        self.assertEqual(summary["reason"], "worker_result_invalid")

    def test_verified_episode_and_replay_complete_only_after_neutralization(self):
        for neutralized in (True, False):
            code, summary = self.exercise(worker_text=json.dumps({"episodes": [{"result_event_verified": True}],
                "neutralized": neutralized, "status": "matches_complete"}), fake_replay=True)
            self.assertEqual(code, 0 if neutralized else 2)
            self.assertEqual(summary["status"], "complete" if neutralized else "incomplete")


if __name__ == "__main__":
    unittest.main()
