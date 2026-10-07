import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import type { Map as MapboxMap } from "mapbox-gl";
import { BARANGAYS } from "../data/barangays.ts";
import {
  BARANGAYS_ID,
  BARANGAY_LABELS_ID,
  CASING_ID,
  CITY_CASING_ID,
  CITY_ID,
  CITY_LINE_ID,
  GLOW_ID,
  LABEL_ID,
  LINE_ID,
  MASK_ID,
  MASK_SOURCE_ID,
  SELECTED_FILL_ID,
  SELECTED_LINE_ID,
  addBarangays,
  addFocus,
  casing,
  cityCasing,
  cityGeoJSON,
  cityLine,
  cityLoops,
  glow,
  labelsGeoJSON,
  mask,
  maskGeoJSON,
  names,
  outline,
  polygonsGeoJSON,
  removeBarangays,
  removeFocus,
  restackFocus,
  selectBarangay,
  selectedFill,
  selectedLine,
} from "./barangays.ts";

// Mapbox's own style validator, which ships with mapbox-gl (no types for its .cjs entry).
const spec = createRequire(import.meta.url)("mapbox-gl/dist/style-spec/index.cjs") as {
  validate: (style: unknown) => { message: string }[];
};

// Just enough of a mapbox-gl Map to record what the layer code asks of it, and to keep the draw order (`order`, bottom
// to top): the basemap's land and street names, then whatever is added, inserted or moved.
function fakeMap(opts: { pins?: string[]; failOn?: string; others?: string[] } = {}) {
  const log: string[] = [];
  const layers = new Map<string, { filter?: unknown }>();
  const order: string[] = ["land", "road-label", ...(opts.pins ?? [])];
  const types: Record<string, string> = { land: "background", "road-label": "symbol", [LABEL_ID]: "symbol" };
  const sources = new Set<string>();
  for (const id of opts.pins ?? []) layers.set(id, {});
  for (const id of opts.others ?? []) {
    layers.set(id, {});
    order.splice(order.indexOf("road-label"), 0, id); // like the traffic: under the street names
  }
  const place = (id: string, before?: string) => {
    const at = order.indexOf(id);
    if (at >= 0) order.splice(at, 1);
    const to = before === undefined ? -1 : order.indexOf(before);
    if (to < 0) order.push(id);
    else order.splice(to, 0, id);
  };
  const map = {
    getStyle: () => ({ layers: order.map((id) => ({ id, type: types[id] ?? "line" })) }),
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
      place(spec.id, before);
    },
    moveLayer(id: string, before?: string) {
      log.push(`moveLayer ${id}${before ? ` before ${before}` : ""}`);
      place(id, before);
    },
    setFilter(id: string, filter: unknown) {
      log.push(`setFilter ${id} ${JSON.stringify(filter)}`);
      layers.set(id, { filter });
    },
    removeLayer(id: string) {
      log.push(`removeLayer ${id}`);
      layers.delete(id);
      order.splice(order.indexOf(id), 1);
    },
    removeSource(id: string) {
      log.push(`removeSource ${id}`);
      sources.delete(id);
    },
  };
  return { map: map as unknown as MapboxMap, log, layers, sources, order };
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
      [CITY_ID]: { type: "geojson", data: cityGeoJSON(BARANGAYS) },
      [MASK_SOURCE_ID]: { type: "geojson", data: maskGeoJSON(BARANGAYS) },
    },
    layers: [mask, glow, casing, outline, selectedFill, selectedLine, cityCasing, cityLine, names],
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
  const { map, log, order } = fakeMap();
  assert.equal(addBarangays(map, BARANGAYS, null), true);
  assert.deepEqual(log.filter((l) => l.startsWith("addSource")), [
    `addSource ${BARANGAYS_ID}`,
    `addSource ${BARANGAY_LABELS_ID}`,
  ]);
  assert.deepEqual(order, ["land", CASING_ID, LINE_ID, SELECTED_FILL_ID, SELECTED_LINE_ID, "road-label", LABEL_ID]);
});

test("every border has a white casing under it, and the borders are solid enough to read over the traffic", () => {
  for (const [line, under] of [[outline, casing], [cityLine, cityCasing]] as const) {
    assert.equal(under.paint!["line-color"], "#ffffff");
    assert.ok((under.paint!["line-opacity"] as number) >= 0.9, "a casing that shows");
    assert.equal(line.paint!["line-opacity"], undefined, "the line itself is not faded");
  }
});

test("the focus: Makati's edge is solid and over its shadow, and the dimming leaves the city clear", () => {
  const { map, order, sources } = fakeMap();
  assert.equal(addFocus(map, BARANGAYS), true);
  assert.deepEqual(order, ["land", MASK_ID, GLOW_ID, CITY_CASING_ID, CITY_LINE_ID, "road-label"]);
  assert.deepEqual([...sources].sort(), [CITY_ID, MASK_SOURCE_ID].sort());
  assert.equal(cityLine.paint!["line-dasharray"], undefined);
  assert.ok((mask.paint!["fill-opacity"] as unknown[]).length > 0);
  assert.equal(mask.layout, undefined);
});

