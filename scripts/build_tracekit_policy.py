"""Compile MiniCode's Tracekit policy mapping.

Tracekit's dev signer always uses its bundled ``dev.yaml``. This script copies
the installed policy packs next to ``tracekit/minicode-policy.yaml`` and
compiles the merged policy to ``.minicode/tracekit/minicode-policy.json`` for a
configured signer.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE = REPO_ROOT / "tracekit" / "minicode-policy.yaml"
OUTPUT_DIR = REPO_ROOT / ".minicode" / "tracekit"
PACKS_DIR = OUTPUT_DIR / "packs"
SIGNER_DIR = OUTPUT_DIR / "signer"


def main() -> int:
    try:
        from tracekit.policy2 import compile

        import tracekit
    except ImportError as exc:
        print(f"tracekit is not installed: {exc}", file=sys.stderr)
        return 1

    installed_packs = Path(tracekit.__file__).resolve().parent / "policy2" / "packs"
    if not installed_packs.is_dir():
        print(f"Tracekit policy packs not found at {installed_packs}", file=sys.stderr)
        return 1

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    SIGNER_DIR.mkdir(parents=True, exist_ok=True)
    if PACKS_DIR.exists():
        shutil.rmtree(PACKS_DIR)
    shutil.copytree(installed_packs, PACKS_DIR)

    target = OUTPUT_DIR / "minicode-policy.yaml"
    shutil.copyfile(SOURCE, target)

    policy, errors = compile.build(str(target))
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1

    output = OUTPUT_DIR / "minicode-policy.json"
    # The compiled JSON already contains the merged rules. A remaining
    # `extends` hash would be read as a relative path by the signer.
    policy.pop("extends", None)
    output.write_text(compile.canonical(policy), encoding="utf-8")
    print(f"wrote {output}")
    print(f"policy_hash: {compile.policy_hash(policy)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
