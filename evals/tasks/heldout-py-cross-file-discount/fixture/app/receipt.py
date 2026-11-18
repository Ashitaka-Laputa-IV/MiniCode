from .orders import order_total


def receipt_line(prices):
    return f"Total: ${order_total(prices):.2f}"
