import assert from "node:assert/strict";
import test from "node:test";

import { formatDate, formatTime } from "../src/index.js";

const date = new Date(2020, 2, 5, 7, 4);

test("formatDate pads month and day", () => {
  assert.equal(formatDate(date), "2020-03-05");
});

test("formatTime pads hours and minutes", () => {
  assert.equal(formatTime(date), "07:04");
});
