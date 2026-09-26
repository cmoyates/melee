"""Explicit paid policy backend for the existing latest-state frame boundary."""

from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
import threading
import time

from .async_policy import MIN_CONFIDENCE, Reply
from .budget import BudgetError, SpendLedger
from .config import owned_path
from .provider import DecisionsClient, MODEL_ALIAS, OpenRouterTransport, ProviderError
from .semantic import CompactObservation, SEMANTIC_VERSION, compact_observation

DESCRIPTIONS = {
    "neutral": "Release all inputs briefly; observe and wait for a better opportunity.",
    "approach": "Move a short safe distance toward the opponent on the current support surface.",
    "retreat": "Move a short safe distance away from the opponent on the current support surface.",
    "jump": "Perform a vertical ground jump, releasing jump after observed takeoff.",
    "shield": "Raise shield, hold briefly after it is observed, then release all inputs.",
}
INSTRUCTIONS = ("Control Fox against a level 3 Mario CPU on Battlefield. Choose the most useful available skill "
    "for the observed situation. Shield against a nearby grounded threat, reposition when spacing is poor, "
    "and consider jumping to change vertical spacing. Neutral is available when waiting is useful. "
    "These are bounded local skills, not attacks. The local executor handles emergencies and legality. "
    "Choose exactly one provided label and return its complete probability distribution.")


def policy_config_hash():
    return hashlib.sha256(json.dumps({"model": MODEL_ALIAS, "descriptions": DESCRIPTIONS,
        "instructions": INSTRUCTIONS, "max_inflight": 1, "interval_seconds": 1,
        "response_timeout_seconds": 1, "minimum_confidence": MIN_CONFIDENCE,
        "circuit_failure_threshold": 3, "circuit_open_seconds": 2,
        "semantic_version": SEMANTIC_VERSION}, sort_keys=True).encode()).hexdigest()


def provider_environment(policy):
    from .matches import isolated_environment
    environment = isolated_environment()
    if policy == "jev":
        for key in ("OPENROUTER_API_KEY", "OPENROUTER_MODEL"):
            if key in os.environ:
                environment[key] = os.environ[key]
    return environment


def preflight(root, policy, budget_directory, max_requests):
    if policy != "jev":
        if budget_directory is not None or max_requests is not None:
            raise ValueError("Provider options require the explicit jev policy")
        return None
    if not budget_directory or type(max_requests) is not int or not 1 <= max_requests <= 200:
        raise ValueError("Jev requires an existing budget and a 1-200 request cap")
    if not os.environ.get("OPENROUTER_API_KEY", "").strip():
        raise ProviderError("missing_credential")
    if os.environ.get("OPENROUTER_MODEL", MODEL_ALIAS) != MODEL_ALIAS:
        raise ProviderError("unverified_model_alias")
    ledger = SpendLedger(owned_path(root, budget_directory) / "spend.jsonl")
    report = ledger.report()
    if report.get("sealed"):
        raise BudgetError("Experiment budget is sealed")
    if datetime.fromisoformat(report["deadline_utc"]) <= datetime.now(timezone.utc):
        raise BudgetError("Budget deadline reached")
    if report["reservation_exceeded"]:
        raise BudgetError("Budget reservation exceeded")
    return report


class CountingTransport:
    def __init__(self, transport):
        self.transport = transport
        self.calls = 0
        self.active = 0
        self.lock = threading.Lock()

    def __call__(self, payload, timeout):
        with self.lock:
            self.calls += 1
            self.active += 1
        try:
            return self.transport(payload, timeout)
        finally:
            with self.lock:
                self.active -= 1


