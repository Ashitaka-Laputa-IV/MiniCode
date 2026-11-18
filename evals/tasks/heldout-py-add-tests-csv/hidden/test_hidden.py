import subprocess
import sys
from pathlib import Path

from app.csv import parse_line


def test_regression_file_exists_with_five_tests():
    test_file = Path.cwd() / "tests" / "test_csv.py"
    assert test_file.is_file(), "tests/test_csv.py was not created"
    text = test_file.read_text(encoding="utf-8")
    assert text.count("def test_") >= 5
    assert text.count("parse_line(") >= 5


def test_regression_file_passes():
    test_file = Path.cwd() / "tests" / "test_csv.py"
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            str(test_file),
        ],
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_quoted_comma_is_one_field():
    assert parse_line('"a,b",c') == ["a,b", "c"]


def test_escaped_quote_inside_field():
    assert parse_line('"say ""hi""",x') == ['say "hi"', "x"]


def test_empty_fields_are_preserved():
    assert parse_line("a,,c,") == ["a", "", "c", ""]
    assert parse_line(",,") == ["", "", ""]


def test_spaces_are_preserved():
    assert parse_line(" a , b ") == [" a ", " b "]


def test_mixed_quoted_and_unquoted_fields():
    assert parse_line('one,"two,three","four ""five"""') == [
        "one",
        "two,three",
        'four "five"',
    ]
