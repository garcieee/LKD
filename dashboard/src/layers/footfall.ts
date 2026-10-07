// Modeled foot traffic: a heat layer over the transit hubs and district anchors, plus a ring on each district.
// The values are a relative 0-100 index from GET /footfall, an estimate and not a count (see
// server/app/services/footfall.py). Drawn under the TomTom lines when those are on, else under the basemap labels.
import type { CanvasSource, Map as MapboxMap } from "mapbox-gl";
import type { Day, Footfall } from "../types/api.ts";
import { BARANGAYS } from "../data/barangays.ts";
import { inside } from "./clip.ts";
import { cityLoops, restackFocus } from "./barangays.ts";
import { CONGESTION_ID } from "./congestion.ts";

export const FOOTFALL_ID = "footfall";
const city = cityLoops(BARANGAYS);
const loops = [...city.outer, ...city.enclaves];
const inCity = (p: { lng: number; lat: number }) => inside([p.lng, p.lat], loops);

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
    features: data.points.filter(inCity).map((p) => ({
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
    features: data.districts.filter(inCity).map((d) => ({
      type: "Feature" as const,
      geometry: { type: "Point" as const, coordinates: [d.lng, d.lat] },
      properties: { id: d.id, name: d.name, tier: d.tier, radius_m: d.radius_m, w: Math.min(1, d.index / 100) },
    })),
  };
}

// Clip the rendered pixels, not only point centres: soft heat and rings must not bleed over the edge.
const SIZE = 2048;
const positions = city.outer.flat();
const west = Math.min(...positions.map((p) => p[0]));
const east = Math.max(...positions.map((p) => p[0]));
const south = Math.min(...positions.map((p) => p[1]));
const north = Math.max(...positions.map((p) => p[1]));
const mercatorY = (lat: number) => Math.log(Math.tan(Math.PI / 4 + lat * Math.PI / 360));
const top = mercatorY(north);
const height = top - mercatorY(south);
const HEIGHT = Math.round(SIZE * height / ((east - west) * Math.PI / 180));
const pixel = (lng: number, lat: number): [number, number] => [
  (lng - west) / (east - west) * SIZE, (top - mercatorY(lat)) / height * HEIGHT,
];

export function drawFootfall(canvas: HTMLCanvasElement, data: Footfall, zoom: number): void {
  canvas.width = SIZE;
  canvas.height = HEIGHT;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  ctx.save();
  ctx.beginPath();
  for (const loop of loops) {
    loop.forEach(([lng, lat], i) => {
      const [x, y] = pixel(lng, lat);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.closePath();
  }
  ctx.clip("evenodd");
  const scale = SIZE / ((east - west) / 360 * 512 * 2 ** zoom);
  const z = Math.min(18, Math.max(11, zoom));
  const radius = (z <= 14 ? 40 + (z - 11) * 10 : z <= 16 ? 70 + (z - 14) * 20 : 110 + (z - 16) * 30) * scale;
  for (const p of data.points.filter(inCity)) {
    const weight = Math.min(1, Math.max(0, p.index / 100));
    if (!weight) continue;
    const [x, y] = pixel(p.lng, p.lat);
    const gradient = ctx.createRadialGradient(x, y, 0, x, y, radius);
    for (const [stop, color] of [...FOOTFALL_RAMP].reverse()) gradient.addColorStop(1 - stop, color);
    ctx.globalAlpha = weight;
    ctx.fillStyle = gradient;
    ctx.fillRect(x - radius, y - radius, radius * 2, radius * 2);
  }
  ctx.globalAlpha = 0.8;
  for (const d of data.districts.filter(inCity)) {
    const [x, y] = pixel(d.lng, d.lat);
    const metresPerPixel = 40075016.686 * Math.cos(d.lat * Math.PI / 180) * (east - west) / 360 / SIZE;
    ctx.beginPath();
    ctx.arc(x, y, d.radius_m / metresPerPixel, 0, 2 * Math.PI);
    ctx.strokeStyle = d.tier === 1 ? "#212e4a" : d.tier === 2 ? "#4f5f86" : "#8a93ab";
    ctx.lineWidth = (d.tier === 1 ? 1.8 : 1.1) * scale;
    ctx.stroke();
  }
  ctx.restore();
}

type Overlay = { data: Footfall; redraw: () => void };
const overlays = new WeakMap<MapboxMap, Overlay>();

export function setFootfall(map: MapboxMap, data: Footfall): void {
  const existing = overlays.get(map);
  if (existing && map.getSource(FOOTFALL_ID)) {
    existing.data = data;
    existing.redraw();
    return;
  }
  if (existing) map.off("zoomend", existing.redraw);
  const canvas = document.createElement("canvas");
  const overlay: Overlay = { data, redraw: () => {
    drawFootfall(canvas, overlay.data, map.getZoom());
    const source = map.getSource<CanvasSource>(FOOTFALL_ID);
    source?.play();
    map.triggerRepaint();
    map.once("render", () => source?.pause());
  } };
  drawFootfall(canvas, data, map.getZoom());
  map.addSource(FOOTFALL_ID, {
    type: "canvas", canvas, animate: false,
    coordinates: [[west, north], [east, north], [east, south], [west, south]],
  });
  const before = map.getLayer(CONGESTION_ID) ? CONGESTION_ID :
    map.getStyle()?.layers?.find((l) => l.type === "symbol")?.id;
  map.addLayer({ id: FOOTFALL_ID, type: "raster", source: FOOTFALL_ID,
    paint: { "raster-opacity": 0.95, "raster-fade-duration": 0 } }, before);
  overlays.set(map, overlay);
  map.on("zoomend", overlay.redraw);
  restackFocus(map);
}

export function removeFootfall(map: MapboxMap): void {
  const overlay = overlays.get(map);
  if (overlay) map.off("zoomend", overlay.redraw);
  overlays.delete(map);
  if (map.getLayer(FOOTFALL_ID)) map.removeLayer(FOOTFALL_ID);
  if (map.getSource(FOOTFALL_ID)) map.removeSource(FOOTFALL_ID);
}
