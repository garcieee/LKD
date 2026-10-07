import { test } from "node:test";
import assert from "node:assert/strict";
import type { Report } from "../../types/api.ts";
import { BARANGAYS } from "../../data/barangays.ts";
import { barangayAt, boundsOf, norm, pointInRing, searchBarangays, sortBarangays, tally, type Barangay } from "./barangays.ts";

const names = (list: Barangay[]) => list.map((b) => b.name);

test("norm: accents, punctuation, case and a Brgy/Barangay prefix do not matter, and Sta. is Santa", () => {
  assert.equal(norm("Dasmariñas"), "dasmarinas");
  assert.equal(norm("  DASMARIÑAS "), "dasmarinas");
  assert.equal(norm("Bel-Air"), "bel air");
  assert.equal(norm("Brgy. Poblacion"), "poblacion");
  assert.equal(norm("Barangay San Lorenzo"), "san lorenzo");
  assert.equal(norm("Sta. Cruz"), "santa cruz");
  assert.equal(norm("???"), "");
});

test("nothing typed lists every barangay, A to Z", () => {
  const all = searchBarangays(BARANGAYS, "");
  assert.equal(all.length, 23);
  assert.deepEqual(names(all), [...names(all)].sort((a, b) => a.localeCompare(b, "en")));
});

test("a few letters find the barangay, however it is spelled", () => {
  assert.deepEqual(names(searchBarangays(BARANGAYS, "pob")), ["Poblacion"]);
  assert.deepEqual(names(searchBarangays(BARANGAYS, "dasmarinas")), ["Dasmariñas"]);
  assert.deepEqual(names(searchBarangays(BARANGAYS, "DASMARIÑAS")), ["Dasmariñas"]);
  assert.deepEqual(names(searchBarangays(BARANGAYS, "belair")), ["Bel-Air"]);
  assert.deepEqual(names(searchBarangays(BARANGAYS, "bel air")), ["Bel-Air"]);
  assert.deepEqual(names(searchBarangays(BARANGAYS, "sta cruz")), ["Santa Cruz"]);
  assert.deepEqual(names(searchBarangays(BARANGAYS, "pio del")), ["Pio del Pilar"]);
});

test("names that start with the search come before names that only have a word that does", () => {
  assert.deepEqual(names(searchBarangays(BARANGAYS, "san")), ["San Antonio", "San Isidro", "San Lorenzo", "Santa Cruz"]);
  assert.deepEqual(names(searchBarangays(BARANGAYS, "cruz")), ["Santa Cruz"], "a later word counts");
  assert.deepEqual(names(searchBarangays(BARANGAYS, "guadalupe")), ["Guadalupe Nuevo", "Guadalupe Viejo"]);
});

test("a district can be asked for in a few ways, and a search that matches nothing is empty", () => {
  for (const q of ["d2", "D2", "district 2", "dist 2", "2"]) {
    assert.deepEqual(names(searchBarangays(BARANGAYS, q)), ["Guadalupe Nuevo", "Guadalupe Viejo", "Pinagkaisahan"], q);
  }
  assert.equal(searchBarangays(BARANGAYS, "district 1").length, 20);
  assert.deepEqual(searchBarangays(BARANGAYS, "zzzz"), []);
});

test("pointInRing: inside, outside, and a notch in an L-shaped ring", () => {
  const square: [number, number][] = [[0, 0], [4, 0], [4, 4], [0, 4], [0, 0]];
  assert.ok(pointInRing(2, 2, square));
  assert.ok(!pointInRing(5, 2, square));
  assert.ok(!pointInRing(-1, 2, square));
  const ell: [number, number][] = [[0, 0], [4, 0], [4, 2], [2, 2], [2, 4], [0, 4], [0, 0]];
  assert.ok(pointInRing(1, 3, ell), "the tall arm");
  assert.ok(!pointInRing(3, 3, ell), "the notch is outside");
});

