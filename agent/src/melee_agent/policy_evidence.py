"""Read-only decision audit against retained source and application observations."""

from collections import Counter, OrderedDict
import hashlib
import json
import math

from .engine import Observation
from .skills import can_start, relative_skill
from .stage import support_surface


def check_acknowledgement(trial, event, row, sources):
    """Require raw motion evidence and observed release for an accepted skill."""
    source = sources.get((trial["episode"], trial["frame"]))
    ack = sources.get((trial["episode"], event.get("ack_frame")))
    if source is None or ack is None or event.get("source_frame") != trial["frame"]:
        return False
    old_row, ack_row = source[2], ack[2]
    raw = ack_row["raw_observation"]["players"]["1"]["raw_post"]
    old = old_row["raw_observation"]["players"]["1"]["raw_post"]
    observed = row["input_provenance"]["observed"]
    if (any(observed["buttons"].values()) or max(observed["l"], observed["r"]) > .025 or
            any(abs(v-.5) > .025 for key in ("main", "c") for v in observed[key])):
        return False
    spec = trial["spec"]
    packet = old_row["control"]["packet"]
    if (event["skill"], event["direction"]) != (spec.name, spec.direction):
        return False
    if spec.name == "move":
        return (not raw["airborne"] and (raw["x"]-old["x"])*spec.direction >= 6 and
            raw["speed_ground_x_self"]*spec.direction > 0 and packet["main"][0] == (1 if spec.direction > 0 else 0))
    if spec.name == "jump":
        length = event["jumpsquat_observed_frames"]
        knee = sources.get((trial["episode"], event["ack_frame"]-length)) if type(length) is int else None
        return (knee is not None and knee[2]["raw_observation"]["players"]["1"]["raw_post"]["action_id"] == 24 and
            packet["buttons"]["X"] and raw["airborne"] and raw["action_id"] in (25,26,27,28) and raw["speed_y_self"] > 0)
    if spec.name == "shield":
        return (raw["action_id"] == 179 and ack_row["input_provenance"]["observed"]["buttons"]["L"] and
            packet["buttons"]["L"] and event["frame"]-event["ack_frame"] >= 9)
    return spec.name == "neutral"


def quantiles(values):
    if not values:
        return None
    values = sorted(values)
    return {"count": len(values), "p50": values[math.ceil(len(values)*.5)-1],
            "p95": values[math.ceil(len(values)*.95)-1], "p99": values[math.ceil(len(values)*.99)-1],
            "max": values[-1]}


