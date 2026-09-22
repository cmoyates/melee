"""Observed Fox recovery/reflex state machine; emits ordinary action intents only.

Native motion IDs are Fox-specific: libmelee's generic enum names alias these
values to other characters' moves. Numeric thresholds below are conservative
agent policy limits, not claims about exact native collision or tech windows.
"""

from collections import Counter

from .engine import Decision
from .stage import GROUND_EDGE, PLATFORMS, support_surface

CHARGE = (353, 354)
TRAVEL = (355, 356)
SPECIAL_FALL = (35, 36, 37, 358, 359)
LEDGE = tuple(range(252, 264))
AIR_ACTIONABLE = tuple(range(25, 35)) + (38,)
KNOWN_SUPPORTS = ("ground", "left", "right", "top")
MAX_RECOVERY_FRAMES = 180
# Fighter origin can dip below zero during an ordinary landing while its ECB
# still approaches the floor. This is a conservative landing corridor, not an
# exact collision query; do not infer offstage status from origin y alone.
LANDING_ORIGIN_FLOOR = -12


def known_support(observation):
    a = observation.bot
    value = support_surface(a.x, a.y, a.grounded)
    return value if value in KNOWN_SUPPORTS else None


def occupied_ledge(observation):
    a, b = observation.bot, observation.opponent
    return b.details.action_id in LEDGE and abs(b.x) > 60 and a.x*b.x > 0


def aim_action(observation):
    """Choose a coarse charge-time aim from current observed geometry."""
    a = observation.bot
    if abs(a.x) <= GROUND_EDGE-8:
        return "aim_up"
    side = 1 if a.x > 0 else -1
    occupied = occupied_ledge(observation)
    target_x = side*(50 if occupied else 60)
    target_y = 25 if occupied else 10
    dx, dy = target_x-a.x, target_y-a.y
    direction = "right" if dx > 0 else "left"
    # Close below Battlefield's lip, a diagonal crosses the side wall before
    # reaching the floor height. Rise outside the wall, then drift after travel.
    outside = abs(a.x)-GROUND_EDGE
    if a.y < 0 and outside > 0:
        clearance = (-a.y+8)/outside
        if clearance > 2:
            return "aim_up"
        if clearance > 1:
            return "aim_steep_"+direction
        if clearance > .5:
            return "aim_diagonal_"+direction
    if abs(dx) < 3 and dy > 0:
        return "aim_up"
    ratio = dy/max(abs(dx), .01)
    if ratio > 1.5:
        return "aim_steep_"+direction
    if ratio > .6:
        return "aim_diagonal_"+direction
    if ratio > .2:
        return "aim_shallow_"+direction
    return direction


def imminent_known_floor(observation):
    a = observation.bot
    velocity = a.details.self_velocity_y+a.details.attack_velocity_y
    if a.grounded or velocity >= -.1:
        return False
    projected_x = a.x + 2*(a.details.self_velocity_x+a.details.attack_velocity_x)
    floors = [(0., -GROUND_EDGE+2, GROUND_EDGE-2)] + [
        (p["height"], p["left"]+2, p["right"]-2) for p in PLATFORMS]
    return any(left <= projected_x <= right and 0 <= (a.y-height)/-velocity <= 3
        for height, left, right in floors)


