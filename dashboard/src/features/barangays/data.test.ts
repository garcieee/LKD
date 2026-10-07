// The generated data/barangays.ts against what it is generated from, and against Makati itself.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { BARANGAYS, DISTRICTS } from "../../data/barangays.ts";
import { MAKATI } from "../../config/makati.ts";
import { pointInRing } from "./barangays.ts";

// What the ticket engine reads: models/tickets/resources/districts.json (OpenStreetMap, ODbL).
const source = JSON.parse(
  readFileSync(new URL("../../../../models/tickets/resources/districts.json", import.meta.url), "utf8"),
) as { districts: Record<string, string>; barangays: { name: string; district_id: number; rings: [number, number][][] }[] };

test("the menu lists the same 23 barangays, districts and outlines as the ticket engine (rebuild it if this fails)", () => {
  assert.equal(BARANGAYS.length, source.barangays.length);
  assert.equal(BARANGAYS.length, 23);
  assert.deepEqual(DISTRICTS, Object.fromEntries(Object.entries(source.districts).map(([k, v]) => [Number(k), v])));
  const byName = new Map(source.barangays.map((b) => [b.name, b]));
  for (const b of BARANGAYS) {
    const s = byName.get(b.name);
    assert.ok(s, `${b.name} is in the source`);
    assert.equal(b.district, s.district_id, b.name);
    assert.equal(b.rings.length, s.rings.length, b.name);
    // Rounded to 5 decimals (about a metre) and with repeated points dropped, so compare the extremes, not every point.
    const lngs = s.rings.flat().map((p) => p[0]);
    const lats = s.rings.flat().map((p) => p[1]);
    assert.ok(Math.abs(b.bbox[0] - Math.min(...lngs)) < 1e-5 && Math.abs(b.bbox[2] - Math.max(...lngs)) < 1e-5, b.name);
    assert.ok(Math.abs(b.bbox[1] - Math.min(...lats)) < 1e-5 && Math.abs(b.bbox[3] - Math.max(...lats)) < 1e-5, b.name);
  }
});

test("ids are unique and URL-safe, ranks run 0 to 22 once each, and the list is A to Z", () => {
  assert.equal(new Set(BARANGAYS.map((b) => b.id)).size, 23);
  for (const b of BARANGAYS) assert.match(b.id, /^[a-z0-9]+(-[a-z0-9]+)*$/, b.name);
  assert.deepEqual([...BARANGAYS.map((b) => b.rank)].sort((a, b) => a - b), Array.from({ length: 23 }, (_, i) => i));
  const sorted = [...BARANGAYS].sort((a, b) => a.name.localeCompare(b.name, "en", { sensitivity: "base" }));
  assert.deepEqual(BARANGAYS.map((b) => b.id), sorted.map((b) => b.id));
});

test("every outline is closed, has real area, and lies in Makati's map (a lng, lat swap would fail this)", () => {
  const [[west, south], [east, north]] = MAKATI.bounds;
  const m = 0.004; // the map's own margin past the city line
  for (const b of BARANGAYS) {
    assert.ok(b.rings.length >= 1, b.name);
    for (const ring of b.rings) {
      assert.ok(ring.length >= 4, `${b.name}: a closed ring has at least 4 points`);
      assert.deepEqual(ring[0], ring.at(-1), `${b.name}: closed`);
      for (const [lng, lat] of ring) {
        assert.ok(lng >= west - m && lng <= east + m && lat >= south - m && lat <= north + m, `${b.name}: ${lng},${lat}`);
      }
    }
    const [w, s, e, n] = b.bbox;
    assert.ok(w < e && s < n, b.name);
  }
});

test("each label point is inside its barangay's box and outline", () => {
  for (const b of BARANGAYS) {
    const [x, y] = b.center;
    assert.ok(x >= b.bbox[0] && x <= b.bbox[2] && y >= b.bbox[1] && y <= b.bbox[3], `${b.name}: in the box`);
    assert.ok(b.rings.some((r) => pointInRing(x, y, r)), `${b.name}: in the outline`);
  }
});
