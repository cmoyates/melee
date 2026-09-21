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
    # Emulator/worker do not need provider credentials or dotenv configuration.
    keep = ("PATH", "HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "TMPDIR", "DISPLAY")
    env = {key: os.environ[key] for key in keep if key in os.environ}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def artifact_bytes(root):
    total = 0
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in files:
            info = (Path(directory) / name).lstat()
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


def preflight(root, duration, episodes, policy):
    config = load_config(root)
    if type(duration) is not int or not 1 <= duration <= config.limits.max_run_seconds:
        raise ValueError("Duration must fit the configured run limit")
    if not 1 <= episodes <= 10 or (policy == "input-probe" and episodes != 1):
        raise ValueError("Choose 1-10 matches, or exactly one input probe")
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


def supervise(root, duration, episodes, policy):
    from .replay import expected_settings, summarize_file
    config, runtime, image = preflight(root, duration, episodes, policy)
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
        options = {"schema_version": 1, "run_id": run_id, "runtime": str(runtime), "disc": str(image),
                    "runtime_sha256": config.runtime_sha256, "disc_sha1": STOCK_DISC_SHA1,
                    "libmelee_commit": "bce21f09984b286e6d36bfd2939e4cd4691f94c2",
                    "duration_seconds": duration, "port": config.slippi_port,
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
        def stop(signum, frame):
            nonlocal requested_stop
            requested_stop = True
        signal.signal(signal.SIGINT, stop)
        signal.signal(signal.SIGTERM, stop)
        try:
            with (run_dir / "worker.log").open("x") as worker_log, (run_dir / "emulator.log").open("x") as emulator_log:
                worker = subprocess.Popen([sys.executable, "-B", "-m", "melee_agent.match_worker", str(run_dir)],
                    stdout=worker_log, stderr=subprocess.STDOUT, env=isolated_environment(), start_new_session=True)
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
                            "worker_pid": worker.pid, "emulator_pid": emulator.pid})
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
        finally:
            # A controller cleanup failure cannot prevent emulator cleanup.
            try:
                terminate_child(worker)
            finally:
                terminate_child(emulator)
        result_path = run_dir / "worker-result.json"
        result = json.loads(result_path.read_text()) if result_path.exists() else {"episodes": [], "neutralized": False}
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
                    len(replays) == episodes and replay_errors == 0 and
                    all(r["outcome"] in ("game", "time") and expected_settings(r["settings"]) for r in replays))
        probe_ok = (reason == "worker_finished" and result.get("status") == "probe_complete" and
                    probe_passed(result.get("probe_samples", [])))
        status = "complete" if complete else "probe_verified" if probe_ok else "incomplete"
        summary = {"schema_version": 1, "run_id": run_id, "status": status, "reason": reason,
                    "policy": policy, "episodes": result["episodes"], "replays": replays,
                    "replay_errors": replay_errors, "neutralized": result["neutralized"],
                    "elapsed_seconds": time.monotonic() - started, "provider_contacted": False,
                    "emulator_stopped": emulator is None or emulator.poll() is not None,
                    "worker_stopped": worker is None or worker.poll() is not None}
        if "error_type" in result:
            summary["worker_error_type"] = result["error_type"]
        write_json(run_dir / "summary.json", summary)
        print(json.dumps(summary), flush=True)
        return 0 if complete or probe_ok else 2


def launch(root, duration, episodes, policy):
    command = [sys.executable, "-B", "-m", "melee_agent.matches", str(root), str(duration), str(episodes), policy]
    supervisor = subprocess.Popen(command, stdin=subprocess.PIPE, start_new_session=True, env=isolated_environment())
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
        raise SystemExit(supervise(Path(sys.argv[1]).resolve(), int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]))
    except Exception as error:
        print(json.dumps({"status": "blocked", "error_type": type(error).__name__,
                            "message": "Match setup failed; check local runtime configuration and launch availability."}))
        raise SystemExit(1)
