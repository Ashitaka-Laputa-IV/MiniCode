import json
import shutil
import subprocess
from pathlib import Path

import pytest

from minicode.evals import runner
from minicode.evals.runner import cost_for, load_suite, summarize, verification_env
from minicode.evals.trace import Trace


def test_smoke_suite_has_twenty_tasks() -> None:
    tasks = load_suite("smoke")
    assert len(tasks) == 20
    assert len({task.id for task in tasks}) == 20
    assert all((task.path / "prompt.md").exists() for task in tasks)
    assert all((task.path / "fixture").is_dir() for task in tasks)
    assert all(task.hidden_tests or task.verify_script for task in tasks)
    for task in tasks:
        if task.hidden_tests is not None:
            assert task.hidden_tests.is_dir()
        if task.verify_script is not None:
            assert task.verify_script.is_file()


def test_verify_env_excludes_secrets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret")
    env = verification_env(tmp_path)
    assert "DEEPSEEK_API_KEY" not in env
    assert str(tmp_path) in env["PYTHONPATH"]


def test_relative_evals_dir_is_resolved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import importlib

    import minicode.evals.runner as runner

    monkeypatch.setenv("MINICODE_EVALS_DIR", "evals")
    reloaded = importlib.reload(runner)
    try:
        assert reloaded.EVALS_DIR.is_absolute()
        task = reloaded.load_suite("smoke")[0]
        assert task.path.is_absolute()
        assert task.hidden_tests is None or task.hidden_tests.is_absolute()
        assert task.verify_script is None or task.verify_script.is_absolute()
    finally:
        monkeypatch.delenv("MINICODE_EVALS_DIR", raising=False)
        importlib.reload(runner)


def test_cost_uses_pricing() -> None:
    pricing = {
        "model": {
            "input_per_million": 1.0,
            "output_per_million": 2.0,
        }
    }
    usage = {"input_tokens": 1_000_000, "output_tokens": 500_000}
    assert cost_for("model", usage, pricing) == 2.0


def test_cost_uses_cached_input_price() -> None:
    pricing = {
        "model": {
            "input_per_million": 1.0,
            "output_per_million": 2.0,
            "cached_input_per_million": 0.1,
        }
    }
    usage = {
        "input_tokens": 1_000_000,
        "cached_input_tokens": 500_000,
        "output_tokens": 0,
    }
    assert cost_for("model", usage, pricing) == 0.55


def test_summarize() -> None:
    results = [
        {
            "passed": True,
            "tool_calls": 2,
            "usage": {"input_tokens": 10, "output_tokens": 5},
            "cost_usd": 0.01,
            "duration_s": 1.5,
        },
        {
            "passed": False,
            "tool_calls": 4,
            "usage": {"input_tokens": 20, "output_tokens": 10},
            "cost_usd": 0.02,
            "duration_s": 2.5,
        },
    ]
    summary = summarize(results)
    assert summary["tasks"] == 2
    assert summary["passed"] == 1
    assert summary["pass_at_1"] == 0.5
    assert summary["avg_tool_calls"] == 3.0
    assert summary["input_tokens"] == 30
    assert summary["cost_usd"] == 0.03
    assert summary["wall_time_s"] == 4.0


def test_summarize_pass_at_k_and_trace_metrics() -> None:
    results = [
        {
            "id": "a",
            "baseline": "minicode-yolo",
            "run": 0,
            "passed": True,
            "failure_reason": "passed",
            "tool_calls": 1,
            "usage": {},
            "cost_usd": 0.0,
            "duration_s": 1.0,
            "trace_summary": {"approvals": 1, "blocked": 0},
        },
        {
            "id": "a",
            "baseline": "minicode-yolo",
            "run": 1,
            "passed": False,
            "failure_reason": "loop",
            "tool_calls": 3,
            "usage": {},
            "cost_usd": 0.0,
            "duration_s": 1.0,
            "trace_summary": {"approvals": 0, "blocked": 0},
        },
        {
            "id": "a",
            "baseline": "minicode-yolo",
            "run": 2,
            "passed": True,
            "failure_reason": "passed",
            "tool_calls": 1,
            "usage": {},
            "cost_usd": 0.0,
            "duration_s": 1.0,
            "trace_summary": {"approvals": 2, "blocked": 1},
        },
        {
            "id": "b",
            "baseline": "minicode-yolo",
            "run": 0,
            "passed": False,
            "failure_reason": "timeout",
            "tool_calls": 0,
            "usage": {},
            "cost_usd": 0.0,
            "duration_s": 2.0,
            "trace_summary": {"approvals": 0, "blocked": 0},
        },
    ]

    summary = summarize(results)

    assert summary["tasks"] == 2
    assert summary["runs"] == 4
    assert summary["passed_tasks"] == 1
    assert summary["pass_at_1"] == 0.5
    assert summary["pass_at_k"] == 0.5
    assert summary["avg_approvals"] == 0.75
    assert summary["avg_blocked"] == 0.25
    assert summary["failure_counts"] == {"loop": 1, "timeout": 1}


