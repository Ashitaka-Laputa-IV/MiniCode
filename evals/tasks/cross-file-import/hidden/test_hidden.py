from app.io import parse
from app.main import run


def test_new_module():
    assert parse("  Hello ") == "hello"


def test_run():
    assert run("  Hello ") == "hello"
