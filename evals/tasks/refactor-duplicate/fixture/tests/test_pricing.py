from app.pricing import price_with_tax, price_with_tax_and_shipping


def test_tax():
    assert price_with_tax(10) == 12.0


def test_tax_and_shipping():
    assert price_with_tax_and_shipping(10, 5) == 17.0
