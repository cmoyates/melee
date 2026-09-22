"""Offline selectors sharing observed commitments, reflexes and packet ownership."""

from collections import Counter
import random

from .fox_reflex import FoxReflex
from .ground_combat import combat_candidates, select_combat
from .skills import SkillArbiter, can_start, relative_skill


class LocalCombatPolicy:
    def __init__(self, mode="heuristic", seed=0):
        if mode not in ("heuristic", "random-legal") or type(seed) is not int:
            raise ValueError("Invalid local combat selector")
        self.mode, self.seed = mode, seed
        self.rng = random.Random(seed)
        self.arbiter = SkillArbiter()
        self.recovery = FoxReflex()
        self.identity = None
        self.previous_frame = None
        self.next_selection = 0
        self.selection = None
        self.owner = "idle"
        self.counts = Counter()

    def decide(self, observation):
        a, b = observation.bot, observation.opponent
        identity = (observation.episode, a.details.life_generation_derived, b.details.life_generation_derived)
        gap = self.previous_frame is not None and self.previous_frame != (observation.episode, observation.frame-1)
        if identity != self.identity or gap:
            self.arbiter.abort(observation, "context_changed")
            self.next_selection = observation.frame
            self.identity = identity
        self.previous_frame = (observation.episode, observation.frame)
        self.selection = None
        emergency = self.recovery.reason(observation)
        if emergency == "hitlag" and self.arbiter.retains_attack_hitlag(observation):
            emergency = None
        reflex = self.recovery.decide(observation)
        if emergency:
            self.arbiter.abort(observation, emergency)
            self.arbiter.step(observation)  # Maintain the same observation cursor while reflex owns input.
            self.owner = "emergency"
            self.counts["emergency_frames"] += 1
            return reflex
        if self.arbiter.active is None and observation.frame >= self.next_selection:
            candidates = combat_candidates(observation)
            label = select_combat(observation, self.mode, self.rng)
            if label is None:
                label = "approach" if can_start(relative_skill("approach", observation), observation) is None else "neutral"
            refusal = self.arbiter.request(relative_skill(label, observation), observation)
            self.selection = {"frame": observation.frame, "mode": self.mode,
                "combat_candidates": list(candidates), "selected": label, "refusal": refusal}
            self.counts["selected:"+label] += 1
            self.next_selection = observation.frame+60
        self.owner = "local" if self.arbiter.active is not None else "idle"
        return self.arbiter.step(observation)

    def trace(self):
        return {**self.arbiter.trace(), "input_owner": self.owner, "local_selection": self.selection,
            "reflex": self.recovery.trace()}

    def close(self):
        return {"schema_version": 1, "mode": self.mode, "seed": self.seed,
            "cadence_frames": 60, "counts": dict(self.counts), "provider_contacted": False}
