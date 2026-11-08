from app.inventory import calc_total


def test_total():
    assert calc_total({"a": 2, "b": 3}) == 5
