import assert from "node:assert/strict";
import path from "node:path";
import test from "node:test";
import { pathToFileURL } from "node:url";

const workspace = process.env.WORKSPACE;
const moduleUrl = pathToFileURL(path.join(workspace, "src", "index.js")).href;
const { formatName, greeting } = await import(moduleUrl);

const ada = { first: "Ada", last: "Lovelace" };

test("formatName supports short names", () => {
  assert.equal(formatName(ada, { short: true }), "Ada");
});

test("greeting forwards the short option", () => {
  assert.equal(greeting(ada, { short: true }), "Hello, Ada!");
});

test("defaults are unchanged", () => {
  assert.equal(formatName(ada), "Ada Lovelace");
  assert.equal(greeting(ada), "Hello, Ada Lovelace!");
  assert.equal(greeting(ada, {}), "Hello, Ada Lovelace!");
});
