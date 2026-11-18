from app.orders import order_total
from app.shipping import shipping_cost
from app.summary import summary_line


def test_express_shipping_cost_doubles():
    assert shipping_cost(2, express=True) == 20.0


def test_express_order_total():
    assert order_total([10], 2, express=True) == 30.0


def test_express_is_forwarded_to_summary():
    assert summary_line([10], 2, express=True) == "Total: $30.00 (express)"


def test_rounding_for_fractional_weight():
    assert shipping_cost(1.5) == 8.75
    assert shipping_cost(1.5, express=True) == 17.5
    assert order_total([10], 1.5, express=True) == 27.5


def test_defaults_are_unchanged():
    assert shipping_cost(2) == 10.0
    assert order_total([10], 2) == 20.0
    assert summary_line([10], 2) == "Total: $20.00"
    assert summary_line([10], 2, express=False) == "Total: $20.00"
