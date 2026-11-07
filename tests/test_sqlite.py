from pathlib import Path
from typing import Any

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from minicode.agent import build_agent


class ScriptedModel(BaseChatModel):
    replies: list[str]
    calls: int = 0

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ScriptedModel":
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        index = min(self.calls, len(self.replies) - 1)
        self.calls += 1
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content=self.replies[index]))]
        )


def test_sqlite_persists_conversation_across_agents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import minicode.agent as agent_module

    savers = []
    original = agent_module.build_checkpointer

    def capture(root, db_path=None):
        saver = original(root, db_path)
        savers.append(saver)
        return saver

    monkeypatch.setattr(agent_module, "build_checkpointer", capture)
    db = tmp_path / "state.sqlite"
    config = {"configurable": {"thread_id": "main"}}

    try:
        first = build_agent(
            model=ScriptedModel(replies=["first answer"]),
            root=tmp_path,
            checkpoint=True,
            db_path=db,
        )
        first.invoke(
            {"messages": [{"role": "user", "content": "first question"}]},
            config=config,
        )

        second = build_agent(
            model=ScriptedModel(replies=["second answer"]),
            root=tmp_path,
            checkpoint=True,
            db_path=db,
        )
        result = second.invoke(
            {"messages": [{"role": "user", "content": "second question"}]},
            config=config,
        )

        contents = [message.content for message in result["messages"]]
        assert "first question" in contents
        assert "first answer" in contents
        assert "second question" in contents
        assert "second answer" in contents
    finally:
        for saver in savers:
            saver.conn.close()
