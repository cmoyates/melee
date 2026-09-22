"""Declared, ordinary-input fresh-match setups and separate measured probes."""

from dataclasses import asdict, dataclass
import hashlib
import json

from .engine import Decision, ScriptedPolicy
from .fox_reflex import FoxReflex
from .skills import SkillArbiter, SkillSpec, inhibited
from .stage import STAGE_ID, support_surface

KINDS = ("grounded", "airborne", "offstage", "ledge", "shielded", "offstage_low")
RESULTS = ("setup_failed", "skill_failed", "succeeded", "timeout")


@dataclass(frozen=True)
class ScenarioV1:
    name: str
    kind: str
    direction: int
    schema_version: int = 1
    setup_timeout_frames: int = 480
    measurement_timeout_frames: int = 180
    measured_policy: str = "baseline"

    def __post_init__(self):
        if (self.schema_version != 1 or self.kind not in KINDS or type(self.direction) is not int or
                self.direction not in (-1, 1) or self.setup_timeout_frames != 480 or
                self.measurement_timeout_frames != 180 or self.measured_policy not in ("baseline", "fox-reflex-v1")):
            raise ValueError("Invalid fixed ScenarioV1 contract")

    def manifest(self):
        return {**asdict(self), "stage_id": STAGE_ID, "bot": "FOX", "opponent": "MARIO", "cpu_level": 3,
            "stocks": 4, "timer_seconds": 480, "initial_state": "fresh_match", "game_rng_seed": None,
            "savestate": None, "setup_privilege": "ordinary_controller_packets_only",
            "setup_inputs": ["wait", "left", "right", "jump", "jump_left", "jump_right", "recover_left", "recover_right"],
            "starting_common": "active life; no hitlag or hitstun; observed neutral input after a queued neutral setup packet",
            "starting_predicate": {
                "grounded": "main ground; signed x in [25,50]; idle/walk/dash state; abs self x speed < 0.25",
                "airborne": "signed x in [20,55]; rising ordinary jump; one remaining jump",
                "offstage": "signed x in (68.4,82]; y in [-12,8]; falling; at least one jump",
                "offstage_low": "signed x in [88,112]; y in [-40,-20]; falling; zero remaining jumps",
                "ledge": "native CliffCatch/CliffWait motion 252/253 on declared side",
                "shielded": "bot stable on main ground; opponent Guard/GuardSetOff within 25 units",
            }[self.kind], "outcome": {
                "grounded": "observed bounded inward movement and neutral release",
                "airborne": "observed landing on a known support surface",
                "offstage": "regain a known stage support or ledge before life loss or timeout",
                "offstage_low": "regain a known stage support or ledge before life loss or timeout",
                "ledge": "ordinary inward ledge return reaches main ground",
                "shielded": "bot shield skill reaches observed success and releases",
            }[self.kind]}


SUITE = tuple(ScenarioV1(kind+"-"+("left" if direction < 0 else "right"), kind, direction)
    for kind in ("grounded", "airborne", "offstage", "ledge") for direction in (-1, 1)) + (ScenarioV1("shielded-opponent", "shielded", -1),)
RECOVERY_SUITE = tuple(ScenarioV1("recovery-"+height+"-"+("left" if direction < 0 else "right"),
    kind, direction, measured_policy="fox-reflex-v1")
    for height, kind in (("high", "offstage"), ("low", "offstage_low")) for direction in (-1, 1))


def find_suite(name):
    if name == "mechanics-v1":
        return SUITE
    if name == "recovery-v1":
        return RECOVERY_SUITE
    raise ValueError("Unknown fixed scenario suite")


def scenario_suite(spec):
    return "recovery-v1" if spec.measured_policy == "fox-reflex-v1" else "mechanics-v1"


def find_scenario(name):
    for spec in SUITE+RECOVERY_SUITE:
        if spec.name == name:
            return spec
    raise ValueError("Unknown fixed mechanical scenario")


def suite_hash(name="mechanics-v1"):
    return hashlib.sha256(json.dumps([spec.manifest() for spec in find_suite(name)], sort_keys=True).encode()).hexdigest()


def stable_ground(observation):
    a = observation.bot
    return (support_surface(a.x, a.y, a.grounded) == "ground" and 14 <= a.details.action_id <= 23 and
        abs(a.details.self_velocity_x) < .25 and a.details.input_neutral_derived)


