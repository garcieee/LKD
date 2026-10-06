import { test } from "node:test";
import assert from "node:assert/strict";
import type { Footfall } from "../types/api.ts";
import { FOOTFALL_RAMP, heatGeoJSON, manilaNow, ringsGeoJSON } from "./footfall.ts";

const data: Footfall = {
  kind: "estimate",
  method: "test",
  day: "mon",
  hour: 8,
  points: [
    { id: "a", name: "A", kind: "hub", lat: 14.55, lng: 121.02, error_m: 40, profile: "cbd", district: "d", index: 80, lower: 60, upper: 100 },
    { id: "b", name: "B", kind: "anchor", lat: 14.56, lng: 121.03, error_m: 20, profile: "cbd", district: "d", index: 130, lower: 0, upper: 100 },
  ],
  districts: [
    { id: "d", name: "D", lat: 14.55, lng: 121.02, radius_m: 500, profile: "cbd", tier: 1, share: 1, hubs: 1, route_ends: 2, anchor: 0.5, basis: "", index: 100, lower: 75, upper: 100 },
  ],
};

test("heat points are [lng, lat] with a 0-1 weight", () => {
  const f = heatGeoJSON(data).features;
  assert.deepEqual(f[0].geometry.coordinates, [121.02, 14.55]);
  assert.equal(f[0].properties.w, 0.8);
});

test("a weight over 100 is clamped to 1", () => {
  assert.equal(heatGeoJSON(data).features[1].properties.w, 1);
});

test("each district gets a ring carrying its radius and tier", () => {
  const f = ringsGeoJSON(data).features;
  assert.equal(f.length, 1);
  assert.deepEqual(f[0].properties, { id: "d", name: "D", tier: 1, radius_m: 500, w: 1 });
});

test("the colour ramp rises from 0 to 1, as mapbox needs", () => {
  const stops = FOOTFALL_RAMP.map(([s]) => s);
  assert.deepEqual(stops, [...stops].sort((a, b) => a - b));
  assert.equal(stops[0], 0);
  assert.equal(stops.at(-1), 1);
});

test("reads the Manila weekday and hour whatever the machine's zone", () => {
  // 2026-10-06 10:00 UTC is Tuesday 18:00 in Manila.
  assert.deepEqual(manilaNow(new Date("2026-10-06T10:00:00Z")), { day: "tue", hour: 18 });
  // 20:00 UTC on Sunday is already Monday 04:00 there.
  assert.deepEqual(manilaNow(new Date("2026-10-04T20:00:00Z")), { day: "mon", hour: 4 });
});
