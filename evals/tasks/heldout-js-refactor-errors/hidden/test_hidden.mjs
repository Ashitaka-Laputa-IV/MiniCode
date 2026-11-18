import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { pathToFileURL } from "node:url";

const workspace = process.env.WORKSPACE;
const moduleUrl = pathToFileURL(path.join(workspace, "src", "index.js")).href;
const { parseInteger, parsePort, parseTimeout } = await import(moduleUrl);
const source = await readFile(path.join(workspace, "src", "validation.js"), "utf8");

test("parseInteger parses digit strings", () => {
  assert.equal(parseInteger("42", "thing"), 42);
  assert.equal(parseInteger("0", "thing"), 0);
});

test("parseInteger rejects non-strings and non-digits", () => {
  assert.throws(() => parseInteger(42, "thing"), {
    name: "TypeError",
    message: "invalid thing",
  });
  assert.throws(() => parseInteger("4x", "thing"), {
    name: "TypeError",
    message: "invalid thing",
  });
});

test("public functions keep their behavior", () => {
  assert.equal(parsePort("8080"), 8080);
  assert.equal(parseTimeout("250"), 250);
  assert.throws(() => parsePort("80x"), { name: "TypeError", message: "invalid port" });
  assert.throws(() => parsePort("0"), { name: "RangeError", message: "port out of range" });
  assert.throws(() => parseTimeout("-1"), {
    name: "TypeError",
    message: "invalid timeout",
  });
});

test("public functions call the helper", () => {
  const calls = source.match(/parseInteger\s*\(/g) ?? [];
  assert.ok(calls.length >= 3);
});
