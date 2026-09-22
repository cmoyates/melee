"""Sealed incident prefixes and deterministic, input-free control-path replay.

Recorded observations are historical inputs. Replay stops at the first changed
packet/decision; it never calls that recorded history a counterfactual future.
"""

from dataclasses import fields
import hashlib
import json
import os
from pathlib import Path
import stat
import uuid

from .async_policy import AsyncPolicy, Delivery, Reply, RequestContext
from .config import load_config, owned_path
from .doctor import STOCK_DISC_SHA1
from .engine import BUTTONS, Decision, FrameExecutor, Observation, Packet

CONTRACT_MODULES = ("engine.py", "skills.py", "stage.py", "rules.py", "async_policy.py", "provider.py", "live_provider.py")
MAX_PREFIX_BYTES = 134_217_728
MAX_RECORDS = 40_000
LIBMELEE_COMMIT = "bce21f09984b286e6d36bfd2939e4cd4691f94c2"


class IncidentError(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def decode(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise IncidentError("duplicate_json_field")
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(IncidentError("nonfinite_json")))
    except (ValueError, UnicodeError):
        raise IncidentError("invalid_incident_json") from None


def open_regular(path, limit):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    information = os.fstat(fd)
    if not stat.S_ISREG(information.st_mode) or information.st_size > limit:
        os.close(fd)
        raise IncidentError("incident_file_type_or_size")
    return os.fdopen(fd, "rb")


def read_json(path, limit=131072):
    with open_regular(path, limit) as handle:
        return decode(handle.read(limit+1))


def contract_hashes():
    source = Path(__file__).parent
    return {name: hashlib.sha256((source/name).read_bytes()).hexdigest() for name in CONTRACT_MODULES}


def validate_packet(value):
    if (set(value) != {"schema_version", "main", "c", "l", "r", "buttons"} or
            any(type(value[key]) is not list or len(value[key]) != 2 for key in ("main", "c")) or
            set(value["buttons"]) != set(BUTTONS) or any(type(v) is not bool for v in value["buttons"].values())):
        raise IncidentError("incident_packet_schema")
    Packet(value["schema_version"], *value["main"], *value["c"], value["l"], value["r"],
        tuple(button for button in BUTTONS if value["buttons"][button]))


def stream_records(path, limit=MAX_PREFIX_BYTES):
    with open_regular(path, limit) as handle:
        count = 0
        while line := handle.readline(65537):
            count += 1
            if len(line) > 65536 or not line.endswith(b"\n") or count > MAX_RECORDS + 10000:
                raise IncidentError("truncated_or_oversized_incident_record")
            yield line, decode(line)


def compact_record(row):
    control, skill = row["control"], row["skill"]
    return {"schema_version": 1, "episode": row["episode"], "frame": row["frame"],
        "observation": control["observation"], "times": {"executor_started_ns": control.get("executor_started_ns"),
            "policy_ns": skill.get("decision_ns"), "queued_ns": control["queued_ns"]},
        "exchange_busy": skill.get("exchange_busy"),
        "deliveries": [event["delivery"] for event in skill["policy_events"]],
        "expected": {"decision": control["decision"], "packet": control["packet"],
            "events": [{"sequence": event["delivery"]["expected"]["sequence"],
                "accepted": event["accepted"], "reason": event["reason"]} for event in skill["policy_events"]],
            "skill": {key: skill[key] for key in ("generation", "active", "event")},
            "input_owner": skill.get("input_owner")}}


def validate_clock(row, observation):
    times = row["times"]
    if (set(times) != {"executor_started_ns", "policy_ns", "queued_ns"} or
            any(type(value) is not int for value in times.values()) or
            not observation.observed_ns <= times["executor_started_ns"] <= times["policy_ns"] <= times["queued_ns"] or
            type(row["exchange_busy"]) is not bool):
        raise IncidentError("invalid_recorded_clock")


def export_incident(root, run, *, episode=1, frame=None, request_id=None, after_frames=60):
    if (type(episode) is not int or episode < 1 or type(after_frames) is not int or not 0 <= after_frames <= 300 or
            (frame is None) == (request_id is None) or (frame is not None and type(frame) is not int)):
        raise IncidentError("invalid_incident_selector")
    launch = read_json(run / "launch.json")
    summary = read_json(run / "summary.json", 1_048_576)
    trace = run / "frames.jsonl"
    original_stat = trace.stat()
    focus = None
    source_digest = hashlib.sha256()
    # The completed run remains private. Hash all history before extracting a
    # prefix, including menu records, so a concurrent edit cannot pass unnoticed.
    for line, row in stream_records(trace, 268_435_456):
        source_digest.update(line)
        if row["menu"] != "IN_GAME":
            continue
        matches = (row["episode"], row["frame"]) == (episode, frame) if request_id is None else any(
            (event["delivery"]["reply"].get("metadata") or {}).get("request_id") == request_id
            for event in row.get("skill", {}).get("policy_events", []))
        if matches:
            if focus is not None:
                raise IncidentError("ambiguous_incident_selector")
            focus = row
    if focus is None:
        raise IncidentError("incident_frame_or_request_not_found")
    incident_id = "incident-" + uuid.uuid4().hex
    folder = owned_path(root, "build/jev/incidents/"+incident_id)
    folder.mkdir(parents=True)
    reasons = set()
    count = size = 0
    first = last = None
    digest = hashlib.sha256()
    end = (focus["episode"], focus["frame"]+after_frames)
    with (folder / "prefix.jsonl").open("xb") as output:
        for _, row in stream_records(trace, 268_435_456):
            if row["menu"] != "IN_GAME":
                continue
            identity = (row["episode"], row["frame"])
            if identity > end:
                break
            if "skill" not in row or "policy_events" not in row["skill"]:
                raise IncidentError("incident_requires_async_policy_trace")
            compact = compact_record(row)
            if any(value is None for value in compact["times"].values()) or type(compact["exchange_busy"]) is not bool:
                reasons.add("missing_exact_clock_or_mailbox_provenance")
            raw = canonical(compact)+b"\n"
            count += 1
            size += len(raw)
            if count > MAX_RECORDS or size > MAX_PREFIX_BYTES or len(raw) > 65536:
                raise IncidentError("incident_prefix_limit")
            output.write(raw)
            digest.update(raw)
            first = first or list(identity)
            last = list(identity)
    current_stat = trace.stat()
    if (current_stat.st_size, current_stat.st_mtime_ns) != (original_stat.st_size, original_stat.st_mtime_ns):
        raise IncidentError("source_changed_during_extraction")
    provider = summary.get("async_policy", {}).get("bridge", {}).get("provider") or {}
    declared = {"runtime_sha256": launch.get("runtime_sha256"), "disc_sha1": launch.get("disc_sha1"),
        "libmelee_commit": launch.get("libmelee_commit"), "stage_id": launch["stage_id"],
        "starting_stocks": launch["starting_stocks"], "time_limit_seconds": launch["match_time_limit_seconds"],
        "source_sha256": {name: launch.get("source_sha256", {}).get(name) for name in CONTRACT_MODULES},
        "provider_config_sha256": provider.get("config_sha256")}
    kind = "synthetic" if launch.get("synthetic_fixture") is True else "emulator"
    if declared["source_sha256"] != contract_hashes():
        reasons.add("policy_contract_mismatch")
    if kind == "emulator" and declared["runtime_sha256"] != load_config(root).runtime_sha256:
        reasons.add("runtime_pin_mismatch")
    focus_raw = canonical(focus)+b"\n"
    (folder / "focus.json").write_bytes(focus_raw)
    manifest = {"schema_version": 1, "incident_id": incident_id, "run_id": launch["run_id"],
        "source_kind": kind, "provider_kind": "openrouter" if launch["policy"] == "jev" else "simulated",
        "declared_provenance": declared, "expected_provenance": declared,
        "source_frames_sha256": source_digest.hexdigest(), "prefix_sha256": digest.hexdigest(),
        "focus_sha256": hashlib.sha256(focus_raw).hexdigest(), "prefix_records": count, "prefix_bytes": size,
        "prefix_first": first, "prefix_last": last, "focus": [focus["episode"], focus["frame"]],
        "replay_supported": not reasons, "replay_blockers": sorted(reasons),
        "interpretation": "Frozen historical observations; stop at divergence; no counterfactual game prediction."}
    manifest["manifest_sha256"] = sha(manifest)
    (folder / "manifest.json").write_bytes(canonical(manifest)+b"\n")
    return explain_manifest(manifest, focus)


def explain_manifest(manifest, focus):
    skill = focus["skill"]
    return {"schema_version": 1, "incident_id": manifest["incident_id"], "run_id": manifest["run_id"],
        "source_kind": manifest["source_kind"], "provider_kind": manifest["provider_kind"], "focus": manifest["focus"],
        "prefix_records": manifest["prefix_records"], "replay_supported": manifest["replay_supported"],
        "replay_blockers": manifest["replay_blockers"], "queued_decision": focus["control"]["decision"],
        "latest_completed_flush": {key: value for key, value in
            (focus.get("input_provenance", {}).get("latest_completed_flush") or {}).items() if key != "packet"},
        "active_skill": skill["active"], "last_observed_skill_event": skill["event"],
        "provider_decisions": [{"sequence": e["delivery"]["expected"]["sequence"],
            "action": e["delivery"]["reply"]["action"], "accepted": e["accepted"], "reason": e["reason"]}
            for e in skill["policy_events"]], "contact": "not_measured", "outcome_attribution": "not_established",
        "interpretation": manifest["interpretation"]}


def verify_bundle(root, folder):
    manifest = read_json(folder / "manifest.json")
    sealed = dict(manifest)
    seal = sealed.pop("manifest_sha256", None)
    if type(manifest.get("schema_version")) is not int or manifest["schema_version"] != 1 or sha(sealed) != seal:
        raise IncidentError("manifest_integrity")
    if manifest["declared_provenance"] != manifest["expected_provenance"]:
        raise IncidentError("provenance_mismatch")
    provenance = manifest["declared_provenance"]
    if provenance["source_sha256"] != contract_hashes():
        raise IncidentError("policy_contract_mismatch")
    if provenance["provider_config_sha256"] is not None:
        from .live_provider import policy_config_hash
        if provenance["provider_config_sha256"] != policy_config_hash():
            raise IncidentError("provider_config_mismatch")
    if (provenance["stage_id"], provenance["starting_stocks"], provenance["time_limit_seconds"]) != (31, 4, 480):
        raise IncidentError("rules_provenance_mismatch")
    if manifest["source_kind"] == "emulator":
        if (provenance["runtime_sha256"] != load_config(root).runtime_sha256 or
                provenance["disc_sha1"] != STOCK_DISC_SHA1 or provenance["libmelee_commit"] != LIBMELEE_COMMIT):
            raise IncidentError("binary_or_dependency_provenance_mismatch")
    elif manifest["source_kind"] != "synthetic":
        raise IncidentError("unknown_incident_origin")
    digest = hashlib.sha256()
    size = count = 0
    first = last = None
    found_focus = False
    focus_compact = None
    for line, row in stream_records(folder / "prefix.jsonl"):
        digest.update(line)
        size += len(line)
        count += 1
        if type(row.get("schema_version")) is not int or row["schema_version"] != 1 or count > MAX_RECORDS:
            raise IncidentError("incident_record_schema")
        observation = Observation.parse(row["observation"])
        if manifest["replay_supported"]:
            validate_clock(row, observation)
        Decision(**row["expected"]["decision"])
        validate_packet(row["expected"]["packet"])
        identity = [observation.episode, observation.frame]
        if identity != [row["episode"], row["frame"]] or (last is not None and identity <= last):
            raise IncidentError("incident_episode_or_frame_order")
        if (row["expected"]["decision"]["episode"], row["expected"]["decision"]["frame"]) != tuple(identity):
            raise IncidentError("incident_decision_identity")
        first = first or identity
        last = identity
        found_focus = found_focus or identity == manifest["focus"]
        if identity == manifest["focus"]:
            focus_compact = row
    if (digest.hexdigest() != manifest["prefix_sha256"] or count != manifest["prefix_records"] or
            size != manifest["prefix_bytes"] or first != manifest["prefix_first"] or last != manifest["prefix_last"] or
            not found_focus or not first or first[0] != 1):
        raise IncidentError("prefix_integrity")
    with open_regular(folder / "focus.json", 65536) as handle:
        raw = handle.read(65537)
    if hashlib.sha256(raw).hexdigest() != manifest["focus_sha256"]:
        raise IncidentError("focus_integrity")
    focus = decode(raw)
    if [focus["episode"], focus["frame"]] != manifest["focus"]:
        raise IncidentError("focus_identity")
    if compact_record(focus) != focus_compact:
        raise IncidentError("focus_prefix_mismatch")
    if not manifest["replay_supported"]:
        raise IncidentError("missing_exact_replay_provenance")
    return manifest


def restore_context(value):
    if set(value) != {field.name for field in fields(RequestContext)}:
        raise IncidentError("request_context_schema")
    return RequestContext(**{**value, "context_key": tuple(value["context_key"])})


class RecordedBridge:
    def __init__(self):
        self.row = None
    def exchange(self, observation, generation, candidates):
        if self.row["exchange_busy"]:
            return None
        result = []
        for value in self.row["deliveries"]:
            reply = value["reply"]
            result.append(Delivery(restore_context(value["expected"]), tuple(value["candidates"]),
                Reply(**{**reply, "context": restore_context(reply["context"])})))
        return result


class RecordedClock:
    def __init__(self):
        self.values = []
    def now_ns(self):
        if not self.values:
            raise IncidentError("unexpected_clock_read")
        return self.values.pop(0)


class PacketDigest:
    def __init__(self):
        self.digest = hashlib.sha256()
    def send(self, packet):
        self.digest.update(canonical(packet.wire())+b"\n")


def replay_incident(root, folder):
    manifest = verify_bundle(root, folder)
    bridge, clock, sink = RecordedBridge(), RecordedClock(), PacketDigest()
    policy = AsyncPolicy(manifest["run_id"], bridge, clock=lambda: bridge.row["times"]["policy_ns"])
    executor = FrameExecutor(policy, sink, clock)
    decisions = hashlib.sha256()
    count = accepted = 0
    divergence = None
    for _, row in stream_records(folder / "prefix.jsonl"):
        bridge.row = row
        observation = Observation.parse(row["observation"])
        times = row["times"]
        validate_clock(row, observation)
        clock.values = [times["executor_started_ns"], times["queued_ns"]]
        control = executor.step(observation)
        if clock.values or control["queued_ns"] != times["queued_ns"]:
            raise IncidentError("executor_clock_contract_mismatch")
        trace = policy.trace()
        events = [{"sequence": e["delivery"]["expected"]["sequence"], "accepted": e["accepted"], "reason": e["reason"]}
            for e in trace["policy_events"]]
        actual = {"decision": control["decision"], "packet": control["packet"], "events": events,
            "skill": {key: trace[key] for key in ("generation", "active", "event")}, "input_owner": trace["input_owner"]}
        count += 1
        accepted += sum(e["accepted"] for e in events)
        decisions.update(canonical({"decision": control["decision"], "events": events})+b"\n")
        if actual != row["expected"]:
            divergence = {"episode": observation.episode, "frame": observation.frame,
                "different_fields": sorted(key for key in actual if actual[key] != row["expected"][key])}
            break
    return {"schema_version": 1, "incident_id": manifest["incident_id"], "status": "fail" if divergence else "pass",
        "replayed_records": count, "accepted_decisions": accepted, "packets_sha256": sink.digest.hexdigest(),
        "decisions_sha256": decisions.hexdigest(), "divergence": divergence,
        "emulator_launched": False, "provider_contacted": False, "controller_written": False,
        "interpretation": manifest["interpretation"]}
