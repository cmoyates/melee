"""Bounded live skill repetitions with explicit refusals and observed outcomes."""

from .engine import Decision
from .skills import SkillArbiter, SkillSpec, can_start, inhibited

SUITE = (SkillSpec("neutral"), SkillSpec("move", -1), SkillSpec("move", 1),
            SkillSpec("jump", -1), SkillSpec("jump", 1), SkillSpec("jump"), SkillSpec("shield"))


def verified_report(report, repeats):
    """Recompute the claimed suite outcomes before the supervisor accepts them."""
    try:
        if (report["status"] != "pass" or report["complete"] is not True or report["repeats"] != repeats or
                report["suite"] != "movement-v1" or not isinstance(report["trials"], list) or
                len(report["trials"]) > 10000 or len(report["groups"]) != len(SUITE)):
            return False
        expected = {(s.name, s.direction) for s in SUITE}
        if {(g["skill"], g["direction"]) for g in report["groups"]} != expected:
            return False
        if any((r["skill"], r["direction"]) not in expected or
                r["status"] not in ("succeeded", "refused", "aborted", "timeout") for r in report["trials"]):
            return False
        for group in report["groups"]:
            rows = [r for r in report["trials"] if (r["skill"], r["direction"]) == (group["skill"], group["direction"])]
            for status in ("succeeded", "refused", "aborted", "timeout"):
                if type(group[status]) is not int or group[status] != sum(r["status"] == status for r in rows):
                    return False
            if (group["succeeded"] < 1 or group["timeout"] or group["attempts"] != len(rows) or
                    group["counted"] != repeats or group["succeeded"] + group["refused"] != repeats):
                return False
        return True
    except (KeyError, TypeError, ValueError):
        return False


class SkillCheckPolicy:
    def __init__(self, repeats=20):
        if type(repeats) is not int or not 1 <= repeats <= 100:
            raise ValueError("Skill repeats must be between 1 and 100")
        self.repeats = repeats
        self.arbiter = SkillArbiter()
        self.results = []
        self.pending = None
        self.ready_frame = None
        self.episode = None
        self.cooldown = 0

    @property
    def counted(self):
        return sum(r["status"] in ("succeeded", "refused") for r in self.results)

    @property
    def complete(self):
        return self.counted == len(SUITE) * self.repeats and self.pending is None

    def decide(self, observation):
        if observation.episode != self.episode:
            self.episode = observation.episode
            self.ready_frame = None
        if self.pending is not None:
            decision = self.arbiter.step(observation)
            if self.arbiter.active is None:
                self.results.append({**self.pending, **self.arbiter.last_event})
                self.pending = None
                self.ready_frame = None
                self.cooldown = 15
            return decision
        if self.complete:
            return Decision(1, observation.episode, observation.frame, "wait")
        # Keep the arbiter's continuity cursor current while waiting for setup.
        self.arbiter.step(observation)
        if inhibited(observation):
            self.ready_frame = None
            return Decision(1, observation.episode, observation.frame, "wait")
        if self.cooldown:
            self.cooldown -= 1
            return Decision(1, observation.episode, observation.frame, "wait")
        if self.ready_frame is None:
            self.ready_frame = observation.frame
        spec = SUITE[self.counted % len(SUITE)]
        reason = can_start(spec, observation)
        if reason and observation.frame - self.ready_frame < 120:
            return Decision(1, observation.episode, observation.frame, "wait")
        pending = {"attempt": len(self.results) + 1, "trial": self.counted + 1, "repetition": self.counted // len(SUITE) + 1,
                    "skill": spec.name, "direction": spec.direction,
                    "source_frame": observation.frame, "source_episode": observation.episode}
        refused = self.arbiter.request(spec, observation)
        if refused:
            self.results.append({**pending, **self.arbiter.last_event})
            self.ready_frame = None
            self.cooldown = 15
            return Decision(1, observation.episode, observation.frame, "wait")
        self.pending = pending
        # Continuity was observed above already; the first packet is next frame.
        return Decision(1, observation.episode, observation.frame, "wait")

    def report(self):
        groups = []
        for spec in SUITE:
            rows = [r for r in self.results if (r["skill"], r["direction"]) == (spec.name, spec.direction)]
            counts = {name: sum(r["status"] == name for r in rows) for name in ("succeeded", "refused", "aborted", "timeout")}
            groups.append({"skill": spec.name, "direction": spec.direction, "attempts": len(rows),
                            "counted": counts["succeeded"] + counts["refused"], **counts})
        return {"suite": "movement-v1", "repeats": self.repeats, "complete": self.complete,
                "groups": groups, "trials": self.results,
                "status": "pass" if self.complete and all(g["timeout"] == 0 and g["succeeded"] > 0 for g in groups) else "incomplete_or_failed"}

    def trace(self):
        return self.arbiter.trace()
