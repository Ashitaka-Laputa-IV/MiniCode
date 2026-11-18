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

function skipWhitespace(text, index) {
  let current = index;
  while (current < text.length && /\s/.test(text[current])) {
    current += 1;
  }
  return current;
}

function closingParen(text, openIndex, name) {
  let depth = 0;
  for (let index = openIndex; index < text.length; index += 1) {
    if (text[index] === "(") {
      depth += 1;
    } else if (text[index] === ")") {
      depth -= 1;
      if (depth === 0) {
        return index;
      }
    }
  }
  assert.fail(`unterminated parameters for ${name}`);
}

function braceBody(text, openIndex, name) {
  let depth = 0;
  for (let index = openIndex; index < text.length; index += 1) {
    if (text[index] === "{") {
      depth += 1;
    } else if (text[index] === "}") {
      depth -= 1;
      if (depth === 0) {
        return text.slice(openIndex + 1, index);
      }
    }
  }
  assert.fail(`unterminated function ${name}`);
}

function functionBody(name) {
  const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const declaration = new RegExp(
    `(?:export\\s+)?(?:async\\s+)?function\\s+${escaped}\\s*\\(`,
  ).exec(source);
  if (declaration) {
    const openParen = source.indexOf("(", declaration.index);
    const closeParen = closingParen(source, openParen, name);
    const openBrace = source.indexOf("{", closeParen);
    assert.ok(openBrace >= 0, `missing body for ${name}`);
    return braceBody(source, openBrace, name);
  }

  const assignment = new RegExp(
    `(?:export\\s+)?(?:const|let|var)\\s+${escaped}\\s*=`,
  ).exec(source);
  if (assignment) {
    let index = skipWhitespace(source, assignment.index + assignment[0].length);
    if (
      source.slice(index, index + 5) === "async" &&
      !/[A-Za-z0-9_$]/.test(source[index + 5] ?? "")
    ) {
      index = skipWhitespace(source, index + 5);
    }
    if (source.slice(index, index + 8) === "function") {
      const openParen = source.indexOf("(", index);
      const closeParen = closingParen(source, openParen, name);
      const openBrace = source.indexOf("{", closeParen);
      assert.ok(openBrace >= 0, `missing body for ${name}`);
      return braceBody(source, openBrace, name);
    }
    if (source[index] === "(") {
      index = skipWhitespace(source, closingParen(source, index, name) + 1);
    } else {
      while (index < source.length && /[A-Za-z0-9_$]/.test(source[index])) {
        index += 1;
      }
      index = skipWhitespace(source, index);
    }
    if (source.slice(index, index + 2) === "=>") {
      index = skipWhitespace(source, index + 2);
      if (source[index] === "{") {
        return braceBody(source, index, name);
      }
      const end = source.indexOf(";", index);
      return source.slice(index, end < 0 ? source.length : end);
    }
  }
  assert.fail(`missing function ${name}`);
}
test("public functions call the helper", () => {
  for (const name of ["formatDate", "formatTime"]) {
    assert.match(functionBody(name), /pad2\s*\(/, `${name} must call pad2`);
  }
});
