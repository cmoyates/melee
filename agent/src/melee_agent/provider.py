"""Bounded OpenRouter Decisions transport; no dependency on controller output.

Submit and collect outside the frame executor. Deadlines complete caller futures
even if the network stalls; a timed-out transport retains its in-flight slot and
spend reservation until its worker actually returns. No retries or hidden queue.
"""

from concurrent.futures import Future
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
import math
import re
import subprocess
import sys
import threading
import time

from .budget import BudgetError, cost_units
from .engine import Observation

MODEL_ALIAS = "~typesafe/jev-latest"
VERIFIED_MODEL = "typesafe/jev-1.13-20260917"
ENDPOINT = "https://openrouter.ai/api/alpha/decisions"
MAX_BODY_BYTES = 16384
MAX_RESPONSE_BYTES = 65536
# 32k context at a routing ceiling of $0.042/M input, $0 output is <= $0.001344.
# Reserve $0.002 and 32k input tokens even for tiny requests until usage is known.
RESERVE_NANO_USD = 2_000_000
RESERVE_INPUT_TOKENS = 32000


class ProviderError(ValueError):
    """Public-safe classification; no server text, credentials or raw payloads."""


@dataclass(frozen=True)
class ChoiceResult:
    request_id: str
    episode: int
    frame: int
    observed_ns: int
    received_ns: int
    action: str
    probabilities: dict
    confidence: float | None
    requested_model: str
    resolved_model: str
    provider: str
    usage: dict
    answers: dict


def probability(value):
    return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1


def decode_response(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ProviderError("duplicate_response_field")
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=unique,
                            parse_constant=lambda _: (_ for _ in ()).throw(ProviderError("nonfinite_response")))
    except (UnicodeError, ValueError):
        raise ProviderError("invalid_response_json") from None


def validate_answer(answer, candidates):
    if set(answer) not in ({"type", "choice", "probabilities"}, {"type", "choice", "probabilities", "confidence"}):
        raise ProviderError("unexpected_answer_fields")
    if answer["type"] != "choice" or answer["choice"] not in candidates:
        raise ProviderError("invalid_choice")
    probs = answer["probabilities"]
    if not isinstance(probs, dict) or set(probs) != set(candidates) or not all(probability(p) for p in probs.values()):
        raise ProviderError("invalid_distribution")
    if not math.isclose(sum(probs.values()), 1, rel_tol=0, abs_tol=1e-5):
        raise ProviderError("invalid_distribution_sum")
    confidence = answer.get("confidence")
    if confidence is not None and not probability(confidence):
        raise ProviderError("invalid_confidence")
    return {"type": "choice", "choice": answer["choice"], "probabilities": dict(probs), "confidence": confidence}


def parse_choice(data, candidates, observation, request_id, received_ns, extra_candidates=None):
    try:
        if not isinstance(data, dict) or "error" in data:
            raise ProviderError("invalid_response")
        if data["model"] != VERIFIED_MODEL or data["provider"] != "TypeSafe":
            raise ProviderError("unverified_model_identity")
        contracts = {"action": candidates, **(extra_candidates or {})}
        if set(data["answers"]) != set(contracts):
            raise ProviderError("unexpected_answers")
        answers = {name: validate_answer(data["answers"][name], labels) for name, labels in contracts.items()}
        answer = answers["action"]
        usage = data["usage"]
        cost_units(usage["cost"])
        if any(type(usage[k]) is not int or usage[k] < 0 for k in ("input_tokens", "output_tokens")):
            raise ProviderError("invalid_usage")
        return ChoiceResult(request_id, observation.episode, observation.frame, observation.observed_ns,
                            received_ns, answer["choice"], answer["probabilities"], answer["confidence"], MODEL_ALIAS,
                            data["model"], data["provider"], {k: usage[k] for k in ("cost", "input_tokens", "output_tokens")}, answers)
    except (KeyError, TypeError, OverflowError, BudgetError):
        raise ProviderError("malformed_response") from None


