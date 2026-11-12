from datetime import date


def format_date(value):
    return value.isoformat()


def parse_date(value):
    return date.fromisoformat(value)
