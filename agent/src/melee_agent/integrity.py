"""Streaming, read-only audit of retained frame capture and input transitions."""

import hashlib
import json
import math


def inspect_integrity(run):
    launch = json.loads((run / "launch.json").read_text())
    summary = json.loads((run / "summary.json").read_text())
    declared_segments = {segment.get('episode'):segment for segment in summary['episodes']}
    digest = hashlib.sha256()
    episodes, counts, errors, transitions = {}, {"records": 0, "game_records": 0}, {}, []
    previous_time = -1
    pending_transition = None
    command_main = None
    current_episode = None

    def error(name):
        errors[name] = errors.get(name, 0) + 1

    with (run / "frames.jsonl").open("rb") as handle:
        while line := handle.readline(65537):
            if len(line) > 65536 or not line.endswith(b"\n"):
                raise ValueError("Oversized or truncated frame record")
            digest.update(line)
            counts["records"] += 1
            record = json.loads(line)
            if record.get("run_id") != launch["run_id"]:
                error("wrong_run")
            timestamp = record["monotonic"]
            if not math.isfinite(timestamp) or timestamp < previous_time:
                error("monotonic_rollback")
            previous_time = timestamp
            if record["menu"] != "IN_GAME":
                continue
            counts["game_records"] += 1
            if record["schema_version"] != 4:
                raise ValueError("Capture integrity requires frame schema 4")
            episode, frame = record["episode"], record["frame"]
            if current_episode != episode:
                if current_episode is not None and episode != current_episode + 1:
                    error("episode_order")
                current_episode = episode
                command_main = pending_transition = None
            item = episodes.setdefault(episode, {"episode": episode, "first_frame": frame,
                "last_frame": frame - 1, "observations": 0, "gaps": 0, "duplicates": 0,
                "rollbacks": 0, "negative_frames": 0, "stocks": {}, "grounded_transitions": {},
                "life_generations": {}, "stock_losses": {}, "positions": {}})
            delta = frame - item["last_frame"]
            item["gaps"] += max(0, delta - 1)
            item["duplicates"] += int(delta == 0)
            item["rollbacks"] += int(delta < 0)
            item["last_frame"] = frame
            item["observations"] += 1
            item["negative_frames"] += int(frame < 0)
            observation = record["control"]["observation"]
            if (observation["episode"], observation["frame"]) != (episode, frame):
                error("control_identity")
            if observation.get('schema_version') == 5:
                segment = declared_segments.get(episode,{})
                if not segment:
                    error('missing_declared_segment')
                sudden = segment.get('phase') == 'sudden_death'
                progress = observation['match']
                if (progress['starting_stocks'] != (1 if sudden else 4) or
                        progress['time_limit_seconds'] != (None if sudden else 480) or
                        (sudden and progress['remaining_seconds_derived'] is not None)):
                    error('segment_progress_rules')
            for port, player in record["raw_observation"]["players"].items():
                raw = player["raw_post"]
                if (raw["frame"], raw["port"]) != (frame, int(port)):
                    error("raw_identity")
                if player["action_frame_libmelee"] != int(raw["action_frame_raw"]) + player["action_frame_adjustment"]:
                    error("action_frame_adjustment")
                stock = raw["stocks"]
                prior_stock = item["stocks"].get(port, stock)
                loss = prior_stock - stock
                if loss < 0:
                    error("stock_increase")
                item["stock_losses"][port] = item["stock_losses"].get(port, 0) + max(0, loss)
                life = player["life_generation_derived"]
                if observation.get('schema_version') == 5:
                    fighter = observation['bot' if port == '1' else 'opponent']
                    if fighter['stocks_remaining'] != stock or fighter['details']['life_generation_derived'] != life:
                        error('normalized_stock_or_life_mismatch')
                if life != item["stock_losses"][port] + 1:
                    error("life_generation")
                item["stocks"][port] = stock
                item["life_generations"][port] = life
                ground = player["grounded_libmelee"]
                ground_state = item["grounded_transitions"].setdefault(port, {"last": ground, "changes": 0,
                    "grounded_frames": 0, "airborne_frames": 0})
                ground_state["changes"] += int(ground != ground_state["last"])
                ground_state["last"] = ground
                ground_state["grounded_frames" if ground else "airborne_frames"] += 1
                position = item["positions"].setdefault(port, {"min_x": raw["x"], "max_x": raw["x"],
                    "min_y": raw["y"], "max_y": raw["y"]})
                for axis in ("x", "y"):
                    position["min_" + axis] = min(position["min_" + axis], raw[axis])
                    position["max_" + axis] = max(position["max_" + axis], raw[axis])
            provenance = record["input_provenance"]
            observed = provenance["observed"]["main"]
            # Restrict lag measurement to held horizontal probe transitions.
            # This is a measured input-value transition, not a per-frame receipt.
            if launch["policy"] == "input-probe":
                if pending_transition and frame > pending_transition["source_frame"]:
                    desired = pending_transition["main"]
                    if all(abs(a - b) <= .025 for a, b in zip(desired, observed)):
                        transitions.append({**pending_transition, "observed_frame": frame,
                            "lag_frames": frame - pending_transition["source_frame"]})
                        pending_transition = None
                main = record["control"]["packet"]["main"]
                if command_main is not None and main != command_main:
                    pending_transition = {"episode": episode, "source_frame": frame, "main": main}
                command_main = main
            flushed = provenance["latest_completed_flush"]
            if flushed and not (flushed["queued_ns"] <= flushed["flush_started_ns"] <= flushed["flush_completed_ns"] <= observation["observed_ns"]):
                error("flush_time_order")
    recorder = summary.get("recorder", {})
    if recorder.get("written") != counts["records"] or recorder.get("unwritten") != 0:
        error("recorder_accounting")
    actual = list(episodes.values())
    reported = summary["episodes"]
    if len(actual) != len(reported):
        error("episode_count")
    for item, worker in zip(actual, reported):
        for key in ("episode", "first_frame", "last_frame", "observations", "gaps", "duplicates", "rollbacks"):
            if item[key] != worker[key]:
                error("worker_" + key)
        item["expected_frame_span"] = item["last_frame"] - item["first_frame"] + 1
        item["span_accounted"] = item["expected_frame_span"] == item["observations"] + item["gaps"] - item["duplicates"]
        if not item["span_accounted"]:
            error("unaccounted_span")
    if not counts["game_records"]:
        error("no_game_observations")
    return {"schema_version": 1, "run_id": launch["run_id"], "status": "pass" if not errors else "fail",
            **counts, "frames_sha256": digest.hexdigest(), "errors": errors,
            "episodes": actual, "input_probe_transitions": transitions,
            "run_status": summary["status"], "elapsed_seconds": summary["elapsed_seconds"]}
