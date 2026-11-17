import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from langgraph.types import Command

from minicode.evals import worker
from minicode.evals.baselines import resolve_baseline
from minicode.evals.trace import Trace


class FakeAgent:
    def __init__(self, updates: list[Any]) -> None:
        self.updates = updates

    def stream(self, input: Any, stream_mode: str, config: Any = None):
        assert input == {"messages": [{"role": "user", "content": "prompt"}]}
        assert stream_mode == "updates"
        if config is not None:
            assert config["configurable"]["thread_id"]
        yield from self.updates


class FakeInterrupt:
    id = "interrupt-1"
    value = {
        "action_requests": [
            {"name": "write_file", "args": {"file_path": "/app.py"}},
        ],
    }


class HitlAgent:
    def __init__(self) -> None:
        self.resumed = False
        self.resume_payload: Any = None

    def stream(self, input: Any, stream_mode: str, config: Any = None):
        assert stream_mode == "updates"
        if isinstance(input, Command):
            self.resumed = True
            self.resume_payload = input.resume
            yield {"model": {"messages": [ai_message(content="done")]}}
        else:
            yield {"__interrupt__": [FakeInterrupt()]}


class HitlUsageAgent:
    """Replay the interrupted AI message the way LangGraph HITL resume does."""

    def __init__(self) -> None:
        self.resume_payload: Any = None
        self.replayed = ai_message(
            tool_calls=[{"name": "write_file", "id": "call-1", "args": {}}],
            usage_metadata={"input_tokens": 10, "output_tokens": 2},
            message_id="ai-1",
        )

    def stream(self, input: Any, stream_mode: str, config: Any = None):
        assert stream_mode == "updates"
        if isinstance(input, Command):
            self.resume_payload = input.resume
            yield {
                "model": {
                    "messages": [
                        self.replayed,
                        ai_message(
                            content="done",
                            usage_metadata={"input_tokens": 20, "output_tokens": 3},
                            message_id="ai-2",
                        ),
                    ]
                }
            }
        else:
            yield {"model": {"messages": [self.replayed]}}
            yield {"__interrupt__": [FakeInterrupt()]}


class PausingAgent:
    """Interrupt once and stay paused unless a resume command arrives."""

    def __init__(self) -> None:
        self.resume_payload: Any = None

    def stream(self, input: Any, stream_mode: str, config: Any = None):
        assert stream_mode == "updates"
        if isinstance(input, Command):
            self.resume_payload = input.resume
            yield {"model": {"messages": [ai_message(content="resumed")]}}
            return
        assert input == {"messages": [{"role": "user", "content": "prompt"}]}
        yield {
            "model": {
                "messages": [
                    ai_message(
                        tool_calls=[
                            {"name": "write_file", "id": "call-1", "args": {"file_path": "/x"}}
                        ],
                        usage_metadata={"input_tokens": 7, "output_tokens": 2},
                    )
                ]
            }
        }
        yield {"__interrupt__": [FakeInterrupt()]}


class ResumeOnlyAgent:
    """Assert the stream starts with Command(resume=...) instead of a prompt."""

    def __init__(self) -> None:
        self.input: Any = None
        self.resume_payload: Any = None

    def stream(self, input: Any, stream_mode: str, config: Any = None):
        assert stream_mode == "updates"
        self.input = input
        assert isinstance(input, Command)
        self.resume_payload = input.resume
        yield {"model": {"messages": [ai_message(content="done")]}}


class FakeModel:
    def invoke(self, prompt: str) -> Any:
        assert prompt == "prompt"
        return SimpleNamespace(
            content="answer",
            usage_metadata={"input_tokens": 3, "output_tokens": 1, "total_tokens": 4},
        )


def ai_message(
    content: str = "",
    *,
    tool_calls: list[dict] | None = None,
    usage_metadata: dict | None = None,
    message_id: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        type="ai",
        id=message_id,
        content=content,
        tool_calls=tool_calls or [],
        usage_metadata=usage_metadata or {},
    )


def test_message_text_string() -> None:
    assert worker.message_text("hello") == "hello"
    assert worker.message_text(SimpleNamespace(content="hello")) == "hello"


def test_message_text_blocks() -> None:
    message = SimpleNamespace(content=[{"text": "first"}, "second", {"text": "third"}])
    assert worker.message_text(message) == "first\nsecond\nthird"


def test_message_text_other() -> None:
    assert worker.message_text(SimpleNamespace(content=123)) == "123"


