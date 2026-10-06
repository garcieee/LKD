// TomTom traffic flow, drawn as raster tiles on top of the basemap.
// Flow styles: absolute | relative | relative-delay | reduced-sensitivity.
// "relative" = current speed against free-flow speed, which is congestion.
import type { Map as MapboxMap } from "mapbox-gl";

export const CONGESTION_ID = "congestion";
export const CONGESTION_STYLE = "relative";
export const REFRESH_MS = 120_000;

// `stamp` busts the tile cache so a refresh actually refetches.
export function congestionTileUrl(key: string, stamp = 0): string {
  if (!key) throw new Error("Missing TomTom key: set VITE_TOMTOM_API_KEY in .env.local");
  const base = `https://api.tomtom.com/traffic/map/4/tile/flow/${CONGESTION_STYLE}/{z}/{x}/{y}.png`;
  return `${base}?key=${encodeURIComponent(key)}${stamp ? `&t=${stamp}` : ""}`;
}

// Keep traffic under the basemap's street labels so they stay readable.
function firstLabelLayerId(map: MapboxMap): string | undefined {
  return map.getStyle()?.layers?.find((l) => l.type === "symbol")?.id;
}

export function addCongestion(map: MapboxMap, key: string, stamp = 0): void {
  removeCongestion(map);
  map.addSource(CONGESTION_ID, {
    type: "raster",
    tiles: [congestionTileUrl(key, stamp)],
    tileSize: 256,
    attribution: "Traffic © TomTom",
  });
  map.addLayer(
    {
      id: CONGESTION_ID,
      type: "raster",
      source: CONGESTION_ID,
      paint: { "raster-opacity": 0.85 },
    },
    firstLabelLayerId(map),
  );
}

export function removeCongestion(map: MapboxMap): void {
  if (map.getLayer(CONGESTION_ID)) map.removeLayer(CONGESTION_ID);
  if (map.getSource(CONGESTION_ID)) map.removeSource(CONGESTION_ID);
}
