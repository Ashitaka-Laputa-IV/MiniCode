from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.base import empty_checkpoint
from langgraph.checkpoint.sqlite import SqliteSaver

from minicode.evals import recovery
from minicode.evals.baselines import resolve_baseline
from minicode.evals.recovery import (
    EXPECTED_RESULT,
    inspect_checkpoint,
    load_recovery_tasks,
    run_recovery_case,
)
from minicode.evals.trace import Trace
from minicode.evals.worker import run_minicode


def write_checkpoint(
    db_path: Path,
    thread_id: str,
    messages: list[Any],
) -> None:
    conn = sqlite3.connect(db_path)
    try:
        saver = SqliteSaver(conn)
        config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
        checkpoint = empty_checkpoint()
        checkpoint["channel_values"]["messages"] = messages
        saved = saver.put(config, checkpoint, {"source": "loop", "step": 0}, {"messages": "1"})
        pending = [
            ("messages", [message])
            for message in messages
            if getattr(message, "type", None) == "tool"
        ]
        if pending:
            saver.put_writes(saved, pending, "task-1")
        conn.commit()
    finally:
        conn.close()


def write_trace(path: Path, *, tool_calls: int = 1) -> None:
    with Trace(path) as trace:
        for index in range(tool_calls):
            trace.record(
                "tool_call",
                id=f"call-{index}",
                name="write_file",
                args={"file_path": "/result.txt"},
            )


def ai_message(message_id: str = "ai-1") -> AIMessage:
    return AIMessage(
        content="",
        id=message_id,
        tool_calls=[
            {
                "name": "write_file",
                "args": {"file_path": "/result.txt", "content": EXPECTED_RESULT},
                "id": "call-write",
            }
        ],
    )


def tool_message(message_id: str = "tool-1") -> ToolMessage:
    return ToolMessage(
        content="Updated file /result.txt",
        id=message_id,
        tool_call_id="call-write",
        name="write_file",
    )


class RecoveryScriptedModel(BaseChatModel):
    """Offline model: request the gated write, then answer after the resume."""

    final: bool = False

    @property
    def _llm_type(self) -> str:
        return "recovery-scripted"

    def bind_tools(self, tools: Any, **kwargs: Any) -> RecoveryScriptedModel:
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        if self.final:
            message = AIMessage(content="done")
        else:
            message = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "write_file",
                        "args": {"file_path": "/result.txt", "content": EXPECTED_RESULT},
                        "id": "call-write",
                    }
                ],
            )
        return ChatResult(generations=[ChatGeneration(message=message)])


def test_recovery_suite_loads_task() -> None:
    tasks = load_recovery_tasks()

    assert [task.id for task in tasks] == ["recovery-write"]
    task = tasks[0]
    assert task.category == "recovery"
    assert (task.path / "fixture").is_dir()
    prompt = task.prompt_file.read_text(encoding="utf-8")
    assert "result.txt" in prompt
    assert EXPECTED_RESULT in prompt


def test_inspect_checkpoint_requires_existing_thread(tmp_path: Path) -> None:
    missing = inspect_checkpoint(tmp_path / "missing.sqlite", "thread")
    assert missing["checkpoint_exists"] is False
    assert missing["tool_messages"] == 0

    db = tmp_path / "checkpoint.sqlite"
    write_checkpoint(db, "other-thread", [ai_message()])
    wrong_thread = inspect_checkpoint(db, "thread")
    assert wrong_thread["checkpoint_exists"] is False


def test_inspect_checkpoint_counts_tool_messages(tmp_path: Path) -> None:
    db = tmp_path / "checkpoint.sqlite"
    write_checkpoint(db, "thread", [ai_message(), tool_message()])

    info = inspect_checkpoint(db, "thread")

    assert info["checkpoint_exists"] is True
    assert info["checkpoint_count"] == 1
    assert info["tool_messages"] == 1
    assert info["repeated_tool_calls"] is False


def test_inspect_checkpoint_detects_repeated_tool_calls(tmp_path: Path) -> None:
    db = tmp_path / "checkpoint.sqlite"
    write_checkpoint(
        db,
        "thread",
        [ai_message(), tool_message("tool-1"), tool_message("tool-2")],
    )

    info = inspect_checkpoint(db, "thread")

    assert info["tool_messages"] == 2
    assert info["repeated_tool_calls"] is True