def test_usage_from_usage_metadata() -> None:
    message = SimpleNamespace(
        usage_metadata={
            "input_tokens": 10,
            "output_tokens": 2,
            "total_tokens": 12,
            "input_token_details": {"cache_read": 4},
            "ignored": 99,
        }
    )
    assert worker.usage(message) == {
        "input_tokens": 10,
        "output_tokens": 2,
        "total_tokens": 12,
        "cached_input_tokens": 4,
    }


def test_usage_from_cached_tokens_alias() -> None:
    message = SimpleNamespace(
        usage_metadata={"input_tokens": 10, "input_token_details": {"cached_tokens": 3}}
    )
    assert worker.usage(message)["cached_input_tokens"] == 3


def test_usage_from_response_metadata() -> None:
    message = SimpleNamespace(
        response_metadata={
            "token_usage": {
                "prompt_tokens": 10,
                "completion_tokens": 2,
                "total_tokens": 12,
                "prompt_cache_hit_tokens": 4,
            }
        }
    )
    assert worker.usage(message) == {
        "input_tokens": 10,
        "output_tokens": 2,
        "total_tokens": 12,
        "cached_input_tokens": 4,
    }


def test_usage_from_response_usage() -> None:
    message = SimpleNamespace(response_metadata={"usage": {"prompt_tokens": 5}})
    assert worker.usage(message) == {"input_tokens": 5}


def test_usage_empty() -> None:
    assert worker.usage(SimpleNamespace()) == {}
    assert worker.usage(SimpleNamespace(usage_metadata={"input_tokens": "bad"})) == {}


