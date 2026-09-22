"""Reproducible, budgeted provider cadence experiment; never controls a fighter."""

from dataclasses import asdict, replace
from datetime import datetime, timezone
from collections import Counter
import hashlib
import json
import math
import os
import time
import uuid

from .budget import SpendLedger
from .config import owned_path
from .engine import Observation
from .provider import DecisionsClient, MODEL_ALIAS, OpenRouterTransport, ProviderError

CRITERIA = {
    "wait": "Stay neutral briefly while observing.",
    "approach": "Move toward the opponent on safe ground.",
    "retreat": "Create space from the opponent on safe ground.",
    "recover": "Return toward the stage when offstage or below the ledge.",
    "shield": "Block an imminent attack while grounded.",
    "jump": "Jump to change height or reach a platform.",
    "jab": "Use a quick close-range grounded attack.",
    "grab": "Grab a nearby shielding opponent.",
    "laser": "Use a ranged laser from a safe distance.",
    "shine": "Use a close-range reflector attack.",
    "up_smash": "Use a strong upward grounded attack.",
    "up_tilt": "Use a close-range upward tilt.",
    "nair": "Use a neutral aerial while airborne.",
    "bair": "Use a backward aerial while airborne.",
    "dash_dance": "Alternate grounded movement to threaten approach.",
    "platform_drop": "Drop through the current platform.",
}


def percentile(values, percent):
    if not values:
        return None
    return sorted(values)[max(0, math.ceil(len(values) * percent / 100) - 1)]


def summarize(rows):
    success = [r for r in rows if r["status"] == "success"]
    latency = [r["latency_seconds"] for r in success]
    groups = {}
    for row in rows:
        key = f"{row['target_hz']}Hz/{row['candidate_count']}choices/{row['question_count']}questions"
        groups.setdefault(key, []).append(row)
    phases = {}
    phase_name = lambda r: r.get("phase", "topup" if r.get("attempt", 0) > 120 else str(r["target_hz"]))
    for name in sorted({phase_name(r) for r in rows}):
        phase = [r for r in rows if phase_name(r) == name]
        complete = [r for r in phase if r["status"] == "success"]
        span = max(r["finished_seconds"] for r in phase) - min(r["scheduled_seconds"] for r in phase)
        phases[name] = {"target_hz": phase[0]["target_hz"], "attempts": len(phase), "submitted": sum(r["submitted"] for r in phase),
            "successful": len(complete), "duration_seconds": span,
            "successful_per_second": len(complete) / span if span > 0 else 0,
            "accepted_within_1s": sum(r["latency_seconds"] <= 1 for r in complete),
            "p95_seconds": percentile([r["latency_seconds"] for r in complete], 95)}
    p95 = percentile(latency, 95)
    recommendation = ("block" if len(success) < 100 else
                        "proceed_at_1hz" if p95 is not None and p95 <= 1 else "reduce_cadence")
    failures = dict(Counter(r.get("reason", "unknown") for r in rows if r["status"] != "success"))
    if recommendation == "proceed_at_1hz" and failures.get("invalid_distribution_sum", 0):
        recommendation = "proceed_at_1hz_with_strict_fallback"
    small = [r for r in rows if r["candidate_count"] == 5 and r["question_count"] == 1]
    return {"status": "fail" if recommendation == "block" else "pass",
        "attempts": len(rows), "submitted": sum(r["submitted"] for r in rows), "successful": len(success),
        "failed_or_not_submitted": len(rows) - len(success),
        "failure_reasons": failures, "latency_population": "validated successful responses only",
        "latency_seconds": {f"p{p}": percentile(latency, p) for p in (50, 95, 99)},
        "accepted_by_age_seconds": {str(age): sum(r["latency_seconds"] <= age for r in success) for age in (.25, .5, 1, 2)},
        "phases": phases, "groups": {key: {"attempts": len(group),
            "successful": sum(r["status"] == "success" for r in group),
            "p95_seconds": percentile([r["latency_seconds"] for r in group if r["status"] == "success"], 95)}
            for key, group in groups.items()}, "recommendation": recommendation,
        "proposed_max_in_flight": 1, "proposed_request_hz": 1 if recommendation.startswith("proceed") else .5,
        "proposed_max_action_age_seconds": 1, "initial_menu": {"max_choices": 5, "question_count": 1,
            "observed_attempts": len(small), "validated_successful": sum(r["status"] == "success" for r in small)},
        "gameplay_verified": False}