def test_real_checkpoint_pause_and_resume(tmp_path: Path) -> None:
    db = tmp_path / "checkpoint.sqlite"
    baseline = resolve_baseline("minicode-ask")
    thread_id = "thread-real"

    phase1 = run_minicode(
        "write result.txt",
        tmp_path,
        RecoveryScriptedModel(),
        10,
        baseline=baseline,
        checkpoint_db=db,
        thread_id=thread_id,
        pause_on_interrupt=True,
    )

    assert phase1["interrupted"] is True
    assert phase1["interrupt_id"]
    assert phase1["thread_id"] == thread_id
    assert not (tmp_path / "result.txt").exists()
    before = inspect_checkpoint(db, thread_id)
    assert before["checkpoint_exists"] is True
    assert before["tool_messages"] == 0

    phase2 = run_minicode(
        "write result.txt",
        tmp_path,
        RecoveryScriptedModel(final=True),
        10,
        baseline=baseline,
        checkpoint_db=db,
        thread_id=thread_id,
        resume_decisions={"decisions": [{"type": "approve"}]},
    )

    assert phase2["interrupted"] is False
    assert phase2["final"] == "done"
    assert (tmp_path / "result.txt").read_text(encoding="utf-8") == EXPECTED_RESULT
    after = inspect_checkpoint(db, thread_id)
    assert after["checkpoint_exists"] is True
    assert after["tool_messages"] == 1
    assert after["repeated_tool_calls"] is False


def test_real_disable_checkpoint_control_keeps_no_persistent_state(tmp_path: Path) -> None:
    db = tmp_path / "checkpoint.sqlite"
    baseline = resolve_baseline("minicode-ask")

    phase1 = run_minicode(
        "write result.txt",
        tmp_path,
        RecoveryScriptedModel(),
        10,
        baseline=baseline,
        checkpoint_db=db,
        thread_id="thread-control",
        pause_on_interrupt=True,
        disable_checkpoint=True,
    )

    assert phase1["interrupted"] is True
    assert phase1["thread_id"] is None
    assert phase1["checkpoint_db"] is None
    assert not db.exists()
    assert not (tmp_path / "result.txt").exists()

    phase2 = run_minicode(
        "write result.txt",
        tmp_path,
        RecoveryScriptedModel(final=True),
        10,
        baseline=baseline,
        checkpoint_db=db,
        thread_id="thread-control",
        resume_decisions={"decisions": [{"type": "approve"}]},
        disable_checkpoint=True,
    )

    assert phase2["interrupted"] is False
    assert phase2["thread_id"] is None
    assert phase2["checkpoint_db"] is None
    assert not db.exists()


def make_worker(
    monkeypatch: pytest.MonkeyPatch,
    *,
    recovery_ok: bool = True,
    control_recovers: bool = False,
):
    """Fake worker that persists checkpoints and simulates both phases."""

    def fake_worker(
        task,
        workspace,
        model,
        baseline,
        *,
        run_index=0,
        trace_file=None,
        checkpoint_db=None,
        thread_id=None,
        pause_on_interrupt=False,
        resume_approve=False,
        disable_checkpoint=False,
        output_name=None,
    ):
        assert baseline == "minicode-ask"
        if trace_file is not None:
            write_trace(trace_file)
        usage = {"input_tokens": 10, "output_tokens": 2}
        writes_checkpoint = not disable_checkpoint or control_recovers
        if pause_on_interrupt:
            if writes_checkpoint:
                write_checkpoint(checkpoint_db, thread_id, [ai_message()])
            return (
                {
                    "ok": True,
                    "interrupted": True,
                    "interrupt_id": "interrupt-1",
                    "pending_actions": [
                        {"name": "write_file", "args": {"file_path": "/result.txt"}}
                    ],
                    "final": "",
                    "tool_calls": 1,
                    "usage": usage,
                    "duration_s": 0.05,
                    "trace_summary": {"tool_calls": 1},
                },
                "",
            )
        if resume_approve:
            if writes_checkpoint and recovery_ok:
                write_checkpoint(checkpoint_db, thread_id, [ai_message(), tool_message()])
            (workspace / "result.txt").write_text(f"{EXPECTED_RESULT}\n", encoding="utf-8")
            return (
                {
                    "ok": True,
                    "interrupted": False,
                    "interrupt_id": None,
                    "pending_actions": [],
                    "final": "done",
                    "tool_calls": 1,
                    "usage": usage,
                    "duration_s": 0.05,
                    "trace_summary": {"tool_calls": 1},
                },
                "",
            )
        raise AssertionError("unexpected worker call")

    monkeypatch.setattr(recovery, "run_worker", fake_worker)


