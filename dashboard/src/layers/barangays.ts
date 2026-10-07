// Makati's barangays on the map: a dashed outline round each, a tint and heavier outline on the selected one, and
// each one's name, drawn while the map is zoomed out and faded away as the streets take over (zoom 14.5 to 16.5).
// The outlines go under the basemap's street names; the barangay names go over them and under the report pins.
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

export const outline: LineLayerSpecification = {
  id: LINE_ID,
  type: "line",
  source: BARANGAYS_ID,
  layout: { "line-join": "round" },
  paint: {
    "line-color": "#4f5f86",
    "line-width": ["interpolate", ["linear"], ["zoom"], 11, 0.8, 15, 1.8],
    "line-opacity": 0.75,
    "line-dasharray": [3, 2],
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
  paint: { "line-color": NAVY, "line-width": 3 },
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

function firstLabelLayerId(map: MapboxMap): string | undefined {
  return map.getStyle()?.layers?.find((l) => l.type === "symbol")?.id;
}

// Draws the barangays, replacing any already drawn. false when the map could not take them (its style not loaded yet):
// the dashboard goes on without them rather than fail.
export function addBarangays(map: MapboxMap, list: readonly Barangay[], selectedId: string | null): boolean {
  try {
    removeBarangays(map);
    map.addSource(BARANGAYS_ID, { type: "geojson", data: polygonsGeoJSON(list) });
    map.addSource(BARANGAY_LABELS_ID, { type: "geojson", data: labelsGeoJSON(list) });
    const below = firstLabelLayerId(map);
    map.addLayer(outline, below);
    map.addLayer(selectedFill, below);
    map.addLayer(selectedLine, below);
    map.addLayer(names, PIN_LAYERS.find((id) => map.getLayer(id)));
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
  for (const id of [LABEL_ID, SELECTED_LINE_ID, SELECTED_FILL_ID, LINE_ID]) if (map.getLayer(id)) map.removeLayer(id);
  for (const id of [BARANGAY_LABELS_ID, BARANGAYS_ID]) if (map.getSource(id)) map.removeSource(id);
}
