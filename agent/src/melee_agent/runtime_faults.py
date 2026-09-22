"""Explicit local fault injection. No key and no external HTTP transport exist here."""

from collections import Counter
from datetime import datetime, timedelta, timezone
import json
import os
import signal
import threading
import time

from .budget import SpendLedger
from .live_provider import ProviderBackend
from .provider import DecisionsClient, VERIFIED_MODEL

MODES = ("network", "frame_gap", "logger_stall", "executor_error", "worker_death",
        "controller_stall", "frame_stall", "rate_cap")


class RuntimeFaults:
    def __init__(self, run_dir, mode):
        if mode not in MODES:
            raise ValueError("Unknown runtime fault mode")
        self.run_dir, self.mode = run_dir, mode
        self.events = []
        self.triggered = False
        self.release = threading.Event()
        self.recorder = None

    def record(self, name, **values):
        self.events.append({"fault": name, "monotonic_ns": time.monotonic_ns(), **values})

    def breadcrumb(self, name, **values):
        self.record(name, **values)
        # Only terminal fault injection writes synchronously, just before the
        # intentional loss of control. Normal per-frame logging stays off-loop.
        with (self.run_dir / "fault-injected.json").open("x") as handle:
            json.dump(self.events[-1], handle)
            handle.write("\n")

    def drop_state(self, frame):
        if self.mode == "frame_stall" and self.triggered:
            return True
        if self.mode in ("frame_gap", "frame_stall") and not self.triggered and frame >= 600:
            self.triggered = True
            self.breadcrumb(self.mode, frame=frame)
            return True
        return False

    def before_control(self, observation):
        if self.triggered or observation.frame < 600:
            return
        if self.mode in ("executor_error", "worker_death"):
            self.triggered = True
            if self.mode == "worker_death" and self.recorder is not None:
                # Preserve the already-issued packets before the deterministic
                # crash boundary; the following observation has no new packet.
                self.recorder.close()
            self.breadcrumb(self.mode, frame=observation.frame, episode=observation.episode)
            if self.mode == "worker_death":
                os.kill(os.getpid(), signal.SIGKILL)
            raise RuntimeError("injected_executor_error")

    def wrap_flush(self, controller):
        if self.mode != "controller_stall":
            return
        original = controller.flush
        calls = 0
        def flush():
            nonlocal calls
            calls += 1
            if calls >= 1200 and not self.triggered:
                self.triggered = True
                self.breadcrumb("controller_stall", flush_call=calls)
                read_fd, write_fd = os.pipe()
                try:
                    while True:
                        os.write(write_fd, b"x" * 65536)
                finally:
                    os.close(read_fd)
                    os.close(write_fd)
            return original()
        controller.flush = flush

    def opener(self, path):
        faults = self
        class StalledFile:
            def __init__(self):
                self.handle = path.open("xb", buffering=65536)
                self.count = 0
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return self.handle.__exit__(*args)
            def write(self, data):
                self.count += 1
                if self.count == 600:
                    faults.triggered = True
                    faults.breadcrumb("logger_stall", record=self.count)
                    faults.release.wait(60)
                return self.handle.write(data)
            def flush(self):
                self.handle.flush()
        return StalledFile

    def report(self):
        return {"schema_version": 1, "mode": self.mode, "simulation_only": True,
                "events": self.events, "counts": dict(Counter(e["fault"] for e in self.events))}


class FaultTransport:
    def __init__(self, faults):
        self.faults = faults
        self.calls = 0
        self.cancel = None

    def __call__(self, payload, timeout):
        self.calls += 1
        index = (self.calls - 1) % 12
        value = json.loads(payload)
        labels = list(value["questions"]["action"]["criteria"])
        mode = ("valid", "disconnect", "http_429", "http_529", "malformed_json", "invalid_distribution",
                "low_confidence", "recovery", "cancellation", "latency_stall", "recovery", "valid")[index]
        self.faults.record(mode, transport_call=self.calls, source_frame=value["state"]["frame"],
            episode=value["state"]["episode"])
        if mode == "disconnect":
            raise OSError("injected_disconnect")
        if mode in ("http_429", "http_529"):
            return int(mode[-3:]), {"Retry-After": "1"}, b""
        if mode == "malformed_json":
            return 200, {}, b"{"
        if mode == "cancellation":
            self.cancel()
        if mode == "latency_stall":
            self.faults.release.wait(2)
        action = labels[self.calls % len(labels)]
        probs = {label: float(label == action) for label in labels}
        if mode == "invalid_distribution":
            probs[action] = .99
        data = {"model": VERIFIED_MODEL, "provider": "TypeSafe", "answers": {
            "action": {"type": "choice", "choice": action, "probabilities": probs,
                        "confidence": .01 if mode == "low_confidence" else .8}},
            "usage": {"cost": 0, "input_tokens": 1, "output_tokens": 1}}
        return 200, {}, json.dumps(data).encode()


class FaultBackend(ProviderBackend):
    def __init__(self, root, run_dir, faults, run_deadline_ns):
        directory = str((run_dir / "simulated-budget").relative_to(root))
        remaining = max(0., (run_deadline_ns-time.monotonic_ns())/1e9)
        SpendLedger.create(root, directory, deadline_utc=(datetime.now(timezone.utc)+timedelta(seconds=remaining+30)).isoformat(),
            max_requests=200, max_input_tokens=8_000_000)
        self.faults = faults
        injected = FaultTransport(faults)
        self.replace_client = False
        super().__init__(root, directory, 6 if faults.mode == "rate_cap" else 200, run_deadline_ns, transport=injected)
        self.name = "simulated-decisions-runtime-v1"
        def cancel():
            self.replace_client = True
            self.client.close()
        injected.cancel = cancel

    def call(self, observation, context, candidates, stop):
        if self.replace_client:
            closed = self.client.close(timeout=1.25)
            if closed["workers_alive"] or closed["timers_alive"]:
                raise RuntimeError("Injected client did not stop")
            self.client = DecisionsClient(self.ledger, self.transport, max_in_flight=1)
            self.replace_client = False
            self.faults.record("client_recreated", source_frame=observation.frame, episode=observation.episode)
        replies = super().call(observation, context, candidates, stop)
        if self.exhausted and len(self.attempts) == self.max_requests:
            self.faults.record("rate_cap", attempts=len(self.attempts))
        return replies

    def close(self):
        self.faults.release.set()
        return {**super().close(), "simulation_only": True, "external_http_calls": 0}
