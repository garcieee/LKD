import { test } from "node:test";
import assert from "node:assert/strict";
import { congestionTileUrl } from "./congestion.ts";

test("keeps the tile placeholders mapbox substitutes", () => {
  const url = congestionTileUrl("abc123");
  assert.match(url, /\/flow\/relative\/\{z\}\/\{x\}\/\{y\}\.png\?/);
});

test("passes the key through, escaped", () => {
  assert.match(congestionTileUrl("a b&c"), /[?&]key=a%20b%26c(&|$)/);
});

test("only busts the cache when given a stamp", () => {
  assert.ok(!congestionTileUrl("k").includes("&t="));
  assert.ok(congestionTileUrl("k", 1700).includes("&t=1700"));
});

test("fails loudly when the key is missing", () => {
  assert.throws(() => congestionTileUrl(""), /VITE_TOMTOM_API_KEY/);
});
