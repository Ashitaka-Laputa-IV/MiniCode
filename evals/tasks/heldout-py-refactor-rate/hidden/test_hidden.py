import ast
from pathlib import Path

from app.metrics import _rate, failure_rate, success_rate


def test_helper_zero_total():
    assert _rate(1, 0) == 0.0


def test_helper_rounding():
    assert _rate(1, 3) == 33.3
    assert _rate(2, 3) == 66.7


def test_public_functions_keep_outputs():
    assert success_rate(3, 4) == 75.0
    assert failure_rate(3, 4) == 25.0
    assert success_rate(0, 0) == 0.0
    assert failure_rate(0, 0) == 0.0


def test_public_functions_call_helper():
    source = (Path.cwd() / "app" / "metrics.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_rate"
    ]
    assert len(calls) >= 2
