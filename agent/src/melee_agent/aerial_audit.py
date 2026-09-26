"""Raw-record evidence for the single aerial and matched landing calibration."""

from collections import Counter

from .aerial import AERIAL, GROUND_START, NAIR, NAIR_LANDING
from .engine import ACTION_PACKETS
from .raw_observation import combat_counters
from .stage import support_surface


def audit_aerial(name, report, rows, errors):
    evidence = {"short_hop_observed": False, "aerial_acknowledged": False, "completed": False,
        "lcancel_attempt_observed": False, "nair_landing_frames": None, "reduced_landing_lag": None}
    try:
        skill = report["skill"]
        if skill != rows[-1]["scenario"]["skill"]:
            errors["aerial_report_trace_mismatch"] += 1
        aerial = (skill.get("event") or {}).get("aerial") or (skill.get("active") or {}).get("aerial")
        if aerial is None:
            errors["aerial_report_missing"] += 1
            return evidence
        indexed = {row["frame"]: row for row in rows}
        def raw(frame):
            return indexed[frame]["raw_observation"]["players"]["1"]["raw_post"]
        def packet(frame):
            return indexed[frame]["control"]["packet"]
        jump, knee, release, takeoff = (aerial[key] for key in
            ("jump_press_frame", "knee_frame", "jump_release_frame", "takeoff_frame"))
        if takeoff is not None:
            evidence["short_hop_observed"] = (jump < knee <= release < takeoff and
                packet(jump) == ACTION_PACKETS["jump"].wire() and raw(knee)["action_id"] == 24 and
                raw(release)["action_id"] == 24 and
                not any(indexed[release]["input_provenance"]["observed"]["buttons"][button] for button in ("X", "Y")) and
                raw(takeoff)["action_id"] in (25, 26) and raw(takeoff)["airborne"] == 1 and
                raw(takeoff)["jumps"] == 1 and raw(takeoff)["speed_y_self"] > 0)
            if not evidence["short_hop_observed"]:
                errors["short_hop_not_observed"] += 1
        press, ack = aerial["attack_press_frame"], aerial["ack_frame"]
        if ack is not None:
            evidence["aerial_acknowledged"] = (evidence["short_hop_observed"] and
                press == takeoff and press < ack and packet(press) == ACTION_PACKETS["attack"].wire() and
                raw(ack)["action_id"] == NAIR and raw(ack)["airborne"] == 1)
            if not evidence["aerial_acknowledged"]:
                errors["aerial_motion_not_observed"] += 1
        attempt = aerial["lcancel_attempt_frame"]
        if attempt is not None:
            evidence["lcancel_attempt_observed"] = (AERIAL[name] and evidence["aerial_acknowledged"] and
                packet(attempt) == ACTION_PACKETS["shield"].wire() and raw(attempt)["action_id"] == NAIR and
                raw(attempt)["airborne"] == 1 and combat_counters(raw(attempt)) == (0, 0))
            if not evidence["lcancel_attempt_observed"]:
                errors["lcancel_attempt_not_observed"] += 1
        if report["result"]["status"] == "succeeded":
            landing, end = aerial["landing_frame"], aerial["end_frame"]
            evidence["completed"] = (evidence["aerial_acknowledged"] and aerial["status"] == "succeeded" and
                landing is not None and ack < landing <= end == rows[-1]["frame"] and
                all(raw(frame)["airborne"] == 0 and support_surface(raw(frame)["x"], raw(frame)["y"], True) == "ground"
                    for frame in range(landing, end+1)) and
                raw(end)["action_id"] in GROUND_START and packet(end) == ACTION_PACKETS["wait"].wire() and
                indexed[end]["control"]["observation"]["bot"]["details"]["input_neutral_derived"])
            if not evidence["completed"]:
                errors["aerial_completion_not_observed"] += 1
            if evidence["completed"]:
                landing_rows = [raw(frame) for frame in range(landing, end+1) if raw(frame)["action_id"] == NAIR_LANDING]
                measured = len(landing_rows)
                if measured != aerial["observed_nair_landing_frames"] or any(combat_counters(row) != (0, 0) for row in landing_rows):
                    errors["aerial_landing_duration_mismatch"] += 1
                elif measured and raw(landing)["action_id"] == NAIR_LANDING:
                    evidence["nair_landing_frames"] = measured
        if aerial["reduced_landing_lag"] is not None:
            errors["uncalibrated_lcancel_success_claim"] += 1
    except (KeyError, TypeError, ValueError):
        errors["aerial_evidence_unavailable"] += 1
    return evidence


def aerial_acceptance(results, repeats):
    groups = {}
    for name in AERIAL:
        for direction in ("left", "right"):
            scenario = name+"-"+direction
            trials = [row for row in results if row["scenario"] == scenario]
            audited = [row for row in trials if row["status"] == "pass"]
            completed = sum(row.get("aerial", {}).get("completed", False) for row in audited)
            durations = [row["aerial"]["nair_landing_frames"] for row in audited
                if row.get("aerial", {}).get("nair_landing_frames") is not None]
            groups[scenario] = {"trials": len(trials), "completed": completed,
                "motion_acknowledged": sum(row.get("aerial", {}).get("aerial_acknowledged", False) for row in audited),
                "lcancel_attempts": sum(row.get("aerial", {}).get("lcancel_attempt_observed", False) for row in audited),
                "landing_duration_counts": dict(Counter(durations)),
                "passed": repeats == 20 and len(trials) == 20 and completed == 20}
    calibration = {}
    for direction in ("left", "right"):
        attempt, control = (groups[name+"-"+direction] for name in AERIAL)
        shortened, ordinary = attempt["landing_duration_counts"], control["landing_duration_counts"]
        valid = (attempt["passed"] and control["passed"] and attempt["lcancel_attempts"] == 20 and
            control["lcancel_attempts"] == 0 and sum(shortened.values()) == 20 and sum(ordinary.values()) == 20 and
            len(shortened) == 1 and len(ordinary) == 1 and next(iter(shortened)) < next(iter(ordinary)))
        calibration[direction] = {"reduced_landing_lag_observed": bool(valid),
            "attempt_duration_counts": shortened, "control_duration_counts": ordinary,
            "scope": "Independent fresh matches in a declared mirrored setup; game RNG is not seeded."}
    return {"passed": all(row["passed"] for row in groups.values()), "scenarios": groups,
        "landing_calibration": calibration,
        "required": "20 audited aerial starts and neutral grounded completions per declared setup/direction. Reduced landing lag is only claimed separately when all matched attempt/control durations support it."}
