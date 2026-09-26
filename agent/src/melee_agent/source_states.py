"""Explicit capture/replay adapters into the same validated observation contract."""

from copy import deepcopy
from types import SimpleNamespace

from .engine import Observation
from .live_control import observe
from .raw_observation import LifeTracker, RawStreamTap, normalized_hurtbox, player_record
from .replay import expected_settings, summarize_file


def captured_observation(row):
    if row.get("menu") != "IN_GAME":
        raise ValueError("Capture row is not a gameplay observation")
    data = row["control"]["observation"]
    version = data.get("schema_version")
    if version == 3:
        # An explicit historical adapter, never an assumed vulnerable target.
        data = deepcopy(data)
        for name, port in (("bot", "1"), ("opponent", "2")):
            if "hurtbox_state" in data[name]["details"]:
                raise ValueError("Unexpected hurtbox field in historical schema")
            raw = row.get("raw_observation", {}).get("players", {}).get(port, {}).get("raw_post", {})
            data[name]["details"]["hurtbox_state"] = normalized_hurtbox(raw)
        data["schema_version"] = 4
    observation = Observation.parse(data)
    if (row.get("episode"), row.get("frame")) != (observation.episode, observation.frame):
        raise ValueError("Capture identity does not match observation")
    return observation


def replay_observations(path, *, episode=1, maximum_bytes=268435456, maximum_frames=40000, phase="regulation"):
    """Read an already-owned completed file; never create a runtime or controller.

    Only the pinned adapter's supported Fox/Mario Battlefield format is accepted.
    Missing mandatory combat flags fail explicitly; optional hurtbox availability
    remains nullable. Controller commitment is absent from a standalone replay.
    """
    import melee
    if type(episode) is not int or episode < 1 or type(maximum_frames) is not int or not 1 <= maximum_frames <= 40000:
        raise ValueError("Invalid replay extraction bound")
    summary = summarize_file(path, maximum_bytes)
    if not expected_settings(summary["settings"], phase=phase):
        raise ValueError("Unsupported replay matchup or rules")
    console = melee.Console(path=str(path), is_dolphin=False)
    if console.temp_dir is not None or console._process is not None or console.controllers:
        raise ValueError("Replay extraction unexpectedly owns runtime resources")
    raw_stream, lives = RawStreamTap(console), LifeTracker()
    try:
        if not console.connect():
            raise ValueError("Replay file could not be opened")
        count = 0
        previous = None
        while (state := console.step()) is not None:
            if state.menu_state != melee.Menu.IN_GAME:
                continue
            if previous is not None and int(state.frame) != previous+1:
                raise ValueError("Replay frames are not a contiguous forward episode")
            previous = int(state.frame)
            if count == 0 and phase == "sudden_death" and (
                    previous != -123 or any(int(state.players[p].stock) != 1 or
                        float(state.players[p].percent) != 300 for p in (1, 2))):
                raise ValueError("Unverified Sudden Death replay start")
            raw = {str(port): player_record(state.players[port], raw_stream.take(int(state.frame), port),
                episode, port, lives, console.zero_indices) for port in (1, 2)}
            yield observe(state, episode, SimpleNamespace(now_ns=lambda: 0), raw,
                starting_stocks=1 if phase == "sudden_death" else 4,
                time_limit_seconds=None if phase == "sudden_death" else 480), raw
            count += 1
            if count >= maximum_frames:
                return
    finally:
        # In file mode temp_dir and _process remain None, so stop only closes
        # the file-stream adapter; no profile deletion or process kill occurs.
        assert console.temp_dir is None and console._process is None
        console.stop()
