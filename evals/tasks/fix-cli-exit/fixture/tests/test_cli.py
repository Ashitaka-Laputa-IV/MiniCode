from app.cli import main


def test_default():
    assert main([]) == 0
