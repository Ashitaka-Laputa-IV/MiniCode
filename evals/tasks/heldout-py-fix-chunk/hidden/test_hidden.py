from app.chunks import chunk


def test_trailing_partial_chunk():
    assert chunk([1, 2, 3], 2) == [[1, 2], [3]]


def test_partial_chunk_when_longer():
    assert chunk("abcde", 2) == ["ab", "cd", "e"]


def test_single_chunk_larger_than_input():
    assert chunk([1, 2], 5) == [[1, 2]]


def test_exact_multiple_is_unchanged():
    assert chunk([1, 2, 3, 4, 5, 6], 3) == [[1, 2, 3], [4, 5, 6]]


def test_empty_input():
    assert chunk([], 2) == []
