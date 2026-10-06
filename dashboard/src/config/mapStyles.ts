// Map (light, like the reference screenshots) and Satellite. Switched by map/MapStyleToggle.tsx.
export const MAP_STYLES = {
  map: "mapbox://styles/mapbox/light-v11",
  satellite: "mapbox://styles/mapbox/satellite-streets-v12",
} as const;

export type MapStyleKey = keyof typeof MAP_STYLES;
export const DEFAULT_MAP_STYLE: MapStyleKey = "map";
