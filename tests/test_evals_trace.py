from pathlib import Path

import pytest

from minicode.evals.trace import Trace, read_trace


def test_trace_records_events_and_summary(tmp_path: Path) -> None:
    path = tmp_path / "trace.jsonl"
    trace = Trace(path)

    trace.record("tool_call", name="execute", args={"command": "uv run pytest"})
    trace.record("tool_call", name="execute", args={"command": "uv run pytest"})
    trace.record("tool_call", name="execute", args={"command": "uv run pytest"})
    trace.record("tool_call", name="write_file", args={"file_path": "/app.py"})
    trace.record(
        "policy_decision",
        tool="execute",
        command="rm -rf /",
        action="DENY",
        reason="hard deny-list",
    )
    trace.record("approval", tool="write_file", decision="approve", reason="ok")
    trace.record("approval", tool="execute", decision="reject", reason="no")
    trace.record("interrupt", id="interrupt-1")
    trace.close()

    summary = trace.summary()

    assert summary["events"] == 8
    assert summary["tool_calls"] == 4
    assert summary["approvals"] == 1
    assert summary["rejections"] == 1
    assert summary["blocked"] == 1
    assert summary["ran_tests"] is True
    assert summary["repeated_tool_calls"] is True
    assert summary["touched_paths"] == ["/app.py"]
    assert summary["denial_reasons"] == {"hard deny-list": 1}

    events = read_trace(path)
    assert len(events) == 8
    assert events[0].type == "tool_call"
    assert events[-1].type == "interrupt"


def test_summary_aggregates_usage_events() -> None:
    trace = Trace()
    trace.record("usage", input_tokens=10, output_tokens=2, total_tokens=12)
    trace.record("usage", input_tokens=5, output_tokens=1, total_tokens=6)

    assert trace.summary()["usage"] == {
        "input_tokens": 15,
        "output_tokens": 3,
        "total_tokens": 18,
    }


def test_trace_sink_adapter() -> None:
    trace = Trace()
    trace.sink("tool_call", {"name": "ls", "args": {}})
    assert trace.events[0].data["name"] == "ls"


def test_read_missing_trace_is_empty(tmp_path: Path) -> None:
    assert read_trace(tmp_path / "missing.jsonl") == []


def test_read_trace_ignores_truncated_final_line(tmp_path: Path) -> None:
    path = tmp_path / "trace.jsonl"
    path.write_text(
        '{"type": "usage", "time": 1.0, "data": {"input_tokens": 100}}\n'
        '{"type": "tool_call", "time": 2.0, "data": {"name": "execute"',
        encoding="utf-8",
    )

    events = read_trace(path)

    assert len(events) == 1
    assert events[0].type == "usage"
    assert events[0].data == {"input_tokens": 100}


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("pytest -q", True),
        ("uv run pytest -q", True),
        ("python -m pytest", True),
        ("python -m unittest discover", True),
        ("npm test", True),
        ("npm run test", True),
        ("make test", True),
        ("echo pytest", False),
        ("pytest --version", False),
        ("pip install pytest", False),
        ("uv run ruff check .", False),
        ("cargo test --no-run", False),
    ],
)
def test_ran_tests_detection(command: str, expected: bool) -> None:
    trace = Trace()
    trace.record("tool_call", name="execute", args={"command": command})

    assert trace.summary()["ran_tests"] is expected


def test_summary_of_empty_trace() -> None:
    summary = Trace().summary()
    assert summary["events"] == 0
    assert summary["tool_calls"] == 0
    assert summary["repeated_tool_calls"] is False


def test_lint_does_not_count_as_running_tests() -> None:
    trace = Trace()
    trace.record("tool_call", name="execute", args={"command": "uv run ruff check ."})

    assert trace.summary()["ran_tests"] is False
