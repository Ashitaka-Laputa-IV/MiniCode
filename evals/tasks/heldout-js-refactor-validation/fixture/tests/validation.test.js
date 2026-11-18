import assert from "node:assert/strict";
import test from "node:test";

import { createAccount, updateAccount } from "../src/index.js";

test("createAccount accepts valid input", () => {
  assert.deepEqual(createAccount({ email: "ada@example.com", age: 36 }), {
    email: "ada@example.com",
    age: 36,
  });
});

test("createAccount rejects invalid email", () => {
  assert.throws(() => createAccount({ email: "nope", age: 36 }), {
    name: "TypeError",
    message: "invalid email",
  });
});

test("updateAccount merges valid input", () => {
  assert.deepEqual(updateAccount({ email: "ada@example.com", age: 36 }, { age: 37 }), {
    email: "ada@example.com",
    age: 37,
  });
});