test("barangayAt finds the barangay a place is in, in the right order of longitude and latitude", () => {
  const at = (lng: number, lat: number) => barangayAt(BARANGAYS, lng, lat)?.name ?? null;
  assert.equal(at(121.0235, 14.5528), "San Lorenzo"); // Greenbelt
  assert.equal(at(121.03, 14.564), "Poblacion"); // Makati Avenue and Jupiter
  assert.equal(at(121.0195, 14.5365), "Magallanes");
  assert.equal(at(121.039, 14.542), "Forbes Park");
  assert.equal(at(121.027, 14.56), "Bel-Air");
  assert.equal(at(121.03, 14.5545), "Urdaneta");
});

test("a place outside the 23 barangays is in none: beyond Makati, or in a barangay that is Taguig now", () => {
  assert.equal(barangayAt(BARANGAYS, 121.1, 14.6), null);
  assert.equal(barangayAt(BARANGAYS, 121.0525, 14.5495), null);
  assert.equal(barangayAt(BARANGAYS, 0, 0), null);
});

test("every barangay's own label point is in that barangay", () => {
  for (const b of BARANGAYS) assert.equal(barangayAt(BARANGAYS, ...b.center)?.id, b.id, b.name);
});

test("boundsOf is the box to zoom to: southwest then northeast, [lng, lat]", () => {
  const poblacion = BARANGAYS.find((b) => b.id === "poblacion")!;
  const [[w, s], [e, n]] = boundsOf(poblacion);
  assert.ok(w < e && s < n);
  assert.ok(w <= poblacion.center[0] && poblacion.center[0] <= e && s <= poblacion.center[1] && poblacion.center[1] <= n);
});

const report = (id: string, lng: number, lat: number, over: Partial<Report> = {}): Report => ({
  id,
  category: "pothole",
  severity: 2,
  lat,
  lng,
  heading: null,
  note: "",
  photo_url: `/photos/${id}.jpg`,
  status: "open",
  created_at: "2026-10-07T00:00:00Z",
  updated_at: "2026-10-07T00:00:00Z",
  ...over,
});
const SAN_LORENZO: [number, number] = [121.0235, 14.5528];
const POBLACION: [number, number] = [121.03, 14.564];

test("tally counts each barangay's tickets: unresolved, urgent, SOS, and all", () => {
  const counts = tally(BARANGAYS, [
    report("a", ...SAN_LORENZO),
    report("b", ...SAN_LORENZO, { status: "assigned", band: "Critical", severity: 3 }),
    report("c", ...SAN_LORENZO, { status: "fixed", band: "Critical", severity: 3 }),
    report("d", ...SAN_LORENZO, { status: "rejected" }),
    report("sos", ...SAN_LORENZO, { category: "sos", severity: 3 }),
    report("e", ...POBLACION),
    report("far", 121.1, 14.6),
  ]);
  assert.deepEqual(counts.get("san-lorenzo"), { unresolved: 3, urgent: 2, sos: 1, total: 5 });
  assert.deepEqual(counts.get("poblacion"), { unresolved: 1, urgent: 0, sos: 0, total: 1 });
  assert.deepEqual(counts.get("bangkal"), { unresolved: 0, urgent: 0, sos: 0, total: 0 }, "a quiet barangay is zeros, not missing");
  assert.equal(counts.size, 23);
});

test("sortBarangays: A to Z as given, or the busiest first with SOS before everything", () => {
  const counts = tally(BARANGAYS, [
    report("a", ...POBLACION),
    report("b", ...POBLACION),
    report("c", ...SAN_LORENZO),
    report("sos", 121.0195, 14.5365, { category: "sos", severity: 3 }), // Magallanes
  ]);
  assert.deepEqual(sortBarangays(BARANGAYS, "name", counts).map((b) => b.id), BARANGAYS.map((b) => b.id));
  assert.deepEqual(sortBarangays(BARANGAYS, "busiest", counts).slice(0, 3).map((b) => b.name), ["Magallanes", "Poblacion", "San Lorenzo"]);
  assert.equal(sortBarangays(BARANGAYS, "busiest", counts)[3].name, "Bangkal", "then the quiet ones A to Z");
});
