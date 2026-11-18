import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { pathToFileURL } from "node:url";

const workspace = process.env.WORKSPACE;
const moduleUrl = pathToFileURL(path.join(workspace, "src", "index.js")).href;
const { clientConfig, mergeDefined, serverConfig } = await import(moduleUrl);
const source = await readFile(path.join(workspace, "src", "config.js"), "utf8");

test("mergeDefined keeps defaults for undefined overrides", () => {
  assert.deepEqual(mergeDefined({ a: 1 }, { a: undefined, b: 2 }), { a: 1, b: 2 });
  assert.deepEqual(mergeDefined({ a: 1 }, {}), { a: 1 });
});

test("mergeDefined returns a new object", () => {
  const defaults = { a: 1 };
  const merged = mergeDefined(defaults, { b: 2 });
  assert.notEqual(merged, defaults);
  assert.deepEqual(defaults, { a: 1 });
});

test("public configs keep their behavior", () => {
  assert.deepEqual(serverConfig(), { host: "localhost", port: 3000 });
  assert.deepEqual(serverConfig({ port: undefined }), { host: "localhost", port: 3000 });
  assert.deepEqual(serverConfig({ port: 8080 }), { host: "localhost", port: 8080 });
  assert.deepEqual(clientConfig({ timeout: 0 }), { host: "localhost", timeout: 0 });
  assert.deepEqual(clientConfig({ host: "example.com" }), {
    host: "example.com",
    timeout: 5000,
  });
});

function functionBody(name) {
  const match = new RegExp(`(?:export\\s+)?function\\s+${name}\\s*\\(`).exec(source);
  assert.ok(match, `missing function ${name}`);
  const openParen = source.indexOf("(", match.index);
  let parenDepth = 0;
  let closeParen = -1;
  for (let index = openParen; index < source.length; index += 1) {
    if (source[index] === "(") {
      parenDepth += 1;
    } else if (source[index] === ")") {
      parenDepth -= 1;
      if (parenDepth === 0) {
        closeParen = index;
        break;
      }
    }
  }
  assert.ok(closeParen >= 0, `unterminated parameters for ${name}`);
  const start = source.indexOf("{", closeParen);
  assert.ok(start >= 0, `missing body for ${name}`);
  let depth = 0;
  for (let index = start; index < source.length; index += 1) {
    if (source[index] === "{") {
      depth += 1;
    } else if (source[index] === "}") {
      depth -= 1;
      if (depth === 0) {
        return source.slice(start + 1, index);
      }
    }
  }
  assert.fail(`unterminated function ${name}`);
}

test("public functions call the helper", () => {
  for (const name of ["serverConfig", "clientConfig"]) {
    assert.match(functionBody(name), /mergeDefined\s*\(/, `${name} must call mergeDefined`);
  }
});
