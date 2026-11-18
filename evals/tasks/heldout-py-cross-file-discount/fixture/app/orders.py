from .discounts import apply_discount


def order_total(prices):
    return apply_discount(sum(prices))
