from app.text import word_count


def test_basic():
    assert word_count("hello world") == 2
