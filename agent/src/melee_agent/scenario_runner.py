"""Fresh-match scenario scheduling and independent raw-state acceptance evidence."""

from collections import Counter
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import random
import select
import shutil
import signal
import subprocess
import sys
import time
import uuid

from .config import load_config, owned_path
from .engine import Observation
from .integrity import inspect_integrity
from .matches import artifact_bytes, isolated_environment, locate_run, terminate_child
from .match_worker import write_json
from .replay import expected_settings
from .scenarios import find_suite, find_scenario, starting_predicate, suite_hash, verified_trial
from .stage import support_surface


def inspect_scenario(run):
    summary = json.loads((run / "summary.json").read_text())
    launch = json.loads((run / "launch.json").read_text())
    report = summary.get("scenario", {})
    name = launch["scenario_name"]
    spec = find_scenario(name)
    integrity = inspect_integrity(run)
    errors = Counter()
    if integrity["status"] != "pass":
        errors["frame_integrity"] += 1
    if not verified_trial(report, name):
        errors["trial_report_invalid"] += 1
    if (summary["status"] != "scenario_recorded" or summary["provider_contacted"] or
            not summary["neutralized"] or not summary["worker_stopped"] or not summary["emulator_stopped"] or
            not summary.get("state_receiver", {}).get("stopped") or summary.get("replay_errors") or
            not summary.get("replays") or any(not expected_settings(replay.get("settings")) for replay in summary["replays"])):
        errors["run_or_cleanup_invalid"] += 1
    start = report.get("measurement_start_frame")
    first = last = prior = None
    measured = []
    boundary = None
    digest = hashlib.sha256()
    with (run / "frames.jsonl").open("rb") as frames:
        for line in frames:
            digest.update(line)
            row = json.loads(line)
            if row["menu"] != "IN_GAME":
                continue
            observation = Observation.parse(row["control"]["observation"])
            trace = row["scenario"]
            first = first or row
            last = row
            for port, fighter in (("1", observation.bot), ("2", observation.opponent)):
                raw = row["raw_observation"]["players"][port]["raw_post"]
                fields = ((fighter.x, raw["x"]), (fighter.y, raw["y"]),
                    (fighter.grounded, raw["airborne"] == 0), (fighter.jumps, raw["jumps"]),
                    (fighter.details.action_id, raw["action_id"]), (fighter.stocks_remaining, raw["stocks"]),
                    (fighter.details.self_velocity_y, raw["speed_y_self"]),
                    (fighter.details.self_velocity_x, raw["speed_ground_x_self"] if fighter.grounded else raw["speed_air_x_self"]))
                if any(not math.isclose(actual, expected, abs_tol=1e-6) for actual, expected in fields):
                    errors["observation_raw_mismatch"] += 1
            if start is None or row["frame"] < start:
                if trace["input_owner"] not in ("setup", "neutral"):
                    errors["measured_input_before_setup"] += 1
            else:
                if trace["input_owner"] == "setup":
                    errors["setup_input_after_measurement"] += 1
                measured.append(row)
                if row["frame"] == start:
                    boundary = row
                    if asdict(observation) != report["initial_observation"] or not starting_predicate(spec, observation):
                        errors["starting_predicate_not_observed"] += 1
                    packet = row["input_provenance"]["observed"]
                    neutral = (not any(packet["buttons"].values()) and max(packet["l"], packet["r"]) <= .025 and
                        all(abs(value-.5) <= .025 for key in ("main", "c") for value in packet[key]))
                    if not neutral or prior is None or prior["control"]["decision"]["action"] != "wait":
                        errors["setup_release_not_observed"] += 1
            prior = row
    result = report.get("result") or {}
    if last is None or last["frame"] != result.get("end_frame") or last["control"]["observation"] != result.get("end_observation"):
        errors["end_state_mismatch"] += 1
    if start is not None and boundary is None:
        errors["measurement_boundary_missing"] += 1
    if len(measured) != result.get("measured_frames"):
        errors["measured_frame_count"] += 1
    if result.get("status") == "succeeded" and measured:
        a = result["end_observation"]["bot"]
        if spec.kind in ("offstage", "offstage_low", "ledge", "airborne"):
            on_stage = support_surface(a["x"], a["y"], a["grounded"]) in ("ground", "left", "right", "top")
            ledge = spec.kind in ("offstage", "offstage_low") and a["details"]["action_id"] in (252, 253)
            if not on_stage and not ledge:
                errors["return_or_landing_not_observed"] += 1
        elif spec.kind == "grounded":
            delta = (a["x"]-report["initial_observation"]["bot"]["x"])*-spec.direction
            if delta < 6 or not a["details"]["input_neutral_derived"]:
                errors["movement_or_release_not_observed"] += 1
        elif sum(row["raw_observation"]["players"]["1"]["raw_post"]["action_id"] == 179 for row in measured) < 8:
            errors["shield_not_observed"] += 1
    return {"schema_version": 1, "run_id": launch["run_id"], "scenario": name,
        "status": "pass" if not errors else "fail", "errors": dict(errors),
        "trial_status": result.get("status"), "trial_reason": result.get("reason"),
        "starting_predicate_reached": boundary is not None,
        "initial_observation_sha256": None if boundary is None else hashlib.sha256(json.dumps(report["initial_observation"], sort_keys=True).encode()).hexdigest(),
        "setup_stopped_frame": report.get("setup_stopped_frame"), "measurement_start_frame": start,
        "measured_frames": len(measured), "frames_sha256": digest.hexdigest(),
        "summary_sha256": hashlib.sha256((run / "summary.json").read_bytes()).hexdigest(),
        "game_frames": integrity["game_records"], "artifact_bytes": artifact_bytes(run),
        "artifacts": {"frames": "build/jev/runs/"+launch["run_id"]+"/frames.jsonl",
            "summary": "build/jev/runs/"+launch["run_id"]+"/summary.json"}}


