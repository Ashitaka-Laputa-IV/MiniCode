import pytest

from minicode.agent import DEFAULT_MODEL, resolve_model, resolve_root, shell_env


def test_resolve_model_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MINICODE_MODEL", raising=False)
    assert resolve_model() == DEFAULT_MODEL


def test_resolve_model_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MINICODE_MODEL", "deepseek:deepseek-reasoner")
    assert resolve_model() == "deepseek:deepseek-reasoner"


def test_resolve_model_explicit_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MINICODE_MODEL", "deepseek:deepseek-reasoner")
    assert resolve_model("openai:gpt-5.5") == "openai:gpt-5.5"


def test_resolve_root_missing(tmp_path) -> None:
    missing = tmp_path / "missing"
    with pytest.raises(ValueError, match="not a directory"):
        resolve_root(missing)


def test_resolve_root_directory(tmp_path) -> None:
    assert resolve_root(tmp_path) == tmp_path.resolve()


def test_shell_env_excludes_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret")
    monkeypatch.setenv("PATH", "bin")
    env = shell_env()
    assert "DEEPSEEK_API_KEY" not in env
    assert any(key.upper() == "PATH" for key in env)
