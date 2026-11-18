import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from app.csv import parse_line

EXPECTED_CSV_SHA256 = (
    "0389f765b73eb6199c02116d893c0234e0815a6ae56c3118ca1ba03e089b9514"
)
MUTATIONS = {
    "comma_inside_quotes": (
        'elif char == "," and not in_quotes:',
        'elif char == ",":',
    ),
    "escaped_quote": (
        'if in_quotes and index + 1 < len(line) and line[index + 1] == \'"\':',
        "if False:",
    ),
    "empty_fields": (
        'fields.append("".join(current))',
        'if current:\n            fields.append("".join(current))',
    ),
    "space_preservation": (
        "current.append(char)",
        "current.append(char.strip())",
    ),
}


def _normalized_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _run_agent_tests(base: Path) -> subprocess.CompletedProcess[str]:
    ini = base / "pytest.ini"
    ini.write_text("[pytest]\n", encoding="utf-8")
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        [str(base), env.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "-c",
            str(ini),
            "--rootdir",
            str(base),
            "--confcutdir",
            str(base),
            "tests/test_csv.py",
        ],
        cwd=base,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )


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


def test_csv_source_is_unchanged():
    source = Path.cwd() / "app" / "csv.py"
    assert _normalized_hash(source) == EXPECTED_CSV_SHA256


def test_agent_tests_detect_csv_mutations():
    workspace = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        shutil.copytree(workspace / "app", base / "app")
        shutil.copytree(workspace / "tests", base / "tests")
        original = (base / "app" / "csv.py").read_text(encoding="utf-8")
        for behavior, (old, new) in MUTATIONS.items():
            mutated = original.replace(old, new, 1)
            assert mutated != original, f"{behavior}: mutation anchor not found"
            (base / "app" / "csv.py").write_text(mutated, encoding="utf-8")
            proc = _run_agent_tests(base)
            assert proc.returncode != 0, (
                f"{behavior}: agent tests did not catch the mutation\n"
                + proc.stdout
                + proc.stderr
            )
        (base / "app" / "csv.py").write_text(original, encoding="utf-8")


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
