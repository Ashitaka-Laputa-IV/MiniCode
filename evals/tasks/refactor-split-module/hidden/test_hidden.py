from datetime import date

from app.dates import format_date, parse_date
from app.report import summary


def test_new_module():
    assert format_date(date(2025, 5, 6)) == "2025-05-06"
    assert parse_date("2025-05-06") == date(2025, 5, 6)


def test_report():
    assert summary(date(2025, 5, 6)) == "date=2025-05-06"
