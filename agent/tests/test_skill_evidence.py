import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from melee_agent.engine import Packet
from melee_agent.skill_evidence import inspect_skills


class SkillEvidenceTests(unittest.TestCase):
    def run_fixture(self, *, release=True, takeoff=True, squat=True):
        run = Path(tempfile.mkdtemp(prefix="jev-skill-evidence-"))
        trial = {"attempt": 1, "skill": "jump", "direction": 0, "status": "succeeded", "episode": 1,
                    "source_frame": 0, "ack_frame": 4, "frame": 5, "jumpsquat_observed_frames": 3}
        (run / "summary.json").write_text(json.dumps({"run_id": "fixture", "skill_check": {
            "repeats": 1, "trials": [trial], "groups": []}}))
        rows = []
        for frame in (0, 1, 4, 5):
            raw = {"action_id": 14 if frame == 0 else (24 if squat else 14) if frame == 1 else 25,
                    "airborne": int(frame >= 4 and takeoff), "speed_y_self": 2. if takeoff else 0., "x": 0.}
            observed = Packet(held=() if release or frame != 5 else ("X",)).wire()
            rows.append({"menu": "IN_GAME", "episode": 1, "frame": frame,
                "raw_observation": {"players": {"1": {"raw_post": raw}}},
                "input_provenance": {"observed": observed},
                "control": {"packet": Packet(held=("X",) if frame == 1 else ()).wire()}})
        (run / "frames.jsonl").write_text(''.join(json.dumps(r) + '\n' for r in rows))
        # Suite aggregate validation has its own adversarial tests; this checks
        # that the independent raw-motion proof does not trust a success label.
        with patch("melee_agent.skill_evidence.verified_report", return_value=True):
            return inspect_skills(run)

    def test_observed_squat_takeoff_and_release_validate(self):
        self.assertEqual(self.run_fixture()["status"], "pass")

    def test_success_label_cannot_hide_missing_release_or_motion(self):
        for change in ({"release": False}, {"takeoff": False}, {"squat": False}):
            self.assertEqual(self.run_fixture(**change)["status"], "fail")


if __name__ == "__main__":
    unittest.main()
