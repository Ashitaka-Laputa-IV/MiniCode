import os
from pathlib import Path
from typing import Any

import pytest
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from minicode.agent import build_agent, resolve_model
from minicode.cli import load_env, message_text

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def live_model() -> BaseChatModel:
    load_env()
    model = resolve_model()
    if not model.startswith("deepseek:"):
        pytest.fail(f"live tests currently require a DeepSeek model, got {model}")
    if not os.getenv("DEEPSEEK_API_KEY"):
        pytest.fail("DEEPSEEK_API_KEY is not set; add it to the shell or .env")
    return init_chat_model(model, temperature=0)


def final_text(messages: list[Any]) -> str:
    for message in reversed(messages):
        if getattr(message, "type", None) == "ai":
            text = message_text(message).strip()
            if text:
                return text
    return ""


def test_live_agent_replies(tmp_path: Path, live_model: BaseChatModel) -> None:
    agent = build_agent(model=live_model, root=tmp_path)
    result = agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "Reply with exactly: ok. Do not use any tools.",
                }
            ]
        }
    )
    text = final_text(result["messages"]).strip().lower()
    assert text, "expected a non-empty final AI message"
    assert text.startswith("ok")


def test_live_agent_uses_tools(tmp_path: Path, live_model: BaseChatModel) -> None:
    (tmp_path / "live-marker.txt").write_text("marker", encoding="utf-8")
    agent = build_agent(model=live_model, root=tmp_path)
    result = agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "Use the ls tool to list the files in the workspace, "
                        "then tell me which file you see. Do not modify anything."
                    ),
                }
            ]
        }
    )
    tool_messages = [
        message for message in result["messages"] if getattr(message, "type", None) == "tool"
    ]
    assert tool_messages, "expected the agent to call a tool"
    assert any("live-marker.txt" in message_text(message) for message in tool_messages)
