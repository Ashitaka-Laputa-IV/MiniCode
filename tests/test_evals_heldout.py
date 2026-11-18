import tomllib

from minicode.evals import runner
from minicode.evals.runner import load_suite


def test_heldout_suite_has_expected_size_and_unique_ids() -> None:
    tasks = load_suite("heldout")
    ids = [task.id for task in tasks]

    assert 6 <= len(tasks) <= 8
    assert len(ids) == len(set(ids))
    assert all(task_id.startswith("heldout-") for task_id in ids)

    suite = tomllib.loads((runner.SUITES_DIR / "heldout.toml").read_text(encoding="utf-8"))
    assert suite["name"] == "heldout"
    assert suite["tasks"] == ids


def test_heldout_suite_is_separate_from_smoke() -> None:
    heldout = load_suite("heldout")
    smoke = load_suite("smoke")

    heldout_ids = {task.id for task in heldout}
    smoke_ids = {task.id for task in smoke}

    assert heldout_ids.isdisjoint(smoke_ids)
    assert len(smoke) == 20


def test_heldout_tasks_have_required_files() -> None:
    for task in load_suite("heldout"):
        fixture = task.path / "fixture"
        hidden = task.path / "hidden"

        assert (task.path / "task.toml").is_file()
        assert task.prompt_file.is_file()
        assert task.prompt_file.read_text(encoding="utf-8").strip()
        assert fixture.is_dir()
        assert hidden.is_dir()
        assert any(hidden.iterdir())
        assert (
            task.hidden_tests is not None or task.verify_script is not None or task.verify_command
        )
        assert task.max_tool_calls <= 20

        if task.hidden_tests is not None:
            assert task.hidden_tests.is_dir()
        if task.verify_script is not None:
            assert task.verify_script.is_file()

        assert hidden.resolve() not in fixture.resolve().parents
        assert fixture.resolve() not in hidden.resolve().parents
        assert not list(fixture.rglob("test_hidden.*"))


def test_heldout_covers_python_javascript_and_required_categories() -> None:
    tasks = load_suite("heldout")

    assert {"bugfix", "cross-file", "add-tests", "refactor"} <= {task.category for task in tasks}

    python_tasks = [task for task in tasks if (task.path / "fixture" / "app").is_dir()]
    javascript_tasks = [
        task for task in tasks if (task.path / "fixture" / "package.json").is_file()
    ]

    assert 4 <= len(python_tasks) <= 5
    assert 2 <= len(javascript_tasks) <= 3
    assert len(python_tasks) + len(javascript_tasks) == len(tasks)
    assert all(task.hidden_tests is not None for task in python_tasks)
    assert all(task.verify_script is not None for task in javascript_tasks)

    for task in javascript_tasks:
        assert task.verify_script is not None
        script = task.verify_script.read_text(encoding="utf-8")
        assert "node" in script
        assert "npm" not in script
