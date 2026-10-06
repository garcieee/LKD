// THE PIN. Makati is set here and nowhere else. Every map opens on this view
// and "Reset to Makati" returns to it.
// Order is [lng, lat] (Mapbox order). Values are approximate: tune them once on screen.
export type LngLat = [number, number];

export const MAKATI = {
  center: [121.0244, 14.5547] as LngLat, // Ayala / CBD
  zoom: 13.6,
  minZoom: 11,
  maxZoom: 19,
  bounds: [
    [120.993, 14.527], // south-west
    [121.056, 14.578], // north-east
  ] as [LngLat, LngLat],
};
