from collections import Counter
from copy import deepcopy
from dataclasses import asdict
import unittest

from melee_agent.engine import ACTION_PACKETS
from melee_agent.scenario_runner import audit_combat, combat_acceptance
from melee_agent.scenarios import find_scenario, find_suite
from test_combat_integration import ground


def evidence(name="jab"):
    motion, action = {"jab": (44, "attack"), "grab": (212, "grab")}[name]
    rows = []
    for frame in range(4):
        observation = ground(frame, motion if frame in (1, 2) else 14)
        players = {}
        for port, fighter in (("1", observation.bot), ("2", observation.opponent)):
            players[port] = {"raw_post": {"action_id": fighter.details.action_id, "x": fighter.x,
                "y": fighter.y, "airborne": 0, "percent": 0., "hurtbox_state": 0,
                "state_flags_2": 0, "state_flags_4": 0, "hitlag_raw": 0., "misc_as_raw": 0.,
                "available": {key: True for key in ("hurtbox_state", "state_flags_2", "state_flags_4", "hitlag_raw", "misc_as_raw")}}}
        label = action if frame == 0 else "wait"
        rows.append({"frame": frame, "raw_observation": {"players": players},
            "control": {"decision": {"action": label}, "packet": ACTION_PACKETS[label].wire(),
                "observation": asdict(observation)}})
    combat = {"press_frame": 0, "ack_frame": 1, "end_frame": 3, "status": "succeeded",
        "contact_frames": [], "shield_contact_frames": [], "capture_frame": None}
    skill = {"event": {"combat": combat}, "active": None}
    rows[-1]["scenario"] = {"skill": deepcopy(skill)}
    return {"skill": skill, "result": {"status": "succeeded"}}, rows


class CombatAuditTests(unittest.TestCase):
    def audit(self, name, report, rows):
        errors = Counter()
        result = audit_combat(find_scenario(name+"-right"), report, rows, errors)
        return result, errors

    def test_motion_label_does_not_replace_actual_press_packet(self):
        report, rows = evidence()
        self.assertFalse(self.audit("jab", report, rows)[1])
        rows[0]["control"]["packet"] = ACTION_PACKETS["wait"].wire()
        result, errors = self.audit("jab", report, rows)
        self.assertFalse(result["motion_acknowledged"])
        self.assertIn("combat_motion_not_observed", errors)

    def test_claimed_capture_requires_both_native_fighter_states(self):
        report, rows = evidence("grab")
        report["skill"]["event"]["combat"]["capture_frame"] = 2
        rows[-1]["scenario"]["skill"] = deepcopy(report["skill"])
        self.assertIn("combat_capture_not_observed", self.audit("grab", report, rows)[1])
        rows[2]["raw_observation"]["players"]["1"]["raw_post"]["action_id"] = 216
        rows[2]["raw_observation"]["players"]["2"]["raw_post"]["action_id"] = 223
        result, errors = self.audit("grab", report, rows)
        self.assertFalse(errors)
        self.assertTrue(result["capture_observed"])
        rows[2]["raw_observation"]["players"]["2"]["raw_post"]["action_id"] = 14
        self.assertIn("combat_capture_not_observed", self.audit("grab", report, rows)[1])

    def test_contact_claim_needs_percent_change_paired_hitlag_and_vulnerability(self):
        report, rows = evidence()
        report["skill"]["event"]["combat"]["contact_frames"] = [2]
        rows[-1]["scenario"]["skill"] = deepcopy(report["skill"])
        self.assertIn("combat_contact_not_observed", self.audit("jab", report, rows)[1])
        for port in ("1", "2"):
            rows[2]["raw_observation"]["players"][port]["raw_post"].update(state_flags_2=32, hitlag_raw=3.)
        victim = rows[2]["raw_observation"]["players"]["2"]["raw_post"]
        victim["percent"] = 3.
        self.assertFalse(self.audit("jab", report, rows)[1])
        victim["hurtbox_state"] = 2
        self.assertIn("combat_contact_not_observed", self.audit("jab", report, rows)[1])

    def test_acceptance_keeps_setup_failures_and_capture_distinction(self):
        trials = [{"scenario": spec.name, "status": "pass", "trial_status": "succeeded",
            "combat": {"motion_acknowledged": True, "completed": True,
                "capture_observed": spec.kind == "combat_grab", "contact_events": 0}}
            for spec in find_suite("ground-combat-v1") for _ in range(20)]
        self.assertTrue(combat_acceptance(trials, 20)["passed"])
        self.assertFalse(combat_acceptance(trials, 1)["passed"])
        failed = deepcopy(trials)
        failed[0].update(trial_status="setup_failed", combat={})
        self.assertFalse(combat_acceptance(failed, 20)["passed"])
        for row in trials:
            row["combat"]["capture_observed"] = False
        self.assertFalse(combat_acceptance(trials, 20)["passed"])

    def test_missing_claimed_acknowledgement_fails_even_when_interrupted(self):
        report, rows = evidence()
        report['result']['status'] = 'skill_failed'
        report['skill']['event']['combat']['ack_frame'] = 99
        rows[-1]['scenario']['skill'] = deepcopy(report['skill'])
        result, errors = self.audit('jab', report, rows)
        self.assertFalse(result['motion_acknowledged'])
        self.assertIn('combat_acknowledgement_frame_missing', errors)

    def test_duplicate_contacts_cannot_inflate_evidence_counts(self):
        report, rows = evidence()
        report['skill']['event']['combat']['contact_frames'] = [2, 2]
        rows[-1]['scenario']['skill'] = deepcopy(report['skill'])
        result, errors = self.audit('jab', report, rows)
        self.assertEqual(result['contact_events'], 0)
        self.assertIn('combat_contact_frame_order', errors)
