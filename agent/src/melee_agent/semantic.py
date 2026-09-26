"""Bounded gameplay meaning shared by live snapshots and private corpus rows."""

from collections import deque
from dataclasses import dataclass
import hashlib
import json
import math

from .engine import Observation
from .native_motions import COMMON_MOTIONS, FOX_MOTIONS, MARIO_MOTIONS
from .skills import can_start, inhibited, relative_skill
from .stage import GROUND_EDGE, PLATFORMS, support_surface

SEMANTIC_VERSION = 1
MAX_SEMANTIC_BYTES = 16384
ROOT_FIELDS = frozenset(("schema_version", "kind", "episode", "frame", "stage", "match", "bot", "opponent",
    "relative", "mechanical", "current_skill", "history", "provenance", "unavailable"))
PROVENANCE = {
    "exact": "native motion IDs, stocks, grounded flag, jump resource, available hurtbox state",
    "derived": "native motion names, normalized animation index, rounded position/damage/velocity, relative geometry, stock/damage comparisons, legal candidates and prior-state history",
    "estimated": "static support surfaces, flag-gated remaining hitlag/hitstun, frame-clock match time",
    "unknown": "exact interruptible frame, exact punish window, collision outcome and opponent intent",
}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def native_motion(character, motion):
    return COMMON_MOTIONS.get(motion) or {"Fox": FOX_MOTIONS, "Mario": MARIO_MOTIONS}.get(character, {}).get(motion)


def rounded(value):
    result = round(value, 3)
    return 0. if result == 0 else result


def fighter_semantics(fighter, character):
    d = fighter.details
    return {"character": character, "native_motion_id": d.action_id,
        "native_motion_name": native_motion(character, d.action_id),
        "animation_frame_normalized": d.action_frame,
        "position_rounded": [rounded(fighter.x), rounded(fighter.y)], "grounded": fighter.grounded,
        "support_estimated": support_surface(fighter.x, fighter.y, fighter.grounded),
        "stocks_remaining": fighter.stocks_remaining, "jumps_remaining": fighter.jumps,
        "percent_rounded": rounded(d.percent), "facing": "right" if d.facing_right else "left",
        "self_velocity_rounded": [rounded(d.self_velocity_x), rounded(d.self_velocity_y)],
        "attack_velocity_rounded": [rounded(d.attack_velocity_x), rounded(d.attack_velocity_y)],
        "hitlag_remaining_estimated": d.hitlag_frames_derived,
        "hitstun_remaining_estimated": d.hitstun_frames_derived,
        "hurtbox_state": {0: "enabled", 1: "disabled", 2: "intangible"}.get(d.hurtbox_state),
        "shield_strength_rounded": rounded(d.shield_strength)}


