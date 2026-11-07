import subprocess
import sys


def test_import_is_silent():
    proc = subprocess.run(
        [sys.executable, "-c", "import app.cli"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""


def test_module_still_runs():
    proc = subprocess.run(
        [sys.executable, "-m", "app.cli"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert proc.stdout.strip() == "hello"
