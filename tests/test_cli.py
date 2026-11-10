import io
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage
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
    reasoning_text,
    run_turn,
    short_json,
)
from minicode.policy import PermissionMode


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


def test_reasoning_text_from_content_blocks() -> None:
    message = SimpleNamespace(
        content_blocks=[
            {"type": "text", "text": "answer"},
            {"type": "reasoning", "reasoning": "plan"},
        ]
    )
    assert reasoning_text(message) == "plan"


def test_reasoning_text_from_real_ai_message() -> None:
    message = AIMessage(content="answer", additional_kwargs={"reasoning_content": "plan"})
    assert reasoning_text(message) == "plan"


def test_reasoning_text_from_summary() -> None:
    message = AIMessage(
        content=[
            {
                "type": "reasoning",
                "summary": [{"type": "summary_text", "text": "plan"}],
            }
        ]
    )
    assert reasoning_text(message) == "plan"


def test_reasoning_text_joins_summary_parts() -> None:
    message = AIMessage(
        content=[
            {
                "type": "reasoning",
                "summary": [
                    {"type": "summary_text", "text": "first"},
                    {"type": "summary_text", "text": "second"},
                ],
            }
        ]
    )
    assert reasoning_text(message) == "first\nsecond"


def test_reasoning_text_from_non_standard_thinking() -> None:
    message = AIMessage(content=[{"type": "thinking", "thinking": "plan", "signature": "s"}])
    assert reasoning_text(message) == "plan"


def test_reasoning_text_joins_multiple_blocks() -> None:
    message = AIMessage(
        content=[
            {"type": "reasoning", "reasoning": "first"},
            {"type": "reasoning", "reasoning": "second"},
        ]
    )
    assert reasoning_text(message) == "first\nsecond"


def test_reasoning_text_from_additional_kwargs() -> None:
    message = SimpleNamespace(
        content_blocks=[],
        additional_kwargs={"reasoning_content": "fallback"},
    )
    assert reasoning_text(message) == "fallback"


def test_reasoning_text_missing() -> None:
    assert reasoning_text(SimpleNamespace(content_blocks=[])) == ""


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


def test_print_update_renders_reasoning() -> None:
    console = Console(record=True, width=200, force_terminal=False)
    tool_call = SimpleNamespace(
        type="ai",
        tool_calls=[{"name": "ls", "args": {"path": "/"}}],
        content="",
        content_blocks=[{"type": "reasoning", "reasoning": "plan"}],
    )
    final = SimpleNamespace(type="ai", tool_calls=[], content="done")

    message = print_update(
        {
            "model": {"messages": [tool_call]},
            "done": {"messages": [final]},
        },
        console,
    )

    assert message is final
    text = console.export_text()
    assert "thinking" in text
    assert "plan" in text
    assert "ls" in text


def test_print_update_hides_reasoning_when_disabled() -> None:
    console = Console(record=True, width=200, force_terminal=False)
    message = SimpleNamespace(
        type="ai",
        tool_calls=[],
        content="done",
        content_blocks=[{"type": "reasoning", "reasoning": "plan"}],
    )

    print_update({"done": {"messages": [message]}}, console, show_thinking=False)

    assert "thinking" not in console.export_text()


def test_print_update_ignores_missing_reasoning() -> None:
    console = Console(record=True, width=200, force_terminal=False)
    final = SimpleNamespace(type="ai", tool_calls=[], content="done")

    message = print_update({"done": {"messages": [final]}}, console)

    assert message is final
    assert "thinking" not in console.export_text()


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


def test_parser_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MINICODE_PERMISSION_MODE", raising=False)
    monkeypatch.delenv("MINICODE_SHELL_ALLOW_LIST", raising=False)
    monkeypatch.delenv("MINICODE_AUDIT_LOG", raising=False)
    args = build_parser().parse_args(["fix", "the", "bug"])
    assert args.prompt == ["fix", "the", "bug"]
    assert args.model is None
    assert args.root == "."
    assert args.debug is False
    assert args.interactive is False
    assert args.thread is None
    assert args.db is None
    assert args.show_thinking is True
    assert args.permission_mode is PermissionMode.ASK
    assert args.shell_allow_list is None
    assert args.audit_log is None
    assert args.no_audit is False


def test_parser_no_thinking() -> None:
    assert build_parser().parse_args(["--no-thinking"]).show_thinking is False


def test_parser_permission_options() -> None:
    args = build_parser().parse_args(
        [
            "--permission-mode",
            "read-only",
            "--shell-allow-list",
            "git status,ls",
        ]
    )
    assert args.permission_mode is PermissionMode.READ_ONLY
    assert args.shell_allow_list == "git status,ls"


def test_parser_audit_options() -> None:
    args = build_parser().parse_args(["--audit-log", "logs/audit.jsonl", "--no-audit"])

    assert args.audit_log == "logs/audit.jsonl"
    assert args.no_audit is True


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
        ["--model", "deepseek:deepseek-flash", "--root", "workspace", "task"]
    )
    assert args.model == "deepseek:deepseek-flash"
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


