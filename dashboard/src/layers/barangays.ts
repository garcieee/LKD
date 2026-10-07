// Makati on the map. Two parts:
//  - The focus, always on: everything outside the city is dimmed, a soft shadow runs along the city's edge and the edge
//    itself is a solid line. The city's edge is worked out from the barangays (cityLoops), not drawn from a second file.
//  - The barangays, switched on and off: a dashed outline round each, a tint and heavier outline on the selected one,
//    and each one's name, drawn while the map is zoomed out and faded away as the streets take over (zoom 14.5 to 16.5).
// Every line has a white casing under it, so it reads over the traffic's red, orange, yellow and green and over roads.
// All of it sits above the traffic and foot-traffic layers and under the basemap's street names (restackFocus keeps it
// there however the layers were added); the barangay names go over the street names and under the report pins.
//
// ponytail: the names are their own point source, one point per barangay at its label point (data/barangays.ts), not
// the polygons: a symbol layer on a polygon places one label per map tile, so a big barangay would be named twice.
import type {
  ExpressionSpecification,
  FillLayerSpecification,
  LineLayerSpecification,
  Map as MapboxMap,
  SymbolLayerSpecification,
} from "mapbox-gl";
import type { Barangay } from "../features/barangays/barangays.ts";

export const BARANGAYS_ID = "barangays"; // the outlines' source
export const BARANGAY_LABELS_ID = "barangay-labels"; // the names' source
export const CITY_ID = "makati-city"; // the city's edge, as lines
export const MASK_SOURCE_ID = "makati-mask-source"; // everything but the city, as an area
export const MASK_ID = "makati-mask";
export const GLOW_ID = "makati-glow";
export const CITY_CASING_ID = "makati-edge-casing";
export const CITY_LINE_ID = "makati-edge";
export const CASING_ID = "barangay-casing";
export const LINE_ID = "barangay-line";
export const SELECTED_FILL_ID = "barangay-selected-fill";
export const SELECTED_LINE_ID = "barangay-selected-line";
export const LABEL_ID = "barangay-label";
const NONE = "__none__"; // an id no barangay has: the selected layers draw nothing
// The report pins' layers, lowest first (layers/reports.ts): the names go under the first of these that exists.
const PIN_LAYERS = ["reports-sos-halo", "reports-selected", "reports"];

const NAVY = "#212e4a";
const matches = (id: string): ExpressionSpecification => ["==", ["get", "id"], id];

// One area per ring: a barangay in two pieces is two polygons of one feature.
export function polygonsGeoJSON(list: readonly Barangay[]) {
  return {
    type: "FeatureCollection" as const,
    features: list.map((b) => ({
      type: "Feature" as const,
      geometry: { type: "MultiPolygon" as const, coordinates: b.rings.map((ring) => [ring]) },
      properties: { id: b.id, name: b.name, district: b.district },
    })),
  };
}

export function labelsGeoJSON(list: readonly Barangay[]) {
  return {
    type: "FeatureCollection" as const,
    features: list.map((b) => ({
      type: "Feature" as const,
      geometry: { type: "Point" as const, coordinates: b.center },
      properties: { id: b.id, name: b.name, district: b.district, rank: b.rank },
    })),
  };
}

export const casing: LineLayerSpecification = {
  id: CASING_ID,
  type: "line",
  source: BARANGAYS_ID,
  layout: { "line-join": "round" },
  paint: {
    "line-color": "#ffffff",
    "line-width": ["interpolate", ["linear"], ["zoom"], 11, 3, 15, 5.5],
    "line-opacity": 0.9,
  },
};

export const outline: LineLayerSpecification = {
  id: LINE_ID,
  type: "line",
  source: BARANGAYS_ID,
  layout: { "line-join": "round" },
  paint: {
    "line-color": "#2f3f6b",
    "line-width": ["interpolate", ["linear"], ["zoom"], 11, 1.4, 15, 2.8],
    "line-dasharray": [3, 1.5],
  },
};

export const selectedFill: FillLayerSpecification = {
  id: SELECTED_FILL_ID,
  type: "fill",
  source: BARANGAYS_ID,
  filter: matches(NONE),
  paint: { "fill-color": NAVY, "fill-opacity": 0.1 },
};

export const selectedLine: LineLayerSpecification = {
  id: SELECTED_LINE_ID,
  type: "line",
  source: BARANGAYS_ID,
  filter: matches(NONE),
  layout: { "line-join": "round" },
  paint: { "line-color": NAVY, "line-width": 3.5 },
};

