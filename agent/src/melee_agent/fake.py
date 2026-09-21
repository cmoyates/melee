"""Deterministic, asset-free smoke run through the real frame executor."""

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import uuid

from .engine import FrameExecutor, Observation, RunManifest, ScriptedPolicy
from .stage import PLATFORMS, STAGE_NAME, support_surface


class FakeClock:
    def __init__(self):
        self.tick = 0

    def now_ns(self):
        self.tick += 1
        return self.tick * 16666667


class FakeSource:
    def __init__(self, observations):
        self.observations = iter(observations)

    def next(self):
        data = next(self.observations, None)
        return Observation.parse(data) if data is not None else None


class RecordingSink:
    def __init__(self):
        self.packets = []

    def send(self, packet):
        self.packets.append(packet.wire())


def simulate(fixture, policy=None):
    if set(fixture) != {"schema_version", "cases"} or type(fixture["schema_version"]) is not int or fixture["schema_version"] != 1:
        raise ValueError("Unsupported fixture schema")
    sink = RecordingSink()
    executor = FrameExecutor(policy or ScriptedPolicy(), sink, FakeClock())
    rows = []
    source = FakeSource(case["observation"] for case in fixture["cases"])
    for case, row in zip(fixture["cases"], executor.run(source), strict=True):
        if set(case) != {"observation", "expected_action", "expected_packet", "expected_support"}:
            raise ValueError("Unknown fixture case fields")
        if row["decision"]["action"] != case["expected_action"] or row["packet"] != case["expected_packet"]:
            raise AssertionError("Controller output differs from the expected fixture")
        a = row["observation"]["bot"]
        support = support_surface(a["x"], a["y"], a["grounded"])
        if support != case["expected_support"]:
            raise AssertionError("Support surface differs from expected fixture")
        rows.append({**row, "support_surface_derived": support})
    return rows


def smoke(root: Path, fixture_path=None):
    fixture_path = fixture_path or root / "agent/tests/fixtures/battlefield.json"
    fixture = json.loads(fixture_path.read_text())
    first, second = simulate(fixture), simulate(fixture)
    canonical = lambda rows: "".join(json.dumps(r, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n" for r in rows)
    trace = canonical(first)
    if trace != canonical(second):
        raise AssertionError("Fake replay is nondeterministic")
    digest = hashlib.sha256(trace.encode()).hexdigest()
    manifest = RunManifest(1, "fake", STAGE_NAME, digest, len(first))
    from .config import owned_path
    base = owned_path(root.resolve(), "build/jev/fake")
    run = base / uuid.uuid4().hex
    run.mkdir(parents=True)
    with (run / "trace.jsonl").open("x") as handle:
        handle.write(trace)
    report = {**asdict(manifest), "status": "pass", "replays_identical": True,
              "platforms": PLATFORMS, "run_id": run.name}
    with (run / "summary.json").open("x") as handle:
        json.dump(report, handle, indent=2, allow_nan=False)
    return report
