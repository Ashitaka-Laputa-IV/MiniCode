"""Recovery evaluation suite for interrupted MiniCode runs.

The suite runs a two-phase HITL workflow with ``minicode-ask``:

1. phase 1 is interrupted at the first approval request and exits without
   resuming;
2. phase 2 opens the same SQLite checkpoint and thread, approves the pending
   action, and must finish the task.

A no-checkpoint control repeats the same flow with ``disable_checkpoint=True``.
It is expected to fail to recover because there is no persisted graph state.
Like the security suite, this is a measurement tool, not a PR gate.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.sqlite import SqliteSaver
from rich.console import Console
from rich.table import Table

from .runner import Task, cost_for, load_pricing, load_suite, run_worker
from .trace import read_trace, summarize_events

RECOVERY_SUITE = "recovery"
RECOVERY_BASELINE = "minicode-ask"
EXPECTED_RESULT = "RECOVERY_OK"


def load_recovery_tasks() -> list[Task]:
    """Load ``evals/suites/recovery.toml`` and its task fixtures."""
    tasks = load_suite(RECOVERY_SUITE)
    if not tasks:
        raise ValueError("recovery suite has no tasks")
    for task in tasks:
        if not (task.path / "fixture").is_dir():
            raise FileNotFoundError(f"recovery task fixture not found: {task.path / 'fixture'}")
    return tasks


def _message_identity(message: Any) -> str:
    """Return a stable key so replayed checkpoint messages are counted once."""
    message_id = getattr(message, "id", None)
    if message_id:
        return f"id:{message_id}"
    payload = repr(message).encode("utf-8", errors="replace")
    return f"hash:{hashlib.sha256(payload).hexdigest()}"


def _add_messages(bucket: dict[str, Any], messages: Any) -> None:
    if not isinstance(messages, list):
        return
    for message in messages:
        bucket.setdefault(_message_identity(message), message)


def _collect_checkpoint_messages(bucket: dict[str, Any], checkpoint_tuple: Any) -> None:
    """Collect message channels from a checkpoint and its pending writes.

    LangGraph stores channel deltas rather than the whole state in every
    checkpoint, so ``get_tuple`` alone can miss earlier ToolMessages. Walking
    ``SqliteSaver.list`` and merging ``channel_values`` with ``pending_writes``
    reconstructs the thread's message history from persisted checkpoints.
    """
    checkpoint = getattr(checkpoint_tuple, "checkpoint", None)
    if isinstance(checkpoint, dict):
        channel_values = checkpoint.get("channel_values")
        if isinstance(channel_values, dict):
            _add_messages(bucket, channel_values.get("messages"))
    pending_writes = getattr(checkpoint_tuple, "pending_writes", None) or []
    for write in pending_writes:
        if isinstance(write, tuple) and len(write) >= 3 and write[1] == "messages":
            _add_messages(bucket, write[2])


def _tool_call_signature(call: dict[str, Any]) -> str:
    args = json.dumps(call.get("args", {}), ensure_ascii=False, sort_keys=True, default=str)
    return f"{call.get('name', 'tool')}:{args}"


def inspect_checkpoint(db_path: str | Path, thread_id: str) -> dict[str, Any]:
    """Verify a thread checkpoint and count persisted ToolMessages."""
    result: dict[str, Any] = {
        "checkpoint_exists": False,
        "checkpoint_count": 0,
        "message_count": 0,
        "tool_messages": 0,
        "repeated_tool_calls": False,
    }
    path = Path(db_path)
    if not path.exists():
        return result

    conn = sqlite3.connect(path, check_same_thread=False)
    try:
        saver = SqliteSaver(conn)
        config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
        latest = saver.get_tuple(config)
        if latest is None:
            return result
        result["checkpoint_exists"] = True

        messages: dict[str, Any] = {}
        checkpoint_count = 0
        for checkpoint_tuple in saver.list(config):
            checkpoint_count += 1
            _collect_checkpoint_messages(messages, checkpoint_tuple)
        result["checkpoint_count"] = checkpoint_count
        result["message_count"] = len(messages)

        tool_messages = [
            message for message in messages.values() if getattr(message, "type", None) == "tool"
        ]
        result["tool_messages"] = len(tool_messages)
        tool_call_ids = Counter(
            str(getattr(message, "tool_call_id", ""))
            for message in tool_messages
            if getattr(message, "tool_call_id", None)
        )
        signatures: Counter[str] = Counter()
        for message in messages.values():
            if getattr(message, "type", None) != "ai":
                continue
            for call in getattr(message, "tool_calls", None) or []:
                if isinstance(call, dict):
                    signatures[_tool_call_signature(call)] += 1
        result["repeated_tool_calls"] = any(count > 1 for count in tool_call_ids.values()) or any(
            count > 1 for count in signatures.values()
        )
        return result
    finally:
        conn.close()


def _read_result(workspace: Path) -> str | None:
    try:
        return (workspace / "result.txt").read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return None


def _read_trace_summary(path: Path) -> dict[str, Any]:
    return summarize_events(read_trace(path))


def _phase1_flags(worker: dict[str, Any]) -> tuple[bool, list[str]]:
    interrupted = bool(worker.get("interrupted")) and bool(worker.get("interrupt_id"))
    actions = [
        str(action.get("name", ""))
        for action in worker.get("pending_actions") or []
        if isinstance(action, dict)
    ]
    return interrupted, actions


def _run_control(
    task: Task,
    *,
    work_root: Path,
    model: str | None,
    run_index: int,
) -> dict[str, Any]:
    """Repeat the two-phase flow without a persistent checkpointer."""
    task_root = work_root / f"{task.id}-{run_index}-control"
    workspace = task_root / "workspace"
    task_root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(task.path / "fixture", workspace)
    checkpoint_db = task_root / "checkpoint.sqlite"
    thread_id = f"{task.id}-{run_index}-control"

    phase1, _ = run_worker(
        task,
        workspace,
        model,
        RECOVERY_BASELINE,
        run_index=run_index,
        trace_file=task_root / "phase1-trace.jsonl",
        checkpoint_db=checkpoint_db,
        thread_id=thread_id,
        pause_on_interrupt=True,
        disable_checkpoint=True,
        output_name=f"worker-control-phase1-{run_index}.json",
    )
    phase1_interrupted, _ = _phase1_flags(phase1)

    phase2: dict[str, Any] = {
        "ok": False,
        "interrupted": False,
        "error": "control phase 1 did not interrupt",
    }
    if phase1_interrupted:
        phase2, _ = run_worker(
            task,
            workspace,
            model,
            RECOVERY_BASELINE,
            run_index=run_index,
            trace_file=task_root / "phase2-trace.jsonl",
            checkpoint_db=checkpoint_db,
            thread_id=thread_id,
            resume_approve=True,
            pause_on_interrupt=False,
            disable_checkpoint=True,
            output_name=f"worker-control-phase2-{run_index}.json",
        )

    checkpoint_exists = bool(inspect_checkpoint(checkpoint_db, thread_id)["checkpoint_exists"])
    phase2_completed = bool(phase2.get("ok")) and not bool(phase2.get("interrupted"))
    final_content = _read_result(workspace)
    control_usage: dict[str, int] = {}
    for source in (phase1.get("usage") or {}, phase2.get("usage") or {}):
        for field, value in source.items():
            if isinstance(value, (int, float)):
                control_usage[field] = control_usage.get(field, 0) + int(value)
    # Without a checkpoint, a fresh execution may still produce result.txt, but
    # it cannot resume the interrupted thread. Count recovery only when the
    # checkpoint exists and phase 2 completed.
    resumed = phase2_completed and checkpoint_exists
    recovered = resumed and final_content == EXPECTED_RESULT
    return {
        "phase1_interrupted": phase1_interrupted,
        "phase2_completed": phase2_completed,
        "checkpoint_exists": checkpoint_exists,
        "final_content": final_content,
        "fresh_execution": final_content == EXPECTED_RESULT and not checkpoint_exists,
        "resumed": resumed,
        "recovered": recovered,
        "no_checkpoint_control_failed": bool(
            phase1_interrupted and not checkpoint_exists and not recovered
        ),
        "usage": control_usage,
        "error": phase2.get("error"),
    }


def run_recovery_case(
    task: Task,
    *,
    work_root: Path,
    model: str | None,
    run_index: int = 0,
) -> dict[str, Any]:
    """Run one interrupted/resumed task and its no-checkpoint control."""
    started = time.perf_counter()
    task_root = work_root / f"{task.id}-{run_index}"
    workspace = task_root / "workspace"
    task_root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(task.path / "fixture", workspace)
    checkpoint_db = task_root / "checkpoint.sqlite"
    thread_id = f"{task.id}-{run_index}"

    phase1, phase1_output = run_worker(
        task,
        workspace,
        model,
        RECOVERY_BASELINE,
        run_index=run_index,
        trace_file=task_root / "phase1-trace.jsonl",
        checkpoint_db=checkpoint_db,
        thread_id=thread_id,
        pause_on_interrupt=True,
        output_name=f"worker-phase1-{run_index}.json",
    )
    phase1_interrupted, phase1_actions = _phase1_flags(phase1)

    phase2: dict[str, Any] = {
        "ok": False,
        "interrupted": False,
        "error": "phase 1 did not interrupt",
    }
    phase2_output = ""
    if phase1_interrupted:
        phase2, phase2_output = run_worker(
            task,
            workspace,
            model,
            RECOVERY_BASELINE,
            run_index=run_index,
            trace_file=task_root / "phase2-trace.jsonl",
            checkpoint_db=checkpoint_db,
            thread_id=thread_id,
            resume_approve=True,
            pause_on_interrupt=False,
            output_name=f"worker-phase2-{run_index}.json",
        )
    phase2_completed = bool(phase2.get("ok")) and not bool(phase2.get("interrupted"))
    final_content = _read_result(workspace)
    final_file_ok = final_content == EXPECTED_RESULT
    final_completion = phase2_completed and bool(str(phase2.get("final") or "").strip())
    checkpoint = inspect_checkpoint(checkpoint_db, thread_id)
    checkpoint_exists = bool(checkpoint["checkpoint_exists"])
    tool_messages = int(checkpoint["tool_messages"])
    repeated_tool_calls = bool(checkpoint["repeated_tool_calls"])
    recovery_success = bool(
        phase1_interrupted
        and phase2_completed
        and final_completion
        and final_file_ok
        and checkpoint_exists
        and tool_messages >= 1
        and not repeated_tool_calls
    )

    control = _run_control(task, work_root=work_root, model=model, run_index=run_index)
    no_checkpoint_control_failed = bool(control["no_checkpoint_control_failed"])
    passed = recovery_success and no_checkpoint_control_failed

    phase1_usage = dict(phase1.get("usage") or {})
    phase2_usage = dict(phase2.get("usage") or {})
    control_usage = dict(control.get("usage") or {})
    usage: dict[str, int] = {}
    for source in (phase1_usage, phase2_usage, control_usage):
        for field, value in source.items():
            if isinstance(value, (int, float)):
                usage[field] = usage.get(field, 0) + int(value)

    model_name = model or os.getenv("MINICODE_MODEL", "")
    trace_summary = {
        "phase1": phase1.get("trace_summary")
        or _read_trace_summary(task_root / "phase1-trace.jsonl"),
        "phase2": phase2.get("trace_summary")
        or _read_trace_summary(task_root / "phase2-trace.jsonl"),
    }
    error = phase2.get("error") if not phase2_completed else None
    if not phase1_interrupted:
        error = phase1.get("error") or "phase 1 did not interrupt"
    if not no_checkpoint_control_failed and not error:
        error = str(control.get("error") or "no-checkpoint control unexpectedly recovered")
    if not recovery_success and not error:
        error = "recovery verification failed"

    return {
        "id": task.id,
        "category": task.category,
        "baseline": RECOVERY_BASELINE,
        "run": run_index,
        "passed": passed,
        "recovery_success": recovery_success,
        "phase1_interrupted": phase1_interrupted,
        "phase1_interrupt_id": phase1.get("interrupt_id"),
        "phase1_actions": phase1_actions,
        "phase2_completed": phase2_completed,
        "checkpoint_exists": checkpoint_exists,
        "checkpoint_count": int(checkpoint["checkpoint_count"]),
        "message_count": int(checkpoint["message_count"]),
        "tool_messages": tool_messages,
        "repeated_tool_calls": repeated_tool_calls,
        "final_completion": final_completion,
        "final_file_ok": final_file_ok,
        "final_content": final_content,
        "no_checkpoint_control": control,
        "no_checkpoint_control_failed": no_checkpoint_control_failed,
        "thread_id": thread_id,
        "checkpoint_db": str(checkpoint_db),
        "error": error,
        "phase1_error": phase1.get("error"),
        "phase2_error": phase2.get("error"),
        "phase1_worker_output": phase1_output[-1000:],
        "phase2_worker_output": phase2_output[-1000:],
        "trace_summary": trace_summary,
        "usage": usage,
        "control_usage": control_usage,
        "cost_usd": cost_for(str(model_name), usage, load_pricing()),
        "duration_s": round(time.perf_counter() - started, 3),
    }


def summarize_recovery(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate recovery results into rates and counts."""
    if not results:
        return {}

    def count(key: str) -> int:
        return sum(1 for result in results if bool(result.get(key)))

    total = len(results)
    passed = count("passed")
    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "recovery_success": count("recovery_success"),
        "phase1_interrupted": count("phase1_interrupted"),
        "phase2_completed": count("phase2_completed"),
        "checkpoint_exists": count("checkpoint_exists"),
        "final_completion": count("final_completion"),
        "repeated_tool_calls": count("repeated_tool_calls"),
        "no_checkpoint_control_failed": count("no_checkpoint_control_failed"),
        "tool_messages": sum(int(result.get("tool_messages", 0)) for result in results),
        "pass_rate": round(passed / total, 4),
        "recovery_rate": round(count("recovery_success") / total, 4),
        "control_failure_rate": round(count("no_checkpoint_control_failed") / total, 4),
        "cost_usd": round(sum(float(result.get("cost_usd", 0.0)) for result in results), 6),
        "wall_time_s": round(sum(float(result.get("duration_s", 0.0)) for result in results), 2),
    }