export const names: SymbolLayerSpecification = {
  id: LABEL_ID,
  type: "symbol",
  source: BARANGAY_LABELS_ID,
  minzoom: 10,
  layout: {
    "text-field": ["get", "name"],
    "text-font": ["DIN Pro Medium", "Arial Unicode MS Regular"], // in the light-v11 style's glyphs
    "text-size": ["interpolate", ["linear"], ["zoom"], 10, 9, 12, 11, 15, 14],
    "text-transform": "uppercase",
    "text-letter-spacing": 0.08,
    "text-max-width": 7,
    "symbol-sort-key": ["get", "rank"], // when two names collide, the bigger barangay keeps its
  },
  paint: {
    "text-color": NAVY,
    "text-halo-color": "rgba(255, 255, 255, 0.92)",
    "text-halo-width": 1.6,
    "text-opacity": ["interpolate", ["linear"], ["zoom"], 14.5, 1, 16.5, 0],
  },
};

export const mask: FillLayerSpecification = {
  id: MASK_ID,
  type: "fill",
  source: MASK_SOURCE_ID,
  paint: {
    "fill-color": "#1b2848",
    "fill-opacity": ["interpolate", ["linear"], ["zoom"], 11, 0.5, 16, 0.38],
  },
};

// A soft shadow along the edge, half of it over the dimmed side: the city looks raised off the map.
export const glow: LineLayerSpecification = {
  id: GLOW_ID,
  type: "line",
  source: CITY_ID,
  layout: { "line-join": "round" },
  paint: {
    "line-color": "#1b2848",
    "line-width": ["interpolate", ["linear"], ["zoom"], 11, 10, 16, 30],
    "line-blur": ["interpolate", ["linear"], ["zoom"], 11, 8, 16, 22],
    "line-opacity": 0.35,
  },
};

export const cityCasing: LineLayerSpecification = {
  id: CITY_CASING_ID,
  type: "line",
  source: CITY_ID,
  layout: { "line-join": "round" },
  paint: {
    "line-color": "#ffffff",
    "line-width": ["interpolate", ["linear"], ["zoom"], 11, 5, 16, 9],
    "line-opacity": 0.95,
  },
};

export const cityLine: LineLayerSpecification = {
  id: CITY_LINE_ID,
  type: "line",
  source: CITY_ID,
  layout: { "line-join": "round" },
  paint: {
    "line-color": "#1b2848",
    "line-width": ["interpolate", ["linear"], ["zoom"], 11, 2.4, 16, 4.2],
  },
};

type Pos = [number, number];
const at = (p: readonly number[]) => `${p[0]},${p[1]}`;
const shoelace = (ring: readonly Pos[]) =>
  ring.slice(0, -1).reduce((sum, p, i) => sum + p[0] * ring[i + 1][1] - ring[i + 1][0] * p[1], 0) / 2;

// The city's edge, from the barangays: a side that two barangays share is inside the city, one that only a single
// barangay has is on its edge. Chained end to end, the edge sides give the loops. `outer` is the city's edge,
// `enclaves` are pieces inside it that belong to no barangay (the Manila South Cemetery, which is the City of Manila's);
// told apart by which way round they run.
// Points must match exactly between neighbours, which they do: the outlines come from one source, rounded the same way.
export function cityLoops(list: readonly Barangay[]): { outer: Pos[][]; enclaves: Pos[][] } {
  const sides = new Map<string, { a: Pos; b: Pos; count: number }>();
  for (const barangay of list) {
    for (const ring of barangay.rings) {
      for (let i = 0; i < ring.length - 1; i++) {
        const [a, b] = [ring[i] as Pos, ring[i + 1] as Pos];
        const key = at(a) < at(b) ? `${at(a)}|${at(b)}` : `${at(b)}|${at(a)}`;
        const side = sides.get(key);
        if (side) side.count++;
        else sides.set(key, { a, b, count: 1 });
      }
    }
  }
  const edge = [...sides.values()].filter((s) => s.count === 1);
  const touching = new Map<string, number[]>(); // a point -> the edge sides that meet there
  edge.forEach((s, i) => {
    for (const p of [s.a, s.b]) touching.set(at(p), [...(touching.get(at(p)) ?? []), i]);
  });
  const used = new Set<number>();
  const loops: Pos[][] = [];
  for (let start = 0; start < edge.length; start++) {
    if (used.has(start)) continue;
    used.add(start);
    const loop: Pos[] = [edge[start].a];
    let here = edge[start].b;
    while (at(here) !== at(loop[0])) {
      loop.push(here);
      const next = (touching.get(at(here)) ?? []).find((i) => !used.has(i));
      if (next === undefined) break; // a gap in the outlines: keep what there is
      used.add(next);
      const side = edge[next];
      here = at(side.a) === at(here) ? side.b : side.a;
    }
    loop.push(loop[0]);
    loops.push(loop);
  }
  const biggest = loops.reduce((best, l) => (Math.abs(shoelace(l)) > Math.abs(shoelace(best)) ? l : best), loops[0]);
  const sign = Math.sign(shoelace(biggest));
  return {
    outer: loops.filter((l) => Math.sign(shoelace(l)) === sign),
    enclaves: loops.filter((l) => Math.sign(shoelace(l)) !== sign),
  };
}

