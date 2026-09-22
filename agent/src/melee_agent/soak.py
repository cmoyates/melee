"""Bounded thirty-minute, no-network runtime fault schedule with retained evidence."""

from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import select
import shutil
import signal
import subprocess
import sys
import time
import uuid

from .budget import SpendLedger
from .config import load_config, owned_path
from .matches import artifact_bytes, isolated_environment, locate_run, terminate_child
from .match_worker import write_json
from .policy_evidence import inspect_policy

INITIAL_PHASES = (("logger_stall", 60), ("executor_error", 60), ("worker_death", 60),
    ("controller_stall", 60), ("frame_stall", 60), ("network", 300), ("frame_gap", 300), ("rate_cap", 300))
REQUIRED_FAULTS = {"logger_stall", "executor_error", "worker_death", "controller_stall", "frame_stall", "frame_gap",
    "rate_cap", "disconnect", "http_429", "http_529", "malformed_json", "invalid_distribution", "low_confidence",
    "cancellation", "latency_stall", "client_recreated", "recovery"}


def assess_run(run, mode, ended_ns):
    summary = json.loads((run / "summary.json").read_text())
    audit = inspect_policy(run, require_participation=False)
    marker_path = run / "fault-injected.json"
    marker = json.loads(marker_path.read_text()) if marker_path.exists() else None
    faults = summary.get("fault_injection", {"counts": {mode: 1} if marker else {}, "events": [marker] if marker else []})
    errors = []
    if audit["status"] != "pass":
        errors.append("policy_audit_failed")
    if not summary["worker_stopped"] or not summary["emulator_stopped"]:
        errors.append("owned_process_not_stopped")
    receiver_path = run / "state-receiver.json"
    receiver_stopped = None
    if receiver_path.exists():
        receiver_pid = json.loads(receiver_path.read_text())["pid"]
        receiver_stopped = False
        check_deadline = time.monotonic()+2
        while time.monotonic() < check_deadline:
            try:
                os.kill(receiver_pid, 0)  # Read-only liveness check, never a PID-based kill.
            except ProcessLookupError:
                receiver_stopped = True
                break
            time.sleep(.05)
        if not receiver_stopped:
            errors.append("state_receiver_still_present")
    if summary.get("provider_contacted"):
        errors.append("unexpected_external_provider")
    if not summary["neutralized"] and mode != "worker_death":
        errors.append("neutralization_failed")
    cleanup_seconds = (ended_ns-marker["monotonic_ns"])/1e9 if marker else None
    if cleanup_seconds is not None and mode != "frame_gap" and cleanup_seconds > 25:
        errors.append("terminal_cleanup_bound_exceeded")
    if mode in ("network", "frame_gap", "rate_cap"):
        if summary["status"] != "captured":
            errors.append("continuous_phase_incomplete")
    elif mode == "logger_stall":
        if summary.get("failure_reason") != "recorder_queue_full" or not summary.get("last_unrecorded_record"):
            errors.append("logger_failure_not_accounted")
        if summary.get("recorder", {}).get("unwritten") != 0:
            errors.append("logger_drain_incomplete")
    elif mode == "executor_error":
        if summary.get("worker_error_type") != "RuntimeError":
            errors.append("executor_failure_missing")
    elif mode == "worker_death":
        if summary["processes"]["worker"]["exit_code"] != -9:
            errors.append("worker_death_missing")
    elif summary["reason"] != "state_stalled":
        errors.append("watchdog_did_not_stop_stall")
    if mode != "network" and not faults["counts"].get(mode):
        errors.append("requested_fault_missing")
    bridge = summary.get("async_policy", {}).get("bridge", {})
    provider = bridge.get("provider")
    if provider is not None:
        if not provider.get("simulation_only") or provider.get("external_http_calls") != 0:
            errors.append("simulation_transport_not_proven")
        if len(provider["attempts"]) > provider["max_requests"]:
            errors.append("run_request_limit_exceeded")
    elif mode != "worker_death":
        errors.append("provider_shutdown_report_missing")
    return {"run_id": summary["run_id"], "mode": mode, "status": "pass" if not errors else "fail",
        "errors": errors, "run_status": summary["status"], "reason": summary["reason"],
        "neutralized": summary["neutralized"], "neutralization_unavailable_due_to_worker_death": mode == "worker_death",
        "worker_stopped": summary["worker_stopped"], "emulator_stopped": summary["emulator_stopped"],
        "state_receiver_stopped": receiver_stopped,
        "fault_counts": faults["counts"], "terminal_fault_to_cleanup_seconds": cleanup_seconds if mode != "frame_gap" else None,
        "audit": audit, "bridge_peak_inflight": bridge.get("peak_inflight"),
        "bridge_peak_mailbox": bridge.get("peak_mailbox"),
        "health_events": provider.get("health_events", []) if provider else [], "artifact_bytes": artifact_bytes(run)}


class SoakInterrupted(BaseException):
    pass


