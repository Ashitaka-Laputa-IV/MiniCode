from app.app import is_debug
from app.settings import debug


def test_new_name():
    assert debug is False


def test_is_debug():
    assert is_debug() is False
