import { test } from "node:test";
import assert from "node:assert/strict";
import { BARANGAYS } from "../data/barangays.ts";
import { cityLoops } from "./barangays.ts";
import { clipFeatures, clipLine, inside } from "./clip.ts";

type Pos = [number, number];
const square: Pos[] = [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]];
const hole: Pos[] = [[4, 4], [6, 4], [6, 6], [4, 6], [4, 4]];

test("inside: in the loop is in, outside is out, and a hole in it is out", () => {
  assert.equal(inside([5, 2], [square]), true);
  assert.equal(inside([11, 5], [square]), false);
  assert.equal(inside([5, 5], [square, hole]), false, "in the hole");
  assert.equal(inside([2, 5], [square, hole]), true);
});

test("a line wholly inside is kept whole, one wholly outside is gone", () => {
  assert.deepEqual(clipLine([[1, 1], [5, 2], [9, 1]], [square]), [[[1, 1], [5, 2], [9, 1]]]);
  assert.deepEqual(clipLine([[11, 1], [15, 5]], [square]), []);
});

test("a line that crosses the border is cut at the border", () => {
  assert.deepEqual(clipLine([[5, 5], [15, 5]], [square]), [[[5, 5], [10, 5]]]);
  assert.deepEqual(clipLine([[-5, 5], [5, 5]], [square]), [[[0, 5], [5, 5]]]);
  assert.deepEqual(clipLine([[-5, 5], [15, 5]], [square]), [[[0, 5], [10, 5]]], "through the city");
});

test("a line that leaves and comes back is two lines, and a hole cuts it too", () => {
  const out = clipLine([[2, 2], [2, 12], [8, 12], [8, 2]], [square]);
  assert.equal(out.length, 2);
  assert.deepEqual(out[0], [[2, 2], [2, 10]]);
  assert.deepEqual(out[1], [[8, 10], [8, 2]]);
  assert.deepEqual(clipLine([[1, 5], [9, 5]], [square, hole]), [[[1, 5], [4, 5]], [[6, 5], [9, 5]]]);
});

test("features keep what the layer paints from, MultiLineString or LineString, and drop what is outside", () => {
  const props = { traffic_level: 0.4, road_type: "Major road", traffic_road_coverage: "full", other: 1 };
  const out = clipFeatures(
    [
      { geometry: { type: "LineString", coordinates: [[5, 5], [15, 5]] }, properties: props },
      { geometry: { type: "MultiLineString", coordinates: [[[1, 1], [2, 2]], [[20, 20], [30, 30]]] }, properties: props },
      { geometry: { type: "LineString", coordinates: [[50, 50], [60, 60]] }, properties: props },
      { geometry: { type: "Point", coordinates: [5, 5] }, properties: props },
    ],
    [square],
  );
  assert.equal(out.features.length, 2);
  assert.deepEqual(out.features[0].geometry.coordinates, [[[5, 5], [10, 5]]]);
  assert.deepEqual(out.features[1].geometry.coordinates, [[[1, 1], [2, 2]]]);
  assert.deepEqual(out.features[0].properties, { traffic_level: 0.4, road_type: "Major road", traffic_road_coverage: "full" });
});

test("on the real city: a road through Makati is cut at its edge, the cemetery and the outside get none", () => {
  const { outer, enclaves } = cityLoops(BARANGAYS);
  const loops = [...outer, ...enclaves];
  const poblacion = BARANGAYS.find((b) => b.id === "poblacion")!;
  assert.equal(inside(poblacion.center as Pos, loops), true);
  const cemetery = enclaves[0];
  const mid: Pos = [
    cemetery.reduce((s, p) => s + p[0], 0) / cemetery.length,
    cemetery.reduce((s, p) => s + p[1], 0) / cemetery.length,
  ];
  assert.equal(inside(mid, loops), false, "the cemetery is not Makati's");
  assert.equal(inside([120.97, 14.6], loops), false, "Manila");
  // East to west across the whole city at Poblacion's latitude, from far outside both ends.
  const lat = poblacion.center[1];
  const [part] = clipLine([[120.95, lat], [121.1, lat]], loops);
  assert.ok(part[0][0] > 120.95 && part[part.length - 1][0] < 121.1, "cut short at both ends");
});
