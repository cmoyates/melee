from dataclasses import replace
import json
from pathlib import Path
import threading
import time
from types import SimpleNamespace
import unittest

from melee_agent.async_policy import (AsyncPolicy, Delivery, LatestBridge, Reply, bind, rejection)
from melee_agent.engine import FrameExecutor, MatchProgress, Observation
from melee_agent.fake import RecordingSink
from melee_agent.skills import SkillSpec

BASE = Observation.parse(json.loads((Path(__file__).parent / "fixtures/battlefield.json").read_text())["cases"][1]["observation"])


def state(frame=10, ns=1_000_000_000, **details):
    return replace(BASE, frame=frame, observed_ns=ns, match=MatchProgress.from_frame(frame, 480, 4),
        bot=replace(BASE.bot, x=0., y=0., grounded=True, stocks_remaining=5-details.get("life_generation_derived", 1),
                    details=replace(BASE.bot.details, **details)))


def delivery(observation=None, sequence=1, generation=0, action="neutral"):
    observation = observation or state()
    candidates = ("neutral", "jump", "shield")
    context = bind("test", observation, sequence, generation, candidates)
    return Delivery(context, candidates, Reply(context, action, observation.observed_ns + 1))


class ManualBridge:
    def __init__(self, replies=()):
        self.replies = list(replies)
    def exchange(self, *args):
        replies, self.replies = self.replies, []
        return replies


