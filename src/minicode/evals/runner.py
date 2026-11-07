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
from typing import Any

from rich.console import Console
from rich.table import Table

PROJECT_ROOT = Path(__file__).resolve().parents[3]
EVALS_DIR = Path(
    os.environ.get("MINICODE_EVALS_DIR", PROJECT_ROOT / "evals")
).expanduser()
TASKS_DIR = EVALS_DIR / "tasks"
SUITES_DIR = EVALS_DIR / "suites"
PRICING_FILE = EVALS_DIR / "pricing.toml"
DEFAULT_SUITE = "smoke"


@dataclass(frozen=True)
class Task:
    id: str
    path: Path
    category: str
    prompt_file: Path
    timeout_seconds: int
    max_tool_calls: int
    hidden_tests: Path | None
    verify_command: str | None
    verify_script: Path | None


def load_task(path: Path) -> Task:
    data = tomllib.loads((path / "task.toml").read_text(encoding="utf-8"))
    task_id = str(data.get("id") or path.name)
    hidden = data.get("hidden_tests")
    verify_script = data.get("verify_script")
    return Task(
        id=task_id,
        path=path,
        category=str(data.get("category", "general")),
        prompt_file=path / str(data.get("prompt_file", "prompt.md")),
        timeout_seconds=int(data.get("timeout_seconds", 180)),
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
    return (
        usage.get("input_tokens", 0) * prices.get("input_per_million", 0.0)
        + usage.get("output_tokens", 0) * prices.get("output_per_million", 0.0)
    ) / 1_000_000


def verification_env(workspace: Path) -> dict[str, str]:
    env = dict(os.environ)
    old = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(workspace) if not old else f"{workspace}{os.pathsep}{old}"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def run_verify(task: Task, workspace: Path) -> tuple[bool, str]:
    if task.hidden_tests is not None:
        shutil.copytree(
            task.hidden_tests,
            workspace / "_hidden_tests",
            dirs_exist_ok=True,
        )

    if task.verify_script is not None:
        command = [sys.executable, str(task.verify_script), str(workspace)]
    else:
        raw = task.verify_command or "python -m pytest -q"
        command = shlex.split(raw)
        if command and command[0] in {"python", "python3"}:
            command[0] = sys.executable

    try:
        proc = subprocess.run(
            command,
            cwd=workspace,
            env=verification_env(workspace),
            capture_output=True,
            text=True,
            timeout=task.timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return False, "verification timed out"
    except OSError as exc:
        return False, f"verification failed to start: {exc}"

    output = (proc.stdout + "\n" + proc.stderr).strip()
    return proc.returncode == 0, output[-4000:]


def run_worker(
    task: Task, workspace: Path, model: str | None, baseline: str
) -> tuple[dict[str, Any], str]:
    output_file = workspace.parent / "worker.json"
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
    if model:
        command.extend(["--model", model])

    try:
        proc = subprocess.run(
            command,
            cwd=workspace,
            env=verification_env(workspace),
            capture_output=True,
            text=True,
            timeout=task.timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return (
            {
                "ok": False,
                "error": f"task timed out after {task.timeout_seconds}s",
                "tool_calls": 0,
                "usage": {},
                "duration_s": float(task.timeout_seconds),
            },
            "",
        )

    if not output_file.exists():
        return (
            {
                "ok": False,
                "error": "worker produced no result",
                "tool_calls": 0,
                "usage": {},
                "duration_s": 0.0,
            },
            (proc.stdout + "\n" + proc.stderr).strip(),
        )
    return json.loads(output_file.read_text(encoding="utf-8")), ""


def run_task(
    task: Task,
    *,
    work_root: Path,
    model: str | None,
    baseline: str,
    pricing: dict[str, dict[str, float]],
) -> dict[str, Any]:
    task_root = work_root / f"{task.id}-{baseline}"
    workspace = task_root / "workspace"
    task_root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(task.path / "fixture", workspace)

    started = time.perf_counter()
    worker, worker_output = run_worker(task, workspace, model, baseline)
    verify_ok = False
    verify_output = ""
    if worker.get("ok"):
        verify_ok, verify_output = run_verify(task, workspace)

    passed = bool(worker.get("ok")) and verify_ok
    model_name = model or os.getenv("MINICODE_MODEL", "")
    result = {
        "id": task.id,
        "category": task.category,
        "baseline": baseline,
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
    }
    if not passed and not result["error"]:
        result["error"] = "verification failed"
    return result


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        return {}
    passed = sum(1 for result in results if result["passed"])
    usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    for result in results:
        for key, value in result["usage"].items():
            if key in usage:
                usage[key] += int(value)
    return {
        "tasks": len(results),
        "passed": passed,
        "pass_at_1": round(passed / len(results), 4),
        "avg_tool_calls": round(
            sum(result["tool_calls"] for result in results) / len(results), 2
        ),
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
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
    keep: bool = False,
) -> dict[str, Any]:
    tasks = load_suite(suite)
    if task_ids:
        wanted = set(task_ids)
        tasks = [task for task in tasks if task.id in wanted]
        missing = wanted - {task.id for task in tasks}
        if missing:
            raise ValueError(f"unknown task(s): {', '.join(sorted(missing))}")

    pricing = load_pricing()
    started_at = datetime.now().astimezone().isoformat(timespec="seconds")
    work_root = Path(tempfile.mkdtemp(prefix="minicode-evals-"))
    results: list[dict[str, Any]] = []

    try:
        for baseline in baselines:
            for task in tasks:
                result = run_task(
                    task,
                    work_root=work_root,
                    model=model,
                    baseline=baseline,
                    pricing=pricing,
                )
                results.append(result)
    finally:
        if not keep:
            shutil.rmtree(work_root, ignore_errors=True)

    by_baseline = {
        baseline: summarize([r for r in results if r["baseline"] == baseline])
        for baseline in baselines
    }
    return {
        "suite": suite,
        "model": model or os.getenv("MINICODE_MODEL", ""),
        "started_at": started_at,
        "baselines": by_baseline,
        "tasks": results,
        "work_dir": str(work_root) if keep else None,
    }


def print_report(report: dict[str, Any]) -> None:
    console = Console()
    table = Table(title=f"MiniCode evals: {report['suite']}")
    table.add_column("task", style="bold")
    table.add_column("baseline")
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
            "yes" if result["passed"] else "no",
            str(result["tool_calls"]),
            f"{usage.get('input_tokens', 0)}/{usage.get('output_tokens', 0)}",
            f"${result['cost_usd']:.4f}",
            f"{result['duration_s']:.1f}s",
            (result["error"] or "")[:40],
        )

    console.print(table)
    for baseline, summary in report["baselines"].items():
        console.print(
            f"[bold]{baseline}[/] pass@1 "
            f"{summary['passed']}/{summary['tasks']} "
            f"({summary['pass_at_1']:.0%}), "
            f"{summary['avg_tool_calls']} calls/task, "
            f"${summary['cost_usd']:.4f}, "
            f"{summary['wall_time_s']:.1f}s"
        )
