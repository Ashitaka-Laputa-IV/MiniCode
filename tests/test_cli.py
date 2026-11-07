import io
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from rich.console import Console

from minicode.cli import (
    build_parser,
    interactive_loop,
    load_env,
    main,
    make_config,
    message_text,
    print_final,
    print_update,
    short_json,
)


def test_message_text_string() -> None:
    assert message_text("hello") == "hello"


def test_message_text_content_blocks() -> None:
    message = {
        "content": [
            {"type": "text", "text": "first"},
            {"type": "text", "text": "second"},
        ]
    }
    assert message_text(message) == "first\nsecond"


def test_short_json_truncates() -> None:
    assert short_json({"key": "value"}) == '{"key": "value"}'
    assert short_json("x" * 200, limit=10).endswith("...")


def test_print_update_renders_tool_activity() -> None:
    console = Console(record=True, width=200, force_terminal=False)
    tool_call = SimpleNamespace(
        type="ai",
        tool_calls=[{"name": "ls", "args": {"path": "/"}}],
        content="",
    )
    tool_result = SimpleNamespace(type="tool", name="ls", content="/a\n/b")
    final = SimpleNamespace(type="ai", tool_calls=[], content="done")

    message = print_update(
        {
            "model": {"messages": [tool_call]},
            "tools": {"messages": [tool_result]},
            "done": {"messages": [final]},
        },
        console,
    )

    assert message is final
    text = console.export_text()
    assert "ls" in text
    assert "/a /b" in text


def test_print_final_uses_raw_text_when_not_terminal() -> None:
    buffer = io.StringIO()
    console = Console(file=buffer, force_terminal=False, soft_wrap=True)
    print_final(SimpleNamespace(content="# Head\n\nbody"), console)

    assert buffer.getvalue() == "# Head\n\nbody\n"


def test_print_final_renders_markdown_on_terminal() -> None:
    buffer = io.StringIO()
    console = Console(file=buffer, force_terminal=True, width=80)
    print_final(SimpleNamespace(content="# Head"), console)

    output = buffer.getvalue()
    assert "Head" in output
    assert "# Head" not in output


def test_parser_defaults() -> None:
    args = build_parser().parse_args(["fix", "the", "bug"])
    assert args.prompt == ["fix", "the", "bug"]
    assert args.model is None
    assert args.root == "."
    assert args.debug is False
    assert args.interactive is False
    assert args.thread is None
    assert args.db is None


def test_parser_thread_and_db() -> None:
    args = build_parser().parse_args(["--thread", "work", "--db", "state.sqlite"])
    assert args.thread == "work"
    assert args.db == "state.sqlite"


def test_make_config() -> None:
    assert make_config("work") == {"configurable": {"thread_id": "work"}}


def test_parser_interactive() -> None:
    assert build_parser().parse_args(["-i"]).interactive is True
    assert build_parser().parse_args(["--interactive"]).interactive is True


def test_parser_root_and_model() -> None:
    args = build_parser().parse_args(
        ["--model", "deepseek:deepseek-chat", "--root", "workspace", "task"]
    )
    assert args.model == "deepseek:deepseek-chat"
    assert args.root == "workspace"


def test_load_env_from_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DEEPSEEK_API_KEY=from-dotenv\nOPENAI_BASE_URL=http://evil.example/v1\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)

    assert load_env() == str(env_file)
    assert os.environ["DEEPSEEK_API_KEY"] == "from-dotenv"
    assert "OPENAI_BASE_URL" not in os.environ


def test_load_env_from_parent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("MINICODE_MODEL=deepseek:deepseek-reasoner\n", encoding="utf-8")
    child = tmp_path / "child"
    child.mkdir()
    monkeypatch.chdir(child)
    monkeypatch.delenv("MINICODE_MODEL", raising=False)

    assert load_env() == str(env_file)
    assert os.environ["MINICODE_MODEL"] == "deepseek:deepseek-reasoner"


def test_load_env_does_not_override_shell(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".env").write_text("DEEPSEEK_API_KEY=from-dotenv\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "from-shell")

    load_env()
    assert os.environ["DEEPSEEK_API_KEY"] == "from-shell"


def test_load_env_ignores_empty_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".env").write_text("MINICODE_MODEL=   \n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MINICODE_MODEL", raising=False)

    load_env()
    assert "MINICODE_MODEL" not in os.environ


