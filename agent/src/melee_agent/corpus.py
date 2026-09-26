"""Private, reproducible semantic cases split by source episode, never by frame."""

from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import uuid

from .config import owned_path
from .incidents import open_regular, read_json, stream_records
from .matches import locate_run
from .semantic import SemanticHistory, canonical, compact_observation
from .tactical_choices import LABELS as CANDIDATE_ORDER, legal_candidates
from .source_states import captured_observation
from .trace_limits import MAX_SOURCE_BYTES

MAX_CORPUS_BYTES = 134217728
COMPILER_MODULES = ("corpus.py", "semantic.py", "source_states.py", "native_motions.py", "skills.py", "ground_combat.py", "stage.py", "engine.py", "trace_limits.py", "tactical_choices.py", "live_control.py", "raw_observation.py", "replay.py")


def digest(path):
    h = hashlib.sha256()
    with open_regular(path, MAX_SOURCE_BYTES) as source:
        size = 0
        for block in iter(lambda: source.read(1048576), b""):
            size += len(block)
            if size > MAX_SOURCE_BYTES:
                raise ValueError("Corpus source byte limit exceeded")
            h.update(block)
    return h.hexdigest()


def compiler_hashes():
    return {name: digest(Path(__file__).parent/name) for name in COMPILER_MODULES}


def episode_split(run_id, episode):
    number = int(hashlib.sha256(f"{run_id}:{episode}".encode()).hexdigest()[:8], 16) % 10
    return "train" if number < 6 else "tuning" if number < 8 else "held_out"


def choose_sources(root, limit):
    candidates = []
    for folder in (root/"build/jev/runs").glob("match-*"):
        if not folder.is_dir() or folder.is_symlink() or not (folder/"summary.json").is_file():
            continue
        summary = read_json(folder/"summary.json", 1048576)
        if (summary.get("status") not in ("captured", "complete", "scenario_recorded", "skills_verified") or
                summary.get("replay_errors") or not summary.get("neutralized") or not summary.get("worker_stopped") or
                not summary.get("emulator_stopped")):
            continue
        policy = summary.get("policy")
        priority = {"jev": 0, "delayed-fake": 1, "heuristic": 2, "random-legal": 2,
            "heuristic-tactical": 2, "random-tactical": 2, "scenario": 3}.get(policy)
        if priority is None:
            continue
        try:
            first = next(row for _, row in stream_records(folder/"frames.jsonl", MAX_SOURCE_BYTES) if row.get("menu") == "IN_GAME")
            captured_observation(first)
        except (ValueError, KeyError, StopIteration):
            continue
        candidates.append((priority, folder.name))
    return [name for _, name in sorted(candidates)[:limit]]


def response_annotations(row):
    replies = []
    for event in row.get("skill", {}).get("policy_events", []):
        delivery = event["delivery"]
        reply, context = delivery["reply"], delivery["expected"]
        metadata = reply.get("metadata") or {}
        semantic_hash = context.get("semantic_sha256")
        replies.append({"source_frame": context["frame"], "source_episode": context["episode"],
            "delivery_frame": row["frame"], "choice": reply["action"], "candidates": delivery["candidates"],
            "accepted": event["accepted"], "rejection_reason": event["reason"],
            "kind": "provider" if metadata.get("resolved_model") else "simulated",
            "resolved_model": metadata.get("resolved_model"), "request_id": metadata.get("request_id"),
            "source_semantic_sha256": semantic_hash,
            "representation": ("Compact observation at the source frame, version recorded by that run; not this delivery frame"
                if semantic_hash else "historical_raw_observation; not generated from this compact payload")})
    return replies


def generate_cases(root, runs, maximum_states):
    base_quota, remainder = divmod(maximum_states, len(runs))
    total = 0
    for run_index, run_id in enumerate(runs):
        quota = base_quota+int(run_index < remainder)
        folder = locate_run(root, run_id)
        summary = read_json(folder/"summary.json", 1048576)
        expected_frames = sum(row.get("observations", 0) for row in summary.get("episodes", []))
        history = SemanticHistory()
        previous_trace = None
        previous_identity = None
        previous_frame = None
        source_index = emitted = 0
        for line, row in stream_records(folder/"frames.jsonl", MAX_SOURCE_BYTES):
            if row.get("menu") != "IN_GAME":
                continue
            observation = captured_observation(row)
            prior = history.before(observation)
            identity = (observation.episode, observation.bot.details.life_generation_derived)
            known = previous_trace is not None and previous_identity == identity and previous_frame == observation.frame-1
            active = previous_trace.get("active") if known else None
            previous_trace = row.get("skill") or row.get("scenario", {}).get("skill")
            previous_identity = identity
            previous_frame = observation.frame
            if observation.frame < 0:
                continue
            selected = source_index >= emitted*expected_frames//quota
            source_index += 1
            if not selected or emitted >= quota:
                continue
            labels = legal_candidates(observation)
            state = compact_observation(observation, labels, active_skill=active, skill_known=known, history=prior)
            yield {"schema_version": 1, "source": {"run_id": run_id, "episode": observation.episode,
                "frame": observation.frame, "observation_schema_version": row["control"]["observation"]["schema_version"],
                "raw_record_sha256": hashlib.sha256(line).hexdigest()},
                "split": episode_split(run_id, observation.episode), "state": state.wire(), "state_sha256": state.sha256,
                "recorded": {"policy": summary["policy"], "controller_action": row["control"]["decision"]["action"],
                    "responses_delivered_on_this_frame": response_annotations(row)}}
            emitted += 1
            total += 1
            if total >= maximum_states:
                return


