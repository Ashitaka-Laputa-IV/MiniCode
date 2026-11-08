import subprocess
import sys


def run(*args):
    return subprocess.run(
        [sys.executable, "-m", "app.cli", *args],
        capture_output=True,
        text=True,
    )


def test_upper():
    proc = run("--upper", "hello")
    assert proc.returncode == 0
    assert proc.stdout.strip() == "HELLO"


def test_default():
    proc = run("hello")
    assert proc.returncode == 0
    assert proc.stdout.strip() == "hello"
