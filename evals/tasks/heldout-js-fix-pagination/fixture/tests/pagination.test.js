import assert from "node:assert/strict";
import test from "node:test";

import { paginate } from "../src/pagination.js";

test("exact multiple has no partial page", () => {
  assert.deepEqual(paginate([1, 2, 3, 4], 1, 2), {
    items: [1, 2],
    page: 1,
    totalPages: 2,
  });
});

test("empty list has zero pages", () => {
  assert.deepEqual(paginate([], 1, 2), {
    items: [],
    page: 1,
    totalPages: 0,
  });
});
