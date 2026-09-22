"""Check reported skill successes against independent raw/observed trace fields."""

import json

from .skill_check import verified_report


def inspect_skills(run):
    summary = json.loads((run / "summary.json").read_text())
    report = summary["skill_check"]
    if not verified_report(report, report["repeats"]):
        raise ValueError("Skill report is incomplete or inconsistent")
    successes = [t for t in report["trials"] if t["status"] == "succeeded"]
    wanted = set()
    for trial in successes:
        for frame in (trial["source_frame"], trial["source_frame"] + 1, trial["ack_frame"], trial["frame"]):
            wanted.add((trial["episode"], frame))
        if trial["jumpsquat_observed_frames"] is not None:
            wanted.add((trial["episode"], trial["ack_frame"] - trial["jumpsquat_observed_frames"]))
    rows = {}
    with (run / "frames.jsonl").open("rb") as handle:
        while line := handle.readline(65537):
            if len(line) > 65536 or not line.endswith(b"\n"):
                raise ValueError("Invalid trace record length")
            row = json.loads(line)
            key = (row.get("episode"), row["frame"])
            if row["menu"] == "IN_GAME" and key in wanted:
                if key in rows:
                    raise ValueError("Duplicate skill evidence frame")
                rows[key] = row
    errors = []
    for trial in successes:
        try:
            episode = trial["episode"]
            source = rows[episode, trial["source_frame"]]
            first = rows[episode, trial["source_frame"] + 1]
            ack = rows[episode, trial["ack_frame"]]
            end = rows[episode, trial["frame"]]
            raw = ack["raw_observation"]["players"]["1"]["raw_post"]
            old = source["raw_observation"]["players"]["1"]["raw_post"]
            observed = end["input_provenance"]["observed"]
            if (any(observed["buttons"].values()) or max(observed["l"], observed["r"]) > .025 or
                    any(abs(v - .5) > .025 for key in ("main", "c") for v in observed[key])):
                raise ValueError("release_not_observed")
            packet = first["control"]["packet"]
            skill, direction = trial["skill"], trial["direction"]
            if skill == "move":
                if (raw["airborne"] or (raw["x"] - old["x"]) * direction < 6 or
                        raw["speed_ground_x_self"] * direction <= 0 or packet["main"][0] != (1 if direction > 0 else 0)):
                    raise ValueError("movement_not_observed")
            elif skill == "jump":
                knee = rows[episode, trial["ack_frame"] - trial["jumpsquat_observed_frames"]]
                if (not packet["buttons"]["X"] or not raw["airborne"] or raw["action_id"] not in (25,26,27,28) or
                        raw["speed_y_self"] <= 0 or knee["raw_observation"]["players"]["1"]["raw_post"]["action_id"] != 24):
                    raise ValueError("jump_not_observed")
            elif skill == "shield":
                if (raw["action_id"] != 179 or not ack["input_provenance"]["observed"]["buttons"]["L"] or
                        not packet["buttons"]["L"] or trial["frame"] - trial["ack_frame"] < 9):
                    raise ValueError("shield_not_observed")
        except (KeyError, TypeError, ValueError) as error:
            errors.append({"attempt": trial["attempt"], "error_type": type(error).__name__})
    return {"schema_version": 1, "run_id": summary["run_id"], "status": "pass" if not errors else "fail",
            "observed_successes_checked": len(successes), "errors": errors,
            "groups": report["groups"], "jump_squat_lengths": sorted({t["jumpsquat_observed_frames"]
                for t in successes if t["skill"] == "jump"})}
