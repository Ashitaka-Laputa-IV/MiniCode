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
  for (const name of ["formatDate", "formatTime"]) {
    assert.match(functionBody(name), /pad2\s*\(/, `${name} must call pad2`);
  }
});
