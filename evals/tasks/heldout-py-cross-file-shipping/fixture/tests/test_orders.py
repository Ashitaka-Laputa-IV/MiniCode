from app.orders import order_total
from app.shipping import shipping_cost
from app.summary import summary_line


def test_default_shipping_cost():
    assert shipping_cost(2) == 10.0


def test_default_order_total_and_summary():
    assert order_total([10], 2) == 20.0
    assert summary_line([10], 2) == "Total: $20.00"