def test_run_full_collects_usage_and_final(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    updates = [
        "not a dict",
        {"model": "not a dict"},
        {"model": {"messages": "not a list"}},
        {"model": {"messages": [SimpleNamespace(type="tool", content="result")]}},
        {
            "model": {
                "messages": [
                    ai_message(
                        tool_calls=[{"name": "ls"}],
                        usage_metadata={"input_tokens": 10, "output_tokens": 1},
                    )
                ]
            }
        },
        {
            "model": {
                "messages": [
                    ai_message(
                        content="done",
                        usage_metadata={"input_tokens": 5, "output_tokens": 2},
                    )
                ]
            }
        },
    ]
    monkeypatch.setattr(worker, "build_agent", lambda **kwargs: FakeAgent(updates))

    result = worker.run_full("prompt", tmp_path, None, 5)

    assert result["final"] == "done"
    assert result["tool_calls"] == 1
    assert result["usage"] == {"input_tokens": 15, "output_tokens": 3}
    assert result["duration_s"] >= 0


def test_run_full_without_ai_message(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(worker, "build_agent", lambda **kwargs: FakeAgent([]))

    result = worker.run_full("prompt", tmp_path, None, 5)

    assert result["final"] == ""
    assert result["tool_calls"] == 0
    assert result["usage"] == {}


def test_run_full_uses_yolo_for_non_interactive_eval(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict = {}

    def fake_build_agent(**kwargs):
        captured.update(kwargs)
        return FakeAgent([])

    monkeypatch.setattr(worker, "build_agent", fake_build_agent)

    worker.run_full("prompt", tmp_path, None, 5)

    assert captured["permission_mode"] == "yolo"


def test_run_full_rejects_tool_limit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    updates = [{"model": {"messages": [ai_message(tool_calls=[{"name": "one"}, {"name": "two"}])]}}]
    monkeypatch.setattr(worker, "build_agent", lambda **kwargs: FakeAgent(updates))

    with pytest.raises(RuntimeError, match="tool call limit exceeded"):
        worker.run_full("prompt", tmp_path, None, 1)


def test_run_full_allows_exact_tool_limit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    updates = [{"model": {"messages": [ai_message(tool_calls=[{"name": "one"}])]}}]
    monkeypatch.setattr(worker, "build_agent", lambda **kwargs: FakeAgent(updates))

    result = worker.run_full("prompt", tmp_path, None, 1)

    assert result["tool_calls"] == 1
    assert result["final"] == ""


def test_run_bare(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(worker, "init_chat_model", lambda model: FakeModel())

    result = worker.run_bare("prompt", "deepseek:deepseek-flash")

    assert result["final"] == "answer"
    assert result["tool_calls"] == 0
    assert result["usage"]["input_tokens"] == 3
    assert result["duration_s"] >= 0


def test_run_bare_uses_resolved_chat_model(monkeypatch: pytest.MonkeyPatch) -> None:
    resolved = FakeModel()
    monkeypatch.setattr(worker, "resolve_chat_model", lambda model: resolved)

    result = worker.run_bare("prompt", "opencode-go:deepseek-v4.1-flash")

    assert result["final"] == "answer"
    assert result["usage"]["total_tokens"] == 4


def test_worker_main_full(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    prompt = tmp_path / "prompt.md"
    prompt.write_text("task", encoding="utf-8")
    output = tmp_path / "worker.json"
    calls: dict = {}

    def fake_run_full(
        prompt: str,
        root: Path,
        model: str | None,
        max_tool_calls: int,
        **kwargs: Any,
    ):
        calls.update(
            prompt=prompt,
            root=root,
            model=model,
            max_tool_calls=max_tool_calls,
            **kwargs,
        )
        return {
            "final": "ok",
            "tool_calls": 0,
            "usage": {},
            "duration_s": 0.1,
        }

    monkeypatch.setattr(worker, "run_full", fake_run_full)

    assert (
        worker.main(
            [
                "--prompt-file",
                str(prompt),
                "--root",
                str(tmp_path),
                "--output",
                str(output),
                "--model",
                "deepseek:deepseek-flash",
                "--max-tool-calls",
                "7",
            ]
        )
        == 0
    )
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["ok"] is True
    assert data["baseline"] == "full"
    assert data["error"] is None
    assert calls == {
        "prompt": "task",
        "root": tmp_path,
        "model": "deepseek:deepseek-flash",
        "max_tool_calls": 7,
        "trace_path": None,
        "checkpoint_db": None,
        "thread_id": None,
        "pause_on_interrupt": False,
        "resume_decisions": None,
        "disable_checkpoint": False,
    }


def test_worker_main_bare(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    prompt = tmp_path / "prompt.md"
    prompt.write_text("task", encoding="utf-8")
    output = tmp_path / "worker.json"
    calls: dict = {}

    def fake_run_bare(prompt: str, model: str | None):
        calls.update(prompt=prompt, model=model)
        return {
            "final": "bare",
            "tool_calls": 0,
            "usage": {},
            "duration_s": 0.1,
        }

    monkeypatch.setattr(worker, "run_bare", fake_run_bare)

    assert (
        worker.main(
            [
                "--prompt-file",
                str(prompt),
                "--root",
                str(tmp_path),
                "--output",
                str(output),
                "--baseline",
                "bare",
                "--model",
                "deepseek:deepseek-flash",
            ]
        )
        == 0
    )
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["ok"] is True
    assert data["baseline"] == "bare"
    assert calls == {"prompt": "task", "model": "deepseek:deepseek-flash"}


def test_worker_main_resume_flags(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    prompt = tmp_path / "prompt.md"
    prompt.write_text("task", encoding="utf-8")
    output = tmp_path / "worker.json"
    calls: dict = {}

    def fake_run_minicode(*args: Any, **kwargs: Any):
        calls.update(kwargs)
        return {
            "final": "resumed",
            "tool_calls": 1,
            "usage": {"input_tokens": 5},
            "duration_s": 0.1,
            "interrupted": False,
            "interrupt_id": None,
            "thread_id": "thread-1",
            "checkpoint_db": str(tmp_path / "checkpoint.sqlite"),
        }

    monkeypatch.setattr(worker, "run_minicode", fake_run_minicode)

    assert (
        worker.main(
            [
                "--prompt-file",
                str(prompt),
                "--root",
                str(tmp_path),
                "--output",
                str(output),
                "--baseline",
                "minicode-ask",
                "--checkpoint-db",
                str(tmp_path / "checkpoint.sqlite"),
                "--thread",
                "thread-1",
                "--pause-on-interrupt",
                "--resume-approve",
                "--disable-checkpoint",
            ]
        )
        == 0
    )
    data = json.loads(output.read_text(encoding="utf-8"))
    assert calls["pause_on_interrupt"] is True
    assert calls["resume_decisions"] == {"decisions": [{"type": "approve"}]}
    assert calls["disable_checkpoint"] is True
    assert data["interrupted"] is False
    assert data["interrupt_id"] is None
    assert data["thread_id"] == "thread-1"
    assert data["checkpoint_db"] == str(tmp_path / "checkpoint.sqlite")


def test_worker_main_records_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    prompt = tmp_path / "prompt.md"
    prompt.write_text("task", encoding="utf-8")
    output = tmp_path / "worker.json"
    trace_file = tmp_path / "trace.jsonl"

    def fail(*args: Any, **kwargs: Any):
        with Trace(kwargs["trace_path"]) as trace:
            trace.record("tool_call", name="execute", args={"command": "pytest -q"})
            trace.record("usage", input_tokens=12, output_tokens=4)
        raise RuntimeError("boom")

    monkeypatch.setattr(worker, "run_full", fail)

    assert (
        worker.main(
            [
                "--prompt-file",
                str(prompt),
                "--root",
                str(tmp_path),
                "--output",
                str(output),
                "--trace-file",
                str(trace_file),
            ]
        )
        == 0
    )
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["ok"] is False
    assert data["error"] == "RuntimeError: boom"
    assert "RuntimeError" in data["traceback"]
    assert data["final"] == ""
    assert data["tool_calls"] == 1
    assert data["usage"] == {"input_tokens": 12, "output_tokens": 4}
    assert data["trace_summary"]["tool_calls"] == 1
    assert data["trace_summary"]["usage"] == {"input_tokens": 12, "output_tokens": 4}
    assert data["interrupted"] is False
    assert data["interrupt_id"] is None
    assert data["thread_id"] is None
    assert data["checkpoint_db"] is None


def test_run_agent_stream_resumes_with_scripted_approval() -> None:
    agent = HitlAgent()
    trace = Trace()

    result = worker.run_agent_stream(
        agent,
        "prompt",
        max_tool_calls=5,
        trace=trace,
        approval_policy="eval",
    )

    assert result["final"] == "done"
    assert result["interrupted"] is False
    assert agent.resumed is True
    assert agent.resume_payload == {"decisions": [{"type": "approve"}]}
    assert trace.summary()["approvals"] == 1
    assert trace.summary()["rejections"] == 0


def test_run_agent_stream_pauses_without_resuming() -> None:
    agent = PausingAgent()
    trace = Trace()

    result = worker.run_agent_stream(
        agent,
        "prompt",
        max_tool_calls=5,
        trace=trace,
        approval_policy="eval",
        pause_on_interrupt=True,
    )

    assert result["interrupted"] is True
    assert result["interrupt_id"] == "interrupt-1"
    assert result["interrupt_ids"] == ["interrupt-1"]
    assert result["pending_actions"] == [{"name": "write_file", "args": {"file_path": "/app.py"}}]
    assert result["tool_calls"] == 1
    assert result["usage"] == {"input_tokens": 7, "output_tokens": 2}
    assert result["final"] == ""
    assert agent.resume_payload is None
    assert trace.summary()["approvals"] == 0
    assert any(event.type == "pause" for event in trace.events)


def test_run_agent_stream_starts_with_resume_decisions() -> None:
    agent = ResumeOnlyAgent()
    trace = Trace()

    result = worker.run_agent_stream(
        agent,
        "ignored",
        max_tool_calls=5,
        trace=trace,
        resume_decisions={"decisions": [{"type": "approve"}]},
    )

    assert isinstance(agent.input, Command)
    assert agent.resume_payload == {"decisions": [{"type": "approve"}]}
    assert result["final"] == "done"
    assert result["interrupted"] is False
    assert trace.events[0].type == "resume_input"


def test_run_agent_stream_does_not_double_count_replayed_usage() -> None:
    agent = HitlUsageAgent()
    trace = Trace()

    result = worker.run_agent_stream(
        agent,
        "prompt",
        max_tool_calls=5,
        trace=trace,
        approval_policy="eval",
    )

    assert result["tool_calls"] == 1
    assert result["usage"] == {"input_tokens": 30, "output_tokens": 5}
    assert trace.summary()["usage"] == {"input_tokens": 30, "output_tokens": 5}
    assert agent.resume_payload == {"decisions": [{"type": "approve"}]}


def test_run_agent_stream_rejects_without_policy() -> None:
    agent = HitlAgent()
    trace = Trace()

    result = worker.run_agent_stream(
        agent,
        "prompt",
        max_tool_calls=5,
        trace=trace,
    )

    assert result["final"] == "done"
    assert trace.summary()["rejections"] == 1
    assert agent.resume_payload["decisions"][0]["type"] == "reject"
    assert "no approval policy configured" in agent.resume_payload["decisions"][0]["message"]


def test_run_minicode_uses_baseline_and_trace(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict = {}

    def fake_build_agent(**kwargs: Any):
        captured.update(kwargs)
        return FakeAgent([])

    monkeypatch.setattr(worker, "build_agent", fake_build_agent)
    trace_file = tmp_path / "trace.jsonl"

    result = worker.run_minicode(
        "prompt",
        tmp_path,
        None,
        5,
        baseline=resolve_baseline("minicode-ask"),
        trace_path=trace_file,
        checkpoint_db=tmp_path / "checkpoint.sqlite",
        thread_id="thread-1",
    )

    assert captured["permission_mode"] == "ask"
    assert captured["checkpoint"] is True
    assert callable(captured["trace_sink"])
    assert result["trace_summary"]["tool_calls"] == 0
    assert trace_file.exists()


def test_run_minicode_no_checkpoint_disables_checkpoint(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict = {}

    def fake_build_agent(**kwargs: Any):
        captured.update(kwargs)
        return FakeAgent([])

    monkeypatch.setattr(worker, "build_agent", fake_build_agent)

    worker.run_minicode(
        "prompt",
        tmp_path,
        None,
        5,
        baseline=resolve_baseline("minicode-no-checkpoint"),
    )

    assert captured["checkpoint"] is False


def test_run_minicode_disable_checkpoint_overrides_baseline(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict = {}

    def fake_build_agent(**kwargs: Any):
        captured.update(kwargs)
        return FakeAgent([])

    monkeypatch.setattr(worker, "build_agent", fake_build_agent)

    result = worker.run_minicode(
        "prompt",
        tmp_path,
        None,
        5,
        baseline=resolve_baseline("minicode-ask"),
        checkpoint_db=tmp_path / "checkpoint.sqlite",
        thread_id="thread-1",
        disable_checkpoint=True,
    )

    assert captured["checkpoint"] is False
    assert captured["db_path"] is None
    assert result["thread_id"] is None
    assert result["checkpoint_db"] is None
    assert result["interrupted"] is False
    assert result["interrupt_id"] is None


def test_run_minicode_passes_recovery_flags(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict = {}
    agent = ResumeOnlyAgent()

    def fake_build_agent(**kwargs: Any):
        captured.update(kwargs)
        return agent

    monkeypatch.setattr(worker, "build_agent", fake_build_agent)

    result = worker.run_minicode(
        "prompt",
        tmp_path,
        None,
        5,
        baseline=resolve_baseline("minicode-ask"),
        checkpoint_db=tmp_path / "checkpoint.sqlite",
        thread_id="thread-1",
        resume_decisions={"decisions": [{"type": "approve"}]},
    )

    assert captured["checkpoint"] is True
    assert agent.resume_payload == {"decisions": [{"type": "approve"}]}
    assert result["thread_id"] == "thread-1"
    assert result["checkpoint_db"] == str(tmp_path / "checkpoint.sqlite")


def test_run_minicode_no_subagents_disables_subagents(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict = {}

    def fake_build_agent(**kwargs: Any):
        captured.update(kwargs)
        return FakeAgent([])

    monkeypatch.setattr(worker, "build_agent", fake_build_agent)

    worker.run_minicode(
        "prompt",
        tmp_path,
        None,
        5,
        baseline=resolve_baseline("minicode-no-subagents"),
    )

    assert captured["subagents"] is False
    assert captured["permission_mode"] == "yolo"
    assert captured["checkpoint"] is True


def test_run_deepagents_default_builds_native_stack(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict = {}

    def fake_backend(**kwargs: Any):
        captured["backend_kwargs"] = kwargs
        return object()

    def fake_create_deep_agent(**kwargs: Any):
        captured.update(kwargs)
        return FakeAgent([])

    monkeypatch.setattr(worker, "LocalShellBackend", fake_backend)
    monkeypatch.setattr(worker, "create_deep_agent", fake_create_deep_agent)

    result = worker.run_deepagents_default(
        "prompt",
        tmp_path,
        "deepseek:deepseek-flash",
        5,
    )

    assert captured["backend_kwargs"]["root_dir"] == tmp_path
    assert captured["backend_kwargs"]["inherit_env"] is False
    assert "system_prompt" not in captured
    assert "interrupt_on" not in captured
    assert result["trace_summary"]["tool_calls"] == 0


def test_run_deepagents_default_accepts_resolved_chat_model(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict = {}
    resolved = FakeModel()

    def fake_backend(**kwargs: Any):
        return object()

    def fake_create_deep_agent(**kwargs: Any):
        captured.update(kwargs)
        return FakeAgent([])

    monkeypatch.setattr(worker, "resolve_chat_model", lambda model: resolved)
    monkeypatch.setattr(worker, "LocalShellBackend", fake_backend)
    monkeypatch.setattr(worker, "create_deep_agent", fake_create_deep_agent)

    worker.run_deepagents_default(
        "prompt",
        tmp_path,
        "opencode-go:deepseek-v4.1-flash",
        5,
    )

    assert captured["model"] is resolved
