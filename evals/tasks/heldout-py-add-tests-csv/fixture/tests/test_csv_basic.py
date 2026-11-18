from app.csv import parse_line


def test_plain_fields():
    assert parse_line("a,b,c") == ["a", "b", "c"]


def test_quoted_field_with_comma():
    assert parse_line('"a,b",c') == ["a,b", "c"]
