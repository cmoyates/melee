"""Latest-state inference boundary. Only the caller of decide owns input selection."""

from collections import Counter, deque
from dataclasses import asdict, dataclass, replace
import hashlib
import json
import threading
import time

from .fox_reflex import FoxReflex
from .semantic import SemanticHistory, compact_observation
from .skills import SkillArbiter, can_start, inhibited, relative_skill
from .stage import support_surface
from .tactical_choices import LABELS, legal_candidates

MAX_AGE_NS = 1_000_000_000
MAX_FRAME_AGE = 60
MIN_CONFIDENCE = .15


def candidate_hash(candidates):
    return hashlib.sha256(json.dumps(list(candidates), separators=(",", ":")).encode()).hexdigest()


def context_key(observation):
    a, b = observation.bot, observation.opponent
    return (support_surface(a.x, a.y, a.grounded), a.grounded,
            1 if b.x > a.x else -1 if b.x < a.x else 0,
            inhibited(observation), abs(a.x) > 65 or a.y < -5)


@dataclass(frozen=True)
class RequestContext:
    run_id: str
    episode: int
    bot_life: int
    opponent_life: int
    frame: int
    observed_ns: int
    sequence: int
    skill_generation: int
    candidate_hash: str
    context_key: tuple
    semantic_sha256: str | None = None


def bind(run_id, observation, sequence, generation, candidates, semantic_sha256=None):
    return RequestContext(run_id, observation.episode, observation.bot.details.life_generation_derived,
        observation.opponent.details.life_generation_derived, observation.frame, observation.observed_ns,
        sequence, generation, candidate_hash(candidates), context_key(observation), semantic_sha256)


@dataclass(frozen=True)
class Reply:
    context: RequestContext
    action: str
    received_ns: int
    fault: str = "none"
    error: str | None = None
    metadata: dict | None = None


@dataclass(frozen=True)
class Delivery:
    expected: RequestContext
    candidates: tuple
    reply: Reply


def rejection(delivery, observation, run_id, generation, last_applied, now_ns, committed):
    """Apply-time checks; submitting a newer request does not supersede a reply."""
    expected, reply = delivery.expected, delivery.reply
    c = reply.context
    if reply.error:
        return "backend:" + reply.error
    if c != expected or candidate_hash(delivery.candidates) != c.candidate_hash:
        return "request_binding"
    confidence = (reply.metadata or {}).get("confidence")
    if confidence is not None and confidence < MIN_CONFIDENCE:
        return "low_confidence"
    if c.run_id != run_id:
        return "wrong_run"
    if c.episode != observation.episode:
        return "wrong_episode"
    if (c.bot_life, c.opponent_life) != (observation.bot.details.life_generation_derived,
                                        observation.opponent.details.life_generation_derived):
        return "wrong_life"
    if c.sequence <= last_applied:
        return "superseded_or_duplicate"
    if not c.observed_ns <= reply.received_ns <= now_ns or not 0 <= now_ns - c.observed_ns <= MAX_AGE_NS:
        return "monotonic_age"
    if not 0 <= observation.frame - c.frame <= MAX_FRAME_AGE:
        return "frame_age"
    if c.skill_generation != generation:
        return "wrong_skill_generation"
    if c.context_key != context_key(observation):
        return "context_changed"
    if reply.action not in delivery.candidates or reply.action not in LABELS:
        return "invalid_candidate"
    if committed:
        return "skill_committed"
    reason = can_start(relative_skill(reply.action, observation), observation)
    return "illegal_now:" + reason if reason else None


class OrderingBackend:
    """Deterministic network faults, real wall-clock delays, no provider contact."""
    name = "ordering-v1"
    max_inflight = 4
    interval = .25

    def call(self, observation, context, candidates, stop):
        index = context.sequence % 12
        delay = (0., .05, 2., .4, .05, 0., 2., .05, .4, .05, 0., .05)[index]
        if stop.wait(delay):
            return []
        c = context
        fault = "none"
        if index == 4:
            c, fault = replace(c, episode=c.episode + 1), "wrong_episode"
        elif index == 5:
            c, fault = replace(c, bot_life=c.bot_life + 1), "wrong_life"
        elif index == 7:
            c, fault = replace(c, skill_generation=c.skill_generation + 1), "wrong_generation"
        elif index == 9:
            c, fault = replace(c, candidate_hash="0" * 64), "wrong_candidates"
        action = candidates[context.sequence % len(candidates)]
        if index == 10:
            action, fault = "not_a_skill", "invalid_candidate"
        reply = Reply(c, action, time.monotonic_ns(), fault)
        return [reply, replace(reply, fault="duplicate")] if index == 3 else [reply]


