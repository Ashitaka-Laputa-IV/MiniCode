from app.pricing import _apply_tax, price_with_tax, price_with_tax_and_shipping


def test_helper():
    assert _apply_tax(10) == 12.0


def test_rounding():
    assert price_with_tax(9.99) == 11.99


def test_shipping_rounding():
    assert price_with_tax_and_shipping(9.99, 1.25) == 13.24
