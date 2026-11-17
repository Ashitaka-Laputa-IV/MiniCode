"""Suite runner for MiniCode task evaluations."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from statistics import pstdev
from typing import Any

from rich.console import Console
from rich.table import Table

from minicode.agent import shell_env

from .baselines import resolve_baselines
from .classify import classify_failure, failure_counts, pass_at_k
from .trace import read_trace, summarize_events

PROJECT_ROOT = Path(__file__).resolve().parents[3]
EVALS_DIR = (
    Path(os.environ.get("MINICODE_EVALS_DIR", PROJECT_ROOT / "evals")).expanduser().resolve()
)
TASKS_DIR = EVALS_DIR / "tasks"
SUITES_DIR = EVALS_DIR / "suites"
PRICING_FILE = EVALS_DIR / "pricing.toml"
SAFE_PYTEST_INI = EVALS_DIR / "pytest-safe.ini"
DEFAULT_SUITE = "smoke"


@dataclass(frozen=True)
class Task:
    id: str
    path: Path
    category: str
    prompt_file: Path
    agent_timeout_seconds: int
    verify_timeout_seconds: int
    max_tool_calls: int
    hidden_tests: Path | None
    verify_command: str | None
    verify_script: Path | None


def load_task(path: Path) -> Task:
    data = tomllib.loads((path / "task.toml").read_text(encoding="utf-8"))
    task_id = str(data.get("id") or path.name)
    hidden = data.get("hidden_tests")
    verify_script = data.get("verify_script")
    timeout = int(data.get("timeout_seconds", 180))
    return Task(
        id=task_id,
        path=path,
        category=str(data.get("category", "general")),
        prompt_file=path / str(data.get("prompt_file", "prompt.md")),
        agent_timeout_seconds=int(data.get("agent_timeout_seconds", timeout)),
        verify_timeout_seconds=int(data.get("verify_timeout_seconds", timeout)),
        max_tool_calls=int(data.get("max_tool_calls", 30)),
        hidden_tests=(path / str(hidden)) if hidden else None,
        verify_command=(str(data["verify_command"]) if "verify_command" in data else None),
        verify_script=(path / str(verify_script)) if verify_script else None,
    )


def load_suite(name: str) -> list[Task]:
    path = SUITES_DIR / f"{name}.toml"
    if not path.exists():
        raise FileNotFoundError(f"suite not found: {path}")
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    tasks = []
    for task_id in data.get("tasks", []):
        task_path = TASKS_DIR / task_id
        if not task_path.is_dir():
            raise FileNotFoundError(f"task not found: {task_path}")
        tasks.append(load_task(task_path))
    return tasks


def load_pricing() -> dict[str, dict[str, float]]:
    if not PRICING_FILE.exists():
        return {}
    data = tomllib.loads(PRICING_FILE.read_text(encoding="utf-8"))
    return {
        str(name): {str(k): float(v) for k, v in values.items()}
        for name, values in data.get("models", {}).items()
    }


def cost_for(model: str, usage: dict[str, int], pricing: dict[str, dict[str, float]]) -> float:
    prices = pricing.get(model, {})
    cached = usage.get("cached_input_tokens", 0)
    uncached = max(usage.get("input_tokens", 0) - cached, 0)
    cached_price = prices.get("cached_input_per_million", prices.get("input_per_million", 0.0))
    return (
        uncached * prices.get("input_per_million", 0.0)
        + cached * cached_price
        + usage.get("output_tokens", 0) * prices.get("output_per_million", 0.0)
    ) / 1_000_000


def verification_env(workspace: Path) -> dict[str, str]:
    """Environment for verification: no provider keys, workspace on import path."""
    env = shell_env()
    old = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(workspace) if not old else f"{workspace}{os.pathsep}{old}"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def worker_env(workspace: Path) -> dict[str, str]:
    """Environment for the agent process: it needs the provider key."""
    env = dict(os.environ)
    old = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(workspace) if not old else f"{workspace}{os.pathsep}{old}"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def failed_result(
    task: Task,
    baseline: str,
    error: str,
    duration_s: float = 0.0,
    run_index: int = 0,
) -> dict[str, Any]:
    return {
        "id": task.id,
        "category": task.category,
        "baseline": baseline,
        "run": run_index,
        "passed": False,
        "worker_ok": False,
        "verify_ok": False,
        "error": error,
        "tool_calls": 0,
        "usage": {},
        "cost_usd": 0.0,
        "duration_s": round(duration_s, 3),
        "verify_output": "",
        "worker_output": "",
        "final": "",
        "trace_summary": {},
        "failure_reason": classify_failure({"passed": False, "error": error}),
    }


def run_verify(task: Task, workspace: Path) -> tuple[bool, str]:
    env = verification_env(workspace)

    if task.hidden_tests is not None:
        hidden_root = workspace.parent / "hidden_tests"
        shutil.rmtree(hidden_root, ignore_errors=True)
        shutil.copytree(task.hidden_tests, hidden_root)
        pytest_args = [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-c",
            str(SAFE_PYTEST_INI),
            "--rootdir",
            str(hidden_root),
            "--confcutdir",
            str(hidden_root),
            "-p",
            "no:cacheprovider",
            str(hidden_root),
        ]
        try:
            collect = subprocess.run(
                pytest_args + ["--collect-only"],
                cwd=workspace,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=task.verify_timeout_seconds,
            )
            collected = sum(1 for line in collect.stdout.splitlines() if "::" in line)
            if collect.returncode != 0:
                return False, (collect.stdout + "\n" + collect.stderr).strip()[-4000:]
            if collected == 0:
                return False, "hidden tests collected 0 tests"
            proc = subprocess.run(
                pytest_args,
                cwd=workspace,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=task.verify_timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            return False, "verification timed out"
        output = (proc.stdout + "\n" + proc.stderr).strip()
        return proc.returncode == 0, output[-4000:]

    if task.verify_script is not None:
        command = [sys.executable, str(task.verify_script), str(workspace)]
    else:
        raw = task.verify_command or "python -m pytest -q"
        command = shlex.split(raw)
        if command and command[0] in {"python", "python3"}:
            command[0] = sys.executable
        if command[:3] == [sys.executable, "-m", "pytest"]:
            command.extend(["-c", str(SAFE_PYTEST_INI), "-p", "no:cacheprovider"])

    try:
        proc = subprocess.run(
            command,
            cwd=workspace,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=task.verify_timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return False, "verification timed out"
    except OSError as exc:
        return False, f"verification failed to start: {exc}"

    output = (proc.stdout + "\n" + proc.stderr).strip()
    return proc.returncode == 0, output[-4000:]


def _worker_failure_result(
    error: str,
    *,
    trace_file: Path | None,
    duration_s: float,
    worker_output: str = "",
) -> tuple[dict[str, Any], str]:
    """Build a failed worker result, recovering partial data from the trace."""
    events = read_trace(trace_file) if trace_file is not None else []
    summary = summarize_events(events)
    return (
        {
            "ok": False,
            "error": error,
            "tool_calls": int(summary.get("tool_calls", 0)),
            "usage": dict(summary.get("usage") or {}),
            "duration_s": round(duration_s, 3),
            "trace_summary": summary,
        },
        worker_output,
    )


def run_worker(
    task: Task,
    workspace: Path,
    model: str | None,
    baseline: str,
    *,
    run_index: int = 0,
    trace_file: Path | None = None,
    checkpoint_db: Path | None = None,
    thread_id: str | None = None,
    pause_on_interrupt: bool = False,
    resume_approve: bool = False,
    disable_checkpoint: bool = False,
    output_name: str | None = None,
) -> tuple[dict[str, Any], str]:
    output_file = workspace.parent / (output_name or f"worker-{run_index}.json")
    started = time.perf_counter()
    command = [
        sys.executable,
        "-m",
        "minicode.evals.worker",
        "--prompt-file",
        str(task.prompt_file),
        "--root",
        str(workspace),
        "--output",
        str(output_file),
        "--baseline",
        baseline,
        "--max-tool-calls",
        str(task.max_tool_calls),
    ]
    if trace_file is not None:
        command.extend(["--trace-file", str(trace_file)])
    if checkpoint_db is not None:
        command.extend(["--checkpoint-db", str(checkpoint_db)])
    if thread_id is not None:
        command.extend(["--thread", thread_id])
    if pause_on_interrupt:
        command.append("--pause-on-interrupt")
    if resume_approve:
        command.append("--resume-approve")
    if disable_checkpoint:
        command.append("--disable-checkpoint")
    if model:
        command.extend(["--model", model])

    try:
        proc = subprocess.run(
            command,
            cwd=workspace,
            env=worker_env(workspace),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=task.agent_timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return _worker_failure_result(
            f"task timed out after {task.agent_timeout_seconds}s",
            trace_file=trace_file,
            duration_s=time.perf_counter() - started,
        )

    if not output_file.exists():
        return _worker_failure_result(
            "worker produced no result",
            trace_file=trace_file,
            duration_s=time.perf_counter() - started,
            worker_output=(proc.stdout + "\n" + proc.stderr).strip(),
        )
    try:
        return json.loads(output_file.read_text(encoding="utf-8")), ""
    except (OSError, json.JSONDecodeError) as exc:
        return _worker_failure_result(
            f"worker result unreadable: {exc}",
            trace_file=trace_file,
            duration_s=time.perf_counter() - started,
            worker_output=(proc.stdout + "\n" + proc.stderr).strip(),
        )


def run_task(
    task: Task,
    *,
    work_root: Path,
    model: str | None,
    baseline: str,
    run_index: int = 0,
    pricing: dict[str, dict[str, float]],
    pause_on_interrupt: bool = False,
    resume_approve: bool = False,
    disable_checkpoint: bool = False,
) -> dict[str, Any]:
    task_root = work_root / f"{task.id}-{baseline}-{run_index}"
    workspace = task_root / "workspace"
    task_root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(task.path / "fixture", workspace)
    trace_file = task_root / "trace.jsonl"
    checkpoint_db = task_root / "checkpoint.sqlite"
    thread_id = f"{task.id}-{baseline}-{run_index}"

    started = time.perf_counter()
    worker, worker_output = run_worker(
        task,
        workspace,
        model,
        baseline,
        run_index=run_index,
        trace_file=trace_file,
        checkpoint_db=checkpoint_db,
        thread_id=thread_id,
        pause_on_interrupt=pause_on_interrupt,
        resume_approve=resume_approve,
        disable_checkpoint=disable_checkpoint,
    )
    verify_ok = False
    verify_output = ""
    if worker.get("ok"):
        try:
            verify_ok, verify_output = run_verify(task, workspace)
        except Exception as exc:
            verify_output = f"verification error: {exc}"

    passed = bool(worker.get("ok")) and verify_ok
    model_name = model or os.getenv("MINICODE_MODEL", "")
    trace_summary = worker.get("trace_summary") or {}
    result = {
        "id": task.id,
        "category": task.category,
        "baseline": baseline,
        "run": run_index,
        "passed": passed,
        "worker_ok": bool(worker.get("ok")),
        "verify_ok": verify_ok,
        "error": worker.get("error"),
        "tool_calls": int(worker.get("tool_calls", 0)),
        "usage": worker.get("usage", {}),
        "cost_usd": cost_for(str(model_name), worker.get("usage", {}), pricing),
        "duration_s": round(time.perf_counter() - started, 3),
        "verify_output": verify_output,
        "worker_output": worker_output[-1000:],
        "final": str(worker.get("final", ""))[:4000],
        "trace_summary": trace_summary,
    }
    result["failure_reason"] = classify_failure(result, trace_summary)
    if not passed and not result["error"]:
        result["error"] = "verification failed"
    return result


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        return {}

    passes = [1.0 if result["passed"] else 0.0 for result in results]
    grouped: dict[str, list[bool]] = {}
    for index, result in enumerate(results):
        task_id = str(result.get("id") or f"task-{index}")
        grouped.setdefault(task_id, []).append(bool(result["passed"]))
    run_count = max(len(flags) for flags in grouped.values())
    pass_k, pass_k_std = pass_at_k(results, run_count)

    usage = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cached_input_tokens": 0,
        "total_tokens": 0,
    }
    for result in results:
        for key, value in result["usage"].items():
            if key in usage:
                usage[key] += int(value)

    traces = [result.get("trace_summary") or {} for result in results]
    passed = sum(1 for result in results if result["passed"])
    return {
        "tasks": len(grouped),
        "runs": len(results),
        "runs_per_task": round(len(results) / len(grouped), 2),
        "passed": passed,
        "passed_tasks": sum(1 for flags in grouped.values() if any(flags)),
        "pass_at_1": round(sum(passes) / len(passes), 4),
        "pass_at_1_std": round(pstdev(passes), 4) if len(passes) > 1 else 0.0,
        "pass_at_k": pass_k,
        "pass_at_k_std": pass_k_std,
        "avg_tool_calls": round(sum(result["tool_calls"] for result in results) / len(results), 2),
        "avg_approvals": round(
            sum(int(trace.get("approvals", 0)) for trace in traces) / len(results), 2
        ),
        "avg_blocked": round(
            sum(int(trace.get("blocked", 0)) for trace in traces) / len(results), 2
        ),
        "failure_counts": failure_counts(results),
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
        "cached_input_tokens": usage["cached_input_tokens"],
        "total_tokens": usage["total_tokens"],
        "cost_usd": round(sum(result["cost_usd"] for result in results), 6),
        "wall_time_s": round(sum(result["duration_s"] for result in results), 2),
    }


def run_suite(
    *,
    suite: str,
    model: str | None,
    baselines: list[str],
    task_ids: list[str] | None = None,
    runs: int = 1,
    keep: bool = False,
) -> dict[str, Any]:
    if runs < 1:
        raise ValueError("runs must be at least 1")
    tasks = load_suite(suite)
    if task_ids:
        wanted = set(task_ids)
        tasks = [task for task in tasks if task.id in wanted]
        missing = wanted - {task.id for task in tasks}
        if missing:
            raise ValueError(f"unknown task(s): {', '.join(sorted(missing))}")

    selected = resolve_baselines(baselines)
    run_count = runs
    pricing = load_pricing()
    started_at = datetime.now().astimezone().isoformat(timespec="seconds")
    work_root = Path(tempfile.mkdtemp(prefix="minicode-evals-"))
    results: list[dict[str, Any]] = []

    try:
        for baseline in selected:
            for task in tasks:
                for run_index in range(run_count):
                    try:
                        result = run_task(
                            task,
                            work_root=work_root,
                            model=model,
                            baseline=baseline,
                            run_index=run_index,
                            pricing=pricing,
                        )
                    except Exception as exc:
                        result = failed_result(
                            task,
                            baseline,
                            f"{type(exc).__name__}: {exc}",
                            run_index=run_index,
                        )
                    results.append(result)
    finally:
        if not keep:
            shutil.rmtree(work_root, ignore_errors=True)

    by_baseline = {
        baseline: summarize([r for r in results if r["baseline"] == baseline])
        for baseline in selected
    }
    return {
        "suite": suite,
        "model": model or os.getenv("MINICODE_MODEL", ""),
        "started_at": started_at,
        "runs": run_count,
        "baselines": by_baseline,
        "tasks": results,
        "work_dir": str(work_root) if keep else None,
    }


def print_report(report: dict[str, Any]) -> None:
    console = Console()
    table = Table(title=f"MiniCode evals: {report['suite']}")
    table.add_column("task", style="bold")
    table.add_column("baseline")
    table.add_column("run", justify="right")
    table.add_column("pass")
    table.add_column("calls", justify="right")
    table.add_column("in/out", justify="right")
    table.add_column("cost", justify="right")
    table.add_column("time", justify="right")
    table.add_column("error", style="red")

    for result in report["tasks"]:
        usage = result["usage"]
        table.add_row(
            result["id"],
            result["baseline"],
            str(result.get("run", 0)),
            "yes" if result["passed"] else "no",
            str(result["tool_calls"]),
            f"{usage.get('input_tokens', 0)}/{usage.get('output_tokens', 0)}",
            f"${result['cost_usd']:.4f}",
            f"{result['duration_s']:.1f}s",
            (result["error"] or "")[:40],
        )

    console.print(table)
    for baseline, summary in report["baselines"].items():
        if not summary:
            console.print(f"[bold]{baseline}[/] no tasks")
            continue
        runs = summary.get("runs", summary["tasks"])
        console.print(
            f"[bold]{baseline}[/] pass@1 "
            f"{summary['passed']}/{runs} "
            f"({summary['pass_at_1']:.0%}), "
            f"pass@{summary.get('runs_per_task', 1):g} "
            f"({summary.get('pass_at_k', summary['pass_at_1']):.0%}), "
            f"{summary['avg_tool_calls']} calls/task, "
            f"approvals {summary.get('avg_approvals', 0)}, "
            f"blocked {summary.get('avg_blocked', 0)}, "
            f"${summary['cost_usd']:.4f}, "
            f"{summary['wall_time_s']:.1f}s"
        )
