import assert from "node:assert/strict";
import test from "node:test";

import { formatName, greeting } from "../src/index.js";

const ada = { first: "Ada", last: "Lovelace" };

test("formatName returns the full name by default", () => {
  assert.equal(formatName(ada), "Ada Lovelace");
});

test("greeting uses the full name by default", () => {
  assert.equal(greeting(ada), "Hello, Ada Lovelace!");
});
