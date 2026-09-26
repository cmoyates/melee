"""Independent raw evidence shared by scenario and asynchronous combat audits."""

from .engine import ACTION_PACKETS
from .ground_combat import COMBAT, START_ACTIONS, CAPTOR, CAPTURED, GUARD
from .raw_observation import combat_counters, normalized_hurtbox
from .stage import support_surface


def audit_combat_trace(name, combat, rows, errors, *, completed):
    expected_motion = COMBAT[name]["motion"]
    evidence = {"motion_acknowledged": False, "completed": False, "contact_events": 0, "capture_observed": False}
    try:
        if combat is None:
            errors["combat_report_missing"] += 1
            return evidence
        indexed = {row["frame"]: row for row in rows}
        press = indexed.get(combat["press_frame"])
        ack = indexed.get(combat["ack_frame"])
        if ack is not None:
            evidence["motion_acknowledged"] = (press is not None and combat["press_frame"] < combat["ack_frame"] and
                press["control"]["decision"]["action"] == COMBAT[name]["action"] and
                press["control"]["packet"] == ACTION_PACKETS[COMBAT[name]["action"]].wire() and
                ack["raw_observation"]["players"]["1"]["raw_post"]["action_id"] == expected_motion)
            if not evidence["motion_acknowledged"]:
                errors["combat_motion_not_observed"] += 1
        elif combat["ack_frame"] is not None:
            errors["combat_acknowledgement_frame_missing"] += 1
        for key in ("contact_frames", "shield_contact_frames"):
            values = combat[key]
            if any(type(value) is not int for value in values) or values != sorted(set(values)):
                errors["combat_contact_frame_order"] += 1
                return evidence
        for frame in combat["contact_frames"]:
            row, prior = indexed[frame], indexed[frame-1]
            a, b = (row["raw_observation"]["players"][port]["raw_post"] for port in ("1", "2"))
            previous = prior["raw_observation"]["players"]["2"]["raw_post"]
            valid = (name != "grab" and evidence["motion_acknowledged"] and a["action_id"] == expected_motion and
                combat_counters(a)[0] > 0 and combat_counters(b)[0] > 0 and b["percent"] > previous["percent"] and
                normalized_hurtbox(b) == 0 and b["action_id"] not in GUARD)
            if not valid:
                errors["combat_contact_not_observed"] += 1
            evidence["contact_events"] += int(valid)
        for frame in combat["shield_contact_frames"]:
            row = indexed[frame]
            a, b = (row["raw_observation"]["players"][port]["raw_post"] for port in ("1", "2"))
            if not combat_counters(a)[0] or b["action_id"] not in (179, 181):
                errors["combat_shield_contact_not_observed"] += 1
        if combat["capture_frame"] is not None:
            row = indexed[combat["capture_frame"]]
            a, b = (row["raw_observation"]["players"][port]["raw_post"] for port in ("1", "2"))
            evidence["capture_observed"] = (name == "grab" and evidence["motion_acknowledged"] and
                a["action_id"] in CAPTOR and b["action_id"] in CAPTURED)
            if not evidence["capture_observed"]:
                errors["combat_capture_not_observed"] += 1
        if completed:
            end = rows[-1]
            a = end["raw_observation"]["players"]["1"]["raw_post"]
            evidence["completed"] = (evidence["motion_acknowledged"] and combat["status"] == "succeeded" and
                combat["end_frame"] == end["frame"] and a["action_id"] in START_ACTIONS and not a["airborne"] and
                support_surface(a["x"], a["y"], True) in ("ground", "left", "right", "top") and
                end["control"]["observation"]["bot"]["details"]["input_neutral_derived"] and
                end["control"]["decision"]["action"] == "wait")
            if not evidence["completed"]:
                errors["combat_completion_not_observed"] += 1
    except (KeyError, TypeError, ValueError, IndexError):
        errors["combat_evidence_unavailable"] += 1
    return evidence
