from app.flags import parse_bool


def test_true():
    assert parse_bool("true") is True


def test_false():
    assert parse_bool("false") is False
