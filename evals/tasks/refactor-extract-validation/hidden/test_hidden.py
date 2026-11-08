import pytest

from app.signup import _ensure_valid_email, create_user, update_user


def test_helper_accepts_valid():
    assert _ensure_valid_email("a@b.com") is None


def test_helper_rejects_invalid():
    with pytest.raises(ValueError):
        _ensure_valid_email("bad")


def test_update_rejects_invalid():
    with pytest.raises(ValueError):
        update_user({"email": "a@b.com"}, "bad")
