import subprocess
import sys


def test_unknown_option_exits_two():
    proc = subprocess.run(
        [sys.executable, "-m", "app.cli", "--bad"],
        capture_output=True,
        text=True,
    )
    output = (proc.stdout + proc.stderr).lower()
    assert proc.returncode == 2
    assert "traceback" not in output
    assert "usage" in output or "unrecognized" in output or "error" in output
