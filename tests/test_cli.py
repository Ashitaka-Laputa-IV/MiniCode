import os
from pathlib import Path

import pytest

from minicode.cli import build_parser, load_env, message_text, short_json


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


def test_parser_defaults() -> None:
    args = build_parser().parse_args(["fix", "the", "bug"])
    assert args.prompt == ["fix", "the", "bug"]
    assert args.model is None
    assert args.root == "."
    assert args.debug is False


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