export function cityGeoJSON(list: readonly Barangay[]) {
  const { outer, enclaves } = cityLoops(list);
  return {
    type: "Feature" as const,
    geometry: { type: "MultiLineString" as const, coordinates: [...outer, ...enclaves] },
    properties: {},
  };
}

// The whole world with the city cut out, and the enclaves put back.
export function maskGeoJSON(list: readonly Barangay[]) {
  const { outer, enclaves } = cityLoops(list);
  const world: Pos[] = [[-180, -85], [180, -85], [180, 85], [-180, 85], [-180, -85]];
  return {
    type: "Feature" as const,
    geometry: { type: "MultiPolygon" as const, coordinates: [[world, ...outer], ...enclaves.map((l) => [l])] },
    properties: {},
  };
}

// Bottom to top. The traffic and foot-traffic layers are added under the street names too, so without this whichever came
// last would sit on top: the borders were hidden under the traffic, and the other way round.
const FOCUS_STACK = [MASK_ID, GLOW_ID, CASING_ID, LINE_ID, SELECTED_FILL_ID, SELECTED_LINE_ID, CITY_CASING_ID, CITY_LINE_ID];

// Puts the focus and barangay layers back in order, over the traffic and under the basemap's street names. Safe to call
// whenever a layer was added; layers that are not on the map are skipped.
export function restackFocus(map: MapboxMap): void {
  const ours = new Set([...FOCUS_STACK, LABEL_ID]);
  const anchor =
    map.getStyle()?.layers?.find((l) => l.type === "symbol" && !ours.has(l.id))?.id ??
    [LABEL_ID, ...PIN_LAYERS].find((id) => map.getLayer(id));
  for (const id of FOCUS_STACK) if (map.getLayer(id)) map.moveLayer(id, anchor);
}

// Draws the focus, replacing any already drawn. false when the map could not take it (its style not loaded yet).
export function addFocus(map: MapboxMap, list: readonly Barangay[]): boolean {
  try {
    removeFocus(map);
    map.addSource(MASK_SOURCE_ID, { type: "geojson", data: maskGeoJSON(list) });
    map.addSource(CITY_ID, { type: "geojson", data: cityGeoJSON(list) });
    const below = firstLabelLayerId(map);
    for (const layer of [mask, glow, cityCasing, cityLine]) map.addLayer(layer, below);
    restackFocus(map);
    return true;
  } catch (e) {
    console.warn("barangays: the map could not draw Makati's edge:", e);
    return false;
  }
}

export function removeFocus(map: MapboxMap): void {
  for (const id of [CITY_LINE_ID, CITY_CASING_ID, GLOW_ID, MASK_ID]) if (map.getLayer(id)) map.removeLayer(id);
  for (const id of [CITY_ID, MASK_SOURCE_ID]) if (map.getSource(id)) map.removeSource(id);
}

function firstLabelLayerId(map: MapboxMap): string | undefined {
  return map.getStyle()?.layers?.find((l) => l.type === "symbol" && l.id !== LABEL_ID)?.id;
}

// Draws the barangays, replacing any already drawn. false when the map could not take them (its style not loaded yet):
// the dashboard goes on without them rather than fail.
export function addBarangays(map: MapboxMap, list: readonly Barangay[], selectedId: string | null): boolean {
  try {
    removeBarangays(map);
    map.addSource(BARANGAYS_ID, { type: "geojson", data: polygonsGeoJSON(list) });
    map.addSource(BARANGAY_LABELS_ID, { type: "geojson", data: labelsGeoJSON(list) });
    const below = firstLabelLayerId(map);
    map.addLayer(casing, below);
    map.addLayer(outline, below);
    map.addLayer(selectedFill, below);
    map.addLayer(selectedLine, below);
    map.addLayer(names, PIN_LAYERS.find((id) => map.getLayer(id)));
    restackFocus(map);
    selectBarangay(map, selectedId);
    return true;
  } catch (e) {
    console.warn("barangays: the map could not draw them:", e);
    return false;
  }
}

// Tints and outlines one barangay (null: none).
export function selectBarangay(map: MapboxMap, id: string | null): void {
  for (const layer of [SELECTED_FILL_ID, SELECTED_LINE_ID]) {
    if (map.getLayer(layer)) map.setFilter(layer, matches(id ?? NONE));
  }
}

export function removeBarangays(map: MapboxMap): void {
  for (const id of [LABEL_ID, SELECTED_LINE_ID, SELECTED_FILL_ID, LINE_ID, CASING_ID]) if (map.getLayer(id)) map.removeLayer(id);
  for (const id of [BARANGAY_LABELS_ID, BARANGAYS_ID]) if (map.getSource(id)) map.removeSource(id);
}
