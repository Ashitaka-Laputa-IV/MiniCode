import assert from "node:assert/strict";
import test from "node:test";

import { binarySearch } from "../src/index.js";

test("finds a value in the middle", () => {
  assert.equal(binarySearch([1, 3, 5, 7, 9], 5), 2);
});

test("returns -1 for a missing value", () => {
  assert.equal(binarySearch([1, 3, 5, 7, 9], 4), -1);
});

test("empty input returns -1", () => {
  assert.equal(binarySearch([], 1), -1);
});
