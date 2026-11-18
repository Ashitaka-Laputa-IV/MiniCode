import assert from "node:assert/strict";
import path from "node:path";
import test from "node:test";
import { pathToFileURL } from "node:url";

const workspace = process.env.WORKSPACE;
const moduleUrl = pathToFileURL(path.join(workspace, "src", "index.js")).href;
const { applyDiscount, cartTotal, formatMoney } = await import(moduleUrl);

const items = [
  { price: 500, quantity: 2 },
  { price: 250, quantity: 1 },
];

test("applyDiscount is exported and applies a percentage", () => {
  assert.equal(applyDiscount(1000, 25), 750);
});

test("applyDiscount rounds to the nearest cent", () => {
  assert.equal(applyDiscount(999, 10), 899);
  assert.equal(applyDiscount(101, 50), 51);
});

test("applyDiscount handles a zero subtotal and zero percent", () => {
  assert.equal(applyDiscount(0, 50), 0);
  assert.equal(applyDiscount(1234, 0), 1234);
});

test("cartTotal accepts discountPercent", () => {
  assert.equal(cartTotal(items, { discountPercent: 20 }), "$10.00");
  assert.equal(cartTotal(items, { discountPercent: 0 }), "$12.50");
});

test("cartTotal keeps default behavior", () => {
  assert.equal(cartTotal(items), "$12.50");
  assert.equal(cartTotal([]), "$0.00");
  assert.equal(cartTotal([{ price: 1000, quantity: 1 }], { discountPercent: 10 }), "$9.00");
});

test("formatMoney is unchanged", () => {
  assert.equal(formatMoney(1250), "$12.50");
});
