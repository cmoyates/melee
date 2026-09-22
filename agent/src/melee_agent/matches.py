"""Bounded local match supervisor, with an independent CLI-liveness watchdog."""

import fcntl
import hashlib
import json
import os
from pathlib import Path
import select
import signal
import stat
import subprocess
import sys
import time
import uuid

from .config import load_config, owned_path, read_path
from .doctor import STOCK_DISC_SHA1, STOCK_DOL_SHA1, digest
from .match_worker import write_json
from .stage import STAGE_NAME, STAGE_ID
from .rules import STARTING_STOCKS, TIME_LIMIT_SECONDS


def isolated_environment():
    # Emulator and ordinary workers never receive provider credentials.
    keep = ("PATH", "HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "TMPDIR", "DISPLAY")
    env = {key: os.environ[key] for key in keep if key in os.environ}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def artifact_bytes(root):
    total = 0
    def scan_error(error):
        raise error
    for directory, dirs, files in os.walk(root, followlinks=False, onerror=scan_error):
        for name in files:
            try:
                info = (Path(directory) / name).lstat()
            except FileNotFoundError:
                continue  # The runtime may rename a replay while we scan it.
            if stat.S_ISREG(info.st_mode):
                total += info.st_size
    return total


def terminate_child(child):
    if child is None or child.poll() is not None:
        return
    child.terminate()
    try:
        child.wait(timeout=3)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait(timeout=3)


def preflight(root, duration, episodes, policy, capture=False):
    config = load_config(root)
    if type(duration) is not int or not 1 <= duration <= config.limits.max_run_seconds:
        raise ValueError("Duration must fit the configured run limit")
    if type(capture) is not bool:
        raise ValueError("Invalid capture mode")
    if type(episodes) is not int or not 1 <= episodes <= (100 if capture else 10) or (policy == "input-probe" and episodes != 1):
        raise ValueError("Choose 1-10 matches, or exactly one input probe; captures allow 100 episodes")
    if policy not in ("smoke", "scripted", "input-probe", "skill-check", "delayed-fake", "jev", "faults", "scenario"):
        raise ValueError("Unknown local policy")
    if not config.disc_image or not config.runtime or not config.runtime_sha256:
        raise ValueError("Configure the verified local disc and runtime first")
    runtime = read_path(root, config.runtime).resolve()
    image = read_path(root, config.disc_image).resolve()
    if digest(runtime, "sha256") != config.runtime_sha256 or not os.access(runtime, os.X_OK):
        raise ValueError("Runtime fingerprint or executable permission mismatch")
    if digest(image, "sha1") != STOCK_DISC_SHA1:
        raise ValueError("Full stock disc fingerprint mismatch")
    if digest(read_path(root, config.stock_dol), "sha1") != STOCK_DOL_SHA1:
        raise ValueError("Stock DOL fingerprint mismatch")
    import importlib.metadata
    distribution = importlib.metadata.distribution("melee")
    source = json.loads(distribution.read_text("direct_url.json") or "{}")
    if (distribution.version != "0.47.3" or
            source.get("vcs_info", {}).get("commit_id") != "bce21f09984b286e6d36bfd2939e4cd4691f94c2"):
        raise ValueError("Install the locked runtime extra")
    return config, runtime, image


def probe_passed(samples):
    right = [s for s in samples if 3 <= s["frame"] <= 19]
    left = [s for s in samples if 43 <= s["frame"] <= 59]
    neutral = [s for s in samples if 75 <= s["frame"] <= 100]
    return (len(right) >= 5 and len(left) >= 5 and len(neutral) >= 5 and
            any(s["main_x"] > 0.9 for s in right) and
            any(s["main_x"] < 0.1 for s in left) and
            any(abs(s["main_x"] - 0.5) < 0.01 for s in neutral) and
            right[-1]["x"] > right[0]["x"] + 1 and left[-1]["x"] < left[0]["x"] - 1)


def read_worker_result(path):
    """A crashed worker may leave no result or a partial JSON file."""
    empty = {"episodes": [], "neutralized": False}
    try:
        with path.open("rb") as handle:
            raw = handle.read(1_048_577)
        if len(raw) > 1_048_576:
            raise ValueError("Worker result exceeds bound")
        result = json.loads(raw)
        if (not isinstance(result, dict) or not isinstance(result.get("episodes"), list) or
                not all(isinstance(e, dict) for e in result["episodes"]) or
                type(result.get("neutralized")) is not bool or
                result.get("status") not in ("error", "interrupted", "matches_complete", "probe_complete", "skill_check_complete", "scenario_complete")):
            raise ValueError("Invalid worker result")
        if "recorder" in result:
            recorder = result["recorder"]
            if (not isinstance(recorder, dict) or recorder.get("status") not in ("running", "closed", "error") or
                    type(recorder.get("writer_stopped")) is not bool or
                    any(type(recorder.get(k)) is not int or recorder[k] < 0
                        for k in ("accepted", "written", "unwritten", "rejected")) or
                    recorder["accepted"] != recorder["written"] + recorder["unwritten"]):
                raise ValueError("Invalid recorder result")
        if "async_policy" in result:
            report = result["async_policy"]
            if not isinstance(report, dict) or not isinstance(report.get("bridge"), dict) or not isinstance(report.get("policy"), dict):
                raise ValueError("Invalid policy report")
            bridge = report["bridge"]
            if (any(type(bridge.get(k)) is not int or bridge[k] < 0 for k in
                    ("worker_limit", "workers_alive", "inflight", "mailbox_remaining")) or
                    not 1 <= bridge["worker_limit"] <= 4 or bridge["workers_alive"] > bridge["worker_limit"] or
                    bridge["inflight"] > bridge["worker_limit"] or bridge["mailbox_remaining"] > 32 or
                    any(type(v) is not int or v < 0 for v in report["policy"].values())):
                raise ValueError("Invalid policy counters")
            provider = bridge.get("provider")
            if provider is not None:
                if (not isinstance(provider, dict) or not isinstance(provider.get("attempts"), list) or
                        len(provider["attempts"]) > 200 or not all(isinstance(a, dict) for a in provider["attempts"]) or
                        not isinstance(provider.get("client_shutdown"), dict) or
                        any(type(provider.get(k)) is not int or provider[k] < 0 for k in ("http_calls", "http_active")) or
                        any(type(provider["client_shutdown"].get(k)) is not int or provider["client_shutdown"][k] < 0
                            for k in ("workers_alive", "timers_alive"))):
                    raise ValueError("Invalid provider shutdown report")
        if "state_receiver" in result and (not isinstance(result["state_receiver"], dict) or
                type(result["state_receiver"].get("stopped")) is not bool):
            raise ValueError("Invalid receiver shutdown report")
        return result, None
    except (OSError, ValueError, UnicodeError) as error:
        return empty, type(error).__name__


def supervise(root, duration, episodes, policy, capture=False, skill_repeats=20, budget_directory=None, max_requests=None, fault_mode=None, scenario_name=None):
    from .replay import expected_settings, summarize_file
    from .live_provider import preflight as provider_preflight, provider_environment
    provider_budget = provider_preflight(root, policy, budget_directory, max_requests)
    from .runtime_faults import MODES
    if (policy == "faults" and fault_mode not in MODES) or (policy != "faults" and fault_mode is not None):
        raise ValueError("Runtime fault injection requires its explicit policy and mode")
    from .scenarios import find_scenario, verified_trial
    if policy == "scenario":
        find_scenario(scenario_name)
        if capture or episodes != 1:
            raise ValueError("Scenarios require one fresh-match trial")
    elif scenario_name is not None:
        raise ValueError("Scenario setup requires its explicit policy")
    config, runtime, image = preflight(root, duration, episodes, policy, capture)
    if type(skill_repeats) is not int or not 1 <= skill_repeats <= 100:
        raise ValueError("Invalid skill repetitions")
    base = owned_path(root, config.run_root)
    base.mkdir(parents=True, exist_ok=True)
    lock_path = root / "build/jev/match.lock"
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as lease:
        try:
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("Another Jev match runner owns the launch lease") from None
        # Fail closed on process inspection errors; never stop a pre-existing game.
        existing = subprocess.run(["pgrep", "-if", "Dolphin.app/Contents/MacOS|Slippi Dolphin.app/Contents/MacOS"],
                                    capture_output=True, timeout=5)
        if existing.returncode != 1:
            raise ValueError("An emulator is already running or process inspection is unavailable")
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as port_probe:
            port_probe.bind(("127.0.0.1", config.slippi_port))
        run_id = "match-" + uuid.uuid4().hex
        run_dir = base / run_id
        run_dir.mkdir()
        (run_dir / "replays").mkdir()
        options = {"schema_version": 2, "run_id": run_id, "runtime": str(runtime), "disc": str(image),
                    "runtime_sha256": config.runtime_sha256, "disc_sha1": STOCK_DISC_SHA1,
                    "libmelee_commit": "bce21f09984b286e6d36bfd2939e4cd4691f94c2",
                    "duration_seconds": duration, "port": config.slippi_port,
                    "max_frame_bytes": config.limits.max_artifact_bytes * 7 // 8,
                    "capture_until_deadline": capture,
                    "fault_mode": fault_mode,
                    "run_deadline_ns": time.monotonic_ns() + int(duration * 1e9),
                    "provider_enabled": policy == "jev", "budget_directory": budget_directory,
                    "max_provider_requests": max_requests, "provider_budget_before": provider_budget,
                    "skill_repeats": skill_repeats,
                    "scenario_name": scenario_name,
                    "source_sha256": {p.name: digest(p, "sha256") for p in sorted(Path(__file__).parent.glob("*.py"))},
                    "policy": policy, "episodes": episodes, "provider_contacted": False,
                    "stage": STAGE_NAME, "stage_id": STAGE_ID,
                    "match_time_limit_seconds": TIME_LIMIT_SECONDS, "starting_stocks": STARTING_STOCKS}
        write_json(run_dir / "launch.json", options)
        print(json.dumps({"event": "started", "run_id": run_id}), flush=True)
        worker = emulator = None
        reason = "worker_error"
        started = time.monotonic()
        deadline = started + duration
        requested_stop = False
        supervisor_error = None
        cleanup_errors = []
        def stop(signum, frame):
            nonlocal requested_stop
            requested_stop = True
        previous_signals = {sig: signal.signal(sig, stop) for sig in (signal.SIGINT, signal.SIGTERM)}
        try:
            with (run_dir / "worker.log").open("x") as worker_log, (run_dir / "emulator.log").open("x") as emulator_log:
                worker = subprocess.Popen([sys.executable, "-B", "-m", "melee_agent.match_worker", str(run_dir)],
                    stdout=worker_log, stderr=subprocess.STDOUT, env=provider_environment(policy), start_new_session=True)
                write_json(run_dir / "worker-process.json", {"pid": worker.pid, "pgid": worker.pid})
                last_size_check = 0
                while True:
                    now = time.monotonic()
                    # CLI keeps stdin open. EOF means its parent died; stop owned children.
                    if select.select([sys.stdin], [], [], 0)[0] and os.read(sys.stdin.fileno(), 1) == b"":
                        reason = "controller_disconnected"
                        break
                    if requested_stop or (run_dir / "stop.request").exists():
                        reason = "stopped"
                        break
                    if now >= deadline:
                        reason = "timeout"
                        break
                    if worker.poll() is not None:
                        reason = "worker_finished" if worker.returncode == 0 else "worker_error"
                        break
                    if emulator is None and (run_dir / "ready.json").exists():
                        emulator = subprocess.Popen([str(runtime), "-e", str(image), "-u", str(run_dir / "profile")],
                            stdout=emulator_log, stderr=subprocess.STDOUT, env=isolated_environment(), start_new_session=True)
                        write_json(run_dir / "processes.json", {"supervisor_pid": os.getpid(),
                            "supervisor_pgid": os.getpgrp(), "worker_pid": worker.pid,
                            "worker_pgid": worker.pid, "emulator_pid": emulator.pid, "emulator_pgid": emulator.pid})
                    if emulator is not None and emulator.poll() is not None:
                        reason = "emulator_exited"
                        break
                    progress = run_dir / "frames.jsonl"
                    if progress.exists() and time.time() - progress.stat().st_mtime > 15:
                        reason = "state_stalled"
                        break
                    if not progress.exists() and now - started > 30:
                        reason = "startup_timeout"
                        break
                    if now - last_size_check >= 1:
                        if artifact_bytes(run_dir) >= config.limits.max_artifact_bytes:
                            reason = "artifact_limit"
                            break
                        last_size_check = now
                    time.sleep(0.1)
        except Exception as error:
            reason = "supervisor_error"
            supervisor_error = type(error).__name__
        finally:
            # Attempt each cleanup even when its sibling's cleanup fails.
            for name, child in (("worker", worker), ("emulator", emulator)):
                try:
                    terminate_child(child)
                except (OSError, subprocess.SubprocessError) as error:
                    cleanup_errors.append({"process": name, "error_type": type(error).__name__})
            for sig, handler in previous_signals.items():
                signal.signal(sig, handler)
        result_path = run_dir / "worker-result.json"
        result, result_error = read_worker_result(result_path)
        if reason == "worker_finished" and result_error:
            reason = "worker_result_invalid"
        if reason == "worker_finished" and result.get("status") == "error":
            reason = "worker_error"
        replays = []
        replay_errors = 0
        for path in sorted((run_dir / "replays").glob("*.slp")):
            try:
                replays.append(summarize_file(path, config.limits.max_artifact_bytes))
            except (ValueError, OSError, KeyError, TypeError):
                replay_errors += 1
        complete = (reason == "worker_finished" and result.get("status") == "matches_complete" and
                    len(result["episodes"]) == episodes and
                    all(e.get("result_event_verified") is True for e in result["episodes"]) and
                    len(replays) == episodes and replay_errors == 0 and
                    all(r["outcome"] in ("game", "time") and expected_settings(r["settings"]) for r in replays))
        try:
            probe_ok = (reason == "worker_finished" and result.get("status") == "probe_complete" and
                        probe_passed(result.get("probe_samples", [])))
        except (KeyError, TypeError, ValueError):
            probe_ok = False
            reason = "worker_result_invalid"
        stopped = all(child is None or child.poll() is not None for child in (worker, emulator))
        if cleanup_errors or not stopped or not result["neutralized"]:
            complete = probe_ok = False
        recorder = result.get("recorder", {})
        if recorder and (recorder["status"] != "closed" or recorder["unwritten"] or recorder["rejected"] or
                            not recorder["writer_stopped"]):
            complete = probe_ok = False
        receiver_closed = result.get("state_receiver", {}).get("stopped", True) is True
        if not receiver_closed:
            complete = probe_ok = False
        captured = (capture and reason == "timeout" and result.get("status") == "interrupted" and
                    result["neutralized"] and stopped and receiver_closed and not cleanup_errors and bool(result["episodes"]) and
                    recorder.get("status") == "closed" and recorder.get("unwritten") == 0 and
                    recorder.get("rejected") == 0 and recorder.get("writer_stopped") is True)
        if policy in ("delayed-fake", "jev", "faults"):
            bridge_report = result.get("async_policy", {}).get("bridge", {})
            async_closed = (bridge_report.get("workers_alive") == 0 and bridge_report.get("inflight") == 0)
            if policy in ("jev", "faults"):
                provider_report = bridge_report.get("provider") or {}
                client_shutdown = provider_report.get("client_shutdown") or {}
                async_closed = (async_closed and provider_report.get("http_active") == 0 and
                    client_shutdown.get("workers_alive") == 0 and client_shutdown.get("timers_alive") == 0)
            if not async_closed:
                captured = complete = probe_ok = False
        skill_report = result.get("skill_check", {})
        from .skill_check import verified_report
        skill_ok = (policy == "skill-check" and reason == "worker_finished" and result.get("status") == "skill_check_complete" and
                    verified_report(skill_report, skill_repeats) and result["neutralized"] and stopped and receiver_closed and not cleanup_errors and
                    recorder.get("status") == "closed" and recorder.get("unwritten") == 0 and recorder.get("rejected") == 0)
        scenario_ok = (policy == "scenario" and reason == "worker_finished" and result.get("status") == "scenario_complete" and
            verified_trial(result.get("scenario", {}), scenario_name) and result["neutralized"] and stopped and receiver_closed and
            not cleanup_errors and recorder.get("status") == "closed" and recorder.get("unwritten") == 0 and
            recorder.get("rejected") == 0 and recorder.get("writer_stopped") is True)
        status = "scenario_recorded" if scenario_ok else "skills_verified" if skill_ok else "captured" if captured else "complete" if complete else "probe_verified" if probe_ok else "incomplete"
        summary = {"schema_version": 1, "run_id": run_id, "status": status, "reason": reason,
                    "policy": policy, "episodes": result["episodes"], "replays": replays,
                    "replay_errors": replay_errors, "neutralized": result["neutralized"],
                    "elapsed_seconds": time.monotonic() - started,
                    "provider_contacted": bool(policy == "jev" and provider_report.get("http_calls", 0)),
                    "emulator_stopped": emulator is None or emulator.poll() is not None,
                    "worker_stopped": worker is None or worker.poll() is not None}
        summary["processes"] = {name: None if child is None else
            {"pid": child.pid, "pgid": child.pid, "exit_code": child.poll()}
            for name, child in (("worker", worker), ("emulator", emulator))}
        if not result["neutralized"]:
            summary["neutralization_failure"] = "worker_result_unavailable" if result_error else "worker_reported_failure"
        if supervisor_error:
            summary["supervisor_error_type"] = supervisor_error
        if result_error:
            summary["worker_result_error_type"] = result_error
        if cleanup_errors:
            summary["cleanup_errors"] = cleanup_errors
        if "error_type" in result:
            summary["worker_error_type"] = result["error_type"]
        for key in ("recorder", "failure_reason", "skill_check", "async_policy", "fault_injection", "last_unrecorded_record", "state_receiver", "scenario"):
            if key in result:
                summary[key] = result[key]
        try:
            write_json(run_dir / "summary.json", summary)
        except OSError as error:
            # Disk-full cannot promise a durable report. Preserve truthful stdout.
            summary.update(status="incomplete", reason="summary_write_failed",
                            prior_reason=reason, summary_error_type=type(error).__name__)
            complete = probe_ok = captured = skill_ok = scenario_ok = False
        print(json.dumps(summary), flush=True)
        return 0 if complete or probe_ok or captured or skill_ok or scenario_ok else 2


def launch(root, duration, episodes, policy, capture=False, skill_repeats=20, budget_directory=None, max_requests=None, fault_mode=None, scenario_name=None):
    from .live_provider import provider_environment
    command = [sys.executable, "-B", "-m", "melee_agent.matches", str(root), str(duration), str(episodes), policy,
                str(int(capture)), str(skill_repeats), budget_directory or "", str(max_requests or 0), fault_mode or "", scenario_name or ""]
    supervisor = subprocess.Popen(command, stdin=subprocess.PIPE, start_new_session=True, env=provider_environment(policy))
    try:
        return supervisor.wait()
    except KeyboardInterrupt:
        supervisor.stdin.close()  # Watchdog observes EOF and cleans up its children.
        return supervisor.wait(timeout=15)
    finally:
        if not supervisor.stdin.closed:
            supervisor.stdin.close()


def locate_run(root, run_id):
    if not run_id.startswith("match-") or len(run_id) != 38 or any(c not in "0123456789abcdef" for c in run_id[6:]):
        raise ValueError("Invalid run ID")
    config = load_config(root)
    run = owned_path(root, str(read_path(root, config.run_root) / run_id))
    if not run.is_dir():
        raise ValueError("Run not found")
    return run


if __name__ == "__main__":
    try:
        raise SystemExit(supervise(Path(sys.argv[1]).resolve(), int(sys.argv[2]), int(sys.argv[3]), sys.argv[4],
                                    len(sys.argv) > 5 and sys.argv[5] == "1", int(sys.argv[6]) if len(sys.argv) > 6 else 20,
                                    sys.argv[7] or None if len(sys.argv) > 7 else None,
                                    (int(sys.argv[8]) or None) if len(sys.argv) > 8 else None,
                                    (sys.argv[9] or None) if len(sys.argv) > 9 else None,
                                    (sys.argv[10] or None) if len(sys.argv) > 10 else None))
    except Exception as error:
        print(json.dumps({"status": "blocked", "error_type": type(error).__name__,
                            "message": "Match setup failed; check local runtime configuration and launch availability."}))
        raise SystemExit(1)