class LatestBridge:
    """Fixed workers, one replaceable snapshot and a bounded delivery mailbox.

    Frame-side operations never wait for the lock. Backend calls (including any
    ledger fsync) run outside the lock and have no controller reference.
    """
    def __init__(self, run_id, backend):
        if type(backend.max_inflight) is not int or not 1 <= backend.max_inflight <= 4:
            raise ValueError("Invalid inference worker limit")
        self.run_id, self.backend = run_id, backend
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.latest = None
        self.deliveries = deque(maxlen=32)
        self.sequence = 0
        self.next_request = 0.
        self.last_source = None
        self.counts = Counter()
        self.active = 0
        self.threads = [threading.Thread(target=self._run, name="jev-inference-" + str(i), daemon=True)
                        for i in range(backend.max_inflight)]
        for thread in self.threads:
            thread.start()

    def exchange(self, observation, generation, candidates, semantic=None):
        if not self.lock.acquire(blocking=False):
            return None
        try:
            self.latest = (observation, generation, tuple(candidates), semantic)
            result = list(self.deliveries)
            self.deliveries.clear()
            return result
        finally:
            self.lock.release()

    def _run(self):
        while not self.stop.wait(.005):
            with self.lock:
                latest = self.latest
                now = time.monotonic()
                if latest is None or now < self.next_request or getattr(self.backend, "exhausted", False):
                    continue
                observation, generation, candidates, semantic = latest
                source = (observation.episode, observation.frame)
                if len(candidates) < 2 or source == self.last_source or time.monotonic_ns() - observation.observed_ns > MAX_AGE_NS:
                    continue
                self.next_request = now + self.backend.interval
                self.last_source = source
                self.sequence += 1
                context = bind(self.run_id, observation, self.sequence, generation, candidates,
                    semantic.sha256 if semantic is not None else None)
                self.active += 1
                self.counts["submitted"] += 1
                self.counts["peak_inflight"] = max(self.counts["peak_inflight"], self.active)
            try:
                replies = self.backend.call(observation, context, candidates, self.stop,
                    **({"semantic": semantic} if getattr(self.backend, "accepts_semantic", False) else {}))
                deliveries = [Delivery(context, candidates, reply) for reply in replies]
            except Exception:
                deliveries = []
                with self.lock:
                    self.counts["backend_errors"] += 1
            finally:
                with self.lock:
                    self.active -= 1
            with self.lock:
                for delivery in deliveries:
                    if len(self.deliveries) == self.deliveries.maxlen:
                        self.counts["mailbox_dropped"] += 1
                    self.deliveries.append(delivery)
                    self.counts["delivered"] += 1
                    self.counts["peak_mailbox"] = max(self.counts["peak_mailbox"], len(self.deliveries))

    def close(self):
        self.stop.set()
        deadline = time.monotonic() + 2.5
        for thread in self.threads:
            thread.join(max(0., deadline - time.monotonic()))
        backend_report = self.backend.close() if hasattr(self.backend, "close") else None
        with self.lock:
            discarded = [asdict(delivery) for delivery in self.deliveries]
            self.deliveries.clear()
            self.counts["shutdown_discarded"] = len(discarded)
        return {**self.report(), "shutdown_deliveries": discarded, "provider": backend_report}

    def report(self):
        with self.lock:
            return {"backend": self.backend.name, **dict(self.counts), "inflight": self.active,
                    "mailbox_remaining": len(self.deliveries), "worker_limit": len(self.threads),
                    "workers_alive": sum(t.is_alive() for t in self.threads)}


