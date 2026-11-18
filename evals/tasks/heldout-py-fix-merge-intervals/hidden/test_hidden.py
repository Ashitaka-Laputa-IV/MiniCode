from app.intervals import merge_intervals


def test_touching_intervals_are_merged():
    assert merge_intervals([(1, 3), (3, 5)]) == [(1, 5)]


def test_touching_chain_is_merged():
    assert merge_intervals([(1, 2), (2, 3), (3, 4)]) == [(1, 4)]


def test_unsorted_touching_intervals_are_merged():
    assert merge_intervals([(4, 5), (1, 2), (2, 3)]) == [(1, 3), (4, 5)]


def test_nested_interval_is_absorbed():
    assert merge_intervals([(1, 10), (2, 3)]) == [(1, 10)]


def test_overlapping_and_touching_mix():
    assert merge_intervals([(5, 7), (1, 3), (3, 4), (6, 9)]) == [(1, 4), (5, 9)]


def test_duplicate_and_single_intervals():
    assert merge_intervals([(2, 4), (2, 4)]) == [(2, 4)]
    assert merge_intervals([(7, 8)]) == [(7, 8)]


def test_empty_and_disjoint_inputs_stay_unchanged():
    assert merge_intervals([]) == []
    assert merge_intervals([(1, 2), (4, 5)]) == [(1, 2), (4, 5)]
