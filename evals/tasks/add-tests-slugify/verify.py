import subprocess
import sys
from pathlib import Path

workspace = Path(sys.argv[1])
test_file = workspace / "tests" / "test_slugify.py"
if not test_file.exists():
    raise SystemExit("tests/test_slugify.py was not created")
text = test_file.read_text(encoding="utf-8")
if "slugify" not in text:
    raise SystemExit("test file does not reference slugify")
if text.count("def test_") < 3:
    raise SystemExit("expected at least three tests")
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
