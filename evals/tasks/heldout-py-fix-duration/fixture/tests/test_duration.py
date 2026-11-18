import pytest

from app.duration import parse_duration


def test_single_component():
    assert parse_duration("45s") == 45
    assert parse_duration("2m") == 120
    assert parse_duration("3h") == 10800


def test_invalid_input_raises():
    with pytest.raises(ValueError):
        parse_duration("soon")
