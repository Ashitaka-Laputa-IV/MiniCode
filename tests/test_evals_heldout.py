import tomllib
from collections import Counter

from minicode.evals import runner
from minicode.evals.runner import load_suite

REAL_TASK_ID = "heldout-real-requests-link-header"


def test_heldout_suite_has_expected_size_and_unique_ids() -> None:
    tasks = load_suite("heldout")
    ids = [task.id for task in tasks]

    assert 20 <= len(tasks) <= 30
    assert len(tasks) == 20
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
        assert task.hidden_tests is not None or task.verify_script is not None
        assert task.max_tool_calls <= 20

        if task.hidden_tests is not None:
            assert task.hidden_tests.is_dir()
            assert any(task.hidden_tests.iterdir())
        if task.verify_script is not None:
            assert task.verify_script.is_file()

        assert hidden.resolve() not in fixture.resolve().parents
        assert fixture.resolve() not in hidden.resolve().parents
        assert not (fixture / "hidden").exists()
        assert not list(fixture.rglob("test_hidden.*"))
        assert not list(fixture.rglob("test_hidden"))


def test_heldout_covers_python_javascript_and_required_categories() -> None:
    tasks = load_suite("heldout")

    categories = Counter(task.category for task in tasks)
    assert {"bugfix", "cross-file", "add-tests", "refactor"} == set(categories)
    assert categories["bugfix"] >= 5
    assert categories["cross-file"] >= 5
    assert categories["add-tests"] >= 3
    assert categories["refactor"] >= 5

    javascript_tasks = [
        task for task in tasks if (task.path / "fixture" / "package.json").is_file()
    ]
    python_tasks = [task for task in tasks if task not in javascript_tasks]

    assert len(python_tasks) == 11
    assert len(javascript_tasks) == 9
    assert len(python_tasks) + len(javascript_tasks) == len(tasks)
    assert all(task.hidden_tests is not None for task in python_tasks)
    assert all((task.path / "hidden").is_dir() for task in javascript_tasks)
    assert all(task.verify_script is not None for task in javascript_tasks)

    for task in javascript_tasks:
        assert task.verify_script is not None
        script = task.verify_script.read_text(encoding="utf-8")
        assert "node" in script
        assert "npm" not in script
        assert any((task.path / "hidden").glob("*.mjs"))


def test_real_requests_fixture_has_provenance_and_license() -> None:
    task = next(task for task in load_suite("heldout") if task.id == REAL_TASK_ID)

    provenance = (task.path / "PROVENANCE.md").read_text(encoding="utf-8")
    assert "psf/requests" in provenance
    assert "v2.4.3" in provenance
    assert "46d646064ca0836a7d7b4d50ea2c762d12ff8ce1" in provenance
    assert "Apache" in provenance
    assert "https://github.com/psf/requests/issues/2250" in provenance
    assert "https://raw.githubusercontent.com/psf/requests/v2.4.3/requests/utils.py" in provenance
    assert "parse_header_links" in provenance

    license_text = (task.path / "LICENSE").read_text(encoding="utf-8")
    assert "Apache License" in license_text
    assert "Version 2.0" in license_text

    fixture_source = (task.path / "fixture" / "linkheader.py").read_text(encoding="utf-8")
    assert "Apache License" in fixture_source
    assert "def parse_header_links" in fixture_source
    assert "split" in fixture_source

    assert task.hidden_tests is not None
    hidden = (task.hidden_tests / "test_hidden.py").read_text(encoding="utf-8")
    assert "a,b" in hidden
    assert "https://example.com/a,b" in hidden
    assert "len(links) == 2" in hidden
