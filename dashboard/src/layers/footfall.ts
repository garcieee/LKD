// Modeled foot traffic: a heat layer over the transit hubs and district anchors, plus a ring on each district.
// The values are a relative 0-100 index from GET /footfall, an estimate and not a count (see
// server/app/services/footfall.py). Drawn under the TomTom lines when those are on, else under the basemap labels.
import type { CircleLayerSpecification, GeoJSONSource, HeatmapLayerSpecification, Map as MapboxMap } from "mapbox-gl";
import type { Day, Footfall } from "../types/api.ts";
import { CONGESTION_ID } from "./congestion.ts";

export const FOOTFALL_ID = "footfall";
const RINGS_ID = "footfall-districts";
const RINGS_SOURCE = "footfall-districts";

// Cool to warm so it never reads as TomTom's red/green: faint blue, violet, magenta, amber at the peak.
export const FOOTFALL_RAMP = [
  [0, "rgba(141,173,241,0)"],
  [0.15, "rgba(141,173,241,0.5)"],
  [0.45, "rgba(109,92,214,0.62)"],
  [0.7, "rgba(190,60,150,0.75)"],
  [1, "rgba(245,166,35,0.9)"],
] as const;

const DAYS: Day[] = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];
export const DAY_LABEL: Record<Day, string> = {
  mon: "Mon",
  tue: "Tue",
  wed: "Wed",
  thu: "Thu",
  fri: "Fri",
  sat: "Sat",
  sun: "Sun",
};

// The Manila weekday and hour, whatever the browser's time zone (Manila has no daylight saving).
export function manilaNow(now = new Date()): { day: Day; hour: number } {
  const t = new Date(now.getTime() + 8 * 3_600_000); // read UTC fields of the shifted time as Manila's
  return { day: DAYS[(t.getUTCDay() + 6) % 7], hour: t.getUTCHours() };
}

// Heat points: one per hub and anchor, weighted 0-1 by index. Mapbox wants [lng, lat].
export function heatGeoJSON(data: Footfall) {
  return {
    type: "FeatureCollection" as const,
    features: data.points.map((p) => ({
      type: "Feature" as const,
      geometry: { type: "Point" as const, coordinates: [p.lng, p.lat] },
      properties: { id: p.id, kind: p.kind, w: Math.min(1, Math.max(0, p.index / 100)) },
    })),
  };
}

// One point per district; the ring's radius is set per zoom from radius_m, its darkness from the tier.
export function ringsGeoJSON(data: Footfall) {
  return {
    type: "FeatureCollection" as const,
    features: data.districts.map((d) => ({
      type: "Feature" as const,
      geometry: { type: "Point" as const, coordinates: [d.lng, d.lat] },
      properties: { id: d.id, name: d.name, tier: d.tier, radius_m: d.radius_m, w: Math.min(1, d.index / 100) },
    })),
  };
}

const heat: HeatmapLayerSpecification = {
  id: FOOTFALL_ID,
  type: "heatmap",
  source: FOOTFALL_ID,
  paint: {
    "heatmap-weight": ["get", "w"],
    "heatmap-intensity": ["interpolate", ["linear"], ["zoom"], 11, 2.4, 16, 3],
    "heatmap-radius": ["interpolate", ["linear"], ["zoom"], 11, 40, 14, 70, 16, 110, 18, 170],
    "heatmap-opacity": 0.95,
    "heatmap-color": ["interpolate", ["linear"], ["heatmap-density"], ...FOOTFALL_RAMP.flat()],
  },
};

// A thin ring marks where a district is; it is a rough circle (radius_m), not a boundary.
// metres per px at the equator is 156543 / 2^zoom, times cos(lat) ~ 0.968 at Makati.
const ringRadius = (zoom: number, metres: number) => metres / ((156543.03 * 0.968) / 2 ** zoom);
const rings: CircleLayerSpecification = {
  id: RINGS_ID,
  type: "circle",
  source: RINGS_SOURCE,
  paint: {
    "circle-radius": [
      "interpolate",
      ["exponential", 2],
      ["zoom"],
      11,
      ["*", ["get", "radius_m"], ringRadius(11, 1)],
      19,
      ["*", ["get", "radius_m"], ringRadius(19, 1)],
    ],
    "circle-color": "rgba(0,0,0,0)",
    "circle-stroke-color": ["match", ["get", "tier"], 1, "#212e4a", 2, "#4f5f86", "#8a93ab"],
    "circle-stroke-width": ["match", ["get", "tier"], 1, 1.8, 1.1],
    "circle-stroke-opacity": 0.8,
  },
};

function firstLabelLayerId(map: MapboxMap): string | undefined {
  return map.getStyle()?.layers?.find((l) => l.type === "symbol")?.id;
}

// Adds the layers on first call; later calls only swap the data, so moving the hour slider does not flicker.
export function setFootfall(map: MapboxMap, data: Footfall): void {
  const heatSource = map.getSource<GeoJSONSource>(FOOTFALL_ID);
  if (heatSource) {
    heatSource.setData(heatGeoJSON(data));
    map.getSource<GeoJSONSource>(RINGS_SOURCE)?.setData(ringsGeoJSON(data));
    return;
  }
  const before = map.getLayer(CONGESTION_ID) ? CONGESTION_ID : firstLabelLayerId(map);
  map.addSource(FOOTFALL_ID, { type: "geojson", data: heatGeoJSON(data) });
  map.addSource(RINGS_SOURCE, { type: "geojson", data: ringsGeoJSON(data) });
  map.addLayer(heat, before);
  map.addLayer(rings, before);
}

export function removeFootfall(map: MapboxMap): void {
  for (const id of [RINGS_ID, FOOTFALL_ID]) if (map.getLayer(id)) map.removeLayer(id);
  for (const id of [RINGS_SOURCE, FOOTFALL_ID]) if (map.getSource(id)) map.removeSource(id);
}
