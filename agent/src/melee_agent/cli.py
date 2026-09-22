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
    match.add_argument("--policy", choices=("scripted", "smoke", "input-probe"), default="scripted")
    match.add_argument("--duration", type=int, default=120, help="Hard wall-clock limit including setup")
    match.add_argument("--episodes", type=int, default=1)
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
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[3]
    if args.command == "provider":
        from .budget import BudgetError, SpendLedger
        from .config import owned_path
        from .provider import ProviderError
        try:
            if args.provider_command == "init-budget":
                ledger = SpendLedger.create(root, args.directory, deadline_utc=args.deadline_utc,
                    limit_usd=args.limit_usd, max_requests=args.max_requests, max_input_tokens=args.max_input_tokens)
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
        return launch(root, args.duration, args.episodes, args.policy)
    if args.command in ("inspect", "stop"):
        from .matches import locate_run
        try:
            run = locate_run(root, args.run_id)
            if args.command == "stop":
                if not (run / "summary.json").exists():
                    (run / "stop.request").touch(exist_ok=True)
                print(json.dumps({"run_id": args.run_id, "stop_requested": True}))
            else:
                summary = run / "summary.json"
                print(summary.read_text() if summary.exists() else json.dumps({"run_id": args.run_id, "status": "running_or_interrupted"}))
            return 0
        except (ValueError, OSError):
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
