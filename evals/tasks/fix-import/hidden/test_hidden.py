from app.calc import add
from app.math_utils import sub


def test_add_negative():
    assert add(-1, 1) == 0


def test_sub():
    assert sub(5, 2) == 3
