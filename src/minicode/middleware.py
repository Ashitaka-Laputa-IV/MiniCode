"""Middleware helpers for MiniCode agent construction."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from langchain.agents.middleware.types import (
        ExtendedModelResponse,
        ModelRequest,
        ModelResponse,
        ResponseT,
    )
    from langchain_core.messages import AIMessage
    from langgraph.prebuilt.tool_node import ToolCallRequest
    from langgraph.types import Command

TASK_TOOL = "task"


def _tool_name(tool: Any) -> str | None:
    if isinstance(tool, dict):
        name = tool.get("name")
        return name if isinstance(name, str) else None
    name = getattr(tool, "name", None)
    return name if isinstance(name, str) else None


class NoSubagentsMiddleware(AgentMiddleware[Any, Any, Any]):
    """Remove and reject the ``task`` tool so subagents cannot be invoked."""

    def wrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], ModelResponse[Any]],
    ) -> ModelResponse[Any]:
        filtered = [tool for tool in request.tools if _tool_name(tool) != TASK_TOOL]
        return handler(request.override(tools=filtered))

    async def awrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], Awaitable[ModelResponse[ResponseT]]],
    ) -> ModelResponse[ResponseT] | AIMessage | ExtendedModelResponse[ResponseT]:
        filtered = [tool for tool in request.tools if _tool_name(tool) != TASK_TOOL]
        return await handler(request.override(tools=filtered))

    def _rejection(self, request: ToolCallRequest) -> ToolMessage | None:
        name = request.tool_call["name"]
        if name != TASK_TOOL:
            return None
        return ToolMessage(
            content="Error: subagents are disabled for this baseline.",
            tool_call_id=request.tool_call["id"] or "",
            name=name,
            status="error",
        )

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command],
    ) -> ToolMessage | Command:
        return self._rejection(request) or handler(request)

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command]],
    ) -> ToolMessage | Command:
        return self._rejection(request) or await handler(request)
