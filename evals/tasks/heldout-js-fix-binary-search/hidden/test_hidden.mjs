import assert from "node:assert/strict";
import path from "node:path";
import test from "node:test";
import { pathToFileURL } from "node:url";

const workspace = process.env.WORKSPACE;
const moduleUrl = pathToFileURL(path.join(workspace, "src", "index.js")).href;
const { binarySearch } = await import(moduleUrl);

test("finds the last element", () => {
  assert.equal(binarySearch([1, 3, 5], 5), 2);
});

test("finds the first element", () => {
  assert.equal(binarySearch([1, 3, 5], 1), 0);
});

test("finds an element in a single-item array", () => {
  assert.equal(binarySearch([7], 7), 0);
});

test("missing single-item value returns -1", () => {
  assert.equal(binarySearch([7], 3), -1);
});

test("handles even and odd lengths", () => {
  assert.equal(binarySearch([1, 2, 3, 4], 4), 3);
  assert.equal(binarySearch([1, 2, 3, 4], 1), 0);
  assert.equal(binarySearch([1, 2, 3, 4, 5], 2), 1);
});

test("returns -1 when the target is outside the range", () => {
  assert.equal(binarySearch([10, 20, 30], 5), -1);
  assert.equal(binarySearch([10, 20, 30], 35), -1);
});
