import subprocess
import sys
from pathlib import Path

import pytest

from app.inventory import Inventory


def test_regression_file_exists_with_four_tests():
    test_file = Path.cwd() / "tests" / "test_inventory.py"
    assert test_file.is_file(), "tests/test_inventory.py was not created"
    text = test_file.read_text(encoding="utf-8")
    assert "reserve" in text
    assert text.count("def test_") >= 4


def test_regression_file_passes():
    test_file = Path.cwd() / "tests" / "test_inventory.py"
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            str(test_file),
        ],
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_unknown_sku_is_rejected():
    inventory = Inventory({"apple": 1})
    with pytest.raises(ValueError, match="insufficient stock"):
        inventory.reserve("pear", 1)


def test_non_positive_quantity_is_rejected():
    inventory = Inventory({"apple": 1})
    with pytest.raises(ValueError, match="quantity must be positive"):
        inventory.reserve("apple", 0)


def test_reserving_all_stock_leaves_zero():
    inventory = Inventory({"apple": 2})
    assert inventory.reserve("apple", 2) == 0
    assert inventory.available("apple") == 0


def test_over_reserving_is_rejected():
    inventory = Inventory({"apple": 2})
    with pytest.raises(ValueError, match="insufficient stock"):
        inventory.reserve("apple", 3)
