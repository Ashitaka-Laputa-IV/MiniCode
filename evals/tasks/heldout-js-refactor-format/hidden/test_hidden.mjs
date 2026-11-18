import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { pathToFileURL } from "node:url";

const workspace = process.env.WORKSPACE;
const moduleUrl = pathToFileURL(path.join(workspace, "src", "index.js")).href;
const { formatDate, formatTime, pad2 } = await import(moduleUrl);
const source = await readFile(path.join(workspace, "src", "format.js"), "utf8");

test("pad2 pads single digits and leaves two digits alone", () => {
  assert.equal(pad2(0), "00");
  assert.equal(pad2(5), "05");
  assert.equal(pad2(12), "12");
});

test("public formatting is unchanged", () => {
  assert.equal(formatDate(new Date(2020, 2, 5, 7, 4)), "2020-03-05");
  assert.equal(formatTime(new Date(2020, 2, 5, 7, 4)), "07:04");
  assert.equal(formatDate(new Date(1999, 11, 31, 23, 59)), "1999-12-31");
  assert.equal(formatTime(new Date(1999, 11, 31, 23, 59)), "23:59");
});

test("public functions call the helper", () => {
  const calls = source.match(/pad2\s*\(/g) ?? [];
  assert.ok(calls.length >= 5);
});
