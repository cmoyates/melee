"""Observed local skills. This module chooses packets but never writes a controller."""

from dataclasses import dataclass

from .engine import Decision, Observation
from .aerial import AERIAL, NAIR, ShortHopAerial, can_start_aerial
from .ground_combat import CAPTOR, COMBAT, GroundCombat, can_start_combat
from .stage import GROUND_EDGE, PLATFORMS, support_surface

# Landing is excluded: a held jump pressed before its actionable window can be
# ignored for the entire landing, then remain held without a new press edge.
GROUND_ACTIONS = frozenset((14, 15, 16, 17, 18, 19, 20, 21, 22, 23))
JUMP_ACTIONS = frozenset((25, 26, 27, 28))
SHIELD_ACTIONS = frozenset((178, 179, 180, 181, 182))


@dataclass(frozen=True)
class SkillSpec:
    name: str
    direction: int = 0

    def __post_init__(self):
        if self.name not in ("neutral", "move", "jump", "shield", *COMBAT, *AERIAL) or type(self.direction) is not int or self.direction not in (-1, 0, 1):
            raise ValueError("Invalid skill")
        if self.name in ("move", *COMBAT, *AERIAL) and self.direction == 0 or self.name in ("neutral", "shield") and self.direction:
            raise ValueError("Invalid skill direction")


def relative_skill(label, observation):
    """Resolve a tactical label once; an active skill keeps its chosen direction."""
    delta = observation.opponent.x - observation.bot.x
    toward = 1 if delta > 0 else -1 if delta < 0 else 1 if observation.bot.details.facing_right else -1
    choices = {"neutral": SkillSpec("neutral"), "approach": SkillSpec("move", toward),
        "retreat": SkillSpec("move", -toward), "jump_toward": SkillSpec("jump", toward),
        "jump_away": SkillSpec("jump", -toward), "jump": SkillSpec("jump"), "shield": SkillSpec("shield"),
        **{name: SkillSpec(name, toward) for name in (*COMBAT, *AERIAL)}}
    try:
        return choices[label]
    except KeyError:
        raise ValueError("Unknown tactical skill label") from None


def inhibited(observation):
    bot, details = observation.bot, observation.bot.details
    if observation.frame < 0:
        return "countdown"
    if bot.stocks_remaining == 0 or details.action_id <= 13:
        return "death_or_respawn"
    if details.hitlag_frames_derived:
        return "hitlag"
    if details.hitstun_frames_derived:
        return "hitstun"
    return None


def can_start(spec, observation):
    reason = inhibited(observation)
    if reason:
        return reason
    bot, details = observation.bot, observation.bot.details
    if spec.name == "neutral":
        return None
    if spec.name in COMBAT:
        return can_start_combat(spec.name, spec.direction, observation)
    if spec.name in AERIAL:
        return can_start_aerial(spec.name, spec.direction, observation)
    if not bot.grounded:
        return "requires_ground"
    if details.action_id not in GROUND_ACTIONS:
        return "motion_not_interruptible"
    if spec.name == "shield" and details.shield_strength < 15:
        return "shield_low"
    if spec.name == "jump" and (not bot.jumps or details.input_jump_held):
        return "jump_unavailable_or_held"
    if spec.name == "move":
        surface = support_surface(bot.x, bot.y, bot.grounded)
        bounds = (-GROUND_EDGE, GROUND_EDGE) if surface == "ground" else next(
            ((p["left"], p["right"]) for p in PLATFORMS if p["id"] == surface), None)
        if bounds is None:
            return "support_edge"
        left, right = bounds
        target = bot.x + 6 * spec.direction
        normal = left+8 <= target <= right-8
        inward_escape = ((bot.x < left+8 or bot.x > right-8) and left < target < right and
            abs(target-(left+right)/2) < abs(bot.x-(left+right)/2))
        if not (normal or inward_escape):
            return "support_edge"
    return None


