import os
from pathlib import Path

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver

from minicode.agent import (
    DEFAULT_CHECKPOINT_DB,
    DEFAULT_MODEL,
    build_agent,
    resolve_db_path,
    resolve_model,
    resolve_root,
    shell_env,
    shell_hint,
)


def test_resolve_model_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MINICODE_MODEL", raising=False)
    assert resolve_model() == DEFAULT_MODEL


def test_resolve_model_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MINICODE_MODEL", "deepseek:deepseek-reasoner")
    assert resolve_model() == "deepseek:deepseek-reasoner"


def test_resolve_model_explicit_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MINICODE_MODEL", "deepseek:deepseek-reasoner")
    assert resolve_model("openai:gpt-5.5") == "openai:gpt-5.5"


def test_resolve_model_empty_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MINICODE_MODEL", raising=False)
    assert resolve_model("") == DEFAULT_MODEL


def test_resolve_root_missing(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    with pytest.raises(ValueError, match="not a directory"):
        resolve_root(missing)


def test_build_agent_rejects_missing_root(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    with pytest.raises(ValueError, match="not a directory"):
        build_agent(root=missing)


def test_build_agent_checkpointer_is_optional(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr("minicode.agent.create_deep_agent", fake_create)

    build_agent(root=tmp_path)
    assert captured["checkpointer"] is None

    build_agent(root=tmp_path, checkpoint=True)
    checkpointer = captured["checkpointer"]
    assert isinstance(checkpointer, SqliteSaver)
    assert (tmp_path / DEFAULT_CHECKPOINT_DB).exists()
    checkpointer.conn.close()


def test_resolve_db_path_default(tmp_path: Path) -> None:
    assert resolve_db_path(tmp_path) == tmp_path / DEFAULT_CHECKPOINT_DB


def test_resolve_db_path_relative_to_root(tmp_path: Path) -> None:
    assert resolve_db_path(tmp_path, "state/agent.sqlite") == (
        tmp_path / "state/agent.sqlite"
    )


def test_resolve_db_path_absolute(tmp_path: Path) -> None:
    db = tmp_path / "custom.sqlite"
    assert resolve_db_path(tmp_path / "workspace", db) == db


def test_resolve_db_path_rejects_memory(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=":memory:"):
        resolve_db_path(tmp_path, ":memory:")


def test_resolve_root_directory(tmp_path: Path) -> None:
    assert resolve_root(tmp_path) == tmp_path.resolve()


def test_shell_env_excludes_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret")
    monkeypatch.setenv("PATH", "bin")
    env = shell_env()
    assert "DEEPSEEK_API_KEY" not in env
    assert any(key.upper() == "PATH" for key in env)


def test_shell_hint_matches_platform() -> None:
    hint = shell_hint()
    if os.name == "nt":
        assert "cmd.exe" in hint
    else:
        assert "POSIX" in hint
