import sys
from types import ModuleType, SimpleNamespace

import pytest

from minicode.audit import AuditError, audit_hint, start_audit


def install_fake_tracekit(monkeypatch: pytest.MonkeyPatch, instrument) -> None:
    module = ModuleType("tracekit")
    module.instrument = instrument  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "tracekit", module)


def test_start_audit_calls_instrument(monkeypatch: pytest.MonkeyPatch) -> None:
    run = SimpleNamespace(run_id="run-1")
    calls: list[object] = []

    def instrument():
        calls.append(run)
        return run

    install_fake_tracekit(monkeypatch, instrument)

    assert start_audit() is run
    assert calls == [run]


def test_start_audit_missing_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "tracekit", None)

    with pytest.raises(AuditError, match="not installed"):
        start_audit()


def test_start_audit_wraps_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def instrument():
        raise RuntimeError("signer is down")

    install_fake_tracekit(monkeypatch, instrument)

    with pytest.raises(AuditError, match="signer is down"):
        start_audit()


def test_start_audit_requires_an_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_tracekit(monkeypatch, lambda: None)

    with pytest.raises(AuditError, match="did not wire"):
        start_audit()


def test_audit_hint_includes_run_id() -> None:
    assert audit_hint(SimpleNamespace(run_id="run-1")) == (
        "audit run recorded (run run-1); verify with: tracekit last"
    )


def test_audit_hint_without_run_id() -> None:
    assert audit_hint(object()) == "audit run recorded; verify with: tracekit last"