class AsyncPolicy:
    def __init__(self, run_id, bridge=None, clock=time.monotonic_ns):
        self.run_id = run_id
        self.bridge = bridge if bridge is not None else LatestBridge(run_id, OrderingBackend())
        self.clock = clock
        self.arbiter = SkillArbiter()
        self.recovery = FoxReflex()
        self.last_applied = 0
        self.next_fallback_ns = 0
        self.events = []
        self.counts = Counter()
        self.last_invalidation = None
        self.last_frame = None
        self.skill_events = []
        self.owner = "idle"
        self.last_owner = "idle"
        self.decision_ns = None
        self.exchange_busy = False
        self.semantic_history = SemanticHistory()
        self.semantic_state = None

    def _record_skill_event(self):
        event = self.arbiter.last_event
        if event is not None and event not in self.skill_events:
            self.skill_events.append(dict(event))

    def _record_owner(self, owner, observation):
        self.last_owner = owner
        self.counts["frames:" + owner] += 1
        if observation.frame >= 0:
            self.counts["play_frames:" + owner] += 1

    def decide(self, observation):
        now = self.clock()
        self.decision_ns = now
        self.events = []
        self.skill_events = []
        if self.arbiter.active is None:
            self.owner = "idle"
        a = observation.bot
        emergency = self.recovery.reason(observation)
        if emergency == "hitlag" and self.arbiter.retains_attack_hitlag(observation):
            emergency = None  # The active attack's observed hitlag retains its commitment.
        # Observe every frame, including ordinary skill ownership, so a landing
        # clears recovery commitments and the continuity cursor stays current.
        reflex_decision = self.recovery.decide(observation)
        identity = (observation.episode, a.details.life_generation_derived,
                    observation.opponent.details.life_generation_derived, emergency)
        discontinuity = self.last_frame is not None and self.last_frame != (observation.episode, observation.frame - 1)
        self.last_frame = (observation.episode, observation.frame)
        if identity != self.last_invalidation or discontinuity:
            if self.last_invalidation is not None:
                self.arbiter.abort(observation, emergency or "context_generation_changed")
                self._record_skill_event()
                self.arbiter.generation += 1
                self.counts["generation_invalidations"] += 1
            self.last_invalidation = identity
        candidates = legal_candidates(observation)
        offered = candidates if not emergency else ()
        self.semantic_state = compact_observation(observation, offered, active_skill=self.arbiter.trace()["active"],
            skill_known=True, history=self.semantic_history.before(observation))
        deliveries = self.bridge.exchange(observation, self.arbiter.generation, offered, self.semantic_state)
        self.exchange_busy = deliveries is None
        if deliveries is None:
            self.counts["mailbox_busy"] += 1
            deliveries = []
        for delivery in deliveries:
            generation = self.arbiter.generation
            committed = self.arbiter.active is not None
            previous = self.last_applied
            reason = rejection(delivery, observation, self.run_id, generation, previous, now, committed)
            if emergency and reason is None:
                reason = "emergency"
            if reason is None:
                reason = self.arbiter.request(relative_skill(delivery.reply.action, observation), observation)
            accepted = reason is None
            if accepted:
                self.last_applied = delivery.expected.sequence
                self.next_fallback_ns = now + 1_500_000_000
                self.owner = "provider"
                self._record_skill_event()
            self.counts["accepted" if accepted else "rejected:" + reason] += 1
            self.events.append({"delivery": asdict(delivery), "accepted": accepted, "reason": reason,
                "apply_ns": now, "generation_before": generation, "last_applied_before": previous,
                "committed_before": committed, "emergency": emergency})
        decision = self.arbiter.step(observation)
        self._record_skill_event()
        if emergency:
            self.counts["emergency_frames"] += 1
            self._record_owner("emergency", observation)
            return reflex_decision
        self._record_owner(self.owner, observation)
        if self.arbiter.active is None and now >= self.next_fallback_ns:
            label = "approach" if "approach" in candidates else "retreat" if "retreat" in candidates else "neutral"
            if self.arbiter.request(relative_skill(label, observation), observation) is None:
                self.next_fallback_ns = now + 1_500_000_000
                self.counts["local_fallbacks"] += 1
                self.owner = "fallback"
                self._record_skill_event()
        return decision

    def trace(self):
        return {**self.arbiter.trace(), "policy_events": self.events, "last_applied_sequence": self.last_applied,
                "transitions": self.skill_events, "input_owner": self.last_owner,
                "decision_ns": self.decision_ns, "exchange_busy": self.exchange_busy,
                "reflex": self.recovery.trace(), "semantic_state": self.semantic_state.wire() if self.semantic_state else None}

    def close(self):
        return {"schema_version": 1, "max_age_ns": MAX_AGE_NS, "max_frame_age": MAX_FRAME_AGE,
                "policy": dict(self.counts), "bridge": self.bridge.close(), "reflex": self.recovery.trace()}