def run_benchmark(root, budget_directory, max_requests=150):
    if type(max_requests) is not int or not 120 <= max_requests <= 150:
        raise ProviderError("benchmark_requires_120_to_150_attempts")
    if os.environ.get("OPENROUTER_MODEL", MODEL_ALIAS) != MODEL_ALIAS:
        raise ProviderError("unverified_model_alias")
    budget = owned_path(root, budget_directory)
    ledger = SpendLedger(budget / "spend.jsonl")
    before = ledger.report()
    client = DecisionsClient(ledger, OpenRouterTransport(os.environ.get("OPENROUTER_API_KEY", "")), max_in_flight=4)
    folder = budget / "benchmarks" / uuid.uuid4().hex
    folder.mkdir(parents=True)
    fixtures = json.loads((root / "agent/tests/fixtures/battlefield.json").read_text())["cases"][1:8]
    module_dir = root / "agent/src/melee_agent"
    manifest = {"schema_version": 1, "started_utc": datetime.now(timezone.utc).isoformat(),
        "requested_model": MODEL_ALIAS, "max_requests": max_requests,
        "target_hz": [1, 2, 5], "candidate_counts": [5, 10, 16], "question_counts": [1, 3],
        "connection_mode": "new subprocess and new HTTP connection per request; provider cache unknown",
        "host_context": "local macOS host; no location or private hostname exported",
        "request_deadline_seconds": 3, "max_in_flight": 4, "budget_before": before,
        "source_sha256": {name: hashlib.sha256((module_dir / name).read_bytes()).hexdigest()
            for name in ("benchmark.py", "provider.py", "provider_http.py", "budget.py", "engine.py")}}
    with (folder / "manifest.json").open("x") as handle:
        json.dump(manifest, handle, indent=2)
    rows, pending = [], []
    start = time.monotonic()

    with (folder / "attempts.jsonl").open("x", buffering=1) as trace:
        def save(row):
            rows.append(row)
            trace.write(json.dumps(row, allow_nan=False) + "\n")
            trace.flush()
            os.fsync(trace.fileno())

        def collect():
            for future, row, submitted_at in pending[:]:
                if not future.done():
                    continue
                row["finished_seconds"] = time.monotonic() - start
                try:
                    result = future.result()
                    row.update(status="success", result=asdict(result),
                        latency_seconds=(result.received_ns - result.observed_ns) / 1e9)
                except Exception as error:
                    row.update(status="failed", reason=str(error) if isinstance(error, ProviderError) else "local_failure",
                                latency_seconds=time.monotonic() - submitted_at)
                save(row)
                pending.remove((future, row, submitted_at))

        def submit(index, hz, scheduled):
            count = (5, 10, 16)[index % 3]
            questions = 1 if (index // 3) % 2 == 0 else 3
            candidates = dict(list(CRITERIA.items())[:count])
            extra = None if questions == 1 else {
                "defensive": {"instructions": "Independently choose the safest survival-oriented action.", "criteria": candidates},
                "aggressive": {"instructions": "Independently choose the best aggressive action that remains plausible here.", "criteria": candidates}}
            row = {"attempt": index + 1, "target_hz": hz, "scheduled_seconds": scheduled - start,
                "phase": "topup" if index >= 120 else str(hz),
                "candidate_count": count, "question_count": questions, "submitted": False}
            observation = replace(Observation.parse(fixtures[index % len(fixtures)]["observation"]), observed_ns=time.monotonic_ns())
            submitted_at = time.monotonic()
            try:
                future = client.submit(observation, candidates, deadline_ns=time.monotonic_ns() + 3_000_000_000,
                                        additional_questions=extra)
                row["submitted"] = True
                pending.append((future, row, submitted_at))
            except (ValueError, OSError) as error:
                row.update(status="not_submitted", reason=str(error) if isinstance(error, ProviderError) else "budget_or_local_limit",
                            finished_seconds=time.monotonic() - start)
                save(row)

        try:
            index = 0
            for hz in (1, 2, 5):
                next_at = time.monotonic()
                for _ in range(40):
                    while time.monotonic() < next_at:
                        collect()
                        time.sleep(min(.01, max(0, next_at - time.monotonic())))
                    submit(index, hz, next_at)
                    index += 1
                    # Never burst to catch up after a local stall.
                    next_at = max(next_at + 1 / hz, time.monotonic())
                    collect()
                while pending:
                    collect()
                    time.sleep(.01)
            while sum(r["status"] == "success" for r in rows) < 100 and index < max_requests:
                submit(index, 1, time.monotonic())
                index += 1
                until = time.monotonic() + 1
                while pending or time.monotonic() < until:
                    collect()
                    time.sleep(.01)
        finally:
            client.close()
            collect()
    report = {"schema_version": 1, "run_id": folder.name, **summarize(rows), "budget_after": ledger.report(),
                "source_sha256": manifest["source_sha256"], "connection_mode": manifest["connection_mode"]}
    with (folder / "summary.json").open("x") as handle:
        json.dump(report, handle, indent=2, allow_nan=False)
        handle.write("\n")
    return report