def summarize_cases(cases):
    splits, responses, policies = Counter(), Counter(), Counter()
    byte_sizes = []
    episodes = set()
    for row in cases:
        splits[row["split"]] += 1
        policies[row["recorded"]["policy"]] += 1
        episodes.add((row["source"]["run_id"], row["source"]["episode"]))
        byte_sizes.append(len(canonical(row["state"]).encode()))
        for reply in row["recorded"]["responses_delivered_on_this_frame"]:
            responses[reply["kind"]] += 1
    sizes = sorted(byte_sizes)
    return {"states": len(cases), "episodes": len(episodes), "split_states": dict(splits),
        "policy_source_states": dict(policies), "responses_on_sampled_delivery_frames": dict(responses),
        "payload_bytes": {"minimum": min(sizes, default=0), "maximum": max(sizes, default=0),
            "median": sizes[len(sizes)//2] if sizes else 0},
        "estimated_payload_tokens_median": math.ceil(sizes[len(sizes)//2]/4) if sizes else 0,
        "token_estimate_method": "UTF-8 payload bytes divided by four; not the provider tokenizer",
        "provider_contacted": False,
        "evaluation_limit": "Extraction/legality corpus only. Sparse historical responses refer to their own earlier source frames and raw representation; they do not score the new compact representation."}


def build_corpus(root, maximum_states=5000, source_limit=12):
    if type(maximum_states) is not int or not 1000 <= maximum_states <= 10000 or type(source_limit) is not int or not 3 <= source_limit <= 24:
        raise ValueError("Invalid corpus bounds")
    runs = choose_sources(root, source_limit)
    if len(runs) < 3:
        raise ValueError("Corpus needs at least three compatible completed source sessions")
    corpus_id = "corpus-"+uuid.uuid4().hex
    folder = owned_path(root, "build/jev/corpora/"+corpus_id)
    folder.mkdir(parents=True)
    sources = {run_id: {name: digest(locate_run(root, run_id)/name) for name in ("frames.jsonl", "summary.json")}
        for run_id in runs}
    cases = list(generate_cases(root, runs, maximum_states))
    raw = "".join(canonical(row)+"\n" for row in cases).encode()
    if len(raw) > MAX_CORPUS_BYTES:
        raise ValueError("Corpus artifact exceeds bound")
    (folder/"states.jsonl").write_bytes(raw)
    manifest = {"schema_version": 1, "corpus_id": corpus_id, "source_runs": runs, "source_sha256": sources,
        "compiler_sha256": compiler_hashes(),
        "maximum_states": maximum_states, "split_by": "episode", "candidate_order": list(CANDIDATE_ORDER),
        "state_file_sha256": hashlib.sha256(raw).hexdigest(), "summary": summarize_cases(cases)}
    (folder/"manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
    return {"corpus_id": corpus_id, **manifest["summary"]}


def validate_corpus(root, corpus_id):
    if not isinstance(corpus_id, str) or len(corpus_id) != 39 or not corpus_id.startswith("corpus-") or any(c not in "0123456789abcdef" for c in corpus_id[7:]):
        raise ValueError("Invalid corpus identifier")
    folder = owned_path(root, "build/jev/corpora/"+corpus_id)
    manifest = read_json(folder/"manifest.json", 1048576)
    if (manifest.get("schema_version") != 1 or manifest.get("corpus_id") != corpus_id or
            manifest.get("candidate_order") != list(CANDIDATE_ORDER) or manifest.get("split_by") != "episode" or
            type(manifest.get("maximum_states")) is not int or not 1000 <= manifest["maximum_states"] <= 10000 or
            not isinstance(manifest.get("source_runs"), list) or not 3 <= len(manifest["source_runs"]) <= 24 or
            any(type(run_id) is not str for run_id in manifest["source_runs"]) or
            len(set(manifest["source_runs"])) != len(manifest["source_runs"])):
        raise ValueError("Invalid corpus manifest")
    if manifest.get("compiler_sha256") != compiler_hashes():
        raise ValueError("Corpus compiler changed; use its matching checkout or build a new corpus")
    for run_id in manifest["source_runs"]:
        for name in ("frames.jsonl", "summary.json"):
            if digest(locate_run(root, run_id)/name) != manifest["source_sha256"][run_id][name]:
                raise ValueError("Corpus source changed")
    path = folder/"states.jsonl"
    if path.stat().st_size > MAX_CORPUS_BYTES or digest(path) != manifest["state_file_sha256"]:
        raise ValueError("Corpus state file changed")
    expected = list(generate_cases(root, manifest["source_runs"], manifest["maximum_states"]))
    actual = [row for _, row in stream_records(path, MAX_CORPUS_BYTES)]
    if actual != expected or summarize_cases(actual) != manifest["summary"]:
        raise ValueError("Corpus state, split, history or label no longer matches its source")
    return {"corpus_id": corpus_id, "status": "pass", "recompiled_states": len(actual), **manifest["summary"]}
