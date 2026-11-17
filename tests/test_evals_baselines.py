import pytest

from minicode.evals.baselines import (
    MATRIX_BASELINES,
    resolve_baseline,
    resolve_baselines,
)


def test_full_is_an_alias_for_minicode_yolo() -> None:
    baseline = resolve_baseline("full")

    assert baseline.name == "minicode-yolo"
    assert baseline.permission_mode == "yolo"
    assert baseline.checkpoint is True


def test_all_expands_to_legacy_full_and_bare() -> None:
    assert resolve_baselines(["all"]) == ["full", "bare"]


def test_matrix_expands_to_all_coding_baselines() -> None:
    assert resolve_baselines(["matrix"]) == MATRIX_BASELINES


def test_baselines_are_deduplicated() -> None:
    assert resolve_baselines(["full", "full", "bare"]) == ["full", "bare"]


def test_unknown_baseline_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown baseline"):
        resolve_baseline("does-not-exist")
