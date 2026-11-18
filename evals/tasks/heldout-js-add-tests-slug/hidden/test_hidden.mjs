import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { pathToFileURL } from "node:url";

const workspace = process.env.WORKSPACE;
const testFile = path.join(workspace, "tests", "slug.test.js");
const moduleUrl = pathToFileURL(path.join(workspace, "src", "index.js")).href;
const { slugify } = await import(moduleUrl);

test("regression test file has at least five tests", async () => {
  const text = await readFile(testFile, "utf8");
  assert.ok((text.match(/test\(/g) ?? []).length >= 5);
  assert.ok((text.match(/slugify\(/g) ?? []).length >= 5);
});

test("regression test file passes", () => {
  const proc = spawnSync(process.execPath, ["--test", "tests/slug.test.js"], {
    cwd: workspace,
    encoding: "utf8",
  });
  assert.equal(proc.status, 0, proc.stdout + proc.stderr);
});

test("slugify folds spaces and punctuation", () => {
  assert.equal(slugify("  Hello,   World!  "), "hello-world");
  assert.equal(slugify("one...two"), "one-two");
});

test("slugify folds accents and trims separators", () => {
  assert.equal(slugify("Café Déjà Vu"), "cafe-deja-vu");
  assert.equal(slugify("--Edge Case--"), "edge-case");
});

test("slugify handles the empty string", () => {
  assert.equal(slugify(""), "");
  assert.equal(slugify("   "), "");
});