def starting_predicate(spec, observation):
    a, b = observation.bot, observation.opponent
    if inhibited(observation) or not a.details.input_neutral_derived:
        return False
    x = spec.direction*a.x
    if spec.kind == "grounded":
        return stable_ground(observation) and 25 <= x <= 50
    if spec.kind == "airborne":
        return not a.grounded and 20 <= x <= 55 and a.details.action_id in (25, 26) and a.details.self_velocity_y > 0 and a.jumps == 1
    if spec.kind == "offstage":
        return not a.grounded and 68.4 < x <= 82 and -12 <= a.y <= 8 and a.details.self_velocity_y <= 0 and a.jumps >= 1
    if spec.kind == "offstage_low":
        return not a.grounded and 88 <= x <= 112 and -40 <= a.y <= -20 and a.details.self_velocity_y < 0 and a.jumps == 0
    if spec.kind == "ledge":
        return a.details.action_id in (252, 253) and x > 60
    return stable_ground(observation) and b.details.action_id in (179, 181) and abs(b.x-a.x) <= 25


class ScenarioPolicy:
    """One trial per fresh match; setup input ownership ends before measurement."""
    def __init__(self, spec):
        self.spec = spec
        self.phase = "setup"
        self.setup_phase = "ground"
        self.owner = "setup"
        self.started = None
        self.life = None
        self.initial = None
        self.measurement_start = None
        self.previous_frame = None
        self.arbiter = SkillArbiter()
        self.probe = ScriptedPolicy()
        self.reflex = FoxReflex() if spec.measured_policy == "fox-reflex-v1" else None
        self.result = None
        self.last_action = "wait"

    @property
    def complete(self):
        return self.result is not None

    def _decision(self, observation, action="wait"):
        self.last_action = action
        return Decision(1, observation.episode, observation.frame, action)

    def _finish(self, observation, status, reason):
        self.result = {"status": status, "reason": reason, "end_episode": observation.episode,
            "end_frame": observation.frame, "end_observation": asdict(observation),
            "measured_frames": 0 if self.measurement_start is None else observation.frame-self.measurement_start+1}
        self.phase = "finished"
        self.owner = "neutral"
        return self._decision(observation)

    def _setup(self, observation):
        a = observation.bot
        direction = self.spec.direction
        outward, inward = ("left", "right") if direction < 0 else ("right", "left")
        if self.setup_phase == "ground":
            if support_surface(a.x, a.y, a.grounded) not in ("ground", None):
                return "right" if a.x < 0 else "left"
            x = a.x*direction
            if x < 25:
                return outward
            if x > 50:
                return inward
            if not stable_ground(observation):
                return "wait"
            self.setup_phase = "prepared"
        if self.spec.kind in ("grounded", "shielded"):
            return "wait"
        if self.spec.kind == "airborne":
            if self.setup_phase == "prepared":
                if a.grounded:
                    return "jump"
                self.setup_phase = "release"
            return "wait"
        if self.setup_phase == "prepared":
            if a.grounded or a.x*direction < 70:
                return outward
            self.setup_phase = "release"
            return "wait"
        if self.spec.kind == "offstage":
            return "wait"
        if self.spec.kind == "offstage_low":
            if self.setup_phase == "release":
                if not a.details.input_neutral_derived:
                    return "wait"
                self.setup_phase = "low_jump"
                return "jump_"+outward
            if self.setup_phase == "low_jump":
                if a.jumps:
                    return outward
                self.setup_phase = "low_drift"
            return outward if a.x*direction < 90 else "wait"
        if a.details.action_id in (252, 253):
            return "wait"
        action = self.probe.decide(observation).action
        return "wait" if action == "attack" else action

    def decide(self, observation):
        if self.complete:
            return self._decision(observation)
        if observation.frame < 0:
            return self._decision(observation)
        identity = (observation.episode, observation.bot.details.life_generation_derived)
        if self.started is None:
            self.started = observation.frame
            self.life = identity
        if identity != self.life:
            return self._finish(observation, "setup_failed" if self.phase == "setup" else "skill_failed", "life_or_episode_changed")
        if self.previous_frame is not None and observation.frame != self.previous_frame+1:
            return self._finish(observation, "setup_failed" if self.phase == "setup" else "skill_failed", "observation_discontinuity")
        self.previous_frame = observation.frame
        if self.phase == "setup":
            if self.last_action == "wait" and starting_predicate(self.spec, observation):
                self.phase = "measured"
                self.owner = "measured"
                self.initial = asdict(observation)
                self.measurement_start = observation.frame
                if self.spec.kind in ("grounded", "shielded"):
                    skill = SkillSpec("move", -self.spec.direction) if self.spec.kind == "grounded" else SkillSpec("shield")
                    reason = self.arbiter.request(skill, observation)
                    if reason:
                        return self._finish(observation, "skill_failed", "skill_refused:"+reason)
            elif observation.frame-self.started >= self.spec.setup_timeout_frames:
                return self._finish(observation, "setup_failed", "starting_predicate_timeout")
            else:
                action = "wait" if inhibited(observation) else self._setup(observation)
                return self._decision(observation, action)
        if inhibited(observation) and self.reflex is None:
            return self._finish(observation, "skill_failed", "measurement_inhibited:"+inhibited(observation))
        if observation.frame-self.measurement_start >= self.spec.measurement_timeout_frames:
            return self._finish(observation, "timeout", "measurement_deadline")
        a = observation.bot
        support = support_surface(a.x, a.y, a.grounded)
        known_support = support in ("ground", "left", "right", "top")
        if self.spec.kind in ("grounded", "shielded"):
            decision = self.arbiter.step(observation)
            if self.arbiter.active is None:
                event = self.arbiter.last_event or {}
                status = "succeeded" if event.get("status") == "succeeded" else "timeout" if event.get("status") == "timeout" else "skill_failed"
                return self._finish(observation, status, "skill:"+str(event.get("status")))
            return decision
        if self.spec.kind == "airborne":
            return self._finish(observation, "succeeded", "observed_landing") if known_support else self._decision(observation)
        if not inhibited(observation) and (known_support or
                (self.spec.kind in ("offstage", "offstage_low") and a.details.action_id in (252, 253))):
            return self._finish(observation, "succeeded", "observed_stage_or_ledge")
        if self.reflex is not None:
            decision = self.reflex.decide(observation)
            if self.reflex.failed:
                return self._finish(observation, "skill_failed", "reflex:"+self.reflex.event["reason"])
            return decision
        if self.spec.kind == "ledge":
            return self._decision(observation, "right" if self.spec.direction < 0 else "left")
        return self.probe.decide(observation)

    def trace(self):
        return {"schema_version": 1, "scenario": self.spec.name, "phase": self.phase,
            "setup_phase": self.setup_phase, "input_owner": self.owner,
            "measurement_start_frame": self.measurement_start, "skill": self.arbiter.trace(),
            "result": {k: v for k, v in (self.result or {}).items() if k != "end_observation"},
            **({"reflex": self.reflex.trace()} if self.reflex else {})}

    def report(self):
        return {"schema_version": 1, "scenario": self.spec.manifest(), "suite_sha256": suite_hash(scenario_suite(self.spec)),
            "complete": self.complete, "setup_started_frame": self.started,
            "setup_stopped_frame": None if self.measurement_start is None else self.measurement_start-1,
            "measurement_start_frame": self.measurement_start, "initial_observation": self.initial,
            "setup_privilege": "ordinary_controller_packets_only", "result": self.result,
            **({"reflex": self.reflex.trace()} if self.reflex else {})}


def verified_trial(report, name):
    try:
        spec = find_scenario(name)
        result = report["result"]
        if (report["complete"] is not True or report["scenario"] != spec.manifest() or
                report["suite_sha256"] != suite_hash(scenario_suite(spec)) or result["status"] not in RESULTS or
                report["setup_privilege"] != "ordinary_controller_packets_only"):
            return False
        if result["status"] == "setup_failed":
            return (report["initial_observation"] is None and report["measurement_start_frame"] is None and
                (result["reason"] != "starting_predicate_timeout" or
                    result["end_frame"]-report["setup_started_frame"] >= spec.setup_timeout_frames))
        from .engine import Observation
        initial = Observation.parse(report["initial_observation"])
        return (starting_predicate(spec, initial) and report["measurement_start_frame"] == initial.frame and
            report["setup_stopped_frame"] == initial.frame-1 and result["end_episode"] == initial.episode and
            result["end_frame"] >= initial.frame)
    except (KeyError, ValueError, TypeError):
        return False
