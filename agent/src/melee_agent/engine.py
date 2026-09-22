"""Asset-free contracts and the frame-to-controller path shared by live and fake runs."""

from dataclasses import asdict, dataclass
import math
from typing import Protocol

from .stage import STAGE_NAME
from .rules import SIMULATION_FPS


def integer(value, name, minimum=None):
    if type(value) is not int or (minimum is not None and value < minimum):
        raise ValueError(f"{name} must be an integer in range")


def finite(value, name, low=None, high=None):
    try:
        valid = type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError(f"{name} must be finite")
    if (low is not None and value < low) or (high is not None and value > high):
        raise ValueError(f"{name} is out of range")


def exact_fields(data, cls):
    if not isinstance(data, dict) or set(data) != set(cls.__dataclass_fields__):
        raise ValueError(f"{cls.__name__} fields do not match schema")


@dataclass(frozen=True)
class FighterDetails:
    action_id: int
    action_frame: int
    life_generation_derived: int
    percent: float
    facing_right: bool
    hitlag_frames_derived: int
    hitstun_frames_derived: int
    self_velocity_x: float
    self_velocity_y: float
    attack_velocity_x: float
    attack_velocity_y: float
    shield_strength: float
    input_neutral_derived: bool
    input_jump_held: bool
    input_shield_held: bool
    hurtbox_state: int | None = None

    def __post_init__(self):
        for name in ("action_id", "hitlag_frames_derived", "hitstun_frames_derived"):
            integer(getattr(self, name), name, 0)
        integer(self.action_frame, "action frame")
        integer(self.life_generation_derived, "life generation", 1)
        if self.action_id > 65535 or self.life_generation_derived > 100:
            raise ValueError("Invalid fighter identity")
        for name in ("percent", "self_velocity_x", "self_velocity_y", "attack_velocity_x", "attack_velocity_y", "shield_strength"):
            finite(getattr(self, name), name)
        for name in ("facing_right", "input_neutral_derived", "input_jump_held", "input_shield_held"):
            if type(getattr(self, name)) is not bool:
                raise ValueError("Invalid fighter boolean")
        if self.hurtbox_state is not None:
            integer(self.hurtbox_state, "hurtbox state", 0)
            if self.hurtbox_state > 2:
                raise ValueError("Unsupported hurtbox state")

    @classmethod
    def parse(cls, data):
        exact_fields(data, cls)
        return cls(**data)


@dataclass(frozen=True)
class Fighter:
    x: float
    y: float
    grounded: bool
    jumps: int
    action: str
    stocks_remaining: int
    details: FighterDetails

    def __post_init__(self):
        finite(self.x, "fighter x")
        finite(self.y, "fighter y")
        if type(self.grounded) is not bool:
            raise ValueError("grounded must be boolean")
        integer(self.jumps, "jumps", 0)
        integer(self.stocks_remaining, "stocks remaining", 0)
        if self.stocks_remaining > 99:
            raise ValueError("Invalid stock count")
        if self.jumps > 6 or not isinstance(self.action, str) or not self.action or len(self.action) > 80:
            raise ValueError("Invalid fighter jumps/action")
        if not isinstance(self.details, FighterDetails):
            raise ValueError("Fighter requires validated details")

    @classmethod
    def parse(cls, data):
        exact_fields(data, cls)
        return cls(**{**data, "details": FighterDetails.parse(data["details"])})


@dataclass(frozen=True)
class MatchProgress:
    time_limit_seconds: int
    starting_stocks: int
    elapsed_seconds_derived: float
    remaining_seconds_derived: float

    def __post_init__(self):
        integer(self.time_limit_seconds, "match time limit", 1)
        integer(self.starting_stocks, "starting stocks", 1)
        if self.time_limit_seconds > 5940 or self.starting_stocks > 99:
            raise ValueError("Unsupported match rules")
        finite(self.elapsed_seconds_derived, "elapsed match time", 0)
        finite(self.remaining_seconds_derived, "remaining match time", 0, self.time_limit_seconds)
        expected = max(0, self.time_limit_seconds - self.elapsed_seconds_derived)
        if not math.isclose(self.remaining_seconds_derived, expected, rel_tol=0, abs_tol=1e-9):
            raise ValueError("Match times disagree")

    @classmethod
    def from_frame(cls, frame, time_limit_seconds, starting_stocks):
        integer(frame, "match frame")
        elapsed = max(0, frame) / SIMULATION_FPS
        return cls(time_limit_seconds, starting_stocks, elapsed, max(0, time_limit_seconds - elapsed))

    @classmethod
    def parse(cls, data):
        exact_fields(data, cls)
        return cls(**data)


