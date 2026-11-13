import sys
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from minicode.relay import RelayError, RelaySession


class FakeActivation:
    def __init__(self, state: list[str]) -> None:
        self.state = state

    async def __aenter__(self):
        self.state.append("enter")
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        self.state.append("exit")


class FailingActivation:
    async def __aenter__(self):
        raise RuntimeError("no signer")

    async def __aexit__(self, exc_type, exc, traceback):
        return None


def install_fake_nemo_relay(
    monkeypatch: pytest.MonkeyPatch,
    state: list[str],
    activation=None,
) -> None:
    @contextmanager
    def fake_scope(name, scope_type):
        state.append(f"scope:{name}:{scope_type}")
        yield

    nemo = ModuleType("nemo_relay")
    nemo.plugin = SimpleNamespace(  # type: ignore[attr-defined]
        activate=activation or (lambda config, plugins: FakeActivation(state))
    )
    nemo.subscribers = SimpleNamespace(  # type: ignore[attr-defined]
        flush=lambda: state.append("flush")
    )
    nemo.scope = SimpleNamespace(scope=fake_scope)  # type: ignore[attr-defined]
    nemo.ScopeType = SimpleNamespace(Agent="agent")  # type: ignore[attr-defined]

    integrations = ModuleType("nemo_relay.integrations")
    deepagents = ModuleType("nemo_relay.integrations.deepagents")
    deepagents.NemoRelayDeepAgentsCallbackHandler = lambda: "handler"  # type: ignore[attr-defined]
    integrations.deepagents = deepagents  # type: ignore[attr-defined]
    nemo.integrations = integrations  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "nemo_relay", nemo)
    monkeypatch.setitem(sys.modules, "nemo_relay.integrations", integrations)
    monkeypatch.setitem(sys.modules, "nemo_relay.integrations.deepagents", deepagents)


def test_config_uses_workspace_events_file(tmp_path: Path) -> None:
    config = RelaySession(root=tmp_path).config()
    component = config["components"][0]
    sink = component["config"]["atof"]["sinks"][0]

    assert component["kind"] == "observability"
    assert component["config"]["enable_full_payloads"] is False
    assert sink["output_directory"] == str(tmp_path / ".minicode" / "relay")
    assert sink["filename"] == "events.jsonl"
    assert sink["mode"] == "append"


def test_start_and_close_plugin_host(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state: list[str] = []
    install_fake_nemo_relay(monkeypatch, state)
    session = RelaySession(root=tmp_path)

    session.start()
    assert state == ["enter"]
    assert (tmp_path / ".minicode" / "relay").is_dir()

    session.close()
    assert state == ["enter", "flush", "exit"]


def test_start_requires_nemo_relay(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setitem(sys.modules, "nemo_relay", None)

    with pytest.raises(RelayError, match="not installed"):
        RelaySession(root=tmp_path).start()


def test_start_reports_activation_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state: list[str] = []
    install_fake_nemo_relay(
        monkeypatch,
        state,
        activation=lambda config, plugins: FailingActivation(),
    )

    with pytest.raises(RelayError, match="no signer"):
        RelaySession(root=tmp_path).start()


def test_default_start_passes_inline_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict = {}

    def activate(config, plugins):
        seen["config"] = config
        seen["plugins"] = plugins
        return FakeActivation([])

    install_fake_nemo_relay(monkeypatch, [], activation=activate)
    session = RelaySession(root=tmp_path)

    session.start()
    session.close()

    assert seen["plugins"] is None
    assert seen["config"]["components"][0]["kind"] == "observability"


def test_custom_plugins_replace_inline_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict = {}

    def activate(config, plugins):
        seen["config"] = config
        seen["plugins"] = plugins
        return FakeActivation([])

    install_fake_nemo_relay(monkeypatch, [], activation=activate)
    session = RelaySession(root=tmp_path, plugins="custom.toml")

    session.start()
    session.close()

    assert seen["plugins"] == "custom.toml"
    assert seen["config"] == {}


def test_attach_preserves_existing_callbacks(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_nemo_relay(monkeypatch, [])
    session = RelaySession(root=".")
    config = {"configurable": {"thread_id": "test"}, "callbacks": ["existing"]}

    attached = session.attach(config)

    assert attached["callbacks"] == ["existing", "handler"]
    assert config["callbacks"] == ["existing"]


def test_turn_wraps_an_agent_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    state: list[str] = []
    install_fake_nemo_relay(monkeypatch, state)
    session = RelaySession(root=".")

    with session.turn("demo"):
        pass

    assert state == ["scope:demo:agent"]


def test_close_before_start_is_a_noop() -> None:
    RelaySession(root=".").close()
