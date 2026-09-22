import json
from pathlib import Path
import tempfile
import unittest

from melee_agent.integrity import inspect_integrity


def capture_fixture():
    rows, summaries = [], []
    for episode in (1, 2):
        for frame in (-123, -122, 0, 1):
            stock = 3 if frame == 1 else 4
            rows.append({"schema_version": 4, "run_id": "fixture", "monotonic": len(rows),
                "menu": "IN_GAME", "episode": episode, "frame": frame,
                "control": {"observation": {"episode": episode, "frame": frame, "observed_ns": len(rows)},
                            "packet": {"main": [1., .5] if frame >= 0 else [.5, .5]}},
                "raw_observation": {"players": {"1": {
                    "raw_post": {"frame": frame, "port": 1, "stocks": stock,
                        "action_frame_raw": 0., "x": float(frame), "y": 0.},
                    "action_frame_libmelee": 1, "action_frame_adjustment": 1,
                    "life_generation_derived": 5 - stock, "grounded_libmelee": frame != 1}}},
                "input_provenance": {"latest_completed_flush": None,
                    "observed": {"main": [1., .5] if frame == 1 else [.5, .5]}}})
        summaries.append({"episode": episode, "first_frame": -123, "last_frame": 1,
            "observations": 4, "gaps": 121, "duplicates": 0, "rollbacks": 0})
    return rows, {"status": "captured", "elapsed_seconds": 600., "episodes": summaries,
                    "recorder": {"written": 8, "unwritten": 0}}


class IntegrityTests(unittest.TestCase):
    def inspect(self, rows, summary, tail=b""):
        run = Path(tempfile.mkdtemp(prefix="jev-integrity-"))
        (run / "launch.json").write_text(json.dumps({"run_id": "fixture", "policy": "input-probe"}))
        (run / "summary.json").write_text(json.dumps(summary))
        (run / "frames.jsonl").write_bytes(b"".join((json.dumps(r) + "\n").encode() for r in rows) + tail)
        return inspect_integrity(run)

    def test_countdowns_resets_explicit_gaps_and_stock_generation_are_accounted(self):
        result = self.inspect(*capture_fixture())
        self.assertEqual(result["status"], "pass")
        self.assertTrue(all(e["span_accounted"] for e in result["episodes"]))
        self.assertEqual([e["negative_frames"] for e in result["episodes"]], [2, 2])
        self.assertEqual([e["life_generations"]["1"] for e in result["episodes"]], [2, 2])
        self.assertEqual([t["lag_frames"] for t in result["input_probe_transitions"]], [1, 1])

    def test_dropped_record_and_worker_accounting_disagreement_fail(self):
        rows, summary = capture_fixture()
        result = self.inspect(rows[1:], summary)
        self.assertEqual(result["status"], "fail")
        self.assertIn("recorder_accounting", result["errors"])
        self.assertIn("worker_first_frame", result["errors"])

    def test_identity_clock_life_and_action_frame_corruption_are_visible(self):
        mutations = [lambda r: r.update(run_id="wrong"), lambda r: r.update(monotonic=-1),
            lambda r: r["raw_observation"]["players"]["1"].update(life_generation_derived=20),
            lambda r: r["raw_observation"]["players"]["1"].update(action_frame_libmelee=2)]
        for mutate in mutations:
            rows, summary = capture_fixture()
            mutate(rows[1])
            self.assertEqual(self.inspect(rows, summary)["status"], "fail")

    def test_truncated_tail_and_old_schema_are_rejected(self):
        rows, summary = capture_fixture()
        with self.assertRaisesRegex(ValueError, "truncated"):
            self.inspect(rows, summary, tail=b'{"frame":')
        rows[0]["schema_version"] = 3
        with self.assertRaisesRegex(ValueError, "schema 4"):
            self.inspect(rows, summary)


if __name__ == "__main__":
    unittest.main()
