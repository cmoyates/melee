from dataclasses import asdict
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from melee_agent.engine import ACTION_PACKETS, Decision
from melee_agent.scenario_runner import inspect_scenario, run_suite
from melee_agent.scenarios import find_scenario, suite_hash
from test_scenarios import position


class ScenarioAuditTests(unittest.TestCase):
    def setUp(self):
        self.run = Path(tempfile.mkdtemp(prefix="jev-scenario-audit-"))
        self.rows = []
        for frame in (-1, 0, 1, 2):
            observation = position(frame, x=-28. if frame == 2 else -35.)
            action = "right" if frame in (0, 1) else "wait"
            raw = {}
            for port, fighter in (("1", observation.bot), ("2", observation.opponent)):
                raw[port] = {"raw_post": {"x": fighter.x, "y": fighter.y, "airborne": int(not fighter.grounded),
                    "jumps": fighter.jumps, "action_id": fighter.details.action_id, "stocks": fighter.stocks_remaining,
                    "percent": fighter.details.percent, "facing": 1 if fighter.details.facing_right else -1,
                    "hurtbox_state": fighter.details.hurtbox_state, "available": {"hurtbox_state": True},
                    "speed_y_self": fighter.details.self_velocity_y, "speed_ground_x_self": fighter.details.self_velocity_x,
                    "speed_air_x_self": fighter.details.self_velocity_x}}
            self.rows.append({"menu": "IN_GAME", "frame": frame, "control": {"observation": asdict(observation),
                "decision": asdict(Decision(1, 1, frame, action)), "packet": ACTION_PACKETS[action].wire()},
                "scenario": {"input_owner": "setup" if frame < 0 else "neutral" if frame == 2 else "measured"},
                "raw_observation": {"players": raw}, "input_provenance": {"observed": ACTION_PACKETS["wait"].wire()}})
        spec = find_scenario("grounded-left")
        self.summary = {"status": "scenario_recorded", "provider_contacted": False, "neutralized": True,
            "worker_stopped": True, "emulator_stopped": True, "state_receiver": {"stopped": True},
            "replay_errors": [], "replays": [{"settings": {"game_mode": 1, "stage_id": 31, "teams": False,
                "timer_seconds": 480, "items": 255, "players": [
                    {"character_external": 2, "type": 0, "stocks": 4},
                    {"character_external": 8, "type": 1, "stocks": 4, "cpu_level": 3}, {"type": 3}, {"type": 3}]}}],
            "scenario": {"complete": True, "scenario": spec.manifest(), "suite_sha256": suite_hash(),
                "setup_privilege": "ordinary_controller_packets_only", "measurement_start_frame": 0,
                "setup_stopped_frame": -1, "initial_observation": self.rows[1]["control"]["observation"],
                "result": {"status": "succeeded", "reason": "skill:succeeded", "end_episode": 1, "end_frame": 2,
                    "end_observation": self.rows[-1]["control"]["observation"], "measured_frames": 3}}}
        (self.run / "launch.json").write_text(json.dumps({"scenario_name": spec.name, "run_id": "synthetic"}))

    def audit(self):
        (self.run / "summary.json").write_text(json.dumps(self.summary))
        (self.run / "frames.jsonl").write_text("".join(json.dumps(row)+"\n" for row in self.rows))
        with patch("melee_agent.scenario_runner.inspect_integrity", return_value={"status": "pass", "game_records": 4}):
            return inspect_scenario(self.run)

    def test_success_needs_raw_movement_and_a_released_setup_boundary(self):
        self.assertEqual(self.audit()["status"], "pass")
        self.rows[0]["control"]["decision"]["action"] = "left"
        self.assertIn("setup_release_not_observed", self.audit()["errors"])

    def test_matching_report_does_not_hide_changed_raw_position(self):
        self.rows[1]["raw_observation"]["players"]["1"]["raw_post"]["x"] = -42.
        self.assertIn("observation_raw_mismatch", self.audit()["errors"])

    def test_setup_inputs_cannot_continue_during_measured_play(self):
        self.rows[2]["scenario"]["input_owner"] = "setup"
        self.assertIn("setup_input_after_measurement", self.audit()["errors"])

    def test_wrong_replay_settings_and_missing_cleanup_are_not_success(self):
        self.summary["replays"][0]["settings"]["stage_id"] = 32
        self.assertIn("run_or_cleanup_invalid", self.audit()["errors"])
        self.summary["replays"][0]["settings"]["stage_id"] = 31
        self.summary["state_receiver"]["stopped"] = False
        self.assertIn("run_or_cleanup_invalid", self.audit()["errors"])

    def test_success_label_without_displacement_is_rejected(self):
        end = self.rows[-1]
        end["control"]["observation"]["bot"]["x"] = -35.
        end["raw_observation"]["players"]["1"]["raw_post"]["x"] = -35.
        self.assertIn("movement_or_release_not_observed", self.audit()["errors"])

    def test_invalid_schedule_bounds_are_rejected_before_configuration_or_processes(self):
        for options in ({"repeats": 0}, {"repeats": 21}, {"duration": 3601}, {"seed": -1}):
            with patch("subprocess.Popen", side_effect=AssertionError("process forbidden")):
                with self.assertRaises(ValueError):
                    run_suite(self.run, **options)


if __name__ == "__main__":
    unittest.main()
