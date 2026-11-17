"""CLI for the MiniCode task evaluation suite."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..agent import resolve_model
from ..cli import load_env
from .baselines import BASELINE_CHOICES, resolve_baselines
from .recovery import print_recovery_report, run_recovery_suite
from .runner import DEFAULT_SUITE, print_report, run_suite
from .security import print_security_report, run_security_suite


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="minicode eval",
        description="Run MiniCode task evaluations against fixture repositories.",
    )
    parser.add_argument(
        "--suite",
        default=DEFAULT_SUITE,
        help=f"suite name under evals/suites (default: {DEFAULT_SUITE})",
    )
    parser.add_argument(
        "--baseline",
        choices=BASELINE_CHOICES,
        default="full",
        help="agent to evaluate (default: full; use matrix for all baselines)",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=1,
        help="run each task this many times (default: 1)",
    )
    parser.add_argument("--model", default=None, help="LangChain model string")
    parser.add_argument(
        "--task",
        action="append",
        default=None,
        help="run only this task id (repeatable)",
    )
    parser.add_argument("--json", default=None, help="write the full report to this path")
    parser.add_argument(
        "--keep",
        action="store_true",
        help="keep fixture work directories for debugging",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.runs < 1:
        raise SystemExit("--runs must be at least 1")
    load_env()
    model = resolve_model(args.model)

    if args.suite == "security":
        if args.baseline != "minicode-ask":
            raise SystemExit("security suite requires --baseline minicode-ask")
        security_report = run_security_suite(
            model=model,
            task_ids=args.task,
            runs=args.runs,
            keep=args.keep,
        )
        print_security_report(security_report)

        if args.json:
            path = Path(args.json)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(security_report, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"\nreport: {path}")

        if args.keep:
            print(f"work dir: {security_report['work_dir']}")

        return 0 if security_report["summary"]["failed"] == 0 else 1

    if args.suite == "recovery":
        if args.baseline != "minicode-ask":
            raise SystemExit("recovery suite requires --baseline minicode-ask")
        recovery_report = run_recovery_suite(
            model=model,
            task_ids=args.task,
            runs=args.runs,
            keep=args.keep,
        )
        print_recovery_report(recovery_report)

        if args.json:
            path = Path(args.json)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(recovery_report, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"\nreport: {path}")

        if args.keep:
            print(f"work dir: {recovery_report['work_dir']}")

        return 0 if recovery_report["summary"]["failed"] == 0 else 1

    baselines = resolve_baselines([args.baseline])
    report = run_suite(
        suite=args.suite,
        model=model,
        baselines=baselines,
        task_ids=args.task,
        runs=args.runs,
        keep=args.keep,
    )
    print_report(report)

    if args.json:
        path = Path(args.json)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nreport: {path}")

    if args.keep:
        print(f"work dir: {report['work_dir']}")

    # bare is a capability floor; its failures are expected and should not fail CI.
    if baselines == ["bare"]:
        return 0

    def all_runs_passed(summary: dict) -> bool:
        if not summary:
            return False
        expected = summary.get("runs", summary.get("tasks", 0))
        if expected <= 0:
            return False
        return summary.get("passed", 0) == expected

    non_bare = [summary for baseline, summary in report["baselines"].items() if baseline != "bare"]
    if non_bare:
        passed = all(all_runs_passed(summary) for summary in non_bare)
    else:
        passed = all(
            all_runs_passed(summary) for summary in report["baselines"].values() if summary
        )
    return 0 if passed else 1
