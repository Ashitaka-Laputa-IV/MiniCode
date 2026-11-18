import ast
from pathlib import Path

from app.records import _field, normalize_email, normalize_name, user_record


def test_helper_handles_none_and_strings():
    assert _field(None) == ""
    assert _field("  x ") == "x"
    assert _field(42) == "42"


def test_public_outputs_are_unchanged():
    assert normalize_name("  Ada   Lovelace ") == "Ada Lovelace"
    assert normalize_name(None) == ""
    assert normalize_email(" ADA@Example.COM ") == "ada@example.com"
    assert normalize_email(None) == ""
    assert user_record(" Ada ", " ADA@Example.COM ") == {
        "name": "Ada",
        "email": "ada@example.com",
    }


def test_public_functions_call_helper():
    source = (Path.cwd() / "app" / "records.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_field"
    ]
    assert len(calls) >= 2
