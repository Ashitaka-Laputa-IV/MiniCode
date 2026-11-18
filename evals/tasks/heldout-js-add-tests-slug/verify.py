import os
import shutil
import subprocess
import sys
from pathlib import Path

workspace = Path(sys.argv[1]).resolve()
test_file = Path(__file__).resolve().parent / "hidden" / "test_hidden.mjs"
node = shutil.which("node")
if node is None:
    raise SystemExit("node executable not found")
env = dict(os.environ)
env["WORKSPACE"] = str(workspace)
raise SystemExit(
    subprocess.run(
        [node, "--test", str(test_file)],
        cwd=workspace,
        env=env,
        timeout=60,
    ).returncode
)
