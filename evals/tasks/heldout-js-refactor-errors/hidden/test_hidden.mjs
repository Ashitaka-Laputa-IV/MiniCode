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
  for (const name of ["parsePort", "parseTimeout"]) {
    assert.match(functionBody(name), /parseInteger\s*\(/, `${name} must call parseInteger`);
  }
});
