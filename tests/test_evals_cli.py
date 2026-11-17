import json
from pathlib import Path

import pytest

from minicode.evals import cli
from minicode.evals.baselines import MATRIX_BASELINES


def make_report(
    passed: int,
    tasks: int,
    *,
    baseline: str = "full",
    work_dir: str | None = None,
) -> dict:
    return {
        "suite": "smoke",
        "model": "test-model",
        "started_at": "2026-01-01T00:00:00+00:00",
        "baselines": {baseline: {"passed": passed, "tasks": tasks}},
        "tasks": [],
        "work_dir": work_dir,
    }


def run_main(monkeypatch: pytest.MonkeyPatch, report: dict, argv: list[str] | None = None):
    calls: dict = {}
    monkeypatch.setattr(cli, "load_env", lambda: None)
    monkeypatch.setattr(cli, "resolve_model", lambda model=None: model or "test-model")
    monkeypatch.setattr(cli, "print_report", lambda result: calls.setdefault("report", result))

    def fake_run_suite(**kwargs):
        calls.update(kwargs)
        return report

    monkeypatch.setattr(cli, "run_suite", fake_run_suite)
    code = cli.main(argv or [])
    return code, calls


def test_parser_defaults() -> None:
    args = cli.build_parser().parse_args([])
    assert args.suite == "smoke"
    assert args.baseline == "full"
    assert args.runs == 1
    assert args.model is None
    assert args.task is None
    assert args.json is None
    assert args.keep is False


def test_parser_repeatable_task_and_choices() -> None:
    args = cli.build_parser().parse_args(
        [
            "--suite",
            "custom",
            "--baseline",
            "all",
            "--model",
            "deepseek:deepseek-flash",
            "--task",
            "one",
            "--task",
            "two",
            "--json",
            "report.json",
            "--keep",
        ]
    )
    assert args.suite == "custom"
    assert args.baseline == "all"
    assert args.model == "deepseek:deepseek-flash"
    assert args.task == ["one", "two"]
    assert args.json == "report.json"
    assert args.keep is True


def test_main_full_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    code, calls = run_main(monkeypatch, make_report(1, 1))

    assert code == 0
    assert calls["suite"] == "smoke"
    assert calls["model"] == "test-model"
    assert calls["baselines"] == ["full"]
    assert calls["task_ids"] is None
    assert calls["keep"] is False
    assert calls["report"]["baselines"]["full"]["passed"] == 1


def test_main_full_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    code, _ = run_main(monkeypatch, make_report(0, 1))
    assert code == 1


def test_main_bare_failure_is_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    code, calls = run_main(monkeypatch, make_report(0, 1, baseline="bare"), ["--baseline", "bare"])

    assert code == 0
    assert calls["baselines"] == ["bare"]


def test_main_all_uses_full_for_exit_code(monkeypatch: pytest.MonkeyPatch) -> None:
    report = make_report(1, 1)
    report["baselines"]["bare"] = {"passed": 0, "tasks": 1}
    code, calls = run_main(monkeypatch, report, ["--baseline", "all"])

    assert code == 0
    assert calls["baselines"] == ["full", "bare"]


def test_main_writes_json_and_keeps_work_dir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    work_dir = tmp_path / "work"
    output = tmp_path / "nested" / "report.json"
    code, calls = run_main(
        monkeypatch,
        make_report(1, 1, work_dir=str(work_dir)),
        ["--json", str(output), "--keep"],
    )

    assert code == 0
    assert calls["keep"] is True
    assert json.loads(output.read_text(encoding="utf-8"))["suite"] == "smoke"
    captured = capsys.readouterr()
    assert "report:" in captured.out
    assert "work dir:" in captured.out


def test_main_matrix_and_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    code, calls = run_main(
        monkeypatch,
        make_report(1, 1),
        ["--baseline", "matrix", "--runs", "2"],
    )

    assert code == 0
    assert calls["baselines"] == MATRIX_BASELINES
    assert calls["runs"] == 2


def test_main_empty_summary_fails_for_non_bare(monkeypatch: pytest.MonkeyPatch) -> None:
    report = make_report(0, 0)
    report["baselines"]["full"] = {}

    code, _ = run_main(monkeypatch, report)

    assert code == 1


def test_main_empty_summary_is_zero_for_bare(monkeypatch: pytest.MonkeyPatch) -> None:
    report = make_report(0, 0, baseline="bare")
    report["baselines"]["bare"] = {}

    code, _ = run_main(monkeypatch, report, ["--baseline", "bare"])

    assert code == 0


def test_main_runs_two_all_passed(monkeypatch: pytest.MonkeyPatch) -> None:
    report = make_report(4, 2)
    report["runs"] = 2
    report["baselines"]["full"]["runs"] = 4

    code, calls = run_main(monkeypatch, report, ["--runs", "2"])

    assert code == 0
    assert calls["runs"] == 2


def test_main_rejects_non_positive_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "load_env", lambda: None)

    with pytest.raises(SystemExit):
        cli.main(["--runs", "0"])


def test_security_suite_requires_ask(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "load_env", lambda: None)
    monkeypatch.setattr(cli, "resolve_model", lambda model=None: model or "test-model")

    with pytest.raises(SystemExit, match="minicode-ask"):
        cli.main(["--suite", "security"])


def test_security_suite_dispatches_with_ask(monkeypatch: pytest.MonkeyPatch) -> None:
    report = {
        "suite": "security",
        "summary": {"total": 1, "failed": 0},
        "work_dir": None,
    }
    calls: dict = {}
    monkeypatch.setattr(cli, "load_env", lambda: None)
    monkeypatch.setattr(cli, "resolve_model", lambda model=None: model or "test-model")
    monkeypatch.setattr(
        cli,
        "run_security_suite",
        lambda **kwargs: calls.update(kwargs) or report,
    )
    monkeypatch.setattr(cli, "print_security_report", lambda result: None)

    code = cli.main(["--suite", "security", "--baseline", "minicode-ask"])

    assert code == 0
    assert calls["model"] == "test-model"
    assert calls["runs"] == 1


def test_security_suite_failure_exits_nonzero(monkeypatch: pytest.MonkeyPatch) -> None:
    report = {
        "suite": "security",
        "summary": {"total": 1, "failed": 1},
        "work_dir": None,
    }
    monkeypatch.setattr(cli, "load_env", lambda: None)
    monkeypatch.setattr(cli, "resolve_model", lambda model=None: model or "test-model")
    monkeypatch.setattr(cli, "run_security_suite", lambda **kwargs: report)
    monkeypatch.setattr(cli, "print_security_report", lambda result: None)

    code = cli.main(["--suite", "security", "--baseline", "minicode-ask"])

    assert code == 1
