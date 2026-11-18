import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from app.inventory import Inventory

EXPECTED_INVENTORY_SHA256 = (
    "c0dcfbe7342677da3793580d121ef563ba0180723590574408033573a3393b16"
)


MUTATIONS = {
    "unknown_sku_allowed": (
        "available = self.available(sku)",
        "available = self._counts.get(sku, quantity)",
    ),
    "zero_quantity_allowed": (
        "if quantity <= 0:",
        "if False:",
    ),
    "full_reserve_leaves_stock": (
        "self._counts[sku] = available - quantity",
        "self._counts[sku] = available - quantity + 1",
    ),
    "over_reserve_allowed": (
        "if quantity > available:",
        "if False:",
    ),
}


def _run_agent_tests(base: Path) -> subprocess.CompletedProcess[str]:
    pytest_ini = base / "pytest.ini"
    pytest_ini.write_text("[pytest]\naddopts =\n", encoding="utf-8")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(base)
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-c",
            str(pytest_ini),
            "--rootdir",
            str(base),
            "--confcutdir",
            str(base),
            "-p",
            "no:cacheprovider",
            str(base / "tests" / "test_inventory.py"),
        ],
        cwd=base,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )


def test_agent_tests_detect_reserve_mutations():
    test_file = Path.cwd() / "tests" / "test_inventory.py"
    assert test_file.is_file(), "tests/test_inventory.py was not created"
    source = (Path.cwd() / "app" / "inventory.py").read_text(encoding="utf-8")
    source = source.replace("\r\n", "\n")

    for name, (original, mutated) in MUTATIONS.items():
        assert original in source, f"fixture changed: missing mutation anchor for {name}"
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            shutil.copytree(Path.cwd() / "app", base / "app")
            (base / "tests").mkdir()
            shutil.copyfile(test_file, base / "tests" / "test_inventory.py")
            inventory = base / "app" / "inventory.py"
            inventory.write_text(
                source.replace(original, mutated, 1), encoding="utf-8"
            )
            proc = _run_agent_tests(base)
        assert proc.returncode != 0, (
            f"agent tests did not catch the {name} behavior\n"
            f"{proc.stdout}{proc.stderr}"
        )


def test_regression_file_exists_with_four_tests():
    test_file = Path.cwd() / "tests" / "test_inventory.py"
    assert test_file.is_file(), "tests/test_inventory.py was not created"
    text = test_file.read_text(encoding="utf-8")
    assert "reserve" in text
    assert text.count("def test_") >= 4


def test_regression_file_passes():
    test_file = Path.cwd() / "tests" / "test_inventory.py"
    assert test_file.is_file(), "tests/test_inventory.py was not created"

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        copied_test = tmp_path / "test_inventory.py"
        shutil.copyfile(test_file, copied_test)
        (tmp_path / "pytest.ini").write_text(
            "[pytest]\naddopts =\n", encoding="utf-8"
        )
        env = os.environ.copy()
        env["PYTHONPATH"] = str(Path.cwd())
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "-c",
                str(tmp_path / "pytest.ini"),
                "--rootdir",
                str(tmp_path),
                "--confcutdir",
                str(tmp_path),
                "-p",
                "no:cacheprovider",
                str(copied_test),
            ],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_inventory_source_is_unchanged():
    source = (Path.cwd() / "app" / "inventory.py").read_text(encoding="utf-8")
    normalized = source.replace("\r\n", "\n")
    assert hashlib.sha256(normalized.encode("utf-8")).hexdigest() == (
        EXPECTED_INVENTORY_SHA256
    )


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
