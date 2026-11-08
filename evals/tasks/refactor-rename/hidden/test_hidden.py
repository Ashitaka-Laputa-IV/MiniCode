from app.inventory import total
from app.report import summary


def test_new_name():
    assert total({"a": 4, "b": 1}) == 5


def test_report_uses_new_name():
    assert summary({"a": 4}) == "total=4"
