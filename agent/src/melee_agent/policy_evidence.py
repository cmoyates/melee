"""Read-only decision audit against retained source and application observations."""

from collections import Counter, OrderedDict
import hashlib
import json
import math

from .engine import Observation
from .skills import can_start, relative_skill
from .stage import support_surface


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
            sources[observation.episode, observation.frame] = (observation, skill)
            if len(sources) > 256:
                sources.popitem(last=False)
            queued_ms.append((control["queued_ns"]-observation.observed_ns)/1e6)
            flushed = row["input_provenance"]["latest_completed_flush"]
            if flushed:
                source = sources.get((flushed["episode"], flushed["source_frame"]))
                if source:
                    flushed_ms.append((flushed["flush_completed_ns"]-source[0].observed_ns)/1e6)
            events = skill.get("policy_events", [])
            if len(events) > 32:
                errors["unbounded_events"] += 1
            for event in events:
                delivery = event["delivery"]
                c, reply = delivery["expected"], delivery["reply"]
                candidates = delivery["candidates"]
                sequence = c["sequence"]
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
                    old, old_skill = source
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
                except (KeyError, TypeError, ValueError):
                    errors["accepted_invalid_skill"] += 1
                last_applied = sequence
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
    fps = [{"episode": e["episode"], "simulation_fps": e.get("simulation_fps")} for e in summary["episodes"]]
    return {"schema_version": 1, "run_id": summary["run_id"], "status": "pass" if not errors else "fail",
        "frames_sha256": digest.hexdigest(), "game_frames": game_frames, "errors": dict(errors),
        "outcomes": dict(outcomes), "injected_faults": dict(faults), "reordered_deliveries": reordered,
        "observed_to_queued_ms": quantiles(queued_ms), "observed_to_flushed_ms": quantiles(flushed_ms),
        "source_to_reply_ms": quantiles(delays_ms), "simulation_fps": fps,
        "run_status": summary["status"], "async_report_present": report is not None}