def test_run_recovery_case_succeeds_and_control_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    task = load_recovery_tasks()[0]
    make_worker(monkeypatch)

    result = run_recovery_case(task, work_root=tmp_path, model=None)

    assert result["passed"] is True
    assert result["recovery_success"] is True
    assert result["phase1_interrupted"] is True
    assert result["phase1_interrupt_id"] == "interrupt-1"
    assert result["phase1_actions"] == ["write_file"]
    assert result["phase2_completed"] is True
    assert result["checkpoint_exists"] is True
    assert result["tool_messages"] == 1
    assert result["repeated_tool_calls"] is False
    assert result["final_completion"] is True
    assert result["final_content"] == EXPECTED_RESULT
    assert result["no_checkpoint_control_failed"] is True
    assert result["no_checkpoint_control"]["checkpoint_exists"] is False
    assert result["no_checkpoint_control"]["fresh_execution"] is True
    assert result["no_checkpoint_control"]["resumed"] is False
    assert result["usage"] == {"input_tokens": 40, "output_tokens": 8}
    assert result["control_usage"] == {"input_tokens": 20, "output_tokens": 4}


def test_run_recovery_case_fails_without_tool_messages(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    task = load_recovery_tasks()[0]
    make_worker(monkeypatch, recovery_ok=False)

    result = run_recovery_case(task, work_root=tmp_path, model=None)

    assert result["passed"] is False
    assert result["recovery_success"] is False
    assert result["checkpoint_exists"] is True
    assert result["tool_messages"] == 0
    assert result["error"] == "recovery verification failed"


def test_run_recovery_case_fails_when_control_recovers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    task = load_recovery_tasks()[0]
    make_worker(monkeypatch, control_recovers=True)

    result = run_recovery_case(task, work_root=tmp_path, model=None)

    assert result["recovery_success"] is True
    assert result["no_checkpoint_control_failed"] is False
    assert result["no_checkpoint_control"]["recovered"] is True
    assert result["passed"] is False
    assert result["error"] == "no-checkpoint control unexpectedly recovered"


def test_run_recovery_suite_filters_and_reports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = load_recovery_tasks()[0]
    monkeypatch.setattr(recovery, "load_recovery_tasks", lambda: [task])
    monkeypatch.setattr(
        recovery,
        "run_recovery_case",
        lambda *args, **kwargs: {
            "id": task.id,
            "category": task.category,
            "baseline": "minicode-ask",
            "run": kwargs.get("run_index", 0),
            "passed": True,
            "recovery_success": True,
            "phase1_interrupted": True,
            "phase2_completed": True,
            "checkpoint_exists": True,
            "final_completion": True,
            "repeated_tool_calls": False,
            "no_checkpoint_control_failed": True,
            "tool_messages": 1,
            "usage": {},
            "cost_usd": 0.0,
            "duration_s": 0.1,
            "error": None,
        },
    )

    report = recovery.run_recovery_suite(model=None, runs=1, keep=False)

    assert report["suite"] == "recovery"
    assert report["baseline"] == "minicode-ask"
    assert report["summary"]["total"] == 1
    assert report["summary"]["passed"] == 1
    assert report["summary"]["recovery_rate"] == 1.0
    assert report["summary"]["tool_messages"] == 1
    assert report["work_dir"] is None

    with pytest.raises(ValueError, match="unknown recovery task"):
        recovery.run_recovery_suite(model=None, task_ids=["missing"])


def test_run_recovery_suite_wraps_exceptions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = load_recovery_tasks()[0]
    monkeypatch.setattr(recovery, "load_recovery_tasks", lambda: [task])

    def boom(*args, **kwargs):
        raise RuntimeError("worker crashed")

    monkeypatch.setattr(recovery, "run_recovery_case", boom)

    report = recovery.run_recovery_suite(model=None, runs=1, keep=False)

    assert report["summary"]["failed"] == 1
    assert report["tasks"][0]["error"] == "RuntimeError: worker crashed"
    assert report["tasks"][0]["passed"] is False


def test_print_recovery_report() -> None:
    report = {
        "suite": "recovery",
        "tasks": [
            {
                "id": "recovery-write",
                "phase1_interrupted": True,
                "phase2_completed": True,
                "checkpoint_exists": True,
                "tool_messages": 1,
                "repeated_tool_calls": False,
                "final_completion": True,
                "no_checkpoint_control_failed": True,
                "passed": True,
                "error": None,
            }
        ],
        "summary": {
            "passed": 1,
            "total": 1,
            "pass_rate": 1.0,
            "recovery_success": 1,
            "recovery_rate": 1.0,
            "phase1_interrupted": 1,
            "checkpoint_exists": 1,
            "tool_messages": 1,
            "repeated_tool_calls": 0,
            "no_checkpoint_control_failed": 1,
        },
    }

    recovery.print_recovery_report(report)
