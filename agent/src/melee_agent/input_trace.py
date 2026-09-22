"""Distinguish queued commands, completed pipe flushes and observed inputs."""

from collections import deque
import time


def observed_packet(controller):
    return {"main": [float(v) for v in controller.main_stick],
            "c": [float(v) for v in controller.c_stick],
            "l": float(controller.l_shoulder), "r": float(controller.r_shoulder),
            "shoulders_merged_by_game": True,
            "buttons": {b.name.removeprefix("BUTTON_"): bool(v) for b, v in controller.button.items()}}


def same_input(packet, observed):
    # Slippi sticks are quantized. Matching values alone do not prove causality.
    return (all(abs(a - b) <= .025 for key in ("main", "c") for a, b in zip(packet[key], observed[key])) and
            all(abs(max(packet["l"], packet["r"]) - observed[key]) <= .025 for key in ("l", "r")) and
            packet["buttons"] == observed["buttons"])


class InputTrace:
    def __init__(self, controller, clock_ns=time.monotonic_ns):
        self.clock_ns = clock_ns
        self.pending = None
        self.sequence = 0
        self.flushed = deque(maxlen=128)
        self.last_flush = None
        original = controller.flush
        def flush():
            started = self.clock_ns()
            original()
            ended = self.clock_ns()
            if self.pending is not None:
                event = {**self.pending, "flush_started_ns": started, "flush_completed_ns": ended}
                self.last_flush = event
                if not self.flushed or self.flushed[-1]["packet_id"] != event["packet_id"]:
                    self.flushed.append(event)
        controller.flush = flush

    def queue(self, control):
        self.sequence += 1
        observation = control["observation"]
        self.pending = {"packet_id": self.sequence, "episode": observation["episode"],
                        "source_frame": observation["frame"], "queued_ns": control["queued_ns"],
                        "packet": control["packet"]}
        return self.sequence

    def observation(self, episode, frame, controller):
        observed = observed_packet(controller)
        matches = [p for p in self.flushed if p["episode"] == episode and p["source_frame"] < frame
                    and same_input(p["packet"], observed)]
        latest = matches[-1] if matches else None
        return {"observed": observed, "latest_completed_flush": self.last_flush,
                "matching_packet_id": latest["packet_id"] if latest else None,
                "matching_value_candidates": len(matches),
                "candidate_lag_frames": frame - latest["source_frame"] if latest else None,
                "application_lag_confirmed": False,
                "acknowledgement_kind": "observed_values_only"}

    def leave_game(self):
        self.pending = self.last_flush = None
        self.flushed.clear()