class OpenRouterTransport:
    def __init__(self, key):
        if not isinstance(key, str) or not key.strip():
            raise ProviderError("missing_credential")
        self._key = key.strip()

    def __call__(self, payload, timeout):
        from .matches import isolated_environment
        # A subprocess bounds even a peer that drip-feeds bytes below a socket's
        # inactivity timeout. Credentials travel through stdin, never argv/logs.
        child = subprocess.Popen([sys.executable, "-B", "-m", "melee_agent.provider_http"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            env=isolated_environment())
        try:
            raw, _ = child.communicate(json.dumps({"key": self._key, "payload": payload.decode(),
                                                    "timeout": timeout}).encode(), timeout=timeout)
            if child.returncode != 0 or len(raw) > MAX_RESPONSE_BYTES * 2:
                raise ProviderError("transport_error")
            envelope = decode_response(raw)
            return envelope["status"], envelope["headers"], envelope["body"].encode()
        except subprocess.TimeoutExpired:
            raise ProviderError("transport_timeout") from None
        finally:
            if child.poll() is None:
                child.kill()
            child.communicate(timeout=2)


def retry_delay(headers):
    value = next((v for k, v in headers.items() if k.lower() == "retry-after"), "1")
    try:
        delay = float(value)
    except (ValueError, TypeError):
        try:
            delay = (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds()
        except (ValueError, TypeError, OverflowError):
            delay = 1
    return max(1, min(3600, delay)) if math.isfinite(delay) else 3600


class DecisionsClient:
    def __init__(self, ledger, transport, *, max_in_flight=1):
        if type(max_in_flight) is not int or not 1 <= max_in_flight <= 4:
            raise ProviderError("invalid_concurrency")
        self.ledger, self.transport = ledger, transport
        self._slots = threading.BoundedSemaphore(max_in_flight)
        self._lock = threading.RLock()
        self._backoff_until = 0
        self._closed = False
        self._futures = set()
        self._workers = set()
        self._timers = set()

    def submit(self, observation, candidates, *, deadline_ns, instructions="Choose the best available action for Fox.",
                additional_questions=None, compact_state=None):
        if not isinstance(observation, Observation):
            raise ProviderError("invalid_observation")
        if (not isinstance(candidates, dict) or not 2 <= len(candidates) <= 16 or
                any(type(k) is not str or not re.fullmatch(r"[a-z][a-z0-9_]{0,39}", k) or
                    type(v) is not str or not 1 <= len(v) <= 256 for k, v in candidates.items())):
            raise ProviderError("invalid_candidates")
        if type(instructions) is not str or not 1 <= len(instructions) <= 1024:
            raise ProviderError("invalid_instructions")
        candidates = dict(candidates)
        questions = {"action": {"type": "choice", "instructions": instructions, "criteria": candidates}}
        extra = {}
        if additional_questions is not None:
            if not isinstance(additional_questions, dict) or len(additional_questions) > 2:
                raise ProviderError("invalid_question_batch")
            for name, question in additional_questions.items():
                if (type(name) is not str or not re.fullmatch(r"[a-z][a-z0-9_]{0,39}", name) or name == "action" or
                        not isinstance(question, dict) or set(question) != {"instructions", "criteria"}):
                    raise ProviderError("invalid_question_batch")
                labels, text = question["criteria"], question["instructions"]
                if (not isinstance(labels, dict) or not 2 <= len(labels) <= 16 or
                        type(text) is not str or not 1 <= len(text) <= 1024 or
                        any(type(k) is not str or not re.fullmatch(r"[a-z][a-z0-9_]{0,39}", k) or
                            type(v) is not str or not 1 <= len(v) <= 256 for k, v in labels.items())):
                    raise ProviderError("invalid_question_batch")
                extra[name] = dict(labels)
                questions[name] = {"type": "choice", "instructions": text, "criteria": extra[name]}
        now = time.monotonic_ns()
        if type(deadline_ns) is not int or not now < deadline_ns <= now + 30_000_000_000:
            raise ProviderError("invalid_deadline")
        if observation.observed_ns > now:
            raise ProviderError("future_observation")
        state = asdict(observation)
        if compact_state is not None:
            from .semantic import CompactObservation
            if (not isinstance(compact_state, CompactObservation) or
                    (compact_state.episode, compact_state.frame, compact_state.observed_ns) !=
                    (observation.episode, observation.frame, observation.observed_ns)):
                raise ProviderError("compact_state_binding")
            state = compact_state.wire()
            if state["mechanical"]["legal_candidates"] != list(candidates):
                raise ProviderError("compact_candidate_binding")
        payload = json.dumps({"model": MODEL_ALIAS, "state": state,
            "questions": questions,
            "provider": {"only": ["TypeSafe"], "allow_fallbacks": False,
                            "max_price": {"prompt": 0.042, "completion": 0}}},
            allow_nan=False, separators=(",", ":")).encode()
        if len(payload) > MAX_BODY_BYTES:
            raise ProviderError("request_too_large")
        with self._lock:
            if self._closed:
                raise ProviderError("client_closed")
            if now < self._backoff_until:
                raise ProviderError("provider_backoff")
            if not self._slots.acquire(blocking=False):
                raise ProviderError("in_flight_limit")
        try:
            request_id = self.ledger.reserve(cost_nano_usd=RESERVE_NANO_USD * len(questions),
                input_tokens=RESERVE_INPUT_TOKENS * len(questions), payload_sha256=hashlib.sha256(payload).hexdigest())
        except BaseException:
            self._slots.release()
            raise
        future = Future()
        future.set_running_or_notify_cancel()
        with self._lock:
            if self._closed:
                self._slots.release()
                future.set_exception(ProviderError("client_closed"))
                return future
            self._futures.add(future)

        def finish(value=None, error=None):
            with self._lock:
                if not future.done():
                    if error:
                        future.set_exception(error)
                    else:
                        future.set_result(value)
                self._futures.discard(future)

        timer = threading.Timer(max(0, (deadline_ns - time.monotonic_ns()) / 1e9),
                                lambda: finish(error=ProviderError("deadline_exceeded")))
        timer.daemon = True

        def work():
            try:
                remaining = (deadline_ns - time.monotonic_ns()) / 1e9
                if remaining <= 0 or future.done():
                    raise ProviderError("deadline_exceeded")
                status, headers, raw = self.transport(payload, remaining)
                if status != 200:
                    if status == 429 or status >= 500:
                        with self._lock:
                            self._backoff_until = max(self._backoff_until,
                                time.monotonic_ns() + int(retry_delay(headers) * 1e9))
                    raise ProviderError("rate_limited" if status == 429 else "http_error")
                data = decode_response(raw)
                # Settle known billing even when the answer is invalid or too late.
                usage = data.get("usage", {}) if isinstance(data, dict) else {}
                self.ledger.settle(request_id, cost_usd=usage["cost"], input_tokens=usage["input_tokens"])
                received = time.monotonic_ns()
                if received > deadline_ns:
                    raise ProviderError("deadline_exceeded")
                result = parse_choice(data, candidates, observation, request_id, received, extra)
                if self.ledger.report()["reservation_exceeded"]:
                    raise ProviderError("reservation_exceeded")
                finish(value=result)
            except Exception as error:
                # Socket exceptions and server responses can contain private data.
                finish(error=error if isinstance(error, ProviderError) else ProviderError("transport_or_accounting_error"))
            finally:
                timer.cancel()
                self._slots.release()
                with self._lock:
                    self._workers.discard(threading.current_thread())
                    self._timers.discard(timer)

        worker = threading.Thread(target=work, name="jev-decision", daemon=True)
        with self._lock:
            if self._closed:
                self._slots.release()
                return future
            self._workers.add(worker)
            self._timers.add(timer)
            timer.start()
            worker.start()
        return future

    def close(self, timeout=0):
        if type(timeout) not in (int, float) or not 0 <= timeout <= 5:
            raise ProviderError("invalid_shutdown_timeout")
        with self._lock:
            self._closed = True
            futures = tuple(self._futures)
            self._futures.clear()
            for future in futures:
                if not future.done():
                    future.set_exception(ProviderError("client_closed"))
            workers, timers = tuple(self._workers), tuple(self._timers)
        deadline = time.monotonic() + timeout
        for thread in (*workers, *timers):
            if thread is not threading.current_thread():
                thread.join(max(0., deadline - time.monotonic()))
        return {"workers_alive": sum(t.is_alive() for t in workers),
                "timers_alive": sum(t.is_alive() for t in timers)}
