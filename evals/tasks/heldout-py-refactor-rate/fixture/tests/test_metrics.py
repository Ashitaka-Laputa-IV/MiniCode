from app.metrics import failure_rate, success_rate


def test_success_rate():
    assert success_rate(3, 4) == 75.0


def test_failure_rate():
    assert failure_rate(3, 4) == 25.0


def test_zero_attempts():
    assert success_rate(0, 0) == 0.0
    assert failure_rate(0, 0) == 0.0