class SkillArbiter:
    """One active commitment, observed acknowledgements and neutral abort output."""
    def __init__(self):
        self.active = None
        self.generation = 0
        self.last_identity = None
        self.last_event = None

    def request(self, spec, observation):
        if self.active is not None:
            return "skill_committed"
        reason = can_start(spec, observation)
        if reason:
            self.last_event = {"status": "refused", "reason": reason, "skill": spec.name,
                "direction": spec.direction, "frame": observation.frame, "episode": observation.episode,
                "generation": self.generation}
            return reason
        self.generation += 1
        self.active = {"spec": spec, "episode": observation.episode,
            "life": observation.bot.details.life_generation_derived, "start_frame": observation.frame,
            "start_x": observation.bot.x, "phase": "await_motion", "ack_frame": None,
            "knee_start": None, "timeout": 180 if spec.name in (*COMBAT, *AERIAL) else 60 if spec.name == "shield" else 40}
        if spec.name in COMBAT:
            self.active["combat"] = GroundCombat(spec.name, spec.direction, observation)
        elif spec.name in AERIAL:
            self.active["aerial"] = ShortHopAerial(spec.name, spec.direction, observation)
        self.last_event = {"status": "started", "skill": spec.name, "direction": spec.direction,
            "frame": observation.frame, "episode": observation.episode, "generation": self.generation}
        return None

    def _finish(self, observation, status, reason):
        active = self.active
        if active is not None:
            primitive = active.get("combat") or active.get("aerial")
            if primitive is not None and primitive.status is None:
                primitive.finish(observation, status, reason)
            self.last_event = {"status": status, "reason": reason, "skill": active["spec"].name,
                "direction": active["spec"].direction, "episode": observation.episode,
                "frame": observation.frame, "source_frame": active["start_frame"],
                "ack_frame": active["ack_frame"], "generation": self.generation,
                "jumpsquat_observed_frames": (active["ack_frame"] - active["knee_start"])
                    if active["knee_start"] is not None and active["ack_frame"] is not None else None,
                **{key: active[key].trace() for key in ("combat", "aerial") if key in active}}
            self.active = None

    def abort(self, observation, reason="external_abort"):
        self._finish(observation, "aborted", reason)
        return Decision(1, observation.episode, observation.frame, "wait")

    def retains_attack_hitlag(self, observation):
        active, details = self.active, observation.bot.details
        if not details.hitlag_frames_derived or details.hitstun_frames_derived or active is None:
            return False
        return (("combat" in active and details.action_id in (COMBAT[active["spec"].name]["motion"], *CAPTOR)) or
            ("aerial" in active and details.action_id == NAIR))

    def step(self, observation):
        if not isinstance(observation, Observation):
            raise ValueError("Skill requires validated observation")
        identity = (observation.episode, observation.frame)
        last = self.last_identity
        self.last_identity = identity
        if last is not None and (identity[0] != last[0] or identity[1] != last[1] + 1):
            return self.abort(observation, "observation_discontinuity")
        active = self.active
        if active is None:
            return Decision(1, *identity, "wait")
        bot, details = observation.bot, observation.bot.details
        if (observation.episode, details.life_generation_derived) != (active["episode"], active["life"]):
            return self.abort(observation, "episode_or_life_changed")
        primitive = active.get("combat") or active.get("aerial")
        if primitive is not None:
            action = primitive.step(observation)
            active["ack_frame"] = primitive.ack_frame
            active["phase"] = primitive.phase
            if primitive.status is not None:
                self._finish(observation, primitive.status, primitive.reason)
            return Decision(1, *identity, action)
        reason = inhibited(observation)
        if reason:
            return self.abort(observation, reason)
        if observation.frame - active["start_frame"] >= active["timeout"]:
            self._finish(observation, "timeout", "motion_or_release_not_observed")
            return Decision(1, *identity, "wait")
        spec, phase = active["spec"], active["phase"]
        if phase == "release":
            if details.input_neutral_derived and observation.frame > active["release_frame"]:
                self._finish(observation, "succeeded", "motion_and_release_observed")
            return Decision(1, *identity, "wait")
        action = "wait"
        acknowledged = False
        if spec.name == "neutral":
            acknowledged = details.input_neutral_derived
        elif spec.name == "move":
            if not bot.grounded:
                return self.abort(observation, "lost_ground_support")
            action = "right" if spec.direction > 0 else "left"
            acknowledged = ((bot.x - active["start_x"]) * spec.direction >= 6 and
                            details.action_id in GROUND_ACTIONS and details.self_velocity_x * spec.direction > 0)
        elif spec.name == "jump":
            action = {0: "jump", 1: "jump_right", -1: "jump_left"}[spec.direction]
            if details.action_id == 24 and active["knee_start"] is None:
                active["knee_start"] = observation.frame
            acknowledged = (active["knee_start"] is not None and not bot.grounded and
                            details.action_id in JUMP_ACTIONS and details.self_velocity_y > 0)
            if not bot.grounded and not acknowledged:
                return self.abort(observation, "unconfirmed_takeoff")
        elif spec.name == "shield":
            if not bot.grounded or details.shield_strength < 10:
                return self.abort(observation, "shield_no_longer_safe")
            action = "shield"
            if details.action_id == 179 and details.input_shield_held:
                if active["ack_frame"] is None:
                    active["ack_frame"] = observation.frame
                acknowledged = observation.frame - active["ack_frame"] >= 8
        if acknowledged:
            if active["ack_frame"] is None:
                active["ack_frame"] = observation.frame
            active.update(phase="release", release_frame=observation.frame)
            action = "wait"
        return Decision(1, *identity, action)

    def trace(self):
        active = self.active
        return {"generation": self.generation, "event": self.last_event,
                "active": None if active is None else {"skill": active["spec"].name,
                    "direction": active["spec"].direction, "phase": active["phase"],
                    "source_frame": active["start_frame"], "episode": active["episode"], "life": active["life"],
                    **{key: active[key].trace() for key in ("combat", "aerial") if key in active}}}
