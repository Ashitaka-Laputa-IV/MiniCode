from pathlib import Path

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


def test_trace_sink_adapter() -> None:
    trace = Trace()
    trace.sink("tool_call", {"name": "ls", "args": {}})
    assert trace.events[0].data["name"] == "ls"


def test_read_missing_trace_is_empty(tmp_path: Path) -> None:
    assert read_trace(tmp_path / "missing.jsonl") == []


def test_summary_of_empty_trace() -> None:
    summary = Trace().summary()
    assert summary["events"] == 0
    assert summary["tool_calls"] == 0
    assert summary["repeated_tool_calls"] is False
