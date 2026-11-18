Add an express-shipping option to the order flow:

- `app.shipping.shipping_cost(weight, express=False)` keeps the current base cost of `5 + 2.5 * weight`, rounded to two decimals. When `express` is true, it doubles that cost and rounds to two decimals.
- `app.orders.order_total(prices, weight, express=False)` forwards the flag to `shipping_cost`.
- `app.summary.summary_line(prices, weight, express=False)` forwards the flag and, when express is true, appends `" (express)"` after the amount. The normal output stays `Total: $...`.

Keep the existing defaults and formatting unchanged, and run the tests.