@dataclass(frozen=True)
class Observation:
    schema_version: int
    episode: int
    frame: int
    observed_ns: int
    stage: str
    bot: Fighter
    opponent: Fighter
    match: MatchProgress

    def __post_init__(self):
        integer(self.schema_version, "schema version")
        if self.schema_version != 4 or self.stage != STAGE_NAME:
            raise ValueError("Unsupported observation version/stage")
        integer(self.episode, "episode", 1)
        integer(self.frame, "frame")
        integer(self.observed_ns, "observed time", 0)
        if not isinstance(self.bot, Fighter) or not isinstance(self.opponent, Fighter):
            raise ValueError("Observation requires validated fighters")
        if not isinstance(self.match, MatchProgress):
            raise ValueError("Observation requires validated match progress")
        if max(self.bot.stocks_remaining, self.opponent.stocks_remaining) > self.match.starting_stocks:
            raise ValueError("Remaining stocks exceed starting stocks")
        for fighter in (self.bot, self.opponent):
            if fighter.details.life_generation_derived != self.match.starting_stocks - fighter.stocks_remaining + 1:
                raise ValueError("Life generation disagrees with observed stocks")
        if not math.isclose(self.match.elapsed_seconds_derived, max(0, self.frame) / SIMULATION_FPS,
                            rel_tol=0, abs_tol=1e-9):
            raise ValueError("Match elapsed time disagrees with simulation frame")

    @classmethod
    def parse(cls, data):
        exact_fields(data, cls)
        return cls(**{**data, "bot": Fighter.parse(data["bot"]), "opponent": Fighter.parse(data["opponent"]),
                        "match": MatchProgress.parse(data["match"])})


@dataclass(frozen=True)
class Decision:
    schema_version: int
    episode: int
    frame: int
    action: str

    def __post_init__(self):
        integer(self.schema_version, "decision version")
        integer(self.episode, "decision episode", 1)
        integer(self.frame, "decision frame")
        if self.schema_version != 1 or type(self.action) is not str or self.action not in ACTION_PACKETS:
            raise ValueError("Unsupported decision version/action")


BUTTONS = ("A", "B", "X", "Y", "Z", "L", "R", "START", "D_UP", "D_DOWN", "D_LEFT", "D_RIGHT")


@dataclass(frozen=True)
class Packet:
    schema_version: int = 1
    main_x: float = 0.5
    main_y: float = 0.5
    c_x: float = 0.5
    c_y: float = 0.5
    l: float = 0.0
    r: float = 0.0
    held: tuple[str, ...] = ()

    def __post_init__(self):
        integer(self.schema_version, "packet version")
        if self.schema_version != 1:
            raise ValueError("Unsupported packet version")
        for name in ("main_x", "main_y", "c_x", "c_y", "l", "r"):
            finite(getattr(self, name), name, 0, 1)
        if (type(self.held) is not tuple or any(type(b) is not str or b not in BUTTONS for b in self.held)
                or len(set(self.held)) != len(self.held)):
            raise ValueError("Invalid packet buttons")

    def wire(self):
        return {"schema_version": 1, "main": [self.main_x, self.main_y], "c": [self.c_x, self.c_y],
                "l": self.l, "r": self.r, "buttons": {b: b in self.held for b in BUTTONS}}


