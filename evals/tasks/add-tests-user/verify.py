import subprocess
import sys
from pathlib import Path

workspace = Path(sys.argv[1])
test_file = workspace / "tests" / "test_user.py"
if not test_file.exists():
    raise SystemExit("tests/test_user.py was not created")
text = test_file.read_text(encoding="utf-8")
if "User" not in text or "display_name" not in text:
    raise SystemExit("test file must cover User.display_name")
if text.count("def test_") < 2:
    raise SystemExit("expected at least two tests")
safe_ini = Path(__file__).resolve().parents[2] / "pytest-safe.ini"
raise SystemExit(
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-c",
            str(safe_ini),
            "-p",
            "no:cacheprovider",
        ],
        cwd=workspace,
        timeout=60,
    ).returncode
)
