TAX_RATE = 0.2


def price_with_tax(amount):
    return round(amount * (1 + TAX_RATE), 2)


def price_with_tax_and_shipping(amount, shipping):
    return round(amount * (1 + TAX_RATE) + shipping, 2)
