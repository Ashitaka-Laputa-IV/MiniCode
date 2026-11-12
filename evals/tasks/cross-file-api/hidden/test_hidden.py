from app.greet import greet
from app.main import run


def test_default_punctuation():
    assert greet("Ada") == "Hello, Ada!"


def test_custom_punctuation():
    assert greet("Ada", "?") == "Hello, Ada?"


def test_run():
    assert run() == "Hello, Ada!"
