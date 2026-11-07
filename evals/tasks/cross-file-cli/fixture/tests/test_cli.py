from app.cli import main


def test_default():
    assert main(["hello"]) == 0
