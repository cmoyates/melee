from types import SimpleNamespace as NS
from pathlib import Path
import re
import struct
import unittest

from melee_agent.raw_observation import CHARACTERS, NATIVE_ACTIONS, LifeTracker, RawStreamTap, decode_post, player_record, stage_record
from melee_agent.input_trace import InputTrace, same_input
from melee_agent.engine import Packet


def event(frame=-123, port=1, action=14, character=1, action_frame=0., size=0x4d):
    result = bytearray(size)
    result[0] = 0x38
    struct.pack_into(">i", result, 1, frame)
    result[5:8] = bytes([port - 1, 0, character])
    struct.pack_into(">H", result, 8, action)
    struct.pack_into(">f", result, 0x22, action_frame)
    result[0x21] = 4
    return result


class ObservationTests(unittest.TestCase):
    def test_explicit_action_subset_matches_native_enum_not_css_ids(self):
        path = Path(__file__).resolve().parents[2] / "src/melee/ft/kinds/ftCommon/forward.h"
        source = path.read_text().split("typedef enum ftCommon_MotionState {")[1].split("}")[0]
        values, value = {}, -1
        for name, assigned in re.findall(r"^\s*(ftCo_MS_\w+)(?:\s*=\s*(-?\d+))?,", source, re.M):
            value = int(assigned) if assigned else value + 1
            values[name] = value
        for number, name in NATIVE_ACTIONS.items():
            self.assertEqual(values[name], number)

    def test_raw_id_domains_and_stage_mapping_are_explicit(self):
        self.assertEqual(CHARACTERS[1], {"name": "FOX", "native_fighter_kind": 1, "external_css_id": 2})
        self.assertEqual(CHARACTERS[0]["external_css_id"], 8)
        stage = stage_record()
        self.assertEqual(stage["slippi_external_id"], 31)
        self.assertEqual(stage["native_gr_kind_mapped"], 36)
        self.assertFalse(stage["native_collision_query_available"])

    def test_raw_action_frame_is_not_replaced_by_normalized_value(self):
        raw = decode_post(event(action_frame=.5))
        player = NS(character=NS(value=1), action=NS(value=14, name="STANDING"), action_frame=1,
                    hitstun_frames_left=0, hitlag_left=0, stock=4, on_ground=True,
                    invulnerable=False, position=NS(x=0., y=0.))
        result = player_record(player, raw, 1, 1, LifeTracker(), {1: {14}})
        self.assertEqual(result["raw_post"]["action_frame_raw"], .5)
        self.assertEqual(result["action_frame_adjustment"], 1)
        player.action_frame = 2
        with self.assertRaisesRegex(ValueError, "normalization"):
            player_record(player, raw, 1, 1, LifeTracker(), {1: {14}})

    def test_unknown_animation_and_absent_fields_remain_explicit(self):
        raw = decode_post(event(action=600, size=0x26))
        self.assertEqual(raw["action_id"], 600)
        self.assertEqual(raw["frame"], -123)
        self.assertFalse(raw["available"]["hitlag_raw"])
        self.assertIsNone(raw["hitlag_raw"])
        player = NS(character=NS(value=1), action=NS(value=600), action_frame=0,
                    hitstun_frames_left=0, hitlag_left=0, stock=4, on_ground=True,
                    invulnerable=False, position=NS(x=0., y=0.))
        result = player_record(player, raw, 1, 1, LifeTracker(), {})
        self.assertFalse(result["action_mapping"]["available"])
        self.assertIsNone(result["action_mapping"]["native_motion_state_mapping"])

    def test_life_generation_resets_with_episode_and_rejects_stock_increase(self):
        tracker = LifeTracker()
        self.assertEqual([tracker.observe(1, 1, s) for s in (4, 4, 3, 3, 2)], [1, 1, 2, 2, 3])
        self.assertEqual(tracker.observe(2, 1, 4), 1)
        tracker.observe(2, 1, 3)
        with self.assertRaises(ValueError):
            tracker.observe(2, 1, 4)

    def test_raw_hook_is_bounded_and_does_not_skip_the_original_parser(self):
        calls = []
        console = NS(_Console__post_frame=lambda state, data: calls.append(len(data)), eventsize={0x38: 0x4d})
        tap = RawStreamTap(console)
        for frame in range(100):
            console._Console__post_frame(None, event(frame=frame))
        self.assertEqual(len(calls), 100)
        self.assertEqual(len(tap.events), 64)
        self.assertEqual(tap.take(99, 1)["frame"], 99)
        with self.assertRaises(ValueError):
            tap.take(0, 1)

    def test_hook_uses_announced_event_length_not_remaining_stream_bytes(self):
        console = NS(_Console__post_frame=lambda state, data: None, eventsize={0x38: 0x26})
        tap = RawStreamTap(console)
        console._Console__post_frame(None, event(size=0x26) + b"x" * 100)
        raw = tap.take(-123, 1)
        self.assertFalse(raw["available"]["hitlag_raw"])
        self.assertEqual(raw["event_bytes"], 0x26)


class InputTraceTests(unittest.TestCase):
    def test_completed_flush_is_distinct_from_queue(self):
        calls = []
        controller = NS(flush=lambda: calls.append(1))
        ticks = iter((10, 11, 12, 13))
        trace = InputTrace(controller, clock_ns=lambda: next(ticks))
        trace.queue({"observation": {"episode": 1, "frame": 7}, "queued_ns": 5, "packet": Packet().wire()})
        self.assertIsNone(trace.last_flush)
        controller.flush()
        self.assertEqual(trace.last_flush["flush_completed_ns"], 11)
        controller.flush()
        self.assertEqual(len(trace.flushed), 1)  # Repeated polling does not invent new commands.
        self.assertEqual(len(calls), 2)
        trace.leave_game()
        self.assertIsNone(trace.pending)
        self.assertEqual(len(trace.flushed), 0)

    def test_failed_pipe_flush_never_claims_a_completed_flush(self):
        def broken():
            raise BrokenPipeError()
        controller = NS(flush=broken)
        trace = InputTrace(controller)
        trace.queue({"observation": {"episode": 1, "frame": 7}, "queued_ns": 5, "packet": Packet().wire()})
        with self.assertRaises(BrokenPipeError):
            controller.flush()
        self.assertIsNone(trace.last_flush)
        self.assertEqual(len(trace.flushed), 0)

    def test_trigger_acknowledgement_reflects_merged_game_value(self):
        packet = Packet(l=1.).wire()
        observed = {**packet, "r": 1.}
        self.assertTrue(same_input(packet, observed))
        observed["main"] = [0., .5]
        self.assertFalse(same_input(packet, observed))


if __name__ == "__main__":
    unittest.main()
