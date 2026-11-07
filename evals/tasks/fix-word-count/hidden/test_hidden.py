from app.text import word_count


def test_multiple_spaces():
    assert word_count("hello   world") == 2


def test_newline():
    assert word_count("hello,  world\nagain") == 3


def test_empty():
    assert word_count("   ") == 0
