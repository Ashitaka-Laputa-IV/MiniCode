from app.discounts import apply_discount
from app.orders import order_total
from app.receipt import receipt_line


def test_default_discount():
    assert apply_discount(100) == 90.0
    assert order_total([50, 50]) == 90.0
    assert receipt_line([50, 50]) == "Total: $90.00"
