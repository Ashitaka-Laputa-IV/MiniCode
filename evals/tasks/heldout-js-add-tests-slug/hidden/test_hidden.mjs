import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { cp, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { pathToFileURL } from "node:url";

const workspace = process.env.WORKSPACE;
const testFile = path.join(workspace, "tests", "slug.test.js");
const sourceFile = path.join(workspace, "src", "slug.js");
const moduleUrl = pathToFileURL(path.join(workspace, "src", "index.js")).href;
const { slugify } = await import(moduleUrl);

const EXPECTED_SLUG_SHA256 =
  "0d9515d49c7a8c21353d1217bf766230e81d52e3d9ccf9d6dd955a6cb1febf37";

const MUTATIONS = [
  {
    name: "unicode normalization is disabled",
    anchor: '.normalize("NFKD")',
    replacement: '.normalize("NFC")',
  },
  {
    name: "diacritic marks are not removed",
    anchor: '.replace(/[\\u0300-\\u036f]/g, "")',
    replacement: '.replace(/[\\u0300-\\u036f]/g, "x")',
  },
  {
    name: "edge separators are not trimmed",
    anchor: '.replace(/^-+|-+$/g, "")',
    replacement: '.replace(/^-+|-+$/g, "x")',
  },
  {
    name: "punctuation is mapped to the wrong separator",
    anchor: '.replace(/[^a-z0-9]+/g, "-")',
    replacement: '.replace(/[^a-z0-9]+/g, "_")',
  },
];

function normalizedHash(text) {
  return createHash("sha256").update(text.replace(/\r\n/g, "\n")).digest("hex");
}

function runTests(cwd) {
  const env = { ...process.env };
  delete env.NODE_TEST_CONTEXT;
  return spawnSync(process.execPath, ["--test", "tests/slug.test.js"], {
    cwd,
    encoding: "utf8",
    env,
  });
}

test("regression test file has at least five tests", async () => {
  const text = await readFile(testFile, "utf8");
  assert.ok((text.match(/test\(/g) ?? []).length >= 5);
  assert.ok((text.match(/slugify\(/g) ?? []).length >= 5);
});

test("regression test file passes", () => {
  const proc = runTests(workspace);
  assert.equal(proc.status, 0, proc.stdout + proc.stderr);
});

test("slug source is unchanged", async () => {
  const source = await readFile(sourceFile, "utf8");
  assert.equal(normalizedHash(source), EXPECTED_SLUG_SHA256);
});

test("agent tests detect slug behavior mutations", async () => {
  const original = await readFile(sourceFile, "utf8");
  for (const mutation of MUTATIONS) {
    const mutated = original.replace(mutation.anchor, mutation.replacement);
    assert.notEqual(mutated, original, `mutation target missing: ${mutation.name}`);
    const dir = await mkdtemp(path.join(os.tmpdir(), "slug-mutation-"));
    try {
      await cp(path.join(workspace, "src"), path.join(dir, "src"), {
        recursive: true,
      });
      await cp(path.join(workspace, "tests"), path.join(dir, "tests"), {
        recursive: true,
      });
      await cp(path.join(workspace, "package.json"), path.join(dir, "package.json"));
      const baseline = runTests(dir);
      assert.equal(
        baseline.status,
        0,
        `unmutated copy failed:\n${baseline.stdout}${baseline.stderr}`,
      );
      await writeFile(path.join(dir, "src", "slug.js"), mutated, "utf8");
      const proc = runTests(dir);
      assert.notEqual(
        proc.status,
        0,
        `agent tests missed mutation: ${mutation.name}\n${proc.stdout}${proc.stderr}`,
      );
    } finally {
      await rm(dir, { recursive: true, force: true });
    }
  }
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
