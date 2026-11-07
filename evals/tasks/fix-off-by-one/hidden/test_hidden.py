from app.range_sum import inclusive_sum


def test_single():
    assert inclusive_sum(1) == 1


def test_five():
    assert inclusive_sum(5) == 15


def test_zero():
    assert inclusive_sum(0) == 0
