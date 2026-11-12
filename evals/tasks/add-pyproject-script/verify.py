import sys
import tomllib
from pathlib import Path

workspace = Path(sys.argv[1])
data = tomllib.loads((workspace / "pyproject.toml").read_text(encoding="utf-8"))
scripts = data.get("project", {}).get("scripts", {})
if scripts.get("hello") != "app.cli:main":
    raise SystemExit(f"unexpected scripts: {scripts}")
