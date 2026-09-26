from dataclasses import asdict, replace
import json
from pathlib import Path
import re
import unittest

from melee_agent.native_motions import COMMON_MOTIONS, FOX_MOTIONS, MARIO_MOTIONS
from melee_agent.semantic import CompactObservation, SemanticHistory, compact_observation, native_motion
from test_combat_integration import ground


class SemanticTests(unittest.TestCase):
    def test_native_names_match_source_enums_including_commented_entries_and_character_aliases(self):
        root = Path(__file__).resolve().parents[2]/"src/melee/ft/kinds"
        common = (root/"ftCommon/forward.h").read_text().split("typedef enum ftCommon_MotionState {")[1].split("}")[0]
        names = re.findall(r"\bftCo_MS_(\w+)\b", common)
        self.assertEqual(names[0], "None")
        self.assertEqual(names[-1], "Count")
        self.assertEqual(COMMON_MOTIONS, dict(enumerate(names[1:-1])))
        self.assertEqual(len(COMMON_MOTIONS), 341)
        for character, prefix, expected in (("Fox", "ftFx", FOX_MOTIONS), ("Mario", "ftMr", MARIO_MOTIONS)):
            source = (root/("ft"+character)/"forward.h").read_text().split("typedef enum ft"+character+"_MotionState {")[1].split("}")[0]
            names = re.findall(r"^\s*"+prefix+r"_MS_(\w+)", source, re.M)
            names = [name for name in names if name not in ("Count", "SelfCount")]
            self.assertEqual(expected, dict(enumerate(names, 341)))
        self.assertEqual(native_motion("Fox", 353), "SpecialHiHold")
        self.assertIsNone(native_motion("Mario", 353))
        self.assertEqual(native_motion("Fox", 212), "Catch")
        self.assertEqual(native_motion("Mario", 253), "CliffWait")

    def test_mirrored_spacing_keeps_local_legality_and_resources(self):
        original = ground()
        mirrored = replace(original, bot=replace(original.bot, x=-original.bot.x,
            details=replace(original.bot.details, facing_right=False)),
            opponent=replace(original.opponent, x=-original.opponent.x,
                details=replace(original.opponent.details, facing_right=True)))
        for observation, side, delta in ((original, "right", 8.), (mirrored, "left", -8.)):
            result = compact_observation(observation, ("neutral", "jab", "grab"), skill_known=True).wire()
            self.assertEqual(result["relative"]["opponent_side"], side)
            self.assertEqual(result["relative"]["opponent_delta_rounded"], [delta, 0.])
            self.assertTrue(result["relative"]["facing_opponent"])
            self.assertEqual(result["mechanical"]["legal_candidates"], ["neutral", "jab", "grab"])
            self.assertEqual(result["bot"]["stocks_remaining"], 4)
            self.assertEqual(result["match"]["time_limit_seconds"], 480)
            self.assertEqual(result["opponent"]["native_motion_name"], "Wait")

    def test_range_boundary_uses_full_precision_before_display_rounding(self):
        observation = ground()
        at_edge = replace(observation, opponent=replace(observation.opponent, x=12.))
        self.assertIn("jab", compact_observation(at_edge, ("jab",)).wire()["mechanical"]["legal_candidates"])
        beyond = replace(observation, opponent=replace(observation.opponent, x=12.00001))
        with self.assertRaisesRegex(ValueError, "illegal"):
            compact_observation(beyond, ("jab",))
        self.assertEqual(compact_observation(beyond, ()).wire()["relative"]["opponent_delta_rounded"][0], 12.)

    def test_stock_comparison_and_match_clock_are_computed_locally(self):
        for stocks, leader, advantage in ((2, "opponent", -1), (3, "tied", 0), (4, "bot", 1)):
            observation = ground(3600)
            observation = replace(observation, bot=replace(observation.bot, stocks_remaining=stocks,
                details=replace(observation.bot.details, life_generation_derived=5-stocks)),
                opponent=replace(observation.opponent, stocks_remaining=3,
                    details=replace(observation.opponent.details, life_generation_derived=2)))
            result = compact_observation(observation, ()).wire()
            self.assertEqual(result["relative"]["stock_advantage"], advantage)
            self.assertEqual(result["relative"]["stock_leader"], leader)
            self.assertEqual(result["match"]["elapsed_seconds_estimated"], 60)
            self.assertEqual(result["match"]["remaining_seconds_estimated"], 420)

    def test_hitlag_animation_index_and_unknown_fields_are_not_punish_windows(self):
        observation = ground(17, 44, action_frame=9, hitlag_frames_derived=3)
        result = compact_observation(observation, ()).wire()
        self.assertEqual(result["bot"]["native_motion_name"], "Attack11")
        self.assertEqual(result["bot"]["animation_frame_normalized"], 9)
        self.assertEqual(result["bot"]["hitlag_remaining_estimated"], 3)
        self.assertEqual(result["mechanical"]["inhibited_reason"], "hitlag")
        self.assertIn("exact_punish_window", result["unavailable"])
        self.assertIn("current_skill", result["unavailable"])
        unknown = replace(ground(), opponent=replace(ground().opponent,
            details=replace(ground().opponent.details, hurtbox_state=None, action_id=999)))
        result = compact_observation(unknown, ("neutral",)).wire()
        self.assertIsNone(result["opponent"]["hurtbox_state"])
        self.assertIsNone(result["opponent"]["native_motion_name"])
        self.assertIn("opponent.hurtbox_state", result["unavailable"])

    def test_history_excludes_current_future_duplicate_and_previous_life_states(self):
        current = ground(20)
        for history in ((ground(20),), (ground(21),), (ground(1), ground(1)),
                (ground(1, life_generation_derived=2),)):
            with self.assertRaises(ValueError):
                compact_observation(current, (), history=history)
        result = compact_observation(current, (), history=(ground(1), ground(10))).wire()
        self.assertEqual([row["frame"] for row in result["history"]], [1, 10])
        self.assertTrue(all(set(row) == {"frame", "bot_motion", "opponent_motion", "opponent_delta_rounded", "stocks"} for row in result["history"]))

    def test_history_is_bounded_and_clears_on_a_gap_or_life_change(self):
        history = SemanticHistory()
        for frame in range(100):
            prior = history.before(ground(frame))
            self.assertLessEqual(len(prior), 4)
            self.assertTrue(all(row.frame < frame for row in prior))
        self.assertEqual([row.frame for row in prior], [45, 60, 75, 90])
        self.assertEqual(history.before(ground(102)), ())
        self.assertEqual(history.before(ground(103, life_generation_derived=2)), ())

    def test_current_skill_is_filtered_and_bound_to_the_present_life(self):
        active = {"skill": "jab", "direction": 1, "phase": "await_completion", "source_frame": 2,
            "episode": 1, "life": 1, "future_outcome": "never include this"}
        result = compact_observation(ground(10, 44), (), active_skill=active, skill_known=True).wire()
        self.assertEqual(result["current_skill"], {"skill": "jab", "direction": 1,
            "phase": "await_completion", "age_frames_derived": 8})
        self.assertNotIn("future_outcome", json.dumps(result))
        for field, value in (("episode", 2), ("life", 2), ("source_frame", 11)):
            with self.assertRaises(ValueError):
                compact_observation(ground(10), (), active_skill={**active, field: value}, skill_known=True)

    def test_compact_identity_and_canonical_payload_are_immutable_and_bounded(self):
        compact = compact_observation(ground(), ("neutral", "jab"))
        self.assertLess(len(compact.payload_json.encode()), 16384)
        modified = compact.wire()
        modified["frame"] += 1
        with self.assertRaises(ValueError):
            CompactObservation(compact.episode, compact.frame, compact.observed_ns, json.dumps(modified))
        self.assertEqual(compact.wire()["frame"], 0)
        self.assertEqual(len(compact.sha256), 64)
