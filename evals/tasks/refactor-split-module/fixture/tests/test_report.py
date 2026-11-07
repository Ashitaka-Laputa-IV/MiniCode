from datetime import date

from app.report import summary


def test_summary():
    assert summary(date(2024, 1, 2)) == "date=2024-01-02"
