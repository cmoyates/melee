"""Controller worker. The separate supervisor owns the emulator process."""

import json
import os
from pathlib import Path
import signal
import sys
import time

from .stage import STAGE_NAME, STAGE_ID, PLATFORMS, support_surface
from .engine import FrameExecutor, ScriptedPolicy
from .live_control import LibmeleeSink, SystemClock, observe
from .rules import STARTING_STOCKS
from .recorder import FrameRecorder, RecorderError
from .raw_observation import LifeTracker, RawStreamTap, player_record, stage_record
from .input_trace import InputTrace


class StopRequested(BaseException):
    """Not InterruptedError: multiprocessing retries that exception internally."""


def write_json(path, value):
    with path.open("x") as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write("\n")


def run(run_dir):
    import melee
    options = json.loads((run_dir / "launch.json").read_text())
    console = None
    controllers = []
    recorder = None
    policy = None
    faults = None
    pending_record = None
    outcome = {"status": "error", "episodes": [], "neutralized": False}
    def interrupted(signum, frame):
        raise StopRequested()
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    try:
        if options["policy"] == "faults":
            from .runtime_faults import RuntimeFaults
            faults = RuntimeFaults(run_dir, options["fault_mode"])
        console = melee.Console(
            path=options["runtime"], dolphin_home_path=str(run_dir / "profile"),
            tmp_home_directory=False, copy_home_directory=False,
            fullscreen=False, disable_audio=True, gfx_backend="OGL",
            blocking_input=False, polling_mode=True, polling_timeout=0.01,
            slippi_port=options["port"], replay_dir=str(run_dir / "replays"),
            replay_monthly_folders=False, save_replays=True,
            infinite_time=False, instant_match_restart=False)
        raw_stream = RawStreamTap(console)
        lives = LifeTracker()
        controllers = [melee.Controller(console, port) for port in (1, 2)]
        if faults:
            faults.wrap_flush(controllers[0])
        input_trace = InputTrace(controllers[0])
        helpers = [melee.MenuHelper(), melee.MenuHelper()]
        write_json(run_dir / "ready.json", {"ready": True})
        if not console.connect():
            raise RuntimeError("state connection failed")
        receiver = getattr(getattr(console, "_slippstream", None), "_worker", None)
        if receiver is not None and receiver.pid is not None:
            write_json(run_dir / "state-receiver.json", {"pid": receiver.pid, "owner": "libmelee_worker"})
        for controller in controllers:
            controller.connect()
        clock = SystemClock()
        if options["policy"] == "scenario":
            from .scenarios import ScenarioPolicy, find_scenario
            policy = ScenarioPolicy(find_scenario(options["scenario_name"]))
        elif options["policy"] == "skill-check":
            from .skill_check import SkillCheckPolicy
            policy = SkillCheckPolicy(options["skill_repeats"])
        elif options["policy"] in ("delayed-fake", "jev", "faults"):
            from .async_policy import AsyncPolicy, LatestBridge
            bridge = None
            if options["policy"] == "jev":
                from .live_provider import ProviderBackend
                backend = ProviderBackend(Path(__file__).resolve().parents[3], options["budget_directory"],
                    options["max_provider_requests"], options["run_deadline_ns"])
                bridge = LatestBridge(options["run_id"], backend)
            elif faults:
                from .runtime_faults import FaultBackend
                backend = FaultBackend(Path(__file__).resolve().parents[3], run_dir, faults, options["run_deadline_ns"])
                bridge = LatestBridge(options["run_id"], backend)
            policy = AsyncPolicy(options["run_id"], bridge)
            if faults:
                original_decide = policy.decide
                def fault_decide(observation):
                    faults.before_control(observation)
                    return original_decide(observation)
                policy.decide = fault_decide
        else:
            policy = ScriptedPolicy(options["policy"])
        executor = FrameExecutor(policy, LibmeleeSink(controllers[0], melee.Button), clock)
        in_game = False
        last_frame = None
        episode = None
        probe_samples = []
        menu_identity = None
        menu_started = time.monotonic()
        recorder = FrameRecorder(run_dir / "frames.jsonl", max_bytes=options["max_frame_bytes"],
            opener=faults.opener(run_dir / "frames.jsonl") if faults and faults.mode == "logger_stall" else None)
        if faults:
            faults.recorder = recorder
        with recorder as frames:
            while True:
                frames.check()
                state = console.step()  # Flushes preceding complete controller packet first.
                if state is None:
                    continue
                if faults and faults.mode == "frame_stall" and faults.triggered:
                    continue
                now = time.monotonic()
                if state.menu_state != menu_identity:
                    menu_identity = state.menu_state
                    menu_started = now
                if state.menu_state != melee.Menu.IN_GAME and now - menu_started > 30:
                    raise RuntimeError("menu transition deadline exceeded")
                if state.menu_state == melee.Menu.SLIPPI_ONLINE_CSS:
                    raise RuntimeError("unexpected online menu")
                if state.menu_state == melee.Menu.IN_GAME:
                    if set(state.players) != {1, 2} or state.is_teams:
                        raise RuntimeError("unexpected controller roles")
                    a, b = state.players[1], state.players[2]
                    if (a.character != melee.Character.FOX or b.character != melee.Character.MARIO or
                            a.cpu_level != 0 or b.cpu_level != 3 or state.stage != melee.Stage.BATTLEFIELD):
                        raise RuntimeError("unexpected matchup")
                    if not in_game:
                        if int(a.stock) != STARTING_STOCKS or int(b.stock) != STARTING_STOCKS:
                            raise RuntimeError("unexpected starting stocks")
                        episode = {"episode": len(outcome["episodes"]) + 1, "first_frame": int(state.frame),
                                    "last_frame": int(state.frame), "observations": 0, "gaps": 0,
                                    "duplicates": 0, "rollbacks": 0, "started_monotonic": now}
                        outcome["episodes"].append(episode)
                        last_frame = None
                        in_game = True
                    current = int(state.frame)
                    if faults and faults.drop_state(current):
                        continue
                    if last_frame is not None:
                        delta = current - last_frame
                        episode["gaps"] += max(0, delta - 1)
                        episode["duplicates"] += int(delta == 0)
                        episode["rollbacks"] += int(delta < 0)
                    last_frame = current
                    episode["last_frame"] = current
                    episode["last_monotonic"] = now
                    elapsed = now - episode["started_monotonic"]
                    episode["simulation_fps"] = (current - episode["first_frame"]) / elapsed if elapsed else None
                    episode["observations"] += 1
                    episode["last_stocks"] = [int(a.stock), int(b.stock)]
                    if options["policy"] == "input-probe" and 0 <= current <= 100:
                        probe_samples.append({"frame": current, "x": float(a.position.x),
                                                "main_x": float(a.controller_state.main_stick[0])})
                    provenance = input_trace.observation(episode["episode"], current, a.controller_state)
                    raw_players = {str(p): player_record(v, raw_stream.take(current, p),
                        episode["episode"], p, lives, console.zero_indices) for p, v in state.players.items()}
                    control = executor.step(observe(state, episode["episode"], clock, raw_players))
                    packet_id = input_trace.queue(control)
                    controllers[1].release_all()
                    record = {"schema_version": 4, "run_id": options["run_id"],
                                "episode": episode["episode"], "frame": current,
                                "monotonic": now, "menu": "IN_GAME", "control": control,
                                "raw_observation": {"schema_version": 2, "players": raw_players,
                                    "slippi_version": [int(v) for v in console.slp_version_tuple], "stage": stage_record()},
                                "attempted_packet_id": packet_id, "input_provenance": provenance,
                                "stage": STAGE_NAME, "stage_id": STAGE_ID,
                                "platforms": PLATFORMS,
                                "players": {str(p): {"character": v.character.name, "stock": int(v.stock),
                                    "percent": float(v.percent), "x": float(v.position.x), "y": float(v.position.y),
                                    "action_id": int(v.action.value), "action_frame": int(v.action_frame),
                                    "grounded": bool(v.on_ground), "jumps": int(v.jumps_left),
                                    "support_surface_derived": support_surface(float(v.position.x), float(v.position.y), bool(v.on_ground)),
                                    "observed_main": [float(x) for x in v.controller_state.main_stick]}
                                    for p, v in state.players.items()}}
                    if hasattr(policy, "trace"):
                        record["scenario" if options["policy"] == "scenario" else "skill"] = policy.trace()
                    if options["policy"] == "scenario" and policy.complete:
                        pending_record = record
                        frames.publish(record)
                        pending_record = None
                        outcome["status"] = "scenario_complete"
                        break
                    if options["policy"] == "skill-check" and policy.complete:
                        pending_record = record
                        frames.publish(record)
                        pending_record = None
                        outcome["status"] = "skill_check_complete"
                        break
                    if options["policy"] == "input-probe" and current >= 120:
                        episode["elapsed_seconds"] = now - episode["started_monotonic"]
                        outcome["probe_samples"] = probe_samples
                        outcome["status"] = "probe_complete"
                        pending_record = record
                        frames.publish(record)
                        pending_record = None
                        break
                else:
                    if in_game:
                        if state.menu_state not in (melee.Menu.POSTGAME_SCORES, melee.Menu.CHARACTER_SELECT):
                            raise RuntimeError("unexpected game exit scene: " + state.menu_state.name)
                        # Slippi skips the vanilla results screen. Require its recorded
                        # GAME/TIME event rather than treating CSS or stock zero as a result.
                        from .replay import expected_settings, summarize_file
                        end_deadline = time.monotonic() + 3
                        verified = None
                        while time.monotonic() < end_deadline:
                            paths = sorted((run_dir / "replays").glob("*.slp"))
                            if len(paths) == len(outcome["episodes"]):
                                try:
                                    candidate = summarize_file(paths[-1], 268435456)
                                    if candidate["outcome"] in ("game", "time") and expected_settings(candidate["settings"]):
                                        verified = candidate
                                        break
                                except (OSError, ValueError, KeyError):
                                    pass
                            time.sleep(0.1)
                        if verified is None:
                            raise RuntimeError("match end or settings could not be verified from replay")
                        episode["result_event_verified"] = True
                        episode["return_scene"] = state.menu_state.name
                        episode["winner_port"] = verified["winner_port"]
                        episode["elapsed_seconds"] = now - episode["started_monotonic"]
                        in_game = False
                        input_trace.leave_game()
                        if len(outcome["episodes"]) >= options["episodes"]:
                            # Allow the runtime's replay writer to finish the end event.
                            time.sleep(1)
                            outcome["status"] = "matches_complete"
                            break
                    ready = (2 in state.players and state.players[2].character == melee.Character.MARIO and
                                state.players[2].cpu_level == 3 and state.players[2].coin_down)
                    helpers[1].menu_helper_simple(state, controllers[1], melee.Character.MARIO,
                        melee.Stage.BATTLEFIELD, cpu_level=3, autostart=False)
                    helpers[0].menu_helper_simple(state, controllers[0], melee.Character.FOX,
                        melee.Stage.BATTLEFIELD, autostart=ready or state.menu_state==melee.Menu.STAGE_SELECT)
                    record = {"schema_version": 1, "run_id": options["run_id"], "menu": state.menu_state.name,
                                "monotonic": now, "frame": int(state.frame)}
                pending_record = record
                frames.publish(record)
                pending_record = None
    except StopRequested:
        outcome["status"] = "interrupted"
    except RecorderError as error:
        outcome.update(status="error", error_type="RecorderError", failure_reason=str(error))
        if pending_record is not None:
            outcome["last_unrecorded_record"] = pending_record
    except Exception as error:
        # Detailed traceback stays in private worker.log. Public summary gets a type only.
        import traceback
        traceback.print_exc()
        outcome["error_type"] = type(error).__name__
    finally:
        neutralized = bool(controllers)
        for controller in controllers:
            try:
                controller.release_all()
                controller.flush()
                controller.disconnect()
            except (OSError, RuntimeError):
                neutralized = False
        outcome["neutralized"] = neutralized
        if faults:
            faults.release.set()
        if policy is not None and hasattr(policy, "close"):
            try:
                outcome["async_policy"] = policy.close()
            except Exception:
                outcome.update(status="error", failure_reason="policy_shutdown_failed")
        if options["policy"] == "skill-check" and policy is not None:
            outcome["skill_check"] = policy.report()
        if options["policy"] == "scenario" and policy is not None:
            outcome["scenario"] = policy.report()
        if recorder is not None:
            try:
                recorder.close()
            except RecorderError as error:
                outcome.update(status="error", error_type="RecorderError", failure_reason=str(error))
            outcome["recorder"] = recorder.report()
        if faults:
            outcome["fault_injection"] = faults.report()
        try:
            if console is not None:
                # No console.run(): emulator belongs to the supervisor. No temporary-home deletion.
                from .state_shutdown import stop_state_receiver
                outcome["state_receiver"] = stop_state_receiver(console)
                if not outcome["state_receiver"]["stopped"]:
                    outcome.update(status="error", failure_reason="state_receiver_shutdown_failed")
        finally:
            write_json(run_dir / "worker-result.json", outcome)


if __name__ == "__main__":
    run(Path(sys.argv[1]))
