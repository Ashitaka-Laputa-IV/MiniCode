from .shipping import shipping_cost


def order_total(prices, weight):
    return round(sum(prices) + shipping_cost(weight), 2)