def run_soak(root, budget_directory, duration=1800):
    if duration != 1800:
        raise ValueError("runtime-v1 certification requires exactly 1800 seconds")
    config = load_config(root)
    directory = owned_path(root, budget_directory)
    ledger = SpendLedger(directory / "spend.jsonl")
    before = ledger.report()
    if (datetime.fromisoformat(before["deadline_utc"])-datetime.now(timezone.utc)).total_seconds() < duration+60:
        raise ValueError("Insufficient time remains in the shared experiment")
    if config.limits.max_run_seconds < 300 or shutil.disk_usage(directory).free < 2_147_483_648:
        raise ValueError("Soak needs a 300-second run limit and 2 GiB of available artifact space")
    soak_id = "soak-" + uuid.uuid4().hex
    folder = directory / "soaks" / soak_id
    folder.mkdir(parents=True)
    started = time.monotonic()
    deadline = started + duration
    report = {"schema_version": 1, "soak_id": soak_id, "suite": "runtime-v1", "simulation_only": True,
        "external_http_calls": 0, "requested_seconds": duration, "status": "running", "phases": [], "budget_before": before}
    write_json(folder / "manifest.json", {"schema_version": 1, "soak_id": soak_id, "suite": "runtime-v1",
        "duration_seconds": duration, "initial_phases": INITIAL_PHASES, "fill_phase": "network",
        "artifact_limit_bytes": 2_147_483_648, "budget_read_only": True})
    def stop(signum, frame):
        raise SoakInterrupted()
    previous = {sig: signal.signal(sig, stop) for sig in (signal.SIGINT, signal.SIGTERM)}
    child = sentinel = None
    current_run = None
    sentinel_survived = True
    try:
        sentinel = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(2000)"], env=isolated_environment())
        phase = 0
        while time.monotonic() < deadline:
            remaining = deadline-time.monotonic()
            if remaining < 30:
                time.sleep(min(1, remaining))
                continue
            if sum(p["artifact_bytes"] for p in report["phases"]) + config.limits.max_artifact_bytes > 2_147_483_648:
                raise ValueError("Soak artifact cap reached")
            mode, target = INITIAL_PHASES[phase] if phase < len(INITIAL_PHASES) else ("network", 300)
            seconds = min(target, int(remaining)-1)
            command = [sys.executable, "-B", "-m", "melee_agent.cli", "capture", "--policy", "faults",
                "--fault", mode, "--duration", str(seconds)]
            child = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                env=isolated_environment(), start_new_session=True)
            if not select.select([child.stdout], [], [], 35)[0]:
                raise ValueError("Phase startup output timed out")
            first = child.stdout.readline(4097)
            event = json.loads(first)
            if event.get("event") != "started":
                raise ValueError("Phase failed before startup")
            current_run = locate_run(root, event["run_id"])
            print(json.dumps({"event": "soak_phase_started", "soak_id": soak_id,
                "phase": phase+1, "mode": mode, "duration": seconds, "run_id": event["run_id"]}), flush=True)
            raw, _ = child.communicate(timeout=seconds+20)
            ended_ns = time.monotonic_ns()
            if len(raw) > 2_097_152:
                raise ValueError("Phase output exceeded its bound")
            result = assess_run(current_run, mode, ended_ns)
            sentinel_survived = sentinel_survived and sentinel.poll() is None
            if not sentinel_survived:
                result["errors"].append("unrelated_sentinel_stopped")
                result["status"] = "fail"
            write_json(folder / (f"phase-{phase+1:02d}.json"), result)
            report["phases"].append(result)
            print(json.dumps({"event": "soak_phase_finished", "phase": phase+1, "mode": mode,
                "status": result["status"], "errors": result["errors"], "game_frames": result["audit"]["game_frames"]}), flush=True)
            child = None
            current_run = None
            phase += 1
            if result["status"] != "pass":
                raise ValueError("A phase failed its expected outcome")
        report["status"] = "pass"
    except SoakInterrupted:
        report.update(status="interrupted", reason="stop_requested")
    except Exception as error:
        report.update(status="fail", error_type=type(error).__name__)
    finally:
        if child is not None and child.poll() is None:
            if current_run is not None:
                (current_run / "stop.request").touch(exist_ok=True)
                try:
                    child.communicate(timeout=10)
                except subprocess.TimeoutExpired:
                    terminate_child(child)
            else:
                terminate_child(child)
        if sentinel is not None:
            sentinel_survived = sentinel_survived and sentinel.poll() is None
            terminate_child(sentinel)
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        report["elapsed_seconds"] = time.monotonic()-started
        report["unrelated_sentinel_survived"] = sentinel_survived
        counts = Counter()
        for phase in report["phases"]:
            counts.update(phase["fault_counts"])
        report["fault_counts"] = dict(counts)
        report["missing_faults"] = sorted(REQUIRED_FAULTS-set(counts))
        report["budget_after"] = ledger.report()
        report["paid_budget_unchanged"] = report["budget_after"] == before
        if report["missing_faults"] or not report["paid_budget_unchanged"] or not sentinel_survived:
            report["status"] = "fail"
        write_json(folder / "summary.json", report)
        print(json.dumps({"event": "soak_finished", "soak_id": soak_id, "status": report["status"],
            "elapsed_seconds": report["elapsed_seconds"], "phases": len(report["phases"]),
            "missing_faults": report["missing_faults"], "paid_budget_unchanged": report["paid_budget_unchanged"]}), flush=True)
    return 0 if report["status"] == "pass" else 2
