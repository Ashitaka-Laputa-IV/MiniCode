from app.intervals import merge_intervals


def test_overlapping_intervals_are_merged():
    assert merge_intervals([(1, 4), (2, 5)]) == [(1, 5)]


def test_disjoint_intervals_are_kept():
    assert merge_intervals([(1, 2), (4, 5)]) == [(1, 2), (4, 5)]


def test_empty_input():
    assert merge_intervals([]) == []
