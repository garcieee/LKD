// TomTom traffic flow, drawn as vector tiles: one thin line per carriageway, coloured by how slow it is.
// Flow styles: absolute | relative | relative-delay | reduced-sensitivity.
// "relative" = current speed against free-flow speed, which is congestion.
//
// Why vector, not TomTom's PNG tiles: the PNGs paint every carriageway as a fat band (thickness 10,
// one value for every zoom: thin enough for zoom 18 means hairlines at city scale). Where the
// elevated Skyway runs over Osmeña Highway, both directions of both roads land within a few pixels
// and the bands stack into one blob. As vectors each carriageway is its own feature, so width,
// colour, side and paint order are ours. Mobile draws the same layer
// (mobile/lib/layers/congestion_layer.dart): keep the two in step.
import type { ExpressionSpecification, LineLayerSpecification, Map as MapboxMap } from "mapbox-gl";
import { MAKATI } from "../config/makati.ts"; // .ts so `node --test` can resolve it

export const CONGESTION_ID = "congestion";
export const CONGESTION_STYLE = "relative";
export const REFRESH_MS = 120_000;

// Vector layer name inside TomTom's tiles; each feature is a road segment with road_type,
// traffic_level and traffic_road_coverage ("full" | "one_side").
const SOURCE_LAYER = "Traffic flow";
// traffic_level snapped to tenths: TomTom merges neighbouring segments on the same step, so over the city
// tiles are 20-35% smaller and have a third to 70% fewer segments (fewer joints). Off by 0.05 at most.
const LEVEL_STEP = 0.1;

// traffic_level = current speed / free-flow speed: 1 is free flow, 0 a standstill. Ascending, as mapbox
// needs. Legend.tsx draws its gradient from this same list.
export const CONGESTION_RAMP = [
  [0, "#e54b4b"], // standstill
  [0.33, "#f28c28"], // heavy
  [0.67, "#f7d154"], // slow
  [1, "#2ecc71"], // free flow
] as const;

// Line width in px by zoom, for a main road. Thin on purpose: from zoom 16 the Skyway's carriageways
// and Osmeña Highway's are only a few px apart, and wider lines touch again.
const WIDTH = [
  [11, 2.2],
  [13, 3],
  [15, 3.4],
  [17, 3.4],
  [19, 6],
] as const;
const roadScale: ExpressionSpecification = [
  "match",
  ["get", "road_type"],
  ["Motorway", "International road", "Major road", "Secondary road"],
  1,
  ["Connecting road", "Major local road"],
  0.8,
  0.6, // Local road, Minor local road
];

// mapbox only allows "zoom" as the input of a top-level interpolate, so the per-feature part goes in each stop.
const byZoom = (px: (w: number) => ExpressionSpecification): ExpressionSpecification => [
  "interpolate",
  ["exponential", 1.5],
  ["zoom"],
  ...WIDTH.flatMap(([z, w]) => [z, px(w)]),
];

// `stamp` busts the tile cache so a refresh actually refetches.
export function congestionTileUrl(key: string, stamp = 0): string {
  if (!key) throw new Error("Missing TomTom key: set VITE_TOMTOM_API_KEY in .env.local");
  const base = `https://api.tomtom.com/traffic/map/4/tile/flow/${CONGESTION_STYLE}/{z}/{x}/{y}.pbf`;
  return `${base}?key=${encodeURIComponent(key)}&trafficLevelStep=${LEVEL_STEP}${stamp ? `&t=${stamp}` : ""}`;
}

export function congestionLayer(): LineLayerSpecification {
  return {
    id: CONGESTION_ID,
    type: "line",
    source: CONGESTION_ID,
    "source-layer": SOURCE_LAYER,
    layout: {
      "line-cap": "round",
      "line-join": "round",
      "line-sort-key": ["-", 1, ["get", "traffic_level"]], // worse congestion draws last, on top
    },
    paint: {
      "line-color": ["interpolate", ["linear"], ["get", "traffic_level"], ...CONGESTION_RAMP.flat()],
      "line-width": byZoom((w) => ["*", roadScale, w]),
      // "one_side" is one direction of a two-way road. Its geometry runs the way traffic does, so
      // shifting it to the right of that (the Philippines drives on the right) sets the two
      // directions side by side instead of on top of each other. "full" lines stay on the centre.
      "line-offset": byZoom((w) => [
        "case",
        ["==", ["get", "traffic_road_coverage"], "one_side"],
        ["*", roadScale, w / 2],
        0,
      ]),
    },
  };
}

// Keep traffic under the basemap's street labels so they stay readable.
function firstLabelLayerId(map: MapboxMap): string | undefined {
  return map.getStyle()?.layers?.find((l) => l.type === "symbol")?.id;
}

export function addCongestion(map: MapboxMap, key: string, stamp = 0): void {
  removeCongestion(map);
  map.addSource(CONGESTION_ID, {
    type: "vector",
    tiles: [congestionTileUrl(key, stamp)],
    bounds: [...MAKATI.bounds[0], ...MAKATI.bounds[1]], // only request tiles over the city (API quota)
    attribution: "Traffic © TomTom",
  });
  map.addLayer(congestionLayer(), firstLabelLayerId(map));
}

export function removeCongestion(map: MapboxMap): void {
  if (map.getLayer(CONGESTION_ID)) map.removeLayer(CONGESTION_ID);
  if (map.getSource(CONGESTION_ID)) map.removeSource(CONGESTION_ID);
}
