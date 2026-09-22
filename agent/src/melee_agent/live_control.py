"""libmelee adaptation at the edge; the frame executor has no emulator dependency."""

import time

from .engine import Fighter, FighterDetails, MatchProgress, Observation
from .rules import STARTING_STOCKS, TIME_LIMIT_SECONDS
from .raw_observation import combat_counters


class SystemClock:
    def now_ns(self):
        return time.monotonic_ns()


def observe(state, episode, clock, raw_players):
    def fighter(player, port):
        hitlag, hitstun = combat_counters(raw_players[str(port)]["raw_post"])
        buttons = {b.name.removeprefix("BUTTON_"): bool(v) for b, v in player.controller_state.button.items()}
        inputs = player.controller_state
        neutral = (not any(buttons.values()) and
            all(abs(float(v) - .5) <= .025 for stick in (inputs.main_stick, inputs.c_stick) for v in stick) and
            max(float(inputs.l_shoulder), float(inputs.r_shoulder)) <= .025)
        details = FighterDetails(int(player.action.value), int(player.action_frame),
            STARTING_STOCKS - int(player.stock) + 1, float(player.percent), bool(player.facing),
            hitlag, hitstun,
            float(player.speed_ground_x_self if player.on_ground else player.speed_air_x_self),
            float(player.speed_y_self), float(player.speed_x_attack), float(player.speed_y_attack),
            float(player.shield_strength), neutral, buttons.get("X", False) or buttons.get("Y", False),
            buttons.get("L", False) or buttons.get("R", False) or max(float(inputs.l_shoulder), float(inputs.r_shoulder)) > .1)
        return Fighter(float(player.position.x), float(player.position.y), bool(player.on_ground),
                        int(player.jumps_left), getattr(player.action, "name", "UNKNOWN"), int(player.stock), details)
    return Observation(3, episode, int(state.frame), clock.now_ns(), state.stage.name,
                        fighter(state.players[1], 1), fighter(state.players[2], 2),
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