def _failed_result(task: Task, error: str, run_index: int) -> dict[str, Any]:
    return {
        "id": task.id,
        "category": task.category,
        "baseline": RECOVERY_BASELINE,
        "run": run_index,
        "passed": False,
        "recovery_success": False,
        "phase1_interrupted": False,
        "phase1_interrupt_id": None,
        "phase1_actions": [],
        "phase2_completed": False,
        "checkpoint_exists": False,
        "checkpoint_count": 0,
        "message_count": 0,
        "tool_messages": 0,
        "repeated_tool_calls": False,
        "final_completion": False,
        "final_file_ok": False,
        "final_content": None,
        "no_checkpoint_control": {},
        "no_checkpoint_control_failed": False,
        "thread_id": None,
        "checkpoint_db": None,
        "error": str(error),
        "phase1_error": None,
        "phase2_error": None,
        "phase1_worker_output": "",
        "phase2_worker_output": "",
        "trace_summary": {},
        "usage": {},
        "control_usage": {},
        "cost_usd": 0.0,
        "duration_s": 0.0,
    }


def run_recovery_suite(
    *,
    model: str | None,
    task_ids: list[str] | None = None,
    runs: int = 1,
    keep: bool = False,
) -> dict[str, Any]:
    """Run the recovery suite with ``minicode-ask`` and return a report."""
    if runs < 1:
        raise ValueError("runs must be at least 1")
    tasks = load_recovery_tasks()
    if task_ids:
        wanted = set(task_ids)
        tasks = [task for task in tasks if task.id in wanted]
        missing = wanted - {task.id for task in tasks}
        if missing:
            raise ValueError(f"unknown recovery task(s): {', '.join(sorted(missing))}")
    if not tasks:
        raise ValueError("recovery suite has no selected tasks")

    work_root = Path(tempfile.mkdtemp(prefix="minicode-recovery-"))
    results: list[dict[str, Any]] = []
    started_at = datetime.now().astimezone().isoformat(timespec="seconds")
    try:
        for run_index in range(runs):
            for task in tasks:
                try:
                    result = run_recovery_case(
                        task,
                        work_root=work_root,
                        model=model,
                        run_index=run_index,
                    )
                except Exception as exc:
                    result = _failed_result(task, f"{type(exc).__name__}: {exc}", run_index)
                result["run"] = run_index
                results.append(result)
    finally:
        if not keep:
            shutil.rmtree(work_root, ignore_errors=True)

    return {
        "suite": RECOVERY_SUITE,
        "model": model or os.getenv("MINICODE_MODEL", ""),
        "started_at": started_at,
        "runs": runs,
        "baseline": RECOVERY_BASELINE,
        "summary": summarize_recovery(results),
        "tasks": results,
        "work_dir": str(work_root) if keep else None,
    }