@pytest.mark.parametrize("failure", ["timeout", "no-output", "bad-output"])
def test_run_worker_recovers_partial_trace(
    failure: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    task = load_suite("smoke")[0]
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    trace_file = tmp_path / "trace.jsonl"
    with Trace(trace_file) as trace:
        trace.record("usage", input_tokens=100, output_tokens=20, total_tokens=120)
        trace.record("tool_call", name="execute", args={"command": "pytest -q"})

    output_file = workspace.parent / "worker-0.json"

    def fake_run(*args, **kwargs):
        if failure == "timeout":
            raise subprocess.TimeoutExpired("worker", 1)
        if failure == "bad-output":
            output_file.write_text("{not json", encoding="utf-8")
        return subprocess.CompletedProcess([], 0, stdout="", stderr="")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    result, _ = runner.run_worker(
        task,
        workspace,
        None,
        "minicode-yolo",
        trace_file=trace_file,
    )

    assert result["ok"] is False
    assert result["tool_calls"] == 1
    assert result["usage"] == {
        "input_tokens": 100,
        "output_tokens": 20,
        "total_tokens": 120,
    }
    assert result["trace_summary"]["tool_calls"] == 1
    assert result["trace_summary"]["usage"] == result["usage"]
    assert result["trace_summary"]["ran_tests"] is True


def test_run_worker_forwards_recovery_flags(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    task = load_suite("smoke")[0]
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    captured: dict = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        output = Path(command[command.index("--output") + 1])
        output.write_text(
            json.dumps(
                {
                    "ok": True,
                    "interrupted": True,
                    "interrupt_id": "interrupt-1",
                    "thread_id": "thread-1",
                    "checkpoint_db": str(tmp_path / "checkpoint.sqlite"),
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess([], 0, stdout="", stderr="")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    result, _ = runner.run_worker(
        task,
        workspace,
        None,
        "minicode-ask",
        trace_file=tmp_path / "trace.jsonl",
        checkpoint_db=tmp_path / "checkpoint.sqlite",
        thread_id="thread-1",
        pause_on_interrupt=True,
        resume_approve=True,
        disable_checkpoint=True,
        output_name="worker-phase1-0.json",
    )

    command = captured["command"]
    assert "--pause-on-interrupt" in command
    assert "--resume-approve" in command
    assert "--disable-checkpoint" in command
    assert command[command.index("--thread") + 1] == "thread-1"
    assert command[command.index("--output") + 1].endswith("worker-phase1-0.json")
    assert result["interrupted"] is True
    assert result["interrupt_id"] == "interrupt-1"


def test_run_task_forwards_recovery_flags(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    task = load_suite("smoke")[0]
    captured: dict = {}

    def fake_worker(*args, **kwargs):
        captured.update(kwargs)
        return ({"ok": False, "error": "stopped", "trace_summary": {}}, "")

    monkeypatch.setattr(runner, "run_worker", fake_worker)

    runner.run_task(
        task,
        work_root=tmp_path,
        model=None,
        baseline="minicode-ask",
        run_index=0,
        pricing={},
        pause_on_interrupt=True,
        resume_approve=True,
        disable_checkpoint=True,
    )

    assert captured["pause_on_interrupt"] is True
    assert captured["resume_approve"] is True
    assert captured["disable_checkpoint"] is True


def test_run_task_classifies_permission_denied(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    task = load_suite("smoke")[0]

    def fake_worker(*args, **kwargs):
        return (
            {
                "ok": True,
                "error": None,
                "tool_calls": 1,
                "usage": {},
                "duration_s": 0.1,
                "trace_summary": {"blocked": 1, "ran_tests": False},
            },
            "",
        )

    monkeypatch.setattr(runner, "run_worker", fake_worker)
    monkeypatch.setattr(runner, "run_verify", lambda task, workspace: (False, "failed"))

    result = runner.run_task(
        task,
        work_root=tmp_path,
        model=None,
        baseline="minicode-ask",
        run_index=0,
        pricing={},
    )

    assert result["failure_reason"] == "permission_denied"


def test_run_task_preserves_worker_summary_when_verify_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    task = load_suite("smoke")[0]

    def fake_worker(*args, **kwargs):
        return (
            {
                "ok": True,
                "error": None,
                "tool_calls": 3,
                "usage": {"input_tokens": 10, "output_tokens": 2},
                "duration_s": 0.1,
                "trace_summary": {"ran_tests": True, "tool_calls": 3},
            },
            "",
        )

    def broken_verify(task, workspace):
        raise RuntimeError("verify crashed")

    monkeypatch.setattr(runner, "run_worker", fake_worker)
    monkeypatch.setattr(runner, "run_verify", broken_verify)

    result = runner.run_task(
        task,
        work_root=tmp_path,
        model=None,
        baseline="minicode-ask",
        run_index=0,
        pricing={},
    )

    assert result["tool_calls"] == 3
    assert result["usage"] == {"input_tokens": 10, "output_tokens": 2}
    assert result["failure_reason"] == "verification_failed"
    assert "verification error: verify crashed" in result["verify_output"]


def test_run_suite_rejects_non_positive_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner, "load_suite", lambda suite: [])

    with pytest.raises(ValueError, match="runs must be at least 1"):
        runner.run_suite(suite="smoke", model=None, baselines=["full"], runs=0)


def test_run_suite_repeats_each_task(monkeypatch: pytest.MonkeyPatch) -> None:
    task = load_suite("smoke")[0]
    calls: list[int] = []

    monkeypatch.setattr(runner, "load_suite", lambda suite: [task])

    def fake_run_task(task, **kwargs):
        calls.append(kwargs["run_index"])
        return {
            "id": task.id,
            "baseline": kwargs["baseline"],
            "run": kwargs["run_index"],
            "passed": True,
            "worker_ok": True,
            "verify_ok": True,
            "error": None,
            "tool_calls": 0,
            "usage": {},
            "cost_usd": 0.0,
            "duration_s": 0.0,
            "verify_output": "",
            "worker_output": "",
            "final": "",
            "trace_summary": {},
            "failure_reason": "passed",
        }

    monkeypatch.setattr(runner, "run_task", fake_run_task)

    report = runner.run_suite(
        suite="smoke",
        model=None,
        baselines=["full", "bare"],
        runs=2,
        keep=True,
    )

    assert report["runs"] == 2
    assert len(report["tasks"]) == 4
    assert calls == [0, 1, 0, 1]
    shutil.rmtree(report["work_dir"])
