"""Explicit local diagnostics, supervised matches, and retained results."""

import argparse
import json
from pathlib import Path

from .doctor import diagnose


def main(argv=None):
    parser = argparse.ArgumentParser(prog="melee-agent")
    commands = parser.add_subparsers(dest="command", required=True)
    doctor = commands.add_parser("doctor", help="Inspect capabilities without launching or spending")
    doctor.add_argument("--json", action="store_true", help="Emit public-safe schema-v1 JSON")
    doctor.add_argument("--workspace", type=Path, default=Path(__file__).resolve().parents[3])
    doctor.add_argument("--config", type=Path, help="Workspace-relative local TOML (default agent/local.toml)")
    doctor.add_argument("--require", choices=("all", "offline", "host_tests", "decomp", "live", "provider"), default="all")
    match = commands.add_parser("match", help="Run supervised Fox versus Mario CPU 3 on Battlefield")
    match.add_argument("--policy", choices=("scripted", "smoke", "input-probe", "neutral-probe", "heuristic", "random-legal", "heuristic-tactical", "random-tactical", "delayed-fake", "jev"), default="scripted")
    match.add_argument("--duration", type=int, default=120, help="Hard wall-clock limit including setup")
    match.add_argument("--episodes", type=int, default=1)
    match.add_argument("--budget", help="Existing shared budget directory; required for jev")
    match.add_argument("--max-requests", type=int, help="Explicit 1-200 attempt cap for this jev run")
    capture = commands.add_parser("capture", help="Capture until a wall-clock deadline, retaining partial final match")
    capture.add_argument("--duration", type=int, default=600)
    capture.add_argument("--policy", choices=("scripted", "smoke", "neutral-probe", "delayed-fake", "jev", "faults", "heuristic", "random-legal", "heuristic-tactical", "random-tactical"), default="scripted")
    capture.add_argument("--fault", help="Explicit runtime-v1 fault mode; only with policy faults")
    capture.add_argument("--budget", help="Existing shared budget directory; required for jev")
    capture.add_argument("--max-requests", type=int, help="Explicit 1-200 attempt cap for this jev run")
    soak = commands.add_parser("soak", help="Thirty-minute runtime-v1 fault schedule; no external provider calls")
    soak.add_argument("--budget", required=True, help="Existing paid ledger to verify remains unchanged")
    soak.add_argument("--duration", type=int, default=1800)
    skills = commands.add_parser("skill-check", help="Observed movement, combat, aerial and recovery repetitions on Battlefield")
    skills.add_argument("--repeats", type=int, default=20)
    skills.add_argument("--duration", type=int, help="Hard wall-clock limit; defaults to 600s movement, 3000s combat, 2400s aerial/recovery")
    skills.add_argument("--suite", choices=("movement-v1", "recovery-v1", "ground-combat-v1", "aerial-v1"), default="movement-v1")
    skills.add_argument("--policy", choices=("offline",), default="offline")
    scenarios = commands.add_parser("scenarios", help="Fresh-match mechanical scenario suite with explicit setup outcomes")
    scenarios.add_argument("--suite", choices=("mechanics-v1", "recovery-v1", "ground-combat-v1", "aerial-v1"), default="mechanics-v1")
    scenarios.add_argument("--repeats", type=int, default=10)
    scenarios.add_argument("--duration", type=int, default=2400, help="Hard wall-clock suite limit")
    scenarios.add_argument("--seed", type=int, default=0, help="Trial ordering only; does not seed game RNG")
    scenario = commands.add_parser("scenario-run", help="One ordinary-input fresh-match mechanical trial")
    scenario.add_argument("--name", required=True)
    scenario.add_argument("--duration", type=int, default=30)
    explain = commands.add_parser("explain", help="Extract a private incident and print a shareable decision explanation")
    explain.add_argument("run_id")
    explain.add_argument("--episode", type=int, default=1)
    selector = explain.add_mutually_exclusive_group(required=True)
    selector.add_argument("--frame", type=int)
    selector.add_argument("--request-id")
    explain.add_argument("--after-frames", type=int, default=60)
    replay = commands.add_parser("replay-incident", help="Verify and replay a sealed prefix without network or emulator")
    replay.add_argument("incident_path")
    replay.add_argument("--verify", action="store_true", help="Integrity verification is always required")
    corpus = commands.add_parser("corpus", help="Build, verify, or explicitly evaluate private semantic states")
    corpus_commands = corpus.add_subparsers(dest="corpus_command", required=True)
    corpus_build = corpus_commands.add_parser("build")
    corpus_build.add_argument("--sources", choices=("local",), default="local")
    corpus_build.add_argument("--split-by", choices=("episode",), default="episode")
    corpus_build.add_argument("--maximum-states", type=int, default=5000)
    corpus_build.add_argument("--source-limit", type=int, default=12)
    corpus_verify = corpus_commands.add_parser("validate", aliases=["verify"])
    corpus_verify.add_argument("corpus_id")
    corpus_evaluate = corpus_commands.add_parser("evaluate", help="Explicit paid frozen-state Decisions evaluation; no emulator")
    corpus_evaluate.add_argument("corpus_id")
    corpus_evaluate.add_argument("--budget", required=True)
    corpus_evaluate.add_argument("--max-requests", type=int, required=True)
    smoke = commands.add_parser("smoke", help="Asset-free deterministic frame-to-controller regression")
    smoke.add_argument("--backend", choices=("fake",), default="fake")
    smoke.add_argument("--fixture", type=Path)
    provider = commands.add_parser("provider", help="Explicit provider probes with persistent experiment budgets")
    provider_commands = provider.add_subparsers(dest="provider_command", required=True)
    budget = provider_commands.add_parser("init-budget", help="Create an immutable budget; existing limits cannot increase")
    budget.add_argument("--directory", required=True)
    budget.add_argument("--deadline-utc", required=True)
    budget.add_argument("--limit-usd", default="1")
    budget.add_argument("--max-requests", type=int, default=600)
    budget.add_argument("--max-input-tokens", type=int, default=1000000)
    continuation = provider_commands.add_parser("continue-budget", help="Permanently seal a parent and carry only unspent dollars into one bounded child")
    continuation.add_argument("--from-directory", required=True)
    continuation.add_argument("--directory", required=True)
    continuation.add_argument("--deadline-utc", required=True)
    continuation.add_argument("--max-requests", type=int, required=True)
    continuation.add_argument("--max-input-tokens", type=int, required=True)
    provider_probe = provider_commands.add_parser("probe", help="Make one paid synthetic Decisions request, with no retries")
    provider_probe.add_argument("--budget", required=True)
    provider_probe.add_argument("--timeout", type=float, default=5)
    provider_report = provider_commands.add_parser("budget", help="Read recorded and uncertain provider costs")
    provider_report.add_argument("--directory", required=True)
    benchmark = provider_commands.add_parser("benchmark", help="Paid 1/2/5 Hz Decisions latency experiment")
    benchmark.add_argument("--budget", required=True)
    benchmark.add_argument("--max-requests", type=int, default=150)
    for name in ("inspect", "stop"):
        command = commands.add_parser(name)
        command.add_argument("run_id")
        if name == "inspect":
            command.add_argument("--integrity", action="store_true")
            command.add_argument("--skills", action="store_true")
            command.add_argument("--policy-evidence", action="store_true")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[3]
    if args.command == "corpus":
        from .corpus import build_corpus, validate_corpus
        try:
            if args.corpus_command == "evaluate":
                from .corpus_evaluation import evaluate_corpus
                report = evaluate_corpus(root, args.corpus_id, args.budget, args.max_requests)
            else:
                report = (build_corpus(root, args.maximum_states, args.source_limit) if args.corpus_command == "build"
                    else validate_corpus(root, args.corpus_id))
            print(json.dumps(report, allow_nan=False))
            return 1 if args.corpus_command == "evaluate" and report["status"] != "completed" else 0
        except (ValueError, OSError, KeyError, TypeError):
            print(json.dumps({"status": "fail", "reason": "corpus_invalid_or_unavailable",
                "provider_contacted": None if args.corpus_command == "evaluate" else False}))
            return 1
    if args.command == "scenario-run":
        from .matches import launch
        return launch(root, args.duration, 1, "scenario", scenario_name=args.name)
    if args.command == "scenarios":
        from .scenario_runner import run_suite
        try:
            return run_suite(root, args.repeats, args.duration, args.seed, args.suite)
        except (ValueError, OSError):
            print(json.dumps({"status": "blocked", "reason": "scenario_preflight_failed"}))
            return 1
    if args.command in ("explain", "replay-incident"):
        from .config import owned_path
        from .incidents import IncidentError, export_incident, replay_incident
        from .matches import locate_run
        try:
            if args.command == "explain":
                report = export_incident(root, locate_run(root, args.run_id), episode=args.episode,
                    frame=args.frame, request_id=args.request_id, after_frames=args.after_frames)
                report["incident_path"] = "build/jev/incidents/" + report["incident_id"]
            else:
                report = replay_incident(root, owned_path(root, args.incident_path))
            print(json.dumps(report, allow_nan=False))
            return 1 if report.get("status") == "fail" else 0
        except (ValueError, OSError, KeyError, TypeError, OverflowError) as error:
            print(json.dumps({"status": "fail", "reason": str(error) if isinstance(error, IncidentError)
                else "invalid_or_unavailable_incident", "emulator_launched": False, "provider_contacted": False}))
            return 1
    if args.command == "soak":
        from .soak import run_soak
        try:
            return run_soak(root, args.budget, args.duration)
        except (ValueError, OSError):
            print(json.dumps({"status": "blocked", "reason": "soak_preflight_failed"}))
            return 1
    if args.command == "provider":
        from .budget import BudgetError, SpendLedger
        from .config import owned_path
        from .provider import ProviderError
        try:
            if args.provider_command == "init-budget":
                ledger = SpendLedger.create(root, args.directory, deadline_utc=args.deadline_utc,
                    limit_usd=args.limit_usd, max_requests=args.max_requests, max_input_tokens=args.max_input_tokens)
                report = ledger.report()
            elif args.provider_command == "continue-budget":
                ledger = SpendLedger.continue_experiment(root, args.from_directory, args.directory,
                    deadline_utc=args.deadline_utc, max_requests=args.max_requests, max_input_tokens=args.max_input_tokens)
                report = ledger.report()
            elif args.provider_command == "budget":
                report = SpendLedger(owned_path(root, args.directory) / "spend.jsonl").report()
            elif args.provider_command == "benchmark":
                from .benchmark import run_benchmark
                report = run_benchmark(root, args.budget, args.max_requests)
            else:
                from .provider_commands import probe
                report = probe(root, args.budget, args.timeout)
            print(json.dumps(report, allow_nan=False))
            return 1 if report.get("status") == "fail" else 0
        except (ValueError, OSError, TimeoutError) as error:
            print(json.dumps({"status": "blocked", "error_type": type(error).__name__,
                                "reason": str(error) if isinstance(error, (BudgetError, ProviderError)) else "local_io_or_configuration",
                                "message": "Provider setup or budget check failed; no automatic retry."}))
            return 1
    if args.command == "smoke":
        from .fake import smoke
        try:
            print(json.dumps(smoke(root, args.fixture)))
            return 0
        except (ValueError, OSError, AssertionError, KeyError, TypeError) as error:
            print(json.dumps({"status": "fail", "backend": "fake", "error_type": type(error).__name__}))
            return 1
    if args.command == "match":
        from .matches import launch
        return launch(root, args.duration, args.episodes, args.policy,
            budget_directory=args.budget, max_requests=args.max_requests)
    if args.command == "capture":
        from .matches import launch
        return launch(root, args.duration, 100, args.policy, capture=True,
                        budget_directory=args.budget, max_requests=args.max_requests, fault_mode=args.fault)
    if args.command == "skill-check":
        if args.suite in ("recovery-v1", "ground-combat-v1", "aerial-v1"):
            from .scenario_runner import run_suite
            try:
                return run_suite(root, args.repeats, (3000 if args.suite == "ground-combat-v1" else 2400) if args.duration is None else args.duration,
                    suite=args.suite, require_acceptance=True)
            except (ValueError, OSError):
                print(json.dumps({"status": "blocked", "reason": "scenario_preflight_failed"}))
                return 1
        from .matches import launch
        return launch(root, 600 if args.duration is None else args.duration, 10, "skill-check", skill_repeats=args.repeats)
    if args.command in ("inspect", "stop"):
        from .matches import locate_run
        try:
            run = locate_run(root, args.run_id)
            if args.command == "stop":
                if not (run / "summary.json").exists():
                    (run / "stop.request").touch(exist_ok=True)
                print(json.dumps({"run_id": args.run_id, "stop_requested": True}))
            else:
                if args.policy_evidence:
                    from .policy_evidence import inspect_policy
                    report = inspect_policy(run)
                    print(json.dumps(report, allow_nan=False))
                    return 0 if report["status"] == "pass" else 1
                elif args.skills:
                    from .skill_evidence import inspect_skills
                    report = inspect_skills(run)
                    print(json.dumps(report, allow_nan=False))
                    return 0 if report["status"] == "pass" else 1
                elif args.integrity:
                    from .integrity import inspect_integrity
                    report = inspect_integrity(run)
                    print(json.dumps(report, allow_nan=False))
                    return 0 if report["status"] == "pass" else 1
                else:
                    summary = run / "summary.json"
                    print(summary.read_text() if summary.exists() else json.dumps({"run_id": args.run_id, "status": "running_or_interrupted"}))
            return 0
        except (ValueError, OSError, KeyError, TypeError):
            print(json.dumps({"status": "error", "message": "Invalid or unavailable run"}))
            return 1
    report = diagnose(args.workspace, args.config, args.require)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"doctor: {report['status']} (required: {report['required_capability']})")
        for item in report["checks"]:
            print(f"{item['status']:7} {item['id']}: {item['message']}")
            if item["remediation"]:
                print(f"        {item['remediation']}")
    return report["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