@dataclass(frozen=True)
class CompactObservation:
    episode: int
    frame: int
    observed_ns: int
    payload_json: str

    def __post_init__(self):
        if type(self.payload_json) is not str or len(self.payload_json.encode()) > MAX_SEMANTIC_BYTES:
            raise ValueError("Compact observation exceeds bound")
        value = json.loads(self.payload_json, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite compact state")))
        if (not isinstance(value, dict) or set(value) != ROOT_FIELDS or value["kind"] != "CompactObservationV1" or
                value["schema_version"] != SEMANTIC_VERSION or (value["episode"], value["frame"]) != (self.episode, self.frame) or
                type(self.episode) is not int or self.episode < 1 or type(self.frame) is not int or
                type(self.observed_ns) is not int or self.observed_ns < 0 or canonical(value) != self.payload_json):
            raise ValueError("Invalid compact observation identity/schema")

    def wire(self):
        return json.loads(self.payload_json)

    @property
    def sha256(self):
        return hashlib.sha256(self.payload_json.encode()).hexdigest()


def compact_observation(observation, candidates, *, active_skill=None, skill_known=False, history=()):
    if not isinstance(observation, Observation):
        raise ValueError("Semantic state requires validated observation")
    labels = tuple(candidates)
    if len(labels) > 16 or len(labels) != len(set(labels)):
        raise ValueError("Invalid semantic candidate list")
    for label in labels:
        if can_start(relative_skill(label, observation), observation) is not None:
            raise ValueError("Semantic candidate is illegal at its source state")
    if type(skill_known) is not bool or len(history) > 4:
        raise ValueError("Invalid semantic context bound")
    a, b = observation.bot, observation.opponent
    skill = None
    if active_skill is not None:
        required = {"skill", "direction", "phase", "source_frame", "episode", "life"}
        if not skill_known or not isinstance(active_skill, dict) or not required <= set(active_skill):
            raise ValueError("Invalid current skill snapshot")
        if (active_skill["episode"] != observation.episode or active_skill["life"] != a.details.life_generation_derived or
                type(active_skill["source_frame"]) is not int or active_skill["source_frame"] > observation.frame or
                not isinstance(active_skill["skill"], str) or not 1 <= len(active_skill["skill"]) <= 40 or
                type(active_skill["direction"]) is not int or active_skill["direction"] not in (-1, 0, 1) or
                not isinstance(active_skill["phase"], str) or not 1 <= len(active_skill["phase"]) <= 40):
            raise ValueError("Current skill context does not match observation")
        skill = {key: active_skill[key] for key in ("skill", "direction", "phase")}
        skill["age_frames_derived"] = observation.frame-active_skill["source_frame"]
    prior = []
    last_frame = None
    for state in history:
        if (not isinstance(state, Observation) or state.episode != observation.episode or state.frame >= observation.frame or
                state.bot.details.life_generation_derived != a.details.life_generation_derived or
                (last_frame is not None and state.frame <= last_frame)):
            raise ValueError("History must be ordered prior states from this episode/life")
        last_frame = state.frame
        prior.append({"frame": state.frame, "bot_motion": native_motion("Fox", state.bot.details.action_id),
            "opponent_motion": native_motion("Mario", state.opponent.details.action_id),
            "opponent_delta_rounded": [rounded(state.opponent.x-state.bot.x), rounded(state.opponent.y-state.bot.y)],
            "stocks": [state.bot.stocks_remaining, state.opponent.stocks_remaining]})
    dx, dy = b.x-a.x, b.y-a.y
    unavailable = ["exact_interruptible_frame", "exact_punish_window", "collision_outcome", "opponent_intent"]
    for key, fighter in (("bot", a), ("opponent", b)):
        if fighter.details.hurtbox_state is None:
            unavailable.append(key+".hurtbox_state")
        if native_motion("Fox" if key == "bot" else "Mario", fighter.details.action_id) is None:
            unavailable.append(key+".native_motion_name")
    if not skill_known:
        unavailable.append("current_skill")
    value = {"schema_version": SEMANTIC_VERSION, "kind": "CompactObservationV1",
        "episode": observation.episode, "frame": observation.frame,
        "stage": {"name": "Battlefield", "main_ground_edges_estimated": [-rounded(GROUND_EDGE), rounded(GROUND_EDGE)],
            "platforms_estimated": [{key: rounded(v) if isinstance(v, float) else v for key, v in p.items()} for p in PLATFORMS]},
        "match": {"time_limit_seconds": observation.match.time_limit_seconds,
            "starting_stocks": observation.match.starting_stocks,
            "elapsed_seconds_estimated": rounded(observation.match.elapsed_seconds_derived),
            "remaining_seconds_estimated": rounded(observation.match.remaining_seconds_derived)},
        "bot": fighter_semantics(a, "Fox"), "opponent": fighter_semantics(b, "Mario"),
        "relative": {"opponent_delta_rounded": [rounded(dx), rounded(dy)],
            "distance_rounded": rounded(math.hypot(dx, dy)),
            "stock_advantage": a.stocks_remaining-b.stocks_remaining,
            "stock_leader": "bot" if a.stocks_remaining > b.stocks_remaining else "opponent" if a.stocks_remaining < b.stocks_remaining else "tied",
            "bot_minus_opponent_percent_rounded": rounded(a.details.percent-b.details.percent),
            "opponent_side": "right" if dx > 0 else "left" if dx < 0 else "aligned",
            "facing_opponent": dx*(1 if a.details.facing_right else -1) > 0,
            "ground_edge_margin_estimated": rounded(GROUND_EDGE-abs(a.x))},
        "mechanical": {"inhibited_reason": inhibited(observation), "input_released": a.details.input_neutral_derived,
            "jump_input_held": a.details.input_jump_held, "shield_input_held": a.details.input_shield_held,
            "legal_candidates": list(labels), "skill_committed": active_skill is not None if skill_known else None},
        "current_skill": skill, "history": prior, "provenance": PROVENANCE, "unavailable": unavailable}
    return CompactObservation(observation.episode, observation.frame, observation.observed_ns, canonical(value))


class SemanticHistory:
    """At most four quarter-second samples; never include the current suffix."""
    def __init__(self):
        self.states = deque(maxlen=4)
        self.identity = self.previous_frame = None
        self.last_sample = None

    def before(self, observation):
        identity = (observation.episode, observation.bot.details.life_generation_derived)
        if identity != self.identity or self.previous_frame != observation.frame-1:
            self.states.clear()
            self.last_sample = None
        self.identity, self.previous_frame = identity, observation.frame
        prior = tuple(self.states)
        if self.last_sample is None or observation.frame-self.last_sample >= 15:
            self.states.append(observation)
            self.last_sample = observation.frame
        return prior
