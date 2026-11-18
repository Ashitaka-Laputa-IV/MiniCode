import assert from "node:assert/strict";
import path from "node:path";
import test from "node:test";
import { pathToFileURL } from "node:url";

const workspace = process.env.WORKSPACE;
const moduleUrl = pathToFileURL(path.join(workspace, "src", "pagination.js")).href;
const { paginate } = await import(moduleUrl);

test("partial final page is counted", () => {
  assert.equal(paginate([1, 2, 3, 4, 5], 1, 2).totalPages, 3);
});

test("last page contains the remaining items", () => {
  assert.deepEqual(paginate([1, 2, 3, 4, 5], 3, 2).items, [5]);
});

test("empty list has zero pages", () => {
  assert.equal(paginate([], 1, 2).totalPages, 0);
});

test("exact multiple is unchanged", () => {
  assert.equal(paginate([1, 2, 3, 4, 5, 6], 2, 3).totalPages, 2);
});
