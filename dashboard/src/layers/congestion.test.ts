import { test } from "node:test";
import assert from "node:assert/strict";
import { CLIPPED_ID, CONGESTION_ID, CONGESTION_RAMP, clippedLayer, congestionLayer, congestionTileUrl, tilesLayer } from "./congestion.ts";

test("keeps the tile placeholders mapbox substitutes", () => {
  const url = congestionTileUrl("abc123");
  assert.match(url, /\/flow\/relative\/\{z\}\/\{x\}\/\{y\}\.pbf\?/);
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

test("asks TomTom to snap traffic_level so neighbouring segments merge", () => {
  assert.match(congestionTileUrl("k"), /[?&]trafficLevelStep=0\.1(&|$)/);
});

test("draws TomTom's 'Traffic flow' vector layer as lines", () => {
  const layer = congestionLayer();
  assert.equal(layer.type, "line");
  assert.equal(layer["source-layer"], "Traffic flow");
});

test("the ramp runs worst to best over 0..1, ascending as mapbox needs", () => {
  const levels = CONGESTION_RAMP.map(([level]) => level);
  assert.equal(levels[0], 0);
  assert.equal(levels.at(-1), 1);
  assert.ok(levels.every((l, i) => i === 0 || l > levels[i - 1]));
});

test("zoom only drives the top-level interpolate of width and offset", () => {
  // mapbox rejects a "zoom" nested inside case/match, and that drops the whole layer.
  const paint = congestionLayer().paint as unknown as Record<string, unknown[]>;
  for (const prop of ["line-width", "line-offset"]) {
    assert.equal(paint[prop][0], "interpolate");
    assert.deepEqual(paint[prop][2], ["zoom"]);
  }
});

test("the clipped layer paints like the vector one, from its own GeoJSON source; the tiles layer draws nothing", () => {
  const vector = congestionLayer();
  const clipped = clippedLayer();
  assert.equal(clipped.id, CLIPPED_ID);
  assert.equal(clipped.source, CLIPPED_ID);
  assert.equal("source-layer" in clipped, false, "a GeoJSON source has no source layer");
  assert.deepEqual(clipped.paint, vector.paint);
  assert.deepEqual(clipped.layout, vector.layout);
  const tiles = tilesLayer();
  assert.equal(tiles.id, CONGESTION_ID);
  assert.equal(tiles.paint!["line-opacity"], 0, "it only loads the tiles");
  assert.equal(vector.paint!["line-opacity"], undefined, "the plain layer is unchanged");
});