def inspect_policy(run):
    summary = json.loads((run / "summary.json").read_text())
    launch = json.loads((run / "launch.json").read_text())
    errors, outcomes, faults = Counter(), Counter(), Counter()
    acknowledgements, input_owners = Counter(), Counter()
    pending_skills, consumed = {}, {}
    sources = OrderedDict()
    queued_ms, flushed_ms, delays_ms = [], [], []
    last_applied = 0
    highest_received = 0
    reordered = 0
    game_frames = 0
    digest = hashlib.sha256()
    with (run / "frames.jsonl").open("rb") as handle:
        while line := handle.readline(65537):
            if len(line) > 65536 or not line.endswith(b"\n"):
                raise ValueError("Invalid trace record length")
            digest.update(line)
            row = json.loads(line)
            if row["menu"] != "IN_GAME":
                continue
            game_frames += 1
            if game_frames > 1_000_000:
                raise ValueError("Trace audit frame limit")
            control = row["control"]
            observation = Observation.parse(control["observation"])
            skill = row.get("skill", {})
            sources[observation.episode, observation.frame] = (observation, skill, row)
            if len(sources) > 256:
                sources.popitem(last=False)
            queued_ms.append((control["queued_ns"]-observation.observed_ns)/1e6)
            flushed = row["input_provenance"]["latest_completed_flush"]
            if flushed:
                source = sources.get((flushed["episode"], flushed["source_frame"]))
                if source:
                    flushed_ms.append((flushed["flush_completed_ns"]-source[0].observed_ns)/1e6)
            events = skill.get("policy_events", [])
            input_owners[skill.get("input_owner", "unrecorded")] += 1
            if len(events) > 32:
                errors["unbounded_events"] += 1
            for event in events:
                delivery = event["delivery"]
                c, reply = delivery["expected"], delivery["reply"]
                candidates = delivery["candidates"]
                sequence = c["sequence"]
                consumed.setdefault(sequence, []).append(delivery)
                reordered += int(sequence < highest_received)
                highest_received = max(highest_received, sequence)
                delays_ms.append((reply["received_ns"]-c["observed_ns"])/1e6)
                faults[reply["fault"]] += 1
                accepted = event["accepted"]
                outcomes["accepted" if accepted else "rejected:" + str(event["reason"])] += 1
                if event["last_applied_before"] != last_applied:
                    errors["applied_sequence_accounting"] += 1
                if not accepted:
                    if not event["reason"]:
                        errors["missing_rejection_reason"] += 1
                    continue
                def check(condition, name):
                    if not condition:
                        errors[name] += 1
                check(c == reply["context"], "accepted_forged_context")
                check(c["run_id"] == launch["run_id"] == row["run_id"], "accepted_wrong_run")
                check(c["episode"] == observation.episode, "accepted_wrong_episode")
                check((c["bot_life"], c["opponent_life"]) ==
                    (observation.bot.details.life_generation_derived, observation.opponent.details.life_generation_derived),
                    "accepted_wrong_life")
                check(sequence > last_applied, "accepted_superseded")
                check(0 <= observation.frame-c["frame"] <= 60, "accepted_stale_frame")
                check(c["observed_ns"] <= reply["received_ns"] <= event["apply_ns"] <= control["queued_ns"] and
                    0 <= event["apply_ns"]-c["observed_ns"] <= 1_000_000_000, "accepted_stale_time")
                check(c["skill_generation"] == event["generation_before"], "accepted_wrong_generation")
                check(not event["committed_before"] and not event["emergency"], "accepted_during_commitment_or_emergency")
                check(reply["action"] in candidates, "accepted_invalid_candidate")
                actual_hash = hashlib.sha256(json.dumps(candidates, separators=(",", ":")).encode()).hexdigest()
                check(c["candidate_hash"] == actual_hash, "accepted_wrong_candidates")
                source = sources.get((c["episode"], c["frame"]))
                check(source is not None, "missing_accepted_source")
                if source:
                    old, old_skill, _ = source
                    check(old.observed_ns == c["observed_ns"], "source_timestamp_mismatch")
                    check(old_skill["generation"] == c["skill_generation"], "source_generation_mismatch")
                    check((old.bot.details.life_generation_derived, old.opponent.details.life_generation_derived) ==
                        (c["bot_life"], c["opponent_life"]), "source_life_mismatch")
                    for snapshot in (old, observation):
                        a, b = snapshot.bot, snapshot.opponent
                        key = [support_surface(a.x, a.y, a.grounded), a.grounded,
                            1 if b.x > a.x else -1 if b.x < a.x else 0, None, abs(a.x) > 65 or a.y < -5]
                        check(c["context_key"] == key, "source_or_current_context_mismatch")
                try:
                    spec = relative_skill(reply["action"], observation)
                    check(can_start(spec, observation) is None, "accepted_illegal_skill")
                    active = skill["active"]
                    check(active is not None and active["source_frame"] == observation.frame and
                        active["skill"] == spec.name and active["direction"] == spec.direction and
                        skill["generation"] == c["skill_generation"] + 1, "accepted_skill_not_started")
                    pending_skills[c["skill_generation"]+1] = {"episode": observation.episode,
                        "frame": observation.frame, "spec": spec, "label": reply["action"]}
                except (KeyError, TypeError, ValueError):
                    errors["accepted_invalid_skill"] += 1
                last_applied = sequence
            transitions = skill.get("transitions", [skill.get("event")])
            for event in transitions:
                if not event or event.get("status") not in ("succeeded", "aborted", "timeout"):
                    continue
                trial = pending_skills.pop(event["generation"], None)
                if trial is None:
                    continue
                if event["status"] == "succeeded":
                    try:
                        valid = check_acknowledgement(trial, event, row, sources)
                    except (KeyError, TypeError, ValueError):
                        valid = False
                    if valid:
                        acknowledgements["observed:"+trial["spec"].name] += 1
                    else:
                        errors["unverified_provider_skill_success"] += 1
                else:
                    acknowledgements[event["status"]] += 1
    report = summary.get("async_policy")
    if report:
        for key, count in outcomes.items():
            if report["policy"].get(key, 0) != count:
                errors["summary_outcome_mismatch"] += 1
        bridge = report["bridge"]
        if bridge["workers_alive"] or bridge["inflight"] or bridge.get("peak_inflight", 0) > bridge["worker_limit"]:
            errors["worker_bound_or_shutdown"] += 1
        if bridge.get("mailbox_dropped", 0):
            errors["mailbox_overflow"] += 1
        if not outcomes["accepted"]:
            errors["no_decisions_applied"] += 1
        provider = bridge.get("provider")
        if provider is not None:
            for delivery in bridge.get("shutdown_deliveries", []):
                consumed.setdefault(delivery["expected"]["sequence"], []).append(delivery)
            attempts = provider["attempts"]
            if len(attempts) > provider["max_requests"] or len(attempts) != len(consumed):
                errors["provider_attempt_accounting"] += 1
            for attempt in attempts:
                deliveries = consumed.get(attempt["sequence"], [])
                if len(deliveries) != 1:
                    errors["provider_return_accounting"] += 1
                    continue
                reply = deliveries[0]["reply"]
                if attempt["status"] == "validated":
                    if reply["metadata"] != attempt["result"] or reply["action"] != attempt["result"]["action"]:
                        errors["provider_result_mismatch"] += 1
                elif reply["error"] != attempt["reason"]:
                    errors["provider_error_mismatch"] += 1
            if (provider["http_active"] or provider["client_shutdown"]["workers_alive"] or
                    provider["client_shutdown"]["timers_alive"]):
                errors["provider_shutdown"] += 1
    fps = [{"episode": e["episode"], "simulation_fps": e.get("simulation_fps")} for e in summary["episodes"]]
    observed_classes = {key.split(":", 1)[1] for key, count in acknowledgements.items() if key.startswith("observed:") and count}
    observed_successes = sum(count for key, count in acknowledgements.items() if key.startswith("observed:"))
    live_acceptance = None
    if report and report["bridge"].get("provider"):
        continuous = max((e.get("last_monotonic", 0)-e.get("started_monotonic", 0) for e in summary["episodes"]), default=0)
        live_acceptance = {"continuous_episode_seconds": continuous, "observed_successes": observed_successes,
            "observed_skill_classes": sorted(observed_classes), "criteria_met": not errors and continuous >= 120 and
                observed_successes >= 20 and len(observed_classes) >= 3 and summary.get("provider_contacted") is True}
    return {"schema_version": 1, "run_id": summary["run_id"], "status": "pass" if not errors else "fail",
        "frames_sha256": digest.hexdigest(), "game_frames": game_frames, "errors": dict(errors),
        "outcomes": dict(outcomes), "injected_faults": dict(faults), "reordered_deliveries": reordered,
        "acknowledgements": dict(acknowledgements), "pending_provider_skills": len(pending_skills),
        "input_owner_frames": dict(input_owners),
        "provider_owned_frame_fraction": input_owners.get("provider", 0)/game_frames
            if game_frames and not input_owners.get("unrecorded") else None,
        "live_acceptance": live_acceptance,
        "observed_to_queued_ms": quantiles(queued_ms), "observed_to_flushed_ms": quantiles(flushed_ms),
        "source_to_reply_ms": quantiles(delays_ms), "simulation_fps": fps,
        "run_status": summary["status"], "async_report_present": report is not None}
