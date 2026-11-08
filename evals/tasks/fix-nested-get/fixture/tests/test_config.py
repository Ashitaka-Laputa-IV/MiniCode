from app.config import get_path


def test_flat():
    assert get_path({"a": 1}, "a") == 1


def test_nested():
    assert get_path({"a": {"b": 2}}, "a.b") == 2