class ProviderBackend:
    name = "openrouter-decisions-v1"
    max_inflight = 1
    interval = 1.
    accepts_semantic = True

    def __init__(self, root, budget_directory, max_requests, run_deadline_ns, *, transport=None):
        if type(max_requests) is not int or not 1 <= max_requests <= 200:
            raise ProviderError("invalid_run_request_limit")
        self.ledger = SpendLedger(owned_path(root, budget_directory) / "spend.jsonl")
        self.budget_before = self.ledger.report()
        if self.budget_before.get("sealed"):
            raise BudgetError("Experiment budget is sealed")
        self.max_requests = max_requests
        global_remaining = (datetime.fromisoformat(self.budget_before["deadline_utc"]) - datetime.now(timezone.utc)).total_seconds()
        self.run_deadline_ns = min(run_deadline_ns, time.monotonic_ns() + int(global_remaining * 1e9))
        self.transport = CountingTransport(transport if transport is not None else
            OpenRouterTransport(os.environ.pop("OPENROUTER_API_KEY", "")))
        self.client = DecisionsClient(self.ledger, self.transport, max_in_flight=1)
        self.counts = Counter()
        self.attempts = []
        self.exhausted = False
        self.failures = 0
        self.open_until_ns = 0
        self.health_events = []
        self.config_hash = policy_config_hash()

    def call(self, observation, context, candidates, stop, semantic=None):
        if stop.is_set() or time.monotonic_ns() + 3_000_000_000 >= self.run_deadline_ns:
            self.exhausted = True
            return []
        if len(self.attempts) >= self.max_requests:
            self.exhausted = True
            return []
        attempt = {"sequence": context.sequence, "source_frame": observation.frame,
            "episode": observation.episode, "submitted_ns": time.monotonic_ns()}
        self.attempts.append(attempt)
        try:
            if time.monotonic_ns() < self.open_until_ns:
                raise ProviderError("circuit_open")
            if semantic is None:
                if context.semantic_sha256 is not None:
                    raise ProviderError("missing_semantic_snapshot")
                semantic = compact_observation(observation, candidates)
            if (not isinstance(semantic, CompactObservation) or
                    (context.semantic_sha256 is not None and context.semantic_sha256 != semantic.sha256)):
                raise ProviderError("semantic_snapshot_binding")
            result = self.client.submit(observation, {label: DESCRIPTIONS[label] for label in candidates},
                deadline_ns=min(time.monotonic_ns() + 1_000_000_000, self.run_deadline_ns - 2_000_000_000),
                instructions=INSTRUCTIONS, compact_state=semantic).result(timeout=1.5)
            if (result.episode, result.frame, result.observed_ns) != (context.episode, context.frame, context.observed_ns):
                raise ProviderError("response_observation_mismatch")
            metadata = asdict(result)
            metadata["semantic_sha256"] = semantic.sha256
            attempt.update(status="validated", request_id=result.request_id,
                received_ns=result.received_ns, result=metadata)
            self.counts["validated"] += 1
            if self.failures:
                self.health_events.append({"state": "recovered", "sequence": context.sequence,
                    "source_frame": observation.frame, "monotonic_ns": time.monotonic_ns()})
            self.failures = 0
            return [Reply(context, result.action, result.received_ns, metadata=metadata)]
        except (ProviderError, BudgetError) as error:
            reason = str(error) if isinstance(error, ProviderError) else "budget_refused"
            if isinstance(error, BudgetError):
                self.exhausted = True
            elif reason not in ("circuit_open", "provider_backoff", "in_flight_limit"):
                self.failures += 1
                if self.failures >= 3:
                    self.open_until_ns = time.monotonic_ns() + 2_000_000_000
                    self.health_events.append({"state": "open", "sequence": context.sequence,
                        "source_frame": observation.frame, "monotonic_ns": time.monotonic_ns()})
            attempt.update(status="rejected", reason=reason, received_ns=time.monotonic_ns())
            self.counts["errors:" + reason] += 1
            return [Reply(context, "", attempt["received_ns"], error=reason)]
        except Exception:
            attempt.update(status="rejected", reason="backend_error", received_ns=time.monotonic_ns())
            self.counts["errors:backend_error"] += 1
            return [Reply(context, "", attempt["received_ns"], error="backend_error")]
        finally:
            if len(self.attempts) >= self.max_requests:
                self.exhausted = True

    def close(self):
        closed = self.client.close(timeout=1.25)
        return {"schema_version": 1, "requested_model": MODEL_ALIAS, "config_sha256": self.config_hash,
            "max_requests": self.max_requests, "attempts": self.attempts, "counts": dict(self.counts),
            "health_events": self.health_events,
            "http_calls": self.transport.calls, "http_active": self.transport.active,
            "client_shutdown": closed, "budget_before": self.budget_before, "budget_after": self.ledger.report()}