def test_load_env_does_not_override_shell(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".env").write_text("DEEPSEEK_API_KEY=from-dotenv\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "from-shell")

    load_env()
    assert os.environ["DEEPSEEK_API_KEY"] == "from-shell"


def test_load_env_ignores_empty_values(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".env").write_text("MINICODE_MODEL=   \n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MINICODE_MODEL", raising=False)

    load_env()
    assert "MINICODE_MODEL" not in os.environ


def test_load_env_strips_whitespace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".env").write_text('DEEPSEEK_API_KEY="  sk-test  "\n', encoding="utf-8")
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
        yield {"model": {"messages": [SimpleNamespace(type="ai", tool_calls=[], content="done")]}}


class ApprovalAgent:
    def __init__(self) -> None:
        self.inputs: list[object] = []

    def stream(self, input, config=None, stream_mode=None):
        self.inputs.append(input)
        if len(self.inputs) == 1:
            yield {
                "__interrupt__": (
                    SimpleNamespace(
                        id="interrupt-1",
                        value={
                            "action_requests": [
                                {
                                    "name": "execute",
                                    "args": {"command": "echo hi"},
                                    "description": "Shell command requires approval",
                                }
                            ],
                            "review_configs": [
                                {
                                    "action_name": "execute",
                                    "allowed_decisions": ["approve", "reject"],
                                }
                            ],
                        },
                    ),
                )
            }
            return
        yield {"model": {"messages": [SimpleNamespace(type="ai", tool_calls=[], content="done")]}}


def test_run_turn_approves_interrupt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr(Console, "input", lambda self, prompt="": "y")

    agent = ApprovalAgent()
    progress = Console(file=io.StringIO(), force_terminal=False, soft_wrap=True)
    config = {"configurable": {"thread_id": "test"}}

    message = run_turn(agent, "do it", progress, config)

    assert message.content == "done"
    assert agent.inputs[0] == {"messages": [{"role": "user", "content": "do it"}]}
    assert agent.inputs[1].resume == {"decisions": [{"type": "approve"}]}
    assert "approval required" in progress.file.getvalue()
    assert "echo hi" in progress.file.getvalue()


def test_run_turn_rejects_interrupt_without_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)

    agent = ApprovalAgent()
    progress = Console(file=io.StringIO(), force_terminal=False, soft_wrap=True)
    config = {"configurable": {"thread_id": "test"}}

    message = run_turn(agent, "do it", progress, config)

    assert message.content == "done"
    assert agent.inputs[1].resume["decisions"][0]["type"] == "reject"
    assert "not a TTY" in progress.file.getvalue()
    assert "echo hi" in progress.file.getvalue()


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


def test_main_passes_sqlite_options(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    def fake_build_agent(**kwargs):
        captured["build"] = kwargs
        return object()

    def fake_loop(agent, progress, output, config, debug, show_thinking=True, audit=None):
        captured["config"] = config
        captured["show_thinking"] = show_thinking
        captured["audit"] = audit
        return 0

    monkeypatch.setattr("minicode.cli.build_agent", fake_build_agent)
    monkeypatch.setattr("minicode.cli.interactive_loop", fake_loop)

    assert main(["-i", "--root", str(tmp_path), "--db", "state.sqlite", "--thread", "work"]) == 0
    assert captured["build"]["db_path"] == "state.sqlite"
    assert captured["build"]["checkpoint"] is True
    audit = captured["build"]["audit"]
    assert audit is not None
    assert audit.path == tmp_path / ".minicode" / "audit.jsonl"
    assert audit.session_id == "work"
    assert audit.mode == "ask"
    assert captured["show_thinking"] is True
    assert captured["config"] == {"configurable": {"thread_id": "work"}}


def test_main_disables_audit_with_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    def fake_build_agent(**kwargs):
        captured["build"] = kwargs
        return object()

    def fake_loop(agent, progress, output, config, debug, show_thinking=True, audit=None):
        return 0

    monkeypatch.setattr("minicode.cli.build_agent", fake_build_agent)
    monkeypatch.setattr("minicode.cli.interactive_loop", fake_loop)

    assert main(["-i", "--root", str(tmp_path), "--no-audit"]) == 0
    assert captured["build"]["audit"] is None


def test_main_resolves_relative_audit_log_under_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict = {}

    def fake_build_agent(**kwargs):
        captured["build"] = kwargs
        return object()

    def fake_loop(agent, progress, output, config, debug, show_thinking=True, audit=None):
        return 0

    monkeypatch.setattr("minicode.cli.build_agent", fake_build_agent)
    monkeypatch.setattr("minicode.cli.interactive_loop", fake_loop)

    assert main(["-i", "--root", str(tmp_path), "--audit-log", "logs/audit.jsonl"]) == 0
    audit = captured["build"]["audit"]
    assert audit is not None
    assert audit.path == tmp_path / "logs" / "audit.jsonl"


def test_main_requires_prompt_when_not_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(""))

    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 2
