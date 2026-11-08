import pytest

from app.signup import create_user, update_user


def test_create():
    assert create_user("a@b.com") == {"email": "a@b.com"}


def test_update():
    user = {"email": "a@b.com"}
    assert update_user(user, "c@d.com")["email"] == "c@d.com"


def test_invalid():
    with pytest.raises(ValueError):
        create_user("bad")