ACTION_PACKETS = {
    "wait": Packet(), "left": Packet(main_x=0.0), "right": Packet(main_x=1.0),
    "drop_right": Packet(main_x=1.0, main_y=0.0), "attack": Packet(held=("A",)),
    "jump_left": Packet(main_x=0.0, held=("X",)), "jump_right": Packet(main_x=1.0, held=("X",)),
    "recover_left": Packet(main_x=0.0, main_y=1.0, held=("B",)),
    "recover_right": Packet(main_x=1.0, main_y=1.0, held=("B",)),
    "jump": Packet(held=("X",)), "shield": Packet(l=1., held=("L",)),
    "special_up": Packet(main_y=1., held=("B",)),
    "aim_up": Packet(main_y=1.),
    "aim_steep_left": Packet(main_x=.25, main_y=1.),
    "aim_steep_right": Packet(main_x=.75, main_y=1.),
    "aim_diagonal_left": Packet(main_x=0., main_y=1.),
    "aim_diagonal_right": Packet(main_x=1., main_y=1.),
    "aim_shallow_left": Packet(main_x=0., main_y=.75),
    "aim_shallow_right": Packet(main_x=1., main_y=.75),
    "down_tilt": Packet(main_y=.25, held=("A",)),
    "grab": Packet(l=1., held=("L", "A")),
    "slow_left": Packet(main_x=.35), "slow_right": Packet(main_x=.65),
}


class StateSource(Protocol):
    def next(self) -> Observation | None: ...


class ControllerSink(Protocol):
    def send(self, packet: Packet) -> None: ...


class TacticalPolicy(Protocol):
    def decide(self, observation: Observation) -> Decision: ...


class MonotonicClock(Protocol):
    def now_ns(self) -> int: ...


class ScriptedPolicy:
    def __init__(self, mode="scripted"):
        if mode not in ("scripted", "smoke", "input-probe"):
            raise ValueError("Unknown scripted policy")
        self.mode = mode

    def decide(self, observation):
        a, b, frame = observation.bot, observation.opponent, observation.frame
        action = "wait"
        if frame >= 0:
            if self.mode == "input-probe":
                action = "right" if frame < 20 else "left" if 40 <= frame < 60 else "wait"
            elif self.mode == "smoke":
                action = "drop_right" if "REBIRTH" in a.action else "right"
            elif abs(a.x) > 65 or a.y < -5:
                direction = "left" if a.x > 0 else "right"
                action = direction
                if not a.grounded:
                    if a.jumps and frame % 12 == 0:
                        action = "jump_" + direction
                    elif a.y < -15:
                        action = "recover_" + direction
            elif abs(b.x - a.x) > 13:
                action = "right" if b.x > a.x else "left"
            elif frame % 12 < 6:
                action = "attack"
        return Decision(1, observation.episode, frame, action)


class FrameExecutor:
    def __init__(self, policy: TacticalPolicy, sink: ControllerSink, clock: MonotonicClock):
        self.policy, self.sink, self.clock = policy, sink, clock
        self.last = None
        self.last_time = -1

    def step(self, observation: Observation):
        if not isinstance(observation, Observation):
            raise ValueError("Executor requires a validated observation")
        identity = (observation.episode, observation.frame)
        if self.last is not None and identity <= self.last:
            raise ValueError("Stale or duplicate observation")
        now = self.clock.now_ns()
        integer(now, "clock time", 0)
        if now < self.last_time or observation.observed_ns > now:
            raise ValueError("Clock or observation time moved outside its horizon")
        decision = self.policy.decide(observation)
        if not isinstance(decision, Decision) or (decision.episode, decision.frame) != identity:
            raise ValueError("Decision belongs to a different observation")
        packet = ACTION_PACKETS[decision.action]
        queued = self.clock.now_ns()
        integer(queued, "queued time", 0)
        if queued < now:
            raise ValueError("Clock moved backwards while deciding")
        self.sink.send(packet)
        self.last, self.last_time = identity, queued
        return {"observation": asdict(observation), "decision": asdict(decision), "packet": packet.wire(),
                "executor_started_ns": now, "queued_ns": queued}

    def run(self, source: StateSource):
        while (observation := source.next()) is not None:
            yield self.step(observation)


@dataclass(frozen=True)
class RunManifest:
    schema_version: int
    backend: str
    stage: str
    trace_sha256: str
    frames: int
    live_validation: str = "blocked"

    def __post_init__(self):
        integer(self.schema_version, "manifest version")
        if self.schema_version != 1 or self.backend != "fake" or self.stage != STAGE_NAME:
            raise ValueError("Unsupported fake-run manifest")
        integer(self.frames, "manifest frames", 0)
        if len(self.trace_sha256) != 64 or any(c not in "0123456789abcdef" for c in self.trace_sha256):
            raise ValueError("Invalid trace digest")
        if self.live_validation != "blocked":
            raise ValueError("Fake runs cannot certify live gameplay")
