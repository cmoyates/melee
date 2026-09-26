from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from melee_agent.corpus import build_corpus, digest, episode_split, generate_cases, response_annotations, validate_corpus
from melee_agent.source_states import captured_observation
from test_combat_integration import ground


class CaptureAdapterTests(unittest.TestCase):
    def test_historical_upgrade_uses_raw_hurtbox_availability_without_mutating_source(self):
        source = {"menu": "IN_GAME", "episode": 1, "frame": 0, "control": {"observation": asdict(ground())}}
        data = source["control"]["observation"]
        data["schema_version"] = 3
        for name in ("bot", "opponent"):
            data[name]["details"].pop("hurtbox_state")
        before = deepcopy(source)
        observation = captured_observation(source)
        self.assertIsNone(observation.bot.details.hurtbox_state)
        self.assertIsNone(observation.opponent.details.hurtbox_state)
        self.assertEqual(source, before)
        source["raw_observation"] = {"players": {"2": {"raw_post": {"hurtbox_state": 2, "available": {"hurtbox_state": True}}}}}
        self.assertEqual(captured_observation(source).opponent.details.hurtbox_state, 2)
        source["frame"] = 1
        with self.assertRaisesRegex(ValueError, "identity"):
            captured_observation(source)


class CorpusTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="jev-corpus-test-")).resolve()
        self.runs = []
        for number in range(3):
            run_id = "match-"+format(number, "032x")
            folder = self.root/"build/jev/runs"/run_id
            folder.mkdir(parents=True)
            summary = {"status": "captured", "policy": "heuristic", "neutralized": True, "worker_stopped": True,
                "emulator_stopped": True, "replay_errors": 0, "episodes": [{"observations": 360}]}
            (folder/"summary.json").write_text(json.dumps(summary))
            with (folder/"frames.jsonl").open("w") as output:
                for frame in range(360):
                    row = {"menu": "IN_GAME", "episode": 1, "frame": frame,
                        "control": {"observation": asdict(ground(frame)), "decision": {"action": "wait"}},
                        "skill": {"active": None, "future_outcome": "forbidden in policy state"},
                        "future_opponent_input": "also forbidden"}
                    output.write(json.dumps(row)+"\n")
            self.runs.append(run_id)

    def build(self):
        with patch("socket.socket", side_effect=AssertionError("network forbidden")), patch("subprocess.Popen", side_effect=AssertionError("process forbidden")):
            result = build_corpus(self.root, maximum_states=1000, source_limit=3)
            validated = validate_corpus(self.root, result["corpus_id"])
        self.assertEqual(validated["status"], "pass")
        self.assertEqual(result["states"], 1000)
        return self.root/"build/jev/corpora"/result["corpus_id"], result

    def test_ordered_states_keep_complete_episodes_together_and_exclude_future_suffixes(self):
        folder, result = self.build()
        rows = [json.loads(line) for line in (folder/"states.jsonl").read_text().splitlines()]
        seen = set()
        previous = {}
        for row in rows:
            source = row["source"]
            identity = (source["run_id"], source["episode"], source["frame"])
            self.assertNotIn(identity, seen)
            seen.add(identity)
            self.assertGreater(source["frame"], previous.get(source["run_id"], -1))
            previous[source["run_id"]] = source["frame"]
            self.assertEqual(row["split"], episode_split(source["run_id"], source["episode"]))
            self.assertTrue(all(state["frame"] < source["frame"] for state in row["state"]["history"]))
        self.assertNotIn("forbidden", (folder/"states.jsonl").read_text())
        self.assertFalse(result["provider_contacted"])

    def test_changing_state_and_updating_its_file_hash_still_fails_source_recompilation(self):
        folder, result = self.build()
        path = folder/"states.jsonl"
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        rows[0]["state"]["bot"]["stocks_remaining"] = 99
        path.write_text("".join(json.dumps(row)+"\n" for row in rows))
        manifest = json.loads((folder/"manifest.json").read_text())
        manifest["state_file_sha256"] = digest(path)
        (folder/"manifest.json").write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "no longer matches"):
            validate_corpus(self.root, result["corpus_id"])

    def test_changed_source_or_duplicate_session_is_rejected(self):
        folder, result = self.build()
        manifest = json.loads((folder/"manifest.json").read_text())
        original = deepcopy(manifest)
        manifest["source_runs"][1] = manifest["source_runs"][0]
        (folder/"manifest.json").write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "manifest"):
            validate_corpus(self.root, result["corpus_id"])
        (folder/"manifest.json").write_text(json.dumps(original))
        source = self.root/"build/jev/runs"/self.runs[0]/"summary.json"
        source.write_text(source.read_text()+"\n")
        with self.assertRaisesRegex(ValueError, "source changed"):
            validate_corpus(self.root, result["corpus_id"])

    def test_missing_frame_discards_prior_skill_commitment(self):
        folder = self.root/"build/jev/runs"/self.runs[0]
        rows = []
        for frame in (0, 2, 3):
            rows.append({"menu": "IN_GAME", "episode": 1, "frame": frame,
                "control": {"observation": asdict(ground(frame)), "decision": {"action": "wait"}},
                "skill": {"active": None}})
        (folder/"frames.jsonl").write_text("".join(json.dumps(row)+"\n" for row in rows))
        (folder/"summary.json").write_text(json.dumps({"policy": "heuristic", "episodes": [{"observations": 3}]}))
        states = [row["state"] for row in generate_cases(self.root, [self.runs[0]], 1000)]
        self.assertIn("current_skill", states[1]["unavailable"])
        self.assertEqual(states[1]["history"], [])
        self.assertNotIn("current_skill", states[2]["unavailable"])

    def test_semantic_response_annotation_keeps_source_binding_separate_from_delivery(self):
        context = {"frame": 5, "episode": 1, "semantic_sha256": "a"*64}
        row = {"frame": 30, "skill": {"policy_events": [{"accepted": False, "reason": "stale",
            "delivery": {"expected": context, "candidates": ["neutral", "approach"],
                "reply": {"action": "approach", "metadata": {"resolved_model": "test-model"}}}}]}}
        annotation, = response_annotations(row)
        self.assertEqual((annotation["source_frame"], annotation["delivery_frame"]), (5, 30))
        self.assertEqual(annotation["source_semantic_sha256"], "a"*64)
        self.assertIn("source frame", annotation["representation"])
        context.pop("semantic_sha256")
        annotation, = response_annotations(row)
        self.assertIsNone(annotation["source_semantic_sha256"])
        self.assertIn("historical_raw", annotation["representation"])
