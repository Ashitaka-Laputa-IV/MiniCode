"""CLI for the MiniCode task evaluation suite."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..agent import resolve_model
from ..cli import load_env
from .runner import DEFAULT_SUITE, EVALS_DIR, print_report, run_suite


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
        choices=["full", "bare", "all"],
        default="full",
        help="agent to evaluate (default: full)",
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
    load_env()
    model = resolve_model(args.model)
    baselines = ["full", "bare"] if args.baseline == "all" else [args.baseline]
    report = run_suite(
        suite=args.suite,
        model=model,
        baselines=baselines,
        task_ids=args.task,
        keep=args.keep,
    )
    print_report(report)

    if args.json:
        path = Path(args.json)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\nreport: {path}")

    if args.keep:
        print(f"work dir: {EVALS_DIR / 'results'} (kept temporary root: {report['work_dir']})")

    passed = all(
        summary["passed"] == summary["tasks"]
        for baseline, summary in report["baselines"].items()
        if baseline != "bare"
    )
    return 0 if passed else 1
