"""Observed Fox grounded primitives, separate from controller ownership.

This module returns action intents; SkillArbiter owns commitment and the shared
FrameExecutor remains the only packet writer. Range and timeout values are
declared conservative policy limits, not native hitbox collision predictions.
"""

from .stage import support_surface

COMBAT = {
    "jab": {"motion": 44, "action": "attack", "range": 12., "expected_last_frame": 21},
    "dtilt": {"motion": 57, "action": "down_tilt", "range": 15., "expected_last_frame": 35},
    "grab": {"motion": 212, "action": "grab", "range": 10., "expected_last_frame": 29},
}
START_ACTIONS = (14, 15, 16, 17, 39, 40)
SUPPORTS = ("ground", "left", "right", "top")
GUARD = (178, 179, 180, 181, 182)
CAPTOR = (213, 216)
CAPTURED = (223, 224, 225, 226, 227, 228)


def can_start_combat(name, direction, observation):
    if name not in COMBAT:
        return "unknown_combat_skill"
    a, b = observation.bot, observation.opponent
    if direction not in (-1, 1):
        return "requires_facing_direction"
    if observation.frame < 0 or a.details.action_id <= 13 or a.stocks_remaining == 0:
        return "death_or_respawn"
    if a.details.hitlag_frames_derived or a.details.hitstun_frames_derived:
        return "own_damage_or_hitlag"
    if not a.grounded or a.details.action_id not in START_ACTIONS:
        return "requires_actionable_ground"
    if not a.details.input_neutral_derived:
        return "requires_released_input"
    surface = support_surface(a.x, a.y, a.grounded)
    if surface not in SUPPORTS or support_surface(b.x, b.y, b.grounded) != surface:
        return "requires_known_shared_support"
    if b.stocks_remaining == 0 or b.details.action_id <= 13:
        return "opponent_inactive"
    if getattr(b.details, "hurtbox_state", None) != 0:
        return "opponent_invulnerable_or_unknown"
    if b.details.action_id in CAPTURED or b.details.action_id in CAPTOR:
        return "opponent_already_captured_or_capturing"
    if (1 if a.details.facing_right else -1) != direction or (b.x-a.x)*direction <= 0:
        return "wrong_facing"
    if abs(b.x-a.x) > COMBAT[name]["range"] or abs(b.y-a.y) > 3:
        return "out_of_range"
    if name != "grab" and b.details.action_id in GUARD:
        return "opponent_shielded"
    return None


def combat_candidates(observation):
    direction = 1 if observation.bot.details.facing_right else -1
    return tuple(name for name in COMBAT if can_start_combat(name, direction, observation) is None)


def select_combat(observation, mode="heuristic", rng=None):
    if mode not in ("heuristic", "random-legal"):
        raise ValueError("Unknown local selector")
    candidates = combat_candidates(observation)
    if not candidates:
        return None
    if mode == "random-legal":
        if rng is None:
            raise ValueError("Random selector requires an explicit generator")
        return rng.choice(candidates)
    if observation.opponent.details.action_id in GUARD and "grab" in candidates:
        return "grab"
    return "jab" if "jab" in candidates else candidates[0]


class GroundCombat:
    """A single fresh press, observed motion, and observed end of commitment."""
    def __init__(self, name, direction, observation):
        refusal = can_start_combat(name, direction, observation)
        if refusal:
            raise ValueError(refusal)
        self.name, self.direction = name, direction
        self.started = observation.frame
        self.identity = (observation.episode, observation.bot.details.life_generation_derived,
            observation.opponent.details.life_generation_derived)
        self.previous_frame = None
        self.previous_percent = observation.opponent.details.percent
        self.phase = "press"
        self.press_frame = None
        self.ack_frame = None
        self.end_frame = None
        self.contact_frames = []
        self.shield_contact_frames = []
        self.capture_frame = None
        self.status = self.reason = None
        self.motion_frames = 0
        self.last_action = "wait"

    def finish(self, observation, status, reason):
        self.status, self.reason = status, reason
        self.end_frame = observation.frame
        self.phase = "finished"
        self.last_action = "wait"
        return "wait"

    def step(self, observation):
        a, b, frame = observation.bot, observation.opponent, observation.frame
        if self.status is not None:
            return "wait"
        identity = (observation.episode, a.details.life_generation_derived, b.details.life_generation_derived)
        if identity != self.identity or a.stocks_remaining == 0 or a.details.action_id <= 13:
            return self.finish(observation, "aborted", "life_or_episode_changed")
        if self.previous_frame is not None and frame != self.previous_frame+1:
            return self.finish(observation, "aborted", "observation_discontinuity")
        self.previous_frame = frame
        if a.details.hitstun_frames_derived:
            return self.finish(observation, "aborted", "own_hitstun")
        if frame-self.started >= 180:
            return self.finish(observation, "timeout", "combat_completion_deadline")
        if not a.grounded or support_surface(a.x, a.y, a.grounded) not in SUPPORTS:
            return self.finish(observation, "aborted", "lost_ground_support")
        if self.press_frame is None:
            refusal = can_start_combat(self.name, self.direction, observation)
            if refusal:
                return self.finish(observation, "aborted", "prepress:"+refusal)
            self.press_frame = frame
            self.phase = "await_motion"
            self.previous_percent = b.details.percent
            self.last_action = COMBAT[self.name]["action"]
            return self.last_action
        motion = COMBAT[self.name]["motion"]
        if a.details.action_id == motion:
            self.motion_frames += 1
            if self.ack_frame is None:
                self.ack_frame = frame
            self.phase = "await_completion"
        if self.ack_frame is not None:
            if (self.name != "grab" and a.details.action_id == motion and a.details.hitlag_frames_derived and
                    b.details.hitlag_frames_derived and b.details.percent > self.previous_percent and
                    getattr(b.details, "hurtbox_state", None) == 0 and b.details.action_id not in GUARD):
                self.contact_frames.append(frame)
            if a.details.hitlag_frames_derived and b.details.action_id in (179, 181):
                self.shield_contact_frames.append(frame)
            if self.name == "grab" and a.details.action_id in CAPTOR and b.details.action_id in CAPTURED:
                if self.capture_frame is None:
                    self.capture_frame = frame
            if a.details.action_id in START_ACTIONS and a.details.input_neutral_derived and not a.details.hitlag_frames_derived:
                return self.finish(observation, "succeeded", "motion_and_actionable_release_observed")
            allowed = (motion,) + ((213, 216, 218) if self.name == "grab" else (41,) if self.name == "dtilt" else ())
            if a.details.action_id not in allowed:
                return self.finish(observation, "aborted", "unexpected_motion_after_acknowledgement")
        elif frame-self.press_frame >= 8:
            return self.finish(observation, "timeout", "combat_start_unacknowledged")
        self.previous_percent = b.details.percent
        self.last_action = "wait"
        return self.last_action

    def trace(self):
        return {"schema_version": 1, "skill": self.name, "direction": self.direction,
            "phase": self.phase, "source_frame": self.started, "press_frame": self.press_frame,
            "ack_frame": self.ack_frame,
            "end_frame": self.end_frame, "status": self.status, "reason": self.reason,
            "motion_frames": self.motion_frames, "contact_frames": list(self.contact_frames),
            "shield_contact_frames": list(self.shield_contact_frames), "capture_frame": self.capture_frame,
            "contact_evidence": "paired_hitlag_and_damage_in_own_attack_motion",
            "capture_evidence": "paired_native_captor_and_captured_motions",
            "last_action": self.last_action}