def test_load_env_strips_whitespace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".env").write_text(
        'DEEPSEEK_API_KEY="  sk-test  "\n', encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    load_env()
    assert os.environ["DEEPSEEK_API_KEY"] == "sk-test"


class FakeCheckpointer:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    def delete_thread(self, thread_id: str) -> None:
        self.deleted.append(thread_id)


class FakeAgent:
    def __init__(self, fail_on_call: int | None = None) -> None:
        self.calls: list[tuple[dict, dict | None]] = []
        self.thread_ids: list[str] = []
        self.fail_on_call = fail_on_call
        self.checkpointer = FakeCheckpointer()

    def stream(self, input, config=None, stream_mode=None):
        self.calls.append((input, config))
        self.thread_ids.append(config["configurable"]["thread_id"])
        if self.fail_on_call == len(self.calls):
            raise RuntimeError("boom")
        yield {
            "model": {
                "messages": [
                    SimpleNamespace(type="ai", tool_calls=[], content="done")
                ]
            }
        }


def test_interactive_loop_runs_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    inputs = iter(["hello", "/exit"])
    monkeypatch.setattr(Console, "input", lambda self, prompt="": next(inputs))

    agent = FakeAgent()
    output_buffer = io.StringIO()
    output = Console(file=output_buffer, force_terminal=False, soft_wrap=True)
    progress = Console(file=io.StringIO(), force_terminal=False, soft_wrap=True)
    config = {"configurable": {"thread_id": "test"}}

    assert interactive_loop(agent, progress, output, config, False) == 0
    assert len(agent.calls) == 1
    assert agent.calls[0][1] == config
    assert "done" in output_buffer.getvalue()


def test_interactive_loop_reset_command(monkeypatch: pytest.MonkeyPatch) -> None:
    inputs = iter(["one", "/reset", "two", "/exit"])
    monkeypatch.setattr(Console, "input", lambda self, prompt="": next(inputs))

    agent = FakeAgent()
    output = Console(file=io.StringIO(), force_terminal=False, soft_wrap=True)
    progress = Console(file=io.StringIO(), force_terminal=False, soft_wrap=True)
    config = {"configurable": {"thread_id": "test"}}

    interactive_loop(agent, progress, output, config, False)
    assert len(agent.thread_ids) == 2
    assert agent.thread_ids[0] == agent.thread_ids[1]
    assert agent.checkpointer.deleted == [agent.thread_ids[0]]


def test_interactive_loop_keeps_thread_for_successful_turns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs = iter(["one", "two", "/exit"])
    monkeypatch.setattr(Console, "input", lambda self, prompt="": next(inputs))

    agent = FakeAgent()
    output = Console(file=io.StringIO(), force_terminal=False, soft_wrap=True)
    progress = Console(file=io.StringIO(), force_terminal=False, soft_wrap=True)
    config = {"configurable": {"thread_id": "test"}}

    interactive_loop(agent, progress, output, config, False)
    assert len(agent.thread_ids) == 2
    assert agent.thread_ids[0] == agent.thread_ids[1]
    assert agent.checkpointer.deleted == []


def test_interactive_loop_resets_thread_after_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs = iter(["bad", "good", "/exit"])
    monkeypatch.setattr(Console, "input", lambda self, prompt="": next(inputs))

    agent = FakeAgent(fail_on_call=1)
    progress_buffer = io.StringIO()
    progress = Console(file=progress_buffer, force_terminal=False, soft_wrap=True)
    output = Console(file=io.StringIO(), force_terminal=False, soft_wrap=True)
    config = {"configurable": {"thread_id": "test"}}

    interactive_loop(agent, progress, output, config, False)
    assert len(agent.thread_ids) == 2
    assert agent.thread_ids[0] == agent.thread_ids[1]
    assert agent.checkpointer.deleted == [agent.thread_ids[0]]
    assert "Context reset" in progress_buffer.getvalue()


def test_interactive_loop_eof(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_eof(self, prompt=""):
        raise EOFError

    monkeypatch.setattr(Console, "input", raise_eof)

    agent = FakeAgent()
    output = Console(file=io.StringIO(), force_terminal=False, soft_wrap=True)
    progress = Console(file=io.StringIO(), force_terminal=False, soft_wrap=True)
    config = {"configurable": {"thread_id": "test"}}

    assert interactive_loop(agent, progress, output, config, False) == 0


def test_main_rejects_prompt_with_interactive(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["-i", "task"])
    assert exc.value.code == 2


def test_main_rejects_sqlite_options_with_prompt() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--db", "state.sqlite", "task"])
    assert exc.value.code == 2


def test_main_rejects_sqlite_options_with_stdin_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("task\n"))
    with pytest.raises(SystemExit) as exc:
        main(["--db", "state.sqlite"])
    assert exc.value.code == 2


def test_main_passes_sqlite_options(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    def fake_build_agent(**kwargs):
        captured["build"] = kwargs
        return object()

    def fake_loop(agent, progress, output, config, debug):
        captured["config"] = config
        return 0

    monkeypatch.setattr("minicode.cli.build_agent", fake_build_agent)
    monkeypatch.setattr("minicode.cli.interactive_loop", fake_loop)

    assert main(["-i", "--db", "state.sqlite", "--thread", "work"]) == 0
    assert captured["build"]["db_path"] == "state.sqlite"
    assert captured["build"]["checkpoint"] is True
    assert captured["config"] == {"configurable": {"thread_id": "work"}}


def test_main_requires_prompt_when_not_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(""))

    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 2
