from app.discounts import apply_discount
from app.orders import order_total
from app.receipt import receipt_line


def test_custom_discount_at_source():
    assert apply_discount(100, 25) == 75.0


def test_custom_discount_through_orders():
    assert order_total([50, 50], 20) == 80.0


def test_custom_discount_through_receipt():
    assert receipt_line([50, 50], 20) == "Total: $80.00"


def test_defaults_still_work():
    assert apply_discount(100) == 90.0
    assert order_total([50, 50]) == 90.0
    assert receipt_line([50, 50]) == "Total: $90.00"


def test_rounding():
    assert apply_discount(10, 33) == 6.7
