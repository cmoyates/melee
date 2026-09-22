from dataclasses import asdict, replace
from types import SimpleNamespace
import unittest

from melee_agent.async_policy import AsyncPolicy
from melee_agent.engine import ACTION_PACKETS, FrameExecutor, Observation
from melee_agent.fake import RecordingSink
from melee_agent.local_combat_policy import LocalCombatPolicy
from melee_agent.raw_observation import normalized_hurtbox
from melee_agent.skills import SkillArbiter, SkillSpec, can_start
from test_async_policy import ManualBridge
from test_scenarios import position


def ground(frame=0, motion=14, **details):
    observation = position(frame, x=0., facing_right=True, action_id=motion, **details)
    return replace(observation, opponent=replace(observation.opponent, x=8., y=0., grounded=True,
        details=replace(observation.opponent.details, action_id=14, percent=0., hurtbox_state=0)))


class CombatIntegrationTests(unittest.TestCase):
    def test_local_selectors_share_candidates_packets_and_cadence(self):
        selected = []
        for mode in ("heuristic", "random-legal"):
            policy = LocalCombatPolicy(mode, seed=7)
            sink = RecordingSink()
            executor = FrameExecutor(policy, sink, SimpleNamespace(now_ns=lambda: 1_100_000_000))
            executor.step(ground())
            selection = policy.trace()["local_selection"]
            self.assertEqual(selection["combat_candidates"], ["jab", "dtilt", "grab"])
            selected.append(selection["selected"])
            motion, action = {"jab": (44, "attack"), "dtilt": (57, "down_tilt"), "grab": (212, "grab")}[selection["selected"]]
            self.assertEqual(sink.packets[-1], ACTION_PACKETS[action].wire())
            executor.step(ground(1, motion, hitlag_frames_derived=2))
            self.assertIsNotNone(policy.arbiter.active)
            executor.step(ground(2))
            self.assertEqual(policy.arbiter.last_event["status"], "succeeded")
            for frame in range(3, 60):
                executor.step(ground(frame))
                self.assertIsNone(policy.trace()["local_selection"])
            self.assertEqual(len(sink.packets), 60)
            self.assertTrue(all(packet == ACTION_PACKETS["wait"].wire() for packet in sink.packets[1:]))
            executor.step(ground(60))
            self.assertIsNotNone(policy.trace()["local_selection"])
            self.assertFalse(policy.close()["provider_contacted"])
        self.assertEqual(selected, ["jab", "dtilt"])

    def test_local_reflex_preempts_attack_and_new_life_rechecks_legality(self):
        policy = LocalCombatPolicy()
        policy.decide(ground())
        policy.decide(ground(1, 44))
        decision = policy.decide(ground(2, 75, hitstun_frames_derived=5, attack_velocity_x=1.))
        self.assertIsNone(policy.arbiter.active)
        self.assertEqual(policy.owner, "emergency")
        self.assertFalse(ACTION_PACKETS[decision.action].wire()["buttons"]["A"])
        inactive = ground(3, 12, life_generation_derived=2)
        policy.decide(inactive)
        self.assertIsNone(policy.arbiter.active)
        self.assertIsNone(policy.selection)

    def test_each_primitive_uses_one_shared_packet_writer_and_returns_neutral(self):
        for name, motion, action in (("jab", 44, "attack"), ("dtilt", 57, "down_tilt"), ("grab", 212, "grab")):
            arbiter, sink = SkillArbiter(), RecordingSink()
            executor = FrameExecutor(SimpleNamespace(decide=arbiter.step), sink,
                SimpleNamespace(now_ns=lambda: 1_100_000_000))
            self.assertIsNone(arbiter.request(SkillSpec(name, 1), ground()))
            executor.step(ground())
            executor.step(ground(1, motion))
            executor.step(ground(2, motion))
            executor.step(ground(3))
            self.assertEqual(sink.packets, [ACTION_PACKETS[action].wire()]+[ACTION_PACKETS["wait"].wire()]*3)
            self.assertEqual(arbiter.last_event["status"], "succeeded")
            self.assertEqual(arbiter.last_event["ack_frame"], 1)
            self.assertEqual(arbiter.last_event["combat"]["end_frame"], 3)

    def test_attack_hitlag_preserves_commitment_but_hitstun_preempts_it(self):
        policy = AsyncPolicy("combat-test", ManualBridge(), clock=lambda: 1_100_000_000)
        policy.next_fallback_ns = 9_000_000_000
        sink = RecordingSink()
        executor = FrameExecutor(policy, sink, SimpleNamespace(now_ns=lambda: 1_100_000_000))
        executor.step(ground())
        policy.arbiter.request(SkillSpec("jab", 1), ground())
        executor.step(ground(1))
        executor.step(ground(2, 44, hitlag_frames_derived=3))
        self.assertIsNotNone(policy.arbiter.active)
        self.assertEqual(policy.arbiter.active["ack_frame"], 2)
        self.assertFalse(any(sink.packets[-1]["buttons"].values()))
        executor.step(ground(3, 75, hitstun_frames_derived=4, attack_velocity_x=1.))
        self.assertIsNone(policy.arbiter.active)
        self.assertEqual(policy.arbiter.last_event["status"], "aborted")
        self.assertEqual(policy.arbiter.last_event["combat"]["reason"], "hitstun")
        self.assertEqual(policy.last_owner, "emergency")
        self.assertEqual(len(sink.packets), 4)
        self.assertFalse(sink.packets[-1]["buttons"]["A"])

    def test_invulnerability_availability_and_schema_are_explicit(self):
        for value in (0, 1, 2):
            self.assertEqual(normalized_hurtbox({"available": {"hurtbox_state": True}, "hurtbox_state": value}), value)
        for value in (None, 3, True, "0"):
            self.assertIsNone(normalized_hurtbox({"available": {"hurtbox_state": True}, "hurtbox_state": value}))
        self.assertIsNone(normalized_hurtbox({"available": {"hurtbox_state": False}, "hurtbox_state": 0}))
        observation = ground()
        for value in (None, 1, 2):
            protected = replace(observation, opponent=replace(observation.opponent,
                details=replace(observation.opponent.details, hurtbox_state=value)))
            self.assertEqual(can_start(SkillSpec("jab", 1), protected), "opponent_invulnerable_or_unknown")
        raw = asdict(observation)
        raw["opponent"]["details"].pop("hurtbox_state")
        with self.assertRaises(ValueError):
            Observation.parse(raw)
        raw = asdict(observation)
        raw["schema_version"] = 3
        with self.assertRaises(ValueError):
            Observation.parse(raw)


if __name__ == "__main__":
    unittest.main()
