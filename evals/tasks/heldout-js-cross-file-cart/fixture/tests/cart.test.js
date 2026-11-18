import assert from "node:assert/strict";
import test from "node:test";

import { cartTotal, formatMoney } from "../src/index.js";

const items = [
  { price: 500, quantity: 2 },
  { price: 250, quantity: 1 },
];

test("formats money", () => {
  assert.equal(formatMoney(1250), "$12.50");
});

test("totals an empty cart", () => {
  assert.equal(cartTotal([]), "$0.00");
});

test("totals item prices and quantities", () => {
  assert.equal(cartTotal(items), "$12.50");
});
