import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from minicode.evals import worker


class FakeAgent:
    def __init__(self, updates: list[Any]) -> None:
        self.updates = updates

    def stream(self, input: Any, stream_mode: str):
        assert stream_mode == "updates"
        yield from self.updates


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
) -> SimpleNamespace:
    return SimpleNamespace(
        type="ai",
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


def test_run_full_rejects_tool_limit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    updates = [{"model": {"messages": [ai_message(tool_calls=[{"name": "one"}, {"name": "two"}])]}}]
    monkeypatch.setattr(worker, "build_agent", lambda **kwargs: FakeAgent(updates))

    with pytest.raises(RuntimeError, match="tool call limit exceeded"):
        worker.run_full("prompt", tmp_path, None, 1)


def test_run_bare(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(worker, "init_chat_model", lambda model: FakeModel())

    result = worker.run_bare("prompt", "deepseek:deepseek-flash")

    assert result["final"] == "answer"
    assert result["tool_calls"] == 0
    assert result["usage"]["input_tokens"] == 3
    assert result["duration_s"] >= 0


def test_worker_main_full(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    prompt = tmp_path / "prompt.md"
    prompt.write_text("task", encoding="utf-8")
    output = tmp_path / "worker.json"
    monkeypatch.setattr(
        worker,
        "run_full",
        lambda *args: {
            "final": "ok",
            "tool_calls": 0,
            "usage": {},
            "duration_s": 0.1,
        },
    )

    assert (
        worker.main(
            [
                "--prompt-file",
                str(prompt),
                "--root",
                str(tmp_path),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["ok"] is True
    assert data["baseline"] == "full"
    assert data["error"] is None


def test_worker_main_bare(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    prompt = tmp_path / "prompt.md"
    prompt.write_text("task", encoding="utf-8")
    output = tmp_path / "worker.json"
    monkeypatch.setattr(
        worker,
        "run_bare",
        lambda *args: {
            "final": "bare",
            "tool_calls": 0,
            "usage": {},
            "duration_s": 0.1,
        },
    )

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
            ]
        )
        == 0
    )
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["ok"] is True
    assert data["baseline"] == "bare"


def test_worker_main_records_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    prompt = tmp_path / "prompt.md"
    prompt.write_text("task", encoding="utf-8")
    output = tmp_path / "worker.json"

    def fail(*args):
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
            ]
        )
        == 0
    )
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["ok"] is False
    assert data["error"] == "RuntimeError: boom"
    assert "RuntimeError" in data["traceback"]
    assert data["final"] == ""
