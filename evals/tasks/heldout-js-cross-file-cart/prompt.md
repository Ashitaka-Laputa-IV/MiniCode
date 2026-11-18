Add a `discountPercent` option to the cart flow:

- `money.applyDiscount(cents, percent = 0)` returns the amount in cents after subtracting `percent` percent, rounded to the nearest whole cent with `Math.round`. A zero subtotal still returns `0`.
- `cart.cartTotal(items, { discountPercent = 0 } = {})` computes the subtotal in cents (each item has integer `price` and `quantity`), applies the discount, and formats the result with `formatMoney`.
- `src/index.js` exports `applyDiscount` in addition to the existing exports.

Keep the default output and all existing behavior unchanged. Run the tests.
