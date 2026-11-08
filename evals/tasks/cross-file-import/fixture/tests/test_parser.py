from app.parser import parse


def test_parse():
    assert parse("  Hello ") == "hello"
