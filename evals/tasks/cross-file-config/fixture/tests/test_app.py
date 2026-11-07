from app.app import is_debug
from app.settings import DEBUG


def test_default():
    assert DEBUG is False
    assert is_debug() is False
