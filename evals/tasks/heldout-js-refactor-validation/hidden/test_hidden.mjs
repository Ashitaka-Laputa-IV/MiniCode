import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { pathToFileURL } from "node:url";

const workspace = process.env.WORKSPACE;
const moduleUrl = pathToFileURL(path.join(workspace, "src", "index.js")).href;
const { assertValidAccount, createAccount, updateAccount } = await import(moduleUrl);
const source = await readFile(path.join(workspace, "src", "validation.js"), "utf8");

test("helper rejects a bad email", () => {
  assert.throws(() => assertValidAccount({ email: "nope", age: 36 }), {
    name: "TypeError",
    message: "invalid email",
  });
});

test("helper rejects a bad age", () => {
  assert.throws(() => assertValidAccount({ email: "ada@example.com", age: -1 }), {
    name: "TypeError",
    message: "invalid age",
  });
});

test("helper accepts valid input", () => {
  assert.doesNotThrow(() => assertValidAccount({ email: "ada@example.com", age: 0 }));
});

test("public functions keep their behavior", () => {
  assert.deepEqual(createAccount({ email: "ada@example.com", age: 36 }), {
    email: "ada@example.com",
    age: 36,
  });
  assert.deepEqual(
    updateAccount({ email: "ada@example.com", age: 36, name: "Ada" }, { age: 37 }),
    { email: "ada@example.com", age: 37, name: "Ada" },
  );
  assert.throws(() => updateAccount({ email: "ada@example.com", age: 36 }, { age: -1 }), {
    name: "TypeError",
    message: "invalid age",
  });
});

function functionBody(name) {
  const pattern = new RegExp(
    `(?:export\\s+)?function\\s+${name}\\s*\\([^)]*\\)\\s*\\{([\\s\\S]*?)\\n\\}`,
    "m",
  );
  const match = source.match(pattern);
  assert.ok(match, `${name} function not found in src/validation.js`);
  return match[1];
}

test("public functions call the helper", () => {
  assert.match(functionBody("createAccount"), /assertValidAccount\s*\(/);
  assert.match(functionBody("updateAccount"), /assertValidAccount\s*\(/);
});
