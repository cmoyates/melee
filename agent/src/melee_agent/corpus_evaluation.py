"""Explicit paid evaluation of frozen corpus states, with no controller/runtime."""

from collections import Counter
from dataclasses import asdict, replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
import uuid

from .budget import BudgetError, SpendLedger
from .config import owned_path
from .corpus import MAX_CORPUS_BYTES, digest, validate_corpus
from .incidents import stream_records
from .live_provider import CountingTransport, DESCRIPTIONS
from .matches import locate_run
from .provider import DecisionsClient, MODEL_ALIAS, OpenRouterTransport, ProviderError
from .semantic import CompactObservation, canonical
from .source_states import captured_observation

CRITERIA = {**DESCRIPTIONS,
    "jab": "Perform one quick grounded jab at the nearby opponent, then release inputs.",
    "dtilt": "Perform one grounded down tilt at the nearby opponent, then release inputs.",
    "grab": "Attempt one grounded grab of the nearby opponent; no automatic throw is included."}
INSTRUCTIONS = ("Control Fox against Mario CPU level 3 on Battlefield. Choose the most useful available skill "
    "to take stocks while preserving Fox's stocks. Use the locally computed spacing, stock comparison and legal "
    "candidates. These are bounded skills; local code owns timing, interruption and recovery. "
    "Choose exactly one provided label and return its complete probability distribution.")


