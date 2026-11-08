from pathlib import Path

import pytest

from minicode.evals.runner import cost_for, load_suite, summarize, verification_env


def test_smoke_suite_has_twenty_tasks() -> None:
    tasks = load_suite("smoke")
    assert len(tasks) == 20
    assert len({task.id for task in tasks}) == 20
    assert all((task.path / "prompt.md").exists() for task in tasks)
    assert all((task.path / "fixture").is_dir() for task in tasks)
    assert all(task.hidden_tests or task.verify_script for task in tasks)
    for task in tasks:
        if task.hidden_tests is not None:
            assert task.hidden_tests.is_dir()
        if task.verify_script is not None:
            assert task.verify_script.is_file()


def test_verify_env_excludes_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret")
    env = verification_env(tmp_path)
    assert "DEEPSEEK_API_KEY" not in env
    assert str(tmp_path) in env["PYTHONPATH"]


def test_cost_uses_pricing() -> None:
    pricing = {
        "model": {
            "input_per_million": 1.0,
            "output_per_million": 2.0,
        }
    }
    usage = {"input_tokens": 1_000_000, "output_tokens": 500_000}
    assert cost_for("model", usage, pricing) == 2.0


def test_summarize() -> None:
    results = [
        {
            "passed": True,
            "tool_calls": 2,
            "usage": {"input_tokens": 10, "output_tokens": 5},
            "cost_usd": 0.01,
            "duration_s": 1.5,
        },
        {
            "passed": False,
            "tool_calls": 4,
            "usage": {"input_tokens": 20, "output_tokens": 10},
            "cost_usd": 0.02,
            "duration_s": 2.5,
        },
    ]
    summary = summarize(results)
    assert summary["tasks"] == 2
    assert summary["passed"] == 1
    assert summary["pass_at_1"] == 0.5
    assert summary["avg_tool_calls"] == 3.0
    assert summary["input_tokens"] == 30
    assert summary["cost_usd"] == 0.03
    assert summary["wall_time_s"] == 4.0