test("the borders end up over the traffic, whichever was drawn first", () => {
  // the traffic is on the map first, then the focus and the barangays...
  const a = fakeMap({ others: ["congestion", "footfall"] });
  addFocus(a.map, BARANGAYS);
  addBarangays(a.map, BARANGAYS, null);
  const top = (o: string[]) => o.indexOf("road-label");
  for (const id of [MASK_ID, GLOW_ID, CASING_ID, LINE_ID, CITY_CASING_ID, CITY_LINE_ID]) {
    assert.ok(a.order.indexOf(id) > a.order.indexOf("congestion"), `${id} over the traffic`);
    assert.ok(a.order.indexOf(id) > a.order.indexOf("footfall"), `${id} over the foot traffic`);
    assert.ok(a.order.indexOf(id) < top(a.order), `${id} under the street names`);
  }
  // ...and the other way: the traffic comes last, lands under the street names, then the stack is put right.
  const b = fakeMap();
  addFocus(b.map, BARANGAYS);
  addBarangays(b.map, BARANGAYS, null);
  b.layers.set("congestion", {});
  (b.map as unknown as { addLayer: (s: { id: string }, before?: string) => void }).addLayer({ id: "congestion" }, "road-label");
  assert.ok(b.order.indexOf("congestion") > b.order.indexOf(LINE_ID), "the traffic landed on top");
  restackFocus(b.map);
  for (const id of [CASING_ID, LINE_ID, CITY_LINE_ID]) assert.ok(b.order.indexOf(id) > b.order.indexOf("congestion"), id);
  assert.deepEqual(
    b.order.filter((id) => id !== "congestion"),
    ["land", MASK_ID, GLOW_ID, CASING_ID, LINE_ID, SELECTED_FILL_ID, SELECTED_LINE_ID, CITY_CASING_ID, CITY_LINE_ID, "road-label", LABEL_ID],
  );
});

test("restacking keeps the names over the street names and under the pins, and skips layers that are not there", () => {
  const { map, order } = fakeMap({ pins: ["reports"] });
  restackFocus(map); // nothing drawn: nothing to move
  assert.deepEqual(order, ["land", "road-label", "reports"]);
  addFocus(map, BARANGAYS);
  addBarangays(map, BARANGAYS, null);
  assert.ok(order.indexOf(LABEL_ID) > order.indexOf("road-label") && order.indexOf(LABEL_ID) < order.indexOf("reports"));
  assert.ok(order.indexOf(CITY_LINE_ID) < order.indexOf("road-label"));
});

test("removing the barangays leaves the focus, and removing the focus takes both sources and its layers", () => {
  const { map, layers, sources } = fakeMap();
  addFocus(map, BARANGAYS);
  addBarangays(map, BARANGAYS, null);
  removeBarangays(map);
  assert.deepEqual([...layers.keys()].sort(), [CITY_CASING_ID, CITY_LINE_ID, GLOW_ID, MASK_ID].sort());
  removeFocus(map);
  assert.equal(layers.size, 0);
  assert.equal(sources.size, 0);
  removeFocus(map);
});

test("the city's edge is one loop round Makati, with the cemetery's enclave apart, and every point on it is on a barangay", () => {
  const { outer, enclaves } = cityLoops(BARANGAYS);
  assert.equal(outer.length, 1);
  assert.equal(enclaves.length, 1);
  for (const loop of [...outer, ...enclaves]) {
    assert.deepEqual(loop[0], loop[loop.length - 1], "closed");
    assert.ok(loop.length > 4);
  }
  const points = new Set(BARANGAYS.flatMap((b) => b.rings.flat().map((p) => p.join())));
  assert.ok(outer[0].every((p) => points.has(p.join())));
  // The edge has far fewer points than the outlines together: the shared sides are gone.
  assert.ok(outer[0].length < BARANGAYS.flatMap((b) => b.rings.flat()).length / 2);
});

test("the mask is the world with Makati cut out, and the enclave filled back in", () => {
  const m = maskGeoJSON(BARANGAYS).geometry.coordinates;
  assert.equal(m.length, 2, "the world with its hole, and the enclave");
  assert.equal(m[0].length, 2, "the world and one hole");
  assert.deepEqual(m[0][0][0], [-180, -85]);
  assert.equal(cityGeoJSON(BARANGAYS).geometry.coordinates.length, 2, "the edge and the enclave's");
});

test("a barangay on its own is its own city: its whole outline is the edge", () => {
  const one = [BARANGAYS[0]];
  const { outer, enclaves } = cityLoops(one);
  assert.equal(outer.length, 1);
  assert.equal(enclaves.length, 0);
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
  assert.deepEqual([...layers.keys()].sort(), [CASING_ID, LABEL_ID, LINE_ID, SELECTED_FILL_ID, SELECTED_LINE_ID].sort());
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
