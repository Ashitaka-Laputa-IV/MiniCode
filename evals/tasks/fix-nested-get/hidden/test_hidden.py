from app.config import get_path


def test_missing_returns_default():
    assert get_path({"a": {"b": 2}}, "a.c", "fallback") == "fallback"


def test_deep_path():
    data = {"a": {"b": {"c": 3}}}
    assert get_path(data, "a.b.c") == 3
