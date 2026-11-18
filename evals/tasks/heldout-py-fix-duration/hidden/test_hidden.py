import pytest

from app.duration import parse_duration


def test_hours_and_minutes():
    assert parse_duration("1h30m") == 5400


def test_minutes_and_seconds():
    assert parse_duration("2m15s") == 135


def test_all_three_components():
    assert parse_duration("1h2m3s") == 3723


def test_zero_and_single_components_are_unchanged():
    assert parse_duration("0s") == 0
    assert parse_duration("45s") == 45
    assert parse_duration("2m") == 120
    assert parse_duration("3h") == 10800


def test_surrounding_whitespace_is_allowed():
    assert parse_duration("  10m  ") == 600
    assert parse_duration(" 1h 30m ") == 5400


@pytest.mark.parametrize("value", ["10m30", "10x", "", "soon", "1h2x", "1 h"])
def test_invalid_input_still_raises(value):
    with pytest.raises(ValueError):
        parse_duration(value)