class SuiteInterrupted(BaseException):
    pass


def recovery_acceptance(results, repeats):
    per_scenario = {}
    for spec in find_suite("recovery-v1"):
        trials = [row for row in results if row["scenario"] == spec.name]
        successes = sum(row["status"] == "pass" and row["trial_status"] == "succeeded" for row in trials)
        per_scenario[spec.name] = {"trials": len(trials), "successes": successes,
            "passed": repeats == 20 and len(trials) == 20 and successes >= 18}
    return {"passed": all(row["passed"] for row in per_scenario.values()),
        "required": "At least 18/20 successful audited returns in every declared mirrored scenario",
        "scenarios": per_scenario}


def run_suite(root, repeats=10, duration=2400, seed=0, suite="mechanics-v1", require_acceptance=False):
    if (type(repeats) is not int or not 1 <= repeats <= 20 or type(duration) is not int or
            not 30 <= duration <= 3600 or type(seed) is not int or not 0 <= seed <= 2147483647):
        raise ValueError("Invalid bounded scenario schedule")
    specs = find_suite(suite)
    config = load_config(root)
    if shutil.disk_usage(root / "build/jev").free < 2_147_483_648:
        raise ValueError("Scenario suite needs 2 GiB free")
    suite_id = "scenarios-"+uuid.uuid4().hex
    folder = owned_path(root, "build/jev/scenarios/"+suite_id)
    folder.mkdir(parents=True)
    order = [(repetition+1, spec.name) for repetition in range(repeats) for spec in specs]
    random.Random(seed).shuffle(order)
    manifest = {"schema_version": 1, "suite_id": suite_id, "suite": suite, "suite_sha256": suite_hash(suite),
        "repeats": repeats, "ordering_seed": seed, "game_rng_seed": None,
        "runtime_sha256": config.runtime_sha256, "initial_state": "fresh_match_per_trial",
        "savestates_supported": False, "duration_seconds": duration, "order": order,
        "scenarios": [spec.manifest() for spec in specs], "artifact_limit_bytes": 2_147_483_648,
        "provider_contacted": False, "repeatability": "Observed predicates are controlled; CPU and game RNG are not seeded."}
    write_json(folder / "manifest.json", manifest)
    started = time.monotonic()
    results = []
    child = current = None
    status = "running"
    reason = None
    def interrupt(signum, frame):
        raise SuiteInterrupted()
    previous = {sig: signal.signal(sig, interrupt) for sig in (signal.SIGINT, signal.SIGTERM)}
    print(json.dumps({"event": "scenario_suite_started", "suite_id": suite_id, "trials": len(order)}), flush=True)
    try:
        for repetition, name in order:
            # Reserve the complete child deadline plus teardown, not a fresh
            # timeout after each startup/read operation.
            if time.monotonic()-started+60 > duration:
                reason = "suite_deadline"
                break
            if sum(row["artifact_bytes"] for row in results)+config.limits.max_artifact_bytes > 2_147_483_648:
                reason = "artifact_limit"
                break
            trial_deadline = time.monotonic()+40
            child = subprocess.Popen([sys.executable, "-B", "-m", "melee_agent.cli", "scenario-run",
                "--name", name, "--duration", "30"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                env=isolated_environment(), start_new_session=True)
            if not select.select([child.stdout], [], [], 35)[0]:
                raise ValueError("Scenario startup timed out")
            event = json.loads(child.stdout.readline(4097))
            if event.get("event") != "started":
                raise ValueError("Scenario failed before startup")
            current = locate_run(root, event["run_id"])
            print(json.dumps({"event": "scenario_started", "suite_id": suite_id, "scenario": name,
                "repetition": repetition, "run_id": current.name}), flush=True)
            output, _ = child.communicate(timeout=max(.01, trial_deadline-time.monotonic()))
            if len(output) > 2_097_152:
                raise ValueError("Scenario output exceeded bound")
            result = {**inspect_scenario(current), "repetition": repetition}
            write_json(folder / (f"trial-{len(results)+1:03d}.json"), result)
            results.append(result)
            print(json.dumps({"event": "scenario_finished", "scenario": name, "repetition": repetition,
                "audit": result["status"], "outcome": result["trial_status"], "reason": result["trial_reason"]}), flush=True)
            child = current = None
            if result["status"] != "pass":
                reason = "trial_audit_failed"
                break
        status = "completed" if len(results) == len(order) and reason is None else "incomplete"
    except SuiteInterrupted:
        status, reason = "interrupted", "stop_requested"
    except Exception as error:
        status, reason = "failed", type(error).__name__
    finally:
        if child is not None and child.poll() is None:
            if current is not None:
                (current / "stop.request").touch(exist_ok=True)
                try:
                    child.communicate(timeout=10)
                except subprocess.TimeoutExpired:
                    terminate_child(child)
            else:
                terminate_child(child)
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        counts = Counter(row["trial_status"] for row in results)
        report = {"schema_version": 1, "suite_id": suite_id, "suite": suite, "status": status,
            "reason": reason, "elapsed_seconds": time.monotonic()-started, "expected_trials": len(order),
            "completed_trials": len(results), "outcomes": dict(counts), "trials": results,
            "provider_contacted": False, "game_rng_seed": None,
            "acceptance_scope": "A completed suite records setup and skill outcomes; it does not imply all skills succeeded."}
        if suite == "recovery-v1":
            report["acceptance"] = recovery_acceptance(results, repeats)
        write_json(folder / "summary.json", report)
        print(json.dumps({k: v for k, v in report.items() if k != "trials"}), flush=True)
    return 0 if status == "completed" and (not require_acceptance or report.get("acceptance", {}).get("passed")) else 2
