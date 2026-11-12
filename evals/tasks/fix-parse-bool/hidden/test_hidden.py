import pytest

from app.flags import parse_bool


@pytest.mark.parametrize("value", ["1", "yes", "on", "TRUE"])
def test_truthy(value):
    assert parse_bool(value) is True


@pytest.mark.parametrize("value", ["0", "no", "off", "FALSE"])
def test_falsy(value):
    assert parse_bool(value) is False


def test_invalid():
    with pytest.raises(ValueError):
        parse_bool("maybe")
