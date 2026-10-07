import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import type { Map as MapboxMap } from "mapbox-gl";
import { BARANGAYS } from "../data/barangays.ts";
import {
  BARANGAYS_ID,
  BARANGAY_LABELS_ID,
  LABEL_ID,
  LINE_ID,
  SELECTED_FILL_ID,
  SELECTED_LINE_ID,
  addBarangays,
  labelsGeoJSON,
  names,
  outline,
  polygonsGeoJSON,
  removeBarangays,
  selectBarangay,
  selectedFill,
  selectedLine,
} from "./barangays.ts";

// Mapbox's own style validator, which ships with mapbox-gl (no types for its .cjs entry).
const spec = createRequire(import.meta.url)("mapbox-gl/dist/style-spec/index.cjs") as {
  validate: (style: unknown) => { message: string }[];
};

// Just enough of a mapbox-gl Map to record what the layer code asks of it.
function fakeMap(opts: { pins?: string[]; failOn?: string } = {}) {
  const log: string[] = [];
  const layers = new Map<string, { filter?: unknown }>(); // in draw order
  const sources = new Set<string>();
  for (const id of opts.pins ?? []) layers.set(id, {});
  const map = {
    getStyle: () => ({ layers: [{ id: "land", type: "background" }, { id: "road-label", type: "symbol" }] }),
    getLayer: (id: string) => layers.get(id),
    getSource: (id: string) => (sources.has(id) ? {} : undefined),
    addSource(id: string) {
      if (opts.failOn === `source ${id}`) throw new Error("Style is not done loading");
      log.push(`addSource ${id}`);
      sources.add(id);
    },
    addLayer(spec: { id: string; filter?: unknown }, before?: string) {
      log.push(`addLayer ${spec.id}${before ? ` before ${before}` : ""}`);
      layers.set(spec.id, { filter: spec.filter });
    },
    setFilter(id: string, filter: unknown) {
      log.push(`setFilter ${id} ${JSON.stringify(filter)}`);
      layers.set(id, { filter });
    },
    removeLayer(id: string) {
      log.push(`removeLayer ${id}`);
      layers.delete(id);
    },
    removeSource(id: string) {
      log.push(`removeSource ${id}`);
      sources.delete(id);
    },
  };
  return { map: map as unknown as MapboxMap, log, layers, sources };
}

test("one MultiPolygon per barangay, [lng, lat], and one label point each with its size rank", () => {
  const polys = polygonsGeoJSON(BARANGAYS);
  assert.equal(polys.features.length, 23);
  const poblacion = polys.features.find((f) => f.properties.id === "poblacion")!;
  assert.equal(poblacion.geometry.type, "MultiPolygon");
  assert.deepEqual(poblacion.geometry.coordinates[0][0], BARANGAYS.find((b) => b.id === "poblacion")!.rings[0]);

  const labels = labelsGeoJSON(BARANGAYS);
  assert.equal(labels.features.length, 23, "one name each, not one per map tile");
  const p = labels.features.find((f) => f.properties.id === "poblacion")!;
  assert.deepEqual(p.geometry.coordinates, BARANGAYS.find((b) => b.id === "poblacion")!.center);
  assert.deepEqual(Object.keys(p.properties).sort(), ["district", "id", "name", "rank"]);
});

test("the layer definitions pass Mapbox's own style validation", () => {
  const style = {
    version: 8,
    glyphs: "mapbox://fonts/mapbox/{fontstack}/{range}.pbf",
    sources: {
      [BARANGAYS_ID]: { type: "geojson", data: polygonsGeoJSON(BARANGAYS) },
      [BARANGAY_LABELS_ID]: { type: "geojson", data: labelsGeoJSON(BARANGAYS) },
    },
    layers: [outline, selectedFill, selectedLine, names],
  };
  assert.deepEqual(spec.validate(style).map((e) => e.message), []);
});

