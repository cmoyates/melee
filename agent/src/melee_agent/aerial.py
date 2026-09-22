"""One Fox short-hop neutral aerial, measured from native state transitions.

This primitive returns intents only. Landing duration is observed independently
of the L-button attempt; no animation index is treated as a game-frame clock.
"""

from .stage import support_surface

AERIAL = {"sh_nair": True, "sh_nair_no_lcancel": False}
GROUND_START = (14, 15, 16, 17)
NAIR = 65
NAIR_LANDING = 70


def can_start_aerial(name, direction, observation):
    a, d = observation.bot, observation.bot.details
    if name not in AERIAL or type(direction) is not int or direction not in (-1, 1):
        return "unknown_aerial_or_direction"
    if observation.frame < 0 or not a.stocks_remaining or d.action_id <= 13:
        return "death_or_respawn"
    if d.hitlag_frames_derived or d.hitstun_frames_derived:
        return "own_damage_or_hitlag"
    if support_surface(a.x, a.y, a.grounded) != "ground" or d.action_id not in GROUND_START:
        return "requires_actionable_main_ground"
    if abs(a.x) > 45 or abs(a.x+15*direction) > 55:
        return "unsupported_approach_geometry"
    if a.jumps != 2 or d.input_jump_held or not d.input_neutral_derived:
        return "requires_fresh_ground_jump"
    if abs(d.self_velocity_x) > .25:
        return "requires_settled_ground"
    return None


