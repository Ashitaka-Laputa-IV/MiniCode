import subprocess
import sys
from pathlib import Path

workspace = Path(sys.argv[1])
test_file = workspace / "tests" / "test_stack.py"
if not test_file.exists():
    raise SystemExit("tests/test_stack.py was not created")
text = test_file.read_text(encoding="utf-8")
for name in ("Stack", "push", "pop", "peek", "is_empty"):
    if name not in text:
        raise SystemExit(f"test file does not cover {name}")
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
