"""Explicit opt-in provider probe; doctor and match commands never call it."""

from dataclasses import asdict, replace
import json
import os
import time
import uuid

from .budget import SpendLedger
from .config import owned_path
from .engine import Observation
from .provider import DecisionsClient, MODEL_ALIAS, OpenRouterTransport, ProviderError


def probe(root, budget_directory, timeout_seconds):
    if not 0 < timeout_seconds <= 30:
        raise ProviderError("invalid_probe_timeout")
    if os.environ.get("OPENROUTER_MODEL", MODEL_ALIAS) != MODEL_ALIAS:
        raise ProviderError("unverified_model_alias")
    directory = owned_path(root, budget_directory)
    ledger = SpendLedger(directory / "spend.jsonl")
    ledger.report()  # Must already exist and be valid; never reset a missing budget.
    transport = OpenRouterTransport(os.environ.get("OPENROUTER_API_KEY", ""))
    client = DecisionsClient(ledger, transport)
    fixture = json.loads((root / "agent/tests/fixtures/battlefield.json").read_text())
    observation = replace(Observation.parse(fixture["cases"][6]["observation"]), observed_ns=time.monotonic_ns())
    candidates = {"recover": "Return safely to the stage when offstage.",
                    "attack": "Attack an opponent while safely onstage."}
    started = time.monotonic_ns()
    report = {"schema_version": 1, "backend": "openrouter", "requested_model": MODEL_ALIAS,
                "observation": asdict(observation), "candidates": candidates}
    try:
        result = client.submit(observation, candidates, deadline_ns=started + int(timeout_seconds * 1e9),
                                instructions="Choose the appropriate priority for this fighter.").result(timeout=timeout_seconds + 1)
        report.update(status="pass", result=asdict(result))
    except ProviderError as error:
        report.update(status="fail", reason=str(error))
    finally:
        client.close()
    report.update(elapsed_seconds=(time.monotonic_ns() - started) / 1e9, budget=ledger.report())
    reports = directory / "probes"
    reports.mkdir(exist_ok=True)
    with (reports / (uuid.uuid4().hex + ".json")).open("x") as handle:
        json.dump(report, handle, indent=2, allow_nan=False)
        handle.write("\n")
    return report