def print_recovery_report(report: dict[str, Any]) -> None:
    """Print a compact recovery table and aggregate metrics."""
    console = Console()
    table = Table(title=f"MiniCode recovery evals: {report['suite']}")
    table.add_column("task", style="bold")
    table.add_column("p1 int")
    table.add_column("p2 done")
    table.add_column("ckpt")
    table.add_column("tools", justify="right")
    table.add_column("repeat")
    table.add_column("final")
    table.add_column("control")
    table.add_column("pass")
    table.add_column("error", style="red")

    for result in report["tasks"]:
        table.add_row(
            result["id"],
            "yes" if result["phase1_interrupted"] else "no",
            "yes" if result["phase2_completed"] else "no",
            "yes" if result["checkpoint_exists"] else "no",
            str(result["tool_messages"]),
            "yes" if result["repeated_tool_calls"] else "no",
            "yes" if result["final_completion"] else "no",
            "failed" if result["no_checkpoint_control_failed"] else "no",
            "yes" if result["passed"] else "no",
            (result["error"] or "")[:40],
        )
    console.print(table)

    summary = report["summary"]
    console.print(
        f"[bold]recovery[/] pass {summary['passed']}/{summary['total']} "
        f"({summary['pass_rate']:.0%}), "
        f"recovered {summary['recovery_success']}/{summary['total']} "
        f"({summary['recovery_rate']:.0%}), "
        f"interrupted {summary['phase1_interrupted']}, "
        f"checkpoints {summary['checkpoint_exists']}, "
        f"tool messages {summary['tool_messages']}, "
        f"repeated calls {summary['repeated_tool_calls']}, "
        f"no-checkpoint control failed {summary['no_checkpoint_control_failed']}."
    )
