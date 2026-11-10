import io
from pathlib import Path
from typing import Any

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.types import Command
from rich.console import Console

from minicode.agent import build_agent
from minicode.cli import run_turn


class ToolCallingModel(BaseChatModel):
    tool_name: str
    tool_args: dict[str, Any]
    calls: int = 0

    @property
    def _llm_type(self) -> str:
        return "tool-calling"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ToolCallingModel":
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.calls += 1
        if self.calls == 1:
            message = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": self.tool_name,
                        "args": self.tool_args,
                        "id": f"call-{self.tool_name}",
                    }
                ],
            )
        else:
            message = AIMessage(content="done")
        return ChatResult(generations=[ChatGeneration(message=message)])


def run_interrupted_tool(
    tmp_path: Path,
    tool_name: str,
    tool_args: dict[str, Any],
) -> tuple[Any, dict[str, Any], Any]:
    model = ToolCallingModel(tool_name=tool_name, tool_args=tool_args)
    agent = build_agent(
        model=model,
        root=tmp_path,
        permission_mode="ask",
        checkpoint=False,
    )
    config = {"configurable": {"thread_id": f"hitl-{tool_name}"}}

    result = agent.invoke(
        {"messages": [{"role": "user", "content": f"use {tool_name}"}]},
        config=config,
        version="v2",
    )
    assert result.interrupts

    interrupt = result.interrupts[0]
    return agent, config, interrupt.value


def test_write_file_requires_approval(tmp_path: Path) -> None:
    agent, config, value = run_interrupted_tool(
        tmp_path,
        "write_file",
        {"file_path": "/approved.txt", "content": "hello"},
    )

    action = value["action_requests"][0]
    assert action["name"] == "write_file"
    assert action["args"]["file_path"] == "/approved.txt"

    result = agent.invoke(
        Command(resume={"decisions": [{"type": "approve"}]}),
        config=config,
        version="v2",
    )

    assert (tmp_path / "approved.txt").read_text(encoding="utf-8") == "hello"
    assert result.value["messages"][-1].content == "done"


def test_rejected_write_does_not_touch_disk(tmp_path: Path) -> None:
    agent, config, _ = run_interrupted_tool(
        tmp_path,
        "write_file",
        {"file_path": "/rejected.txt", "content": "hello"},
    )

    agent.invoke(
        Command(
            resume={
                "decisions": [
                    {
                        "type": "reject",
                        "message": "User rejected this action. Do not retry it.",
                    }
                ]
            }
        ),
        config=config,
        version="v2",
    )

    assert not (tmp_path / "rejected.txt").exists()


def test_read_only_blocks_write_without_interrupt(tmp_path: Path) -> None:
    model = ToolCallingModel(
        tool_name="write_file",
        tool_args={"file_path": "/read-only.txt", "content": "hello"},
    )
    agent = build_agent(model=model, root=tmp_path, permission_mode="read-only")

    result = agent.invoke(
        {"messages": [{"role": "user", "content": "write a file"}]},
        config={"configurable": {"thread_id": "read-only"}},
        version="v2",
    )

    assert not result.interrupts
    assert not (tmp_path / "read-only.txt").exists()
    assert result.value["messages"][-1].content == "done"


def test_yolo_skips_interrupt(tmp_path: Path) -> None:
    model = ToolCallingModel(
        tool_name="write_file",
        tool_args={"file_path": "/yolo.txt", "content": "hello"},
    )
    agent = build_agent(model=model, root=tmp_path, permission_mode="yolo")

    result = agent.invoke(
        {"messages": [{"role": "user", "content": "write a file"}]},
        config={"configurable": {"thread_id": "yolo"}},
        version="v2",
    )

    assert not result.interrupts
    assert (tmp_path / "yolo.txt").read_text(encoding="utf-8") == "hello"
    assert result.value["messages"][-1].content == "done"


def test_run_turn_handles_real_stream_interrupt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = ToolCallingModel(
        tool_name="execute",
        tool_args={"command": "echo hitl-ok"},
    )
    agent = build_agent(model=model, root=tmp_path, permission_mode="ask")
    progress = Console(file=io.StringIO(), force_terminal=False, soft_wrap=True)
    config = {"configurable": {"thread_id": "stream-hitl"}}

    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr(Console, "input", lambda self, prompt="": "y")

    message = run_turn(agent, "run the command", progress, config)

    assert message.content == "done"
    assert "approval required" in progress.file.getvalue()
    assert "echo hitl-ok" in progress.file.getvalue()
    assert "hitl-ok" in progress.file.getvalue()


def test_execute_requires_approval(tmp_path: Path) -> None:
    agent, config, value = run_interrupted_tool(
        tmp_path,
        "execute",
        {"command": "echo hitl-ok"},
    )

    action = value["action_requests"][0]
    assert action["name"] == "execute"
    assert action["args"]["command"] == "echo hitl-ok"

    result = agent.invoke(
        Command(resume={"decisions": [{"type": "approve"}]}),
        config=config,
        version="v2",
    )

    tool_messages = [message for message in result.value["messages"] if message.type == "tool"]
    assert any("hitl-ok" in str(message.content) for message in tool_messages)
    assert result.value["messages"][-1].content == "done"
