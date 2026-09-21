"""libmelee adaptation at the edge; the frame executor has no emulator dependency."""

import time

from .engine import Fighter, MatchProgress, Observation
from .rules import STARTING_STOCKS, TIME_LIMIT_SECONDS


class SystemClock:
    def now_ns(self):
        return time.monotonic_ns()


def observe(state, episode, clock):
    def fighter(player):
        return Fighter(float(player.position.x), float(player.position.y), bool(player.on_ground),
                        int(player.jumps_left), getattr(player.action, "name", "UNKNOWN"), int(player.stock))
    return Observation(2, episode, int(state.frame), clock.now_ns(), state.stage.name,
                        fighter(state.players[1]), fighter(state.players[2]),
                        MatchProgress.from_frame(int(state.frame), TIME_LIMIT_SECONDS, STARTING_STOCKS))


class LibmeleeSink:
    def __init__(self, controller, buttons):
        self.controller, self.buttons = controller, buttons

    def send(self, packet):
        c, b = self.controller, self.buttons
        c.release_all()
        c.tilt_analog(b.BUTTON_MAIN, packet.main_x, packet.main_y)
        c.tilt_analog(b.BUTTON_C, packet.c_x, packet.c_y)
        c.press_shoulder(b.BUTTON_L, packet.l)
        c.press_shoulder(b.BUTTON_R, packet.r)
        for name in packet.held:
            c.press_button(b["BUTTON_" + name])
        # Console.step flushes this complete packet before the next observation.
