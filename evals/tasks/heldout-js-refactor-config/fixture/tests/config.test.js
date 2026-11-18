import assert from "node:assert/strict";
import test from "node:test";

import { clientConfig, serverConfig } from "../src/index.js";

test("serverConfig defaults", () => {
  assert.deepEqual(serverConfig(), { host: "localhost", port: 3000 });
});

test("serverConfig applies defined overrides", () => {
  assert.deepEqual(serverConfig({ port: 8080 }), { host: "localhost", port: 8080 });
});

test("clientConfig defaults and overrides", () => {
  assert.deepEqual(clientConfig(), { host: "localhost", timeout: 5000 });
  assert.deepEqual(clientConfig({ host: "example.com" }), {
    host: "example.com",
    timeout: 5000,
  });
});
