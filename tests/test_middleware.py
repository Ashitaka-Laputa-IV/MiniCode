from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

from langchain_core.messages import ToolMessage

from minicode.middleware import NoSubagentsMiddleware


class FakeModelRequest:
    def __init__(self, tools: list[Any]) -> None:
        self.tools = tools

    def override(self, **overrides: Any) -> FakeModelRequest:
        return FakeModelRequest(overrides["tools"])


def test_no_subagents_middleware_filters_task_tool() -> None:
    request = FakeModelRequest(
        [
            SimpleNamespace(name="task"),
            SimpleNamespace(name="read_file"),
            {"name": "write_file"},
        ]
    )
    captured: dict[str, Any] = {}

    def handler(model_request: FakeModelRequest) -> list[str]:
        captured["names"] = [
            tool.name if hasattr(tool, "name") else tool["name"] for tool in model_request.tools
        ]
        return captured["names"]

    result = NoSubagentsMiddleware().wrap_model_call(request, handler)  # type: ignore[arg-type]

    assert result == ["read_file", "write_file"]
    assert captured["names"] == ["read_file", "write_file"]


def test_no_subagents_middleware_rejects_task_execution() -> None:
    request = SimpleNamespace(tool_call={"name": "task", "id": "call-1"})
    called = False

    def handler(tool_request: Any) -> ToolMessage:
        nonlocal called
        called = True
        return ToolMessage(content="ok", tool_call_id="call-1")

    result = NoSubagentsMiddleware().wrap_tool_call(request, handler)  # type: ignore[arg-type]

    assert called is False
    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    assert result.tool_call_id == "call-1"
    assert "subagents are disabled" in str(result.content)


def test_no_subagents_middleware_allows_other_tools() -> None:
    request = SimpleNamespace(tool_call={"name": "read_file", "id": "call-2"})

    def handler(tool_request: Any) -> ToolMessage:
        return ToolMessage(content="ok", tool_call_id=tool_request.tool_call["id"])

    result = NoSubagentsMiddleware().wrap_tool_call(request, handler)  # type: ignore[arg-type]

    assert isinstance(result, ToolMessage)
    assert result.content == "ok"


def test_no_subagents_middleware_filters_task_tool_async() -> None:
    request = FakeModelRequest([SimpleNamespace(name="task"), SimpleNamespace(name="read_file")])

    async def handler(model_request: FakeModelRequest) -> list[str]:
        return [tool.name for tool in model_request.tools]

    result = asyncio.run(
        NoSubagentsMiddleware().awrap_model_call(request, handler)  # type: ignore[arg-type]
    )

    assert result == ["read_file"]


def test_no_subagents_middleware_rejects_task_execution_async() -> None:
    request = SimpleNamespace(tool_call={"name": "task", "id": "call-3"})
    called = False

    async def handler(tool_request: Any) -> ToolMessage:
        nonlocal called
        called = True
        return ToolMessage(content="ok", tool_call_id="call-3")

    result = asyncio.run(
        NoSubagentsMiddleware().awrap_tool_call(request, handler)  # type: ignore[arg-type]
    )

    assert called is False
    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    assert result.tool_call_id == "call-3"
    assert "subagents are disabled" in str(result.content)