def select_cases(rows, maximum):
    eligible = [row for row in rows if 2 <= len(row["state"]["mechanical"]["legal_candidates"]) <= 16]
    if any(label not in CRITERIA for row in eligible for label in row["state"]["mechanical"]["legal_candidates"]):
        raise ValueError("Unsupported corpus evaluation candidates")
    count = min(maximum, len(eligible))
    return [eligible[i*(len(eligible)-1)//max(1, count-1)] for i in range(count)]


def evaluate_corpus(root, corpus_id, budget_directory, max_requests, *, transport=None, sleep=time.sleep):
    if type(max_requests) is not int or not 1 <= max_requests <= 1000:
        raise ValueError("Evaluation requires a 1-1000 request bound")
    if os.environ.get("OPENROUTER_MODEL", MODEL_ALIAS) != MODEL_ALIAS:
        raise ProviderError("unverified_model_alias")
    validation = validate_corpus(root, corpus_id)
    folder = owned_path(root, "build/jev/corpora/"+corpus_id)
    selected = select_cases([row for _, row in stream_records(folder/"states.jsonl", MAX_CORPUS_BYTES)], max_requests)
    if not selected:
        raise ValueError("No states have at least two available candidates")
    ledger = SpendLedger(owned_path(root, budget_directory)/"spend.jsonl")
    before = ledger.report()
    if datetime.now(timezone.utc) >= datetime.fromisoformat(before["deadline_utc"]):
        raise BudgetError("Experiment deadline reached")
    counted_transport = CountingTransport(transport if transport is not None else
        OpenRouterTransport(os.environ.get("OPENROUTER_API_KEY", "")))
    client = DecisionsClient(ledger, counted_transport)
    evaluation_id = "evaluation-"+uuid.uuid4().hex
    output = folder/evaluation_id
    output.mkdir()
    wanted = {(r["source"]["run_id"], r["source"]["episode"], r["source"]["frame"]): r for r in selected}
    observations = {}
    for run_id in dict.fromkeys(key[0] for key in wanted):
        for _, row in stream_records(locate_run(root, run_id)/"frames.jsonl", 268435456):
            key = (run_id, row.get("episode"), row.get("frame"))
            if key in wanted and row.get("menu") == "IN_GAME":
                observations[key] = captured_observation(row)
    if observations.keys() != wanted.keys():
        client.close()
        raise ValueError("Selected source observation missing")
    manifest = {"schema_version": 1, "corpus_id": corpus_id, "evaluation_id": evaluation_id,
        "corpus_manifest_sha256": digest(folder/"manifest.json"), "corpus_validation": validation,
        "requested_model": MODEL_ALIAS, "maximum_requests": max_requests, "budget_before": before,
        "instructions": INSTRUCTIONS, "criteria_order": list(CRITERIA), "criteria": CRITERIA,
        "request_interval_seconds": 1, "request_timeout_seconds": 3,
        "selected": [{"source": row["source"], "state_sha256": row["state_sha256"], "split": row["split"]} for row in selected],
        "source_sha256": {name: digest(Path(__file__).parent/name) for name in
            ("corpus_evaluation.py", "provider.py", "provider_http.py", "budget.py")}}
    (output/"manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
    results = []
    started = time.monotonic()
    next_request = started
    try:
        with (output/"responses.jsonl").open("x", buffering=1) as trace:
            for row in selected:
                if time.monotonic()-started > 3600:
                    break
                sleep(max(0, next_request-time.monotonic()))
                next_request = time.monotonic()+1
                source = row["source"]
                original = observations[(source["run_id"], source["episode"], source["frame"])]
                # Frozen gameplay identity stays fixed; this transport has a new
                # monotonic lifetime, including after a host reboot.
                observation = replace(original, observed_ns=time.monotonic_ns())
                compact = CompactObservation(observation.episode, observation.frame, observation.observed_ns, canonical(row["state"]))
                candidates = {label: CRITERIA[label] for label in row["state"]["mechanical"]["legal_candidates"]}
                result = {"source": source, "state_sha256": compact.sha256, "split": row["split"],
                    "original_observed_ns": original.observed_ns}
                start = time.monotonic()
                stop = False
                try:
                    response = client.submit(observation, candidates, compact_state=compact,
                        instructions=INSTRUCTIONS, deadline_ns=time.monotonic_ns()+3_000_000_000).result(timeout=3.5)
                    result.update(status="validated", response=asdict(response))
                except (ProviderError, BudgetError, TimeoutError) as error:
                    result.update(status="refused", reason=str(error) if isinstance(error, ProviderError) else
                        "budget_refused" if isinstance(error, BudgetError) else "deadline_exceeded")
                    stop = isinstance(error, BudgetError) or result["reason"] in (
                        "rate_limited", "http_error", "provider_backoff", "unverified_model_identity", "reservation_exceeded")
                result["latency_seconds"] = time.monotonic()-start
                trace.write(canonical(result)+"\n")
                trace.flush()
                os.fsync(trace.fileno())
                results.append(result)
                if stop:
                    break
    finally:
        closed = client.close(timeout=5)
    after = ledger.report()
    valid = [r for r in results if r["status"] == "validated"]
    report = {"schema_version": 1, "corpus_id": corpus_id, "evaluation_id": evaluation_id,
        "status": "completed" if len(valid) == len(selected) else "partial",
        "selected_states": len(selected), "attempted_states": len(results), "validated_responses": len(valid),
        "reserved_requests": after["requests"]-before["requests"],
        "submitted_requests": counted_transport.calls,
        "provider_contacted": counted_transport.calls > 0,
        "refusals": dict(Counter(r["reason"] for r in results if r["status"] != "validated")),
        "choices": dict(Counter(r["response"]["action"] for r in valid)),
        "validated_by_split": dict(Counter(r["split"] for r in valid)),
        "validated_input_tokens": sum(r["response"]["usage"]["input_tokens"] for r in valid),
        "budget_before": before, "budget_after": after, "client_closed": closed,
        "responses_sha256": digest(output/"responses.jsonl"), "elapsed_seconds": time.monotonic()-started,
        "emulator_launched": False, "controller_inputs_sent": 0,
        "evaluation_limit": "Ordered frozen-state provider decisions. Choices are not ground truth; no win rate or live apply-time success is inferred."}
    (output/"summary.json").write_text(json.dumps(report, indent=2)+"\n")
    return report
