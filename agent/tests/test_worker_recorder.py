"""Logger failures cross the worker boundary and still neutralize controllers."""

from enum import Enum
import errno
import json
from pathlib import Path
import signal
import struct
import tempfile
import threading
import time
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from melee_agent import match_worker
from melee_agent.engine import BUTTONS
from melee_agent.recorder import FrameRecorder


class WorkerRecorderTests(unittest.TestCase):
    def exercise(self, full_disk):
        events, recorders = [], []
        release = threading.Event()
        buttons = Enum("Button", {"BUTTON_" + name: i for i, name in enumerate((*BUTTONS, "MAIN", "C"))})
        characters = Enum("Character", {"FOX": 1, "MARIO": 0})
        stages = Enum("Stage", {"BATTLEFIELD": 31})
        menus = Enum("Menu", {"IN_GAME": 1, "SLIPPI_ONLINE_CSS": 2})

        class Writer:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def flush(self): pass
            def write(self, data):
                if full_disk:
                    raise OSError(errno.ENOSPC, "fixture")
                release.wait(timeout=5)
                return len(data)

        class Console:
            def __init__(self, **kwargs):
                self.controllers, self.frame = [], -124
                self.eventsize = {0x38: 0x4d, 0x36: 0xf0}
                self.zero_indices = {0: {14}, 1: {14}}
                self.slp_version_tuple = (3, 18, 0)
                self._Console__post_frame = lambda state, event: None
                self._Console__game_start = lambda state, event: None
            def connect(self): return True
            def stop(self): events.append("console_stopped")
            def step(self):
                time.sleep(.001)
                for controller in self.controllers:
                    controller.flush()
                self.frame += 1
                if self.frame == -123:
                    from test_matches import replay_fixture
                    self._Console__game_start(None,replay_fixture()[8:8+0xf0])
                players = {}
                for port in (1, 2):
                    character = characters.FOX if port == 1 else characters.MARIO
                    data = bytearray(0x4d)
                    data[0] = 0x38
                    struct.pack_into(">i", data, 1, self.frame)
                    data[5:8] = bytes([port - 1, 0, character.value])
                    struct.pack_into(">H", data, 8, 14)
                    data[0x21] = 4
                    self._Console__post_frame(None, data)
                    players[port] = NS(character=character, cpu_level=0 if port == 1 else 3,
                        stock=4, percent=0., position=NS(x=0., y=0.), on_ground=True, jumps_left=2,
                        action=NS(value=14, name="STANDING"), action_frame=1, hitstun_frames_left=0,
                        hitlag_left=0, invulnerable=False,
                        facing=True, speed_ground_x_self=0., speed_air_x_self=0., speed_y_self=0.,
                        speed_x_attack=0., speed_y_attack=0., shield_strength=60.,
                        controller_state=NS(main_stick=(.5, .5), c_stick=(.5, .5), l_shoulder=0., r_shoulder=0.,
                            button={buttons["BUTTON_" + name]: False for name in BUTTONS}))
                return NS(frame=self.frame, players=players, stage=stages.BATTLEFIELD, is_teams=False, menu_state=menus.IN_GAME)

        class Controller:
            def __init__(self, console, port): console.controllers.append(self)
            def connect(self): pass
            def release_all(self): events.append("neutral")
            def flush(self): events.append("flushed")
            def disconnect(self): events.append("disconnected")
            def tilt_analog(self, *args): pass
            def press_shoulder(self, *args): pass
            def press_button(self, *args): pass

        def recorder(path, **kwargs):
            result = FrameRecorder(path, capacity=2, opener=Writer)
            recorders.append(result)
            original_close = result.close
            def close():
                events.append("recorder_join")
                return original_close(timeout=.02)
            result.close = close
            return result

        run = Path(tempfile.mkdtemp(prefix="jev-worker-recorder-"))
        (run / "launch.json").write_text(json.dumps({"runtime": "fixture", "port": 51441,
            "run_id": "fixture", "policy": "input-probe", "max_frame_bytes": 1000000}))
        fake_melee = NS(Console=Console, Controller=Controller, Button=buttons, MenuHelper=lambda: None,
                        Menu=menus, Character=characters, Stage=stages)
        previous = {s: signal.getsignal(s) for s in (signal.SIGINT, signal.SIGTERM)}
        try:
            with patch.dict("sys.modules", {"melee": fake_melee}), patch.object(match_worker, "FrameRecorder", side_effect=recorder):
                match_worker.run(run)
            outcome = json.loads((run / "worker-result.json").read_text())
            self.assertTrue(outcome["neutralized"])
            self.assertEqual(outcome["status"], "error")
            self.assertEqual(outcome["failure_reason"], "recorder_io_or_encoding_error" if full_disk else "recorder_queue_full")
            self.assertLess(events.index("disconnected"), events.index("recorder_join"))
            self.assertEqual(events[-1], "console_stopped")
        finally:
            release.set()
            for result in recorders:
                result.thread.join(timeout=2)
            for sig, handler in previous.items():
                signal.signal(sig, handler)

    def test_full_disk_stops_worker_after_neutralization(self):
        self.exercise(True)

    def test_stalled_disk_queue_stops_worker_without_waiting_for_io(self):
        self.exercise(False)


if __name__ == "__main__":
    unittest.main()