class FoxReflex:
    def __init__(self):
        self.identity = None
        self.last_frame = None
        self.phase = "idle"
        self.phase_frame = None
        self.started_frame = None
        self.jump_attempted = False
        self.jump_requested_with = None
        self.jump_request_frame = None
        self.special_attempted = False
        self.special_request_frame = None
        self.special_launched = False
        self.ledge_neutral_frames = 0
        self.last_hitstun = False
        self.last_tech_frame = -1000
        self.last_tech_state = False
        self.failed = False
        self.event = None
        self.counts = Counter()
        self.last_action = "wait"

    def _phase(self, value, observation, reason=None):
        if self.phase != value or reason is not None:
            self.phase = value
            self.phase_frame = observation.frame
            self.event = {"phase": value, "frame": observation.frame, "episode": observation.episode,
                "reason": reason, "life": observation.bot.details.life_generation_derived}
            self.counts["phase:"+value] += 1

    def _reset(self, observation, reason, preserve_deadline=False):
        self.started_frame = self.started_frame if preserve_deadline else None
        self.jump_attempted = self.special_attempted = self.special_launched = self.failed = False
        self.jump_requested_with = self.jump_request_frame = self.special_request_frame = None
        self.ledge_neutral_frames = 0
        self.last_hitstun = False
        self.last_tech_frame = observation.frame if preserve_deadline else -1000
        self.last_tech_state = False
        self._phase("idle", observation, reason)

    def reason(self, observation):
        a = observation.bot
        if observation.frame < 0 or a.stocks_remaining == 0 or a.details.action_id <= 13:
            return "death_or_respawn"
        if a.details.hitlag_frames_derived:
            return "hitlag"
        if a.details.hitstun_frames_derived:
            return "hitstun"
        if a.details.action_id in LEDGE:
            return "ledge"
        if a.grounded:
            if known_support(observation) is None:
                return "unknown_geometry"
            return "edge" if known_support(observation) == "ground" and abs(a.x) > 62 else None
        if (abs(a.x) > 62 or a.y < LANDING_ORIGIN_FLOOR or self.started_frame is not None or
                a.details.action_id in CHARGE+TRAVEL+SPECIAL_FALL):
            return "recovery"
        return None

    def _defense(self, observation):
        a = observation.bot
        if (a.details.hitstun_frames_derived and not a.details.hitlag_frames_derived and
                not a.details.input_shield_held and observation.frame-self.last_tech_frame >= 40 and
                imminent_known_floor(observation)):
            self.last_tech_frame = observation.frame
            self.counts["tech_attempts"] += 1
            self._phase("tech_pulse", observation)
            return "shield"
        self._phase("defensive_drift", observation)
        if abs(a.details.attack_velocity_x)+abs(a.details.attack_velocity_y) < .01:
            return "wait"
        right = a.x < -5 or (abs(a.x) <= 5 and a.details.attack_velocity_x < 0)
        return "aim_shallow_right" if right else "aim_shallow_left"

    def decide_action(self, observation):
        a, frame = observation.bot, observation.frame
        identity = (observation.episode, a.details.life_generation_derived)
        if identity != self.identity:
            self._reset(observation, "initial" if self.identity is None else "life_or_episode_changed")
            self.identity = identity
            self.last_frame = None
        if self.last_frame is not None and frame != self.last_frame+1:
            self._reset(observation, "observation_discontinuity", preserve_deadline=True)
            self.last_frame = frame
            return self._output("wait")
        self.last_frame = frame
        if frame < 0 or a.stocks_remaining == 0 or a.details.action_id <= 13:
            if self.phase != "inactive":
                self._reset(observation, "death_or_respawn")
            self._phase("inactive", observation)
            return self._output("wait")
        tech_state = a.details.action_id in (199, 200, 201, 202, 203, 204)
        if tech_state and not self.last_tech_state:
            self.counts["observed_tech_states"] += 1
        self.last_tech_state = tech_state
        hitstun = bool(a.details.hitstun_frames_derived)
        if hitstun and not self.last_hitstun:
            # Damage interrupts an earlier charge/travel commitment. Fresh
            # resource observations govern the next attempt after hitstun.
            self.special_attempted = self.special_launched = False
            self.jump_attempted = False
            self.special_request_frame = None
            self.jump_request_frame = None
            self.counts["damage_interruptions"] += 1
        self.last_hitstun = hitstun
        if hitstun or a.details.hitlag_frames_derived:
            return self._output(self._defense(observation))
        support = known_support(observation)
        if support is not None and a.details.action_id not in LEDGE:
            if self.started_frame is not None:
                self.counts["observed_stage_returns"] += 1
            self.started_frame = None
            self.jump_attempted = self.special_attempted = self.special_launched = self.failed = False
            self.jump_request_frame = self.special_request_frame = None
            if support == "ground" and abs(a.x) > 62:
                self._phase("edge_clear", observation)
                return self._output("left" if a.x > 0 else "right")
            self._phase("safe", observation)
            return self._output("wait")
        if self.reason(observation) is None:
            self._phase("idle", observation)
            return self._output("wait")
        if self.started_frame is None:
            self.started_frame = frame
        if self.failed:
            return self._output("wait")
        if (a.grounded and a.details.action_id not in LEDGE) or a.jumps > 2:
            return self._fail(observation, "unknown_geometry_or_resources")
        if frame-self.started_frame >= MAX_RECOVERY_FRAMES:
            return self._fail(observation, "recovery_deadline")
        if a.y < -85 or abs(a.x) > 130:
            return self._fail(observation, "outside_declared_recovery_envelope")
        inward = "left" if a.x > 0 else "right"
        if a.details.action_id == 252:
            self.ledge_neutral_frames = 0
            self._phase("ledge_catch", observation)
            return self._output("wait")
        if a.details.action_id == 253:
            if a.details.input_neutral_derived:
                self.ledge_neutral_frames += 1
            else:
                self.ledge_neutral_frames = 0
            if self.ledge_neutral_frames < 2:
                self._phase("ledge_release", observation)
                return self._output("wait")
            self._phase("ledge_climb", observation)
            return self._output(inward)
        if a.details.action_id in LEDGE:
            self._phase("ledge_return_animation", observation)
            return self._output("wait")
        self.ledge_neutral_frames = 0
        if a.details.action_id in CHARGE:
            self.special_attempted = True
            self._phase("charge_aim", observation)
            return self._output(aim_action(observation))
        if a.details.action_id in TRAVEL:
            if not self.special_launched:
                self.special_launched = True
                self.counts["observed_firefox_launches"] += 1
                if a.jumps:
                    self.counts["launch_jump_counter_mismatch"] += 1
            self.jump_attempted = True
            self._phase("firefox_travel", observation)
            return self._output(inward)
        if a.details.action_id in SPECIAL_FALL or self.special_launched:
            self._phase("special_fall_drift", observation)
            return self._output(inward)
        if self.special_request_frame is not None:
            if frame-self.special_request_frame >= 8:
                return self._fail(observation, "special_start_unacknowledged")
            self._phase("await_charge", observation)
            return self._output("aim_up")
        if self.jump_request_frame is not None:
            if (a.jumps < self.jump_requested_with and a.details.action_id in (27, 28) and
                    a.details.self_velocity_y > 0):
                self.counts["observed_double_jumps"] += 1
                self.jump_request_frame = None
                self._phase("jump_release", observation)
                return self._output(inward)
            if frame-self.jump_request_frame < 8:
                self._phase("await_jump", observation)
                return self._output(inward)
            self.jump_request_frame = None
            self.counts["unacknowledged_jump_attempts"] += 1
        if a.details.input_jump_held:
            self._phase("release_jump", observation)
            return self._output(inward)
        if a.details.action_id not in AIR_ACTIONABLE:
            self._phase("await_actionable_air", observation)
            return self._output(inward)
        if abs(a.x) <= GROUND_EDGE-8 and LANDING_ORIGIN_FLOOR <= a.y < 10:
            self._phase("await_stage_landing", observation)
            return self._output("wait")
        if a.jumps and not self.jump_attempted and (a.y < 5 or a.details.self_velocity_y <= 0):
            self.jump_attempted = True
            self.jump_requested_with = a.jumps
            self.jump_request_frame = frame
            self.counts["jump_attempts"] += 1
            self._phase("jump_press", observation)
            return self._output("jump_"+inward)
        if (not self.special_attempted and (a.jumps == 0 or self.jump_attempted) and
                a.details.self_velocity_y <= 0 and a.y < 10):
            self.special_attempted = True
            self.special_request_frame = frame
            self.counts["special_attempts"] += 1
            self._phase("upb_start", observation)
            return self._output("special_up")
        self._phase("inward_drift", observation)
        return self._output(inward)

    def _fail(self, observation, reason):
        self.failed = True
        self._phase("failed", observation, reason)
        return self._output("wait")

    def _output(self, action):
        self.last_action = action
        return action

    def decide(self, observation):
        return Decision(1, observation.episode, observation.frame, self.decide_action(observation))

    def trace(self):
        return {"schema_version": 1, "phase": self.phase, "phase_frame": self.phase_frame,
            "started_frame": self.started_frame, "jump_attempted": self.jump_attempted,
            "special_attempted": self.special_attempted, "special_launched": self.special_launched,
            "failed": self.failed, "last_action": self.last_action, "event": self.event,
            "counts": dict(self.counts)}
