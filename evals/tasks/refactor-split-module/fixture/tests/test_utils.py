from datetime import date

from app.utils import format_date, parse_date


def test_format():
    assert format_date(date(2024, 1, 2)) == "2024-01-02"


def test_parse():
    assert parse_date("2024-01-02") == date(2024, 1, 2)