class AsyncPolicyTests(unittest.TestCase):
    def check(self, value, observation=None, **overrides):
        options = dict(run_id="test", generation=0, last_applied=0, now_ns=1_100_000_000, committed=False)
        options.update(overrides)
        return rejection(value, observation or state(11), **options)

    def test_complete_request_binding_rejects_each_forged_field(self):
        original = delivery()
        changes = dict(run_id="other", episode=2, bot_life=2, opponent_life=2, frame=9,
            observed_ns=0, sequence=2, skill_generation=1, candidate_hash="fake", context_key=())
        for key, value in changes.items():
            changed = replace(original, reply=replace(original.reply, context=replace(original.expected, **{key: value})))
            self.assertEqual(self.check(changed), "request_binding", key)

    def test_both_age_clocks_and_future_timestamps_are_rejected(self):
        original = delivery()
        self.assertEqual(self.check(original, state(71)), "frame_age")
        self.assertEqual(self.check(original, state(9)), "frame_age")
        self.assertEqual(self.check(original, now_ns=2_000_000_001), "monotonic_age")
        self.assertEqual(self.check(replace(original, reply=replace(original.reply, received_ns=1_200_000_000))), "monotonic_age")
        self.assertEqual(self.check(replace(original, reply=replace(original.reply, received_ns=999_999_999))), "monotonic_age")

    def test_respawn_episode_generation_and_context_changes_invalidate(self):
        original = delivery()
        self.assertEqual(self.check(original, replace(state(11), episode=2)), "wrong_episode")
        self.assertEqual(self.check(original, state(11, life_generation_derived=2)), "wrong_life")
        self.assertEqual(self.check(original, generation=1), "wrong_skill_generation")
        current = state(11)
        current = replace(current, opponent=replace(current.opponent, x=-100.))
        self.assertEqual(self.check(original, current), "context_changed")

    def test_newer_submission_does_not_starve_valid_reply_but_newer_application_does(self):
        older, newer = delivery(sequence=8), delivery(sequence=9)
        self.assertIsNone(self.check(older, last_applied=7))
        self.assertIsNone(self.check(newer, last_applied=7))
        self.assertEqual(self.check(older, last_applied=9), "superseded_or_duplicate")
        self.assertEqual(self.check(newer, last_applied=9), "superseded_or_duplicate")

    def test_candidate_and_current_legality_checked_at_application(self):
        self.assertEqual(self.check(delivery(action="attack")), "invalid_candidate")
        self.assertEqual(self.check(delivery(action="jump"), state(11, input_jump_held=True)), "illegal_now:jump_unavailable_or_held")
        self.assertEqual(self.check(delivery(action="shield"), state(11, shield_strength=0.)), "illegal_now:shield_low")

    def test_duplicate_batch_applies_exactly_once_through_shared_executor(self):
        response = delivery()
        bridge = ManualBridge([response, response])
        policy = AsyncPolicy("test", bridge, clock=lambda: 1_100_000_000)
        sink = RecordingSink()
        executor = FrameExecutor(policy, sink, SimpleNamespace(now_ns=lambda: 1_100_000_000))
        executor.step(state(11))
        self.assertEqual([e["accepted"] for e in policy.events], [True, False])
        self.assertEqual(policy.events[1]["reason"], "superseded_or_duplicate")
        self.assertEqual(len(sink.packets), 1)

    def test_active_commitment_survives_reply_and_hitstun_overrides_with_neutral(self):
        bridge = ManualBridge()
        policy = AsyncPolicy("test", bridge, clock=lambda: 1_100_000_000)
        policy.arbiter.request(SkillSpec("jump"), state())
        bridge.replies = [delivery(generation=1, action="shield")]
        self.assertEqual(policy.decide(state(11)).action, "jump")
        self.assertEqual(policy.events[0]["reason"], "skill_committed")
        self.assertEqual(policy.decide(state(12, hitstun_frames_derived=5)).action, "wait")
        self.assertIsNone(policy.arbiter.active)
        self.assertEqual(policy.arbiter.last_event["status"], "aborted")

    def test_discontinuous_observation_invalidates_generation_before_reply(self):
        bridge = ManualBridge()
        policy = AsyncPolicy("test", bridge, clock=lambda: 1_100_000_000)
        policy.next_fallback_ns = 9_000_000_000
        policy.decide(state(10))
        bridge.replies = [delivery()]
        self.assertEqual(policy.decide(state(12)).action, "wait")
        self.assertFalse(policy.events[0]["accepted"])
        self.assertEqual(policy.events[0]["reason"], "wrong_skill_generation")

    def test_fixed_workers_do_not_block_frame_loop_or_queue_observations(self):
        entered = threading.Event()
        class BlockingBackend:
            name, max_inflight, interval = "blocking-test", 1, 0.
            def __init__(self):
                self.frames = []
            def call(self, observation, context, candidates, stop):
                self.frames.append(observation.frame)
                entered.set()
                stop.wait(10)
                return []
        backend = BlockingBackend()
        bridge = LatestBridge("test", backend)
        try:
            now = time.monotonic_ns()
            bridge.exchange(state(10, now), 0, ("neutral", "jump"))
            self.assertTrue(entered.wait(1))
            started = time.monotonic()
            for frame in range(11, 1011):
                bridge.exchange(state(frame, time.monotonic_ns()), 0, ("neutral", "jump"))
            self.assertLess(time.monotonic() - started, .5)
            self.assertEqual(backend.frames, [10])
            self.assertEqual(bridge.latest[0].frame, 1010)
            with bridge.lock:
                started = time.monotonic()
                self.assertIsNone(bridge.exchange(state(), 0, ("neutral", "jump")))
                self.assertLess(time.monotonic() - started, .05)
        finally:
            report = bridge.close()
        self.assertEqual(report["workers_alive"], 0)
        self.assertEqual(report["peak_inflight"], 1)
        self.assertEqual(report["inflight"], 0)

    def test_mailbox_is_bounded_under_duplicate_flood(self):
        class FloodBackend:
            name, max_inflight, interval = "flood-test", 1, 0.
            def call(self, observation, context, candidates, stop):
                return [Reply(context, "neutral", time.monotonic_ns())] * 100
        bridge = LatestBridge("test", FloodBackend())
        try:
            bridge.exchange(state(ns=time.monotonic_ns()), 0, ("neutral", "jump"))
            deadline = time.monotonic() + 1
            while bridge.report().get("delivered", 0) < 100 and time.monotonic() < deadline:
                time.sleep(.005)
            report = bridge.report()
            self.assertEqual(report["mailbox_remaining"], 32)
            self.assertEqual(report["mailbox_dropped"], 68)
        finally:
            self.assertEqual(bridge.close()["workers_alive"], 0)


if __name__ == "__main__":
    unittest.main()