test("the validator would catch a mistake here (so the check above means something)", () => {
  const style = {
    version: 8,
    sources: { s: { type: "geojson", data: { type: "FeatureCollection", features: [] } } },
    layers: [{ ...outline, source: "s", paint: { "line-width": ["interpolate", ["linear"], ["zoom"], 11] } }],
  };
  assert.ok(spec.validate(style).length > 0);
});

test("the names show from a city view and fade out as the streets take over", () => {
  assert.equal(names.minzoom, 10);
  assert.deepEqual(names.paint!["text-opacity"], ["interpolate", ["linear"], ["zoom"], 14.5, 1, 16.5, 0]);
});

test("adding draws the outlines under the basemap's street names, and the names over them", () => {
  const { map, log } = fakeMap();
  assert.equal(addBarangays(map, BARANGAYS, null), true);
  assert.deepEqual(log.filter((l) => !l.startsWith("setFilter")), [
    `addSource ${BARANGAYS_ID}`,
    `addSource ${BARANGAY_LABELS_ID}`,
    `addLayer ${LINE_ID} before road-label`,
    `addLayer ${SELECTED_FILL_ID} before road-label`,
    `addLayer ${SELECTED_LINE_ID} before road-label`,
    `addLayer ${LABEL_ID}`,
  ]);
});

test("the names go under the report pins when those are already on the map", () => {
  const { map, log } = fakeMap({ pins: ["reports-sos-halo", "reports-selected", "reports"] });
  addBarangays(map, BARANGAYS, null);
  assert.ok(log.includes(`addLayer ${LABEL_ID} before reports-sos-halo`));
});

test("adding again replaces what was drawn instead of adding a second set", () => {
  const { map, layers, sources } = fakeMap();
  addBarangays(map, BARANGAYS, null);
  addBarangays(map, BARANGAYS, "poblacion");
  assert.equal(sources.size, 2);
  assert.deepEqual([...layers.keys()].sort(), [LABEL_ID, LINE_ID, SELECTED_FILL_ID, SELECTED_LINE_ID].sort());
});

test("selecting tints one barangay, and null tints none", () => {
  const { map, layers } = fakeMap();
  addBarangays(map, BARANGAYS, "poblacion");
  assert.deepEqual(layers.get(SELECTED_FILL_ID)!.filter, ["==", ["get", "id"], "poblacion"]);
  assert.deepEqual(layers.get(SELECTED_LINE_ID)!.filter, ["==", ["get", "id"], "poblacion"]);
  selectBarangay(map, null);
  const none = (layers.get(SELECTED_FILL_ID)!.filter as unknown[])[2];
  assert.ok(!BARANGAYS.some((b) => b.id === none), "an id no barangay has");
  selectBarangay(map, "bel-air");
  assert.deepEqual(layers.get(SELECTED_LINE_ID)!.filter, ["==", ["get", "id"], "bel-air"]);
});

test("selecting before they are drawn does nothing and does not fail", () => {
  const { map, log } = fakeMap();
  selectBarangay(map, "poblacion");
  assert.deepEqual(log, []);
});

test("removing takes away every layer and both sources, and is safe to repeat", () => {
  const { map, layers, sources } = fakeMap();
  addBarangays(map, BARANGAYS, null);
  removeBarangays(map);
  assert.equal(layers.size, 0);
  assert.equal(sources.size, 0);
  removeBarangays(map);
});

test("a map that cannot take them yet is logged, not thrown: the dashboard goes on without them", () => {
  const { map } = fakeMap({ failOn: `source ${BARANGAY_LABELS_ID}` });
  const warn = console.warn;
  const warned: unknown[][] = [];
  console.warn = (...args: unknown[]) => void warned.push(args);
  try {
    assert.equal(addBarangays(map, BARANGAYS, null), false);
  } finally {
    console.warn = warn;
  }
  assert.equal(warned.length, 1);
});
