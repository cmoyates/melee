from collections import Counter
from copy import deepcopy
from dataclasses import asdict
import unittest

from melee_agent.aerial import ShortHopAerial
from melee_agent.aerial_audit import audit_aerial, aerial_acceptance
from melee_agent.engine import ACTION_PACKETS
from test_aerial import aerial_state


def recorded_aerial():
    skill = ShortHopAerial("sh_nair", 1, aerial_state())
    observations = [aerial_state(), aerial_state(1, 24, input_jump_held=True), aerial_state(2, 24),
        aerial_state(3, 25, y=3., airborne=True, self_velocity_y=2.5),
        aerial_state(4, 65, y=5., airborne=True, self_velocity_y=-1.),
        aerial_state(5, 65, y=3., airborne=True, self_velocity_y=-1.5),
        aerial_state(6, 65, y=1., airborne=True, self_velocity_y=-2.)] + [
        aerial_state(frame, 70) for frame in range(7, 14)] + [aerial_state(14)]
    rows = []
    previous = ACTION_PACKETS["wait"].wire()
    for observation in observations:
        a, d = observation.bot, observation.bot.details
        action = skill.step(observation)
        packet = ACTION_PACKETS[action].wire()
        raw = {"action_id": d.action_id, "x": a.x, "y": a.y, "airborne": int(not a.grounded),
            "jumps": a.jumps, "speed_y_self": d.self_velocity_y,
            "state_flags_2": 0, "state_flags_4": 0, "hitlag_raw": 0., "misc_as_raw": 0.,
            "available": {key: True for key in ("state_flags_2", "state_flags_4", "hitlag_raw", "misc_as_raw")}}
        rows.append({"frame": observation.frame, "raw_observation": {"players": {"1": {"raw_post": raw}}},
            "control": {"packet": packet, "observation": asdict(observation)},
            "input_provenance": {"observed": previous}})
        previous = packet
    trace = {"active": None, "event": {"aerial": skill.trace()}}
    report = {"skill": trace, "result": {"status": "succeeded"}}
    rows[-1]["scenario"] = {"skill": deepcopy(trace)}
    return report, rows


class AerialAuditTests(unittest.TestCase):
    def audit(self, report, rows):
        errors = Counter()
        result = audit_aerial("sh_nair", report, rows, errors)
        return result, errors

    def test_raw_release_and_attack_packet_are_required_for_acknowledgement(self):
        report, rows = recorded_aerial()
        result, errors = self.audit(report, rows)
        self.assertFalse(errors)
        self.assertTrue(result["short_hop_observed"])
        self.assertTrue(result["aerial_acknowledged"])
        rows[2]["input_provenance"]["observed"] = ACTION_PACKETS["jump"].wire()
        self.assertIn("short_hop_not_observed", self.audit(report, rows)[1])
        report, rows = recorded_aerial()
        rows[3]["control"]["packet"] = ACTION_PACKETS["right"].wire()
        self.assertIn("aerial_motion_not_observed", self.audit(report, rows)[1])

    def test_lcancel_input_and_measured_landing_duration_are_independent(self):
        report, rows = recorded_aerial()
        result, errors = self.audit(report, rows)
        self.assertFalse(errors)
        self.assertTrue(result["lcancel_attempt_observed"])
        self.assertEqual(result["nair_landing_frames"], 7)
        self.assertIsNone(result["reduced_landing_lag"])
        rows[5]["control"]["packet"] = ACTION_PACKETS["wait"].wire()
        self.assertIn("lcancel_attempt_not_observed", self.audit(report, rows)[1])
        report, rows = recorded_aerial()
        rows[8]["raw_observation"]["players"]["1"]["raw_post"]["action_id"] = 42
        self.assertIn("aerial_landing_duration_mismatch", self.audit(report, rows)[1])

    def test_forged_landing_success_and_reduced_lag_claim_are_rejected(self):
        report, rows = recorded_aerial()
        rows[-1]["raw_observation"]["players"]["1"]["raw_post"]["airborne"] = 1
        self.assertIn("aerial_completion_not_observed", self.audit(report, rows)[1])
        report, rows = recorded_aerial()
        report["skill"]["event"]["aerial"]["reduced_landing_lag"] = True
        rows[-1]["scenario"]["skill"] = deepcopy(report["skill"])
        self.assertIn("uncalibrated_lcancel_success_claim", self.audit(report, rows)[1])

    def test_calibration_requires_twenty_clean_attempt_and_control_trials_per_direction(self):
        rows = [{"scenario": name+"-"+direction, "status": "pass",
            "aerial": {"completed": True, "aerial_acknowledged": True,
                "lcancel_attempt_observed": name == "sh_nair", "nair_landing_frames": 7 if name == "sh_nair" else 15}}
            for name in ("sh_nair", "sh_nair_no_lcancel") for direction in ("left", "right") for _ in range(20)]
        result = aerial_acceptance(rows, 20)
        self.assertTrue(result["passed"])
        self.assertTrue(all(row["reduced_landing_lag_observed"] for row in result["landing_calibration"].values()))
        rows[-1]["aerial"]["nair_landing_frames"] = 7
        self.assertFalse(aerial_acceptance(rows, 20)["landing_calibration"]["right"]["reduced_landing_lag_observed"])
        rows[0].update(status="pass", aerial={})
        self.assertFalse(aerial_acceptance(rows, 20)["passed"])