class ShortHopAerial:
    def __init__(self, name, direction, observation):
        refusal = can_start_aerial(name, direction, observation)
        if refusal:
            raise ValueError(refusal)
        self.name, self.direction = name, direction
        self.lcancel_enabled = AERIAL[name]
        self.source_frame = observation.frame
        self.source_y = observation.bot.y
        self.identity = (observation.episode, observation.bot.details.life_generation_derived)
        self.previous_frame = None
        self.jump_press_frame = self.knee_frame = self.jump_release_frame = None
        self.takeoff_frame = self.attack_press_frame = self.ack_frame = None
        self.lcancel_attempt_frame = self.landing_frame = self.end_frame = None
        self.landing_motion = None
        self.landing_frames = 0
        self.takeoff_velocity_y = None
        self.peak_height = 0.
        self.phase = "jump_press"
        self.status = self.reason = None
        self.last_action = "wait"

    def output(self, action="wait"):
        self.last_action = action
        return action

    def finish(self, observation, status, reason):
        self.status, self.reason = status, reason
        self.end_frame = observation.frame
        self.phase = "finished"
        return self.output()

    def step(self, observation):
        a, d, frame = observation.bot, observation.bot.details, observation.frame
        if self.status is not None:
            return self.output()
        if (observation.episode, d.life_generation_derived) != self.identity or not a.stocks_remaining or d.action_id <= 13:
            return self.finish(observation, "aborted", "life_or_episode_changed")
        if self.previous_frame is not None and frame != self.previous_frame+1:
            return self.finish(observation, "aborted", "observation_discontinuity")
        self.previous_frame = frame
        if d.hitstun_frames_derived:
            return self.finish(observation, "aborted", "own_hitstun")
        if frame-self.source_frame >= 180:
            return self.finish(observation, "timeout", "aerial_completion_deadline")
        if abs(a.x) > 55 or a.y < -12 or a.y > 24:
            return self.finish(observation, "aborted", "unsupported_air_geometry")
        self.peak_height = max(self.peak_height, a.y-self.source_y)
        if self.jump_press_frame is None:
            refusal = can_start_aerial(self.name, self.direction, observation)
            if refusal:
                return self.finish(observation, "aborted", "prepress:"+refusal)
            self.jump_press_frame = frame
            self.phase = "await_takeoff"
            return self.output("jump")
        if self.attack_press_frame is not None and self.ack_frame is None and not a.grounded and d.action_id == NAIR:
            self.ack_frame = frame
            self.phase = "airborne"
        if d.hitlag_frames_derived:
            return self.output()
        if self.takeoff_frame is None:
            if frame-self.jump_press_frame >= 8:
                return self.finish(observation, "timeout", "takeoff_not_observed")
            if d.action_id == 24 and a.grounded:
                if self.knee_frame is None:
                    self.knee_frame = frame
                if not d.input_jump_held and self.jump_release_frame is None:
                    self.jump_release_frame = frame
                return self.output()
            if not a.grounded:
                if (self.knee_frame is None or self.jump_release_frame is None or
                        d.action_id not in (25, 26) or a.jumps != 1 or d.self_velocity_y <= 0):
                    return self.finish(observation, "aborted", "unconfirmed_short_hop")
                self.takeoff_frame = frame
                self.takeoff_velocity_y = d.self_velocity_y
                self.attack_press_frame = frame
                self.phase = "await_aerial"
                return self.output("attack")  # Neutral stick plus fresh A selects AttackAirN.
            if d.action_id not in GROUND_START:
                return self.finish(observation, "aborted", "unexpected_jumpsquat_motion")
            return self.output()
        if self.ack_frame is None:
            if a.grounded:
                return self.finish(observation, "aborted", "landed_before_aerial_ack")
            if d.action_id == NAIR:
                self.ack_frame = frame
                self.phase = "airborne"
            elif frame-self.attack_press_frame >= 8:
                return self.finish(observation, "timeout", "aerial_not_observed")
            elif d.action_id not in (25, 26, 29):
                return self.finish(observation, "aborted", "unexpected_aerial_motion")
            else:
                return self.output()
        if a.grounded:
            if support_surface(a.x, a.y, True) != "ground":
                return self.finish(observation, "aborted", "unsupported_landing_surface")
            if self.landing_frame is None:
                self.landing_frame = frame
                self.landing_motion = d.action_id
                self.phase = "landing"
            if d.action_id == NAIR_LANDING:
                self.landing_frames += 1
            elif d.action_id in GROUND_START:
                if not d.input_neutral_derived:
                    return self.output()
                return self.finish(observation, "succeeded", "aerial_and_neutral_landing_observed")
            elif d.action_id != 42:
                return self.finish(observation, "aborted", "unexpected_landing_motion")
            return self.output()
        if self.landing_frame is not None:
            return self.finish(observation, "aborted", "left_landing_support")
        if d.action_id not in (NAIR, 29, 30, 31):
            return self.finish(observation, "aborted", "interrupted_aerial_motion")
        velocity = d.self_velocity_y+d.attack_velocity_y
        if (self.lcancel_enabled and self.lcancel_attempt_frame is None and d.action_id == NAIR and
                not d.input_shield_held and velocity < -.1 and 0 <= a.y/-velocity <= 3):
            self.lcancel_attempt_frame = frame
            return self.output("shield")
        return self.output("right" if self.direction > 0 else "left")

    def trace(self):
        return {"schema_version": 1, "skill": self.name, "direction": self.direction,
            "phase": self.phase, "source_frame": self.source_frame,
            "jump_press_frame": self.jump_press_frame, "knee_frame": self.knee_frame,
            "jump_release_frame": self.jump_release_frame, "takeoff_frame": self.takeoff_frame,
            "attack_press_frame": self.attack_press_frame, "ack_frame": self.ack_frame,
            "takeoff_velocity_y": self.takeoff_velocity_y, "peak_height": self.peak_height,
            "lcancel_attempt_frame": self.lcancel_attempt_frame, "landing_frame": self.landing_frame,
            "landing_motion": self.landing_motion,
            "observed_nair_landing_frames": self.landing_frames if self.status == "succeeded" else None,
            "reduced_landing_lag": None, "landing_calibration": "requires_matched_no_lcancel_trials",
            "end_frame": self.end_frame, "status": self.status, "reason": self.reason,
            "last_action": self.last_action}
