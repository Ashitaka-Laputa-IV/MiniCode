import assert from "node:assert/strict";
import test from "node:test";

import { parsePort, parseTimeout } from "../src/index.js";

test("parsePort accepts a valid port", () => {
  assert.equal(parsePort("8080"), 8080);
});

test("parsePort rejects non-digits", () => {
  assert.throws(() => parsePort("80x"), { name: "TypeError", message: "invalid port" });
});

test("parsePort rejects an out-of-range port", () => {
  assert.throws(() => parsePort("0"), { name: "RangeError", message: "port out of range" });
});

test("parseTimeout accepts zero and positive values", () => {
  assert.equal(parseTimeout("0"), 0);
  assert.equal(parseTimeout("250"), 250);
});
