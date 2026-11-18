Add a configurable discount percentage to the pricing flow:

- `app.discounts.apply_discount(total, percent=10)` returns the total after subtracting `percent` percent, rounded to two decimals.
- `app.orders.order_total(prices, discount_percent=10)` forwards the percentage.
- `app.receipt.receipt_line(prices, discount_percent=10)` also forwards it and keeps the current `Total: $...` format.

Keep the existing defaults and behavior unchanged, and run the tests.
