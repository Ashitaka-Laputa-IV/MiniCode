from .orders import order_total


def summary_line(prices, weight):
    return f"Total: ${order_total(prices, weight):.2f}"
