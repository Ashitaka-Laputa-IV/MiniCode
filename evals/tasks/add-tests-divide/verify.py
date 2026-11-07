import subprocess
import sys
from pathlib import Path

workspace = Path(sys.argv[1])
test_file = workspace / "tests" / "test_divide.py"
if not test_file.exists():
    raise SystemExit("tests/test_divide.py was not created")
text = test_file.read_text(encoding="utf-8")
if "pytest.raises" not in text or "ZeroDivisionError" not in text:
    raise SystemExit("test must cover ZeroDivisionError with pytest.raises")
if text.count("def test_") < 2:
    raise SystemExit("expected at least two tests")
raise SystemExit(
    subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=workspace).returncode
)
