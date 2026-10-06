// mapbox-gl map, opens pinned on Makati, draws the congestion layer and the report pins.
import { useEffect, useImperativeHandle, useRef, useState, type Ref } from "react";
import mapboxgl from "mapbox-gl";
import "mapbox-gl/dist/mapbox-gl.css";
import { ENV } from "../config/env";
import { MAKATI, lockBounds } from "../config/makati";
import { MAP_STYLES, DEFAULT_MAP_STYLE } from "../config/mapStyles";
import { addCongestion, removeCongestion } from "../layers/congestion";
import { bindReportPins, setReportPins } from "../layers/reports";
import type { Report } from "../types/api";

// Camera commands for the panels. `coveredRight`: px of map hidden under a panel on the right,
// so the pin lands in the middle of what is still visible.
export type MapHandle = { show: (lng: number, lat: number, coveredRight?: number) => void };

type Props = {
  congestionOn: boolean;
  stamp: number;
  reports: Report[] | null;
  selectedId: string | null;
  onSelect: (id: string) => void;
  ref?: Ref<MapHandle>;
};

export default function MapCanvas({ congestionOn, stamp, reports, selectedId, onSelect, ref }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<mapboxgl.Map | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    // Built once and kept for the life of the page. StrictMode mounts twice,
    // and removing a mapbox-gl map mid-init loses the WebGL context, which
    // leaves a blank canvas behind.
    if (map.current || !container.current || !ENV.mapboxToken) return;
    mapboxgl.accessToken = ENV.mapboxToken;
    const el = container.current;
    const bounds = lockBounds(el.clientWidth, el.clientHeight);
    map.current = new mapboxgl.Map({
      container: el,
      style: MAP_STYLES[DEFAULT_MAP_STYLE],
      bounds, // opens framed on the whole city
      maxBounds: bounds, // and can't leave it (see lockBounds)
      projection: "mercator", // the style's globe projection makes maxBounds clamp only the centre
      minZoom: MAKATI.minZoom,
      maxZoom: MAKATI.maxZoom,
      attributionControl: false,
    });
    // Default (responsive) attribution: full text on desktop, so "Traffic © TomTom"
    // stays readable; Mapbox collapses it below 640px.
    map.current.addControl(new mapboxgl.AttributionControl(), "bottom-right");
    // The lock follows the viewport's shape: redo it, and re-frame the city, when that changes.
    map.current.on("resize", () => {
      const b = lockBounds(el.clientWidth, el.clientHeight);
      map.current?.setMaxBounds(b).fitBounds(b, { duration: 0 });
    });
    map.current.once("load", () => setLoaded(true));
  }, []);

  // Both layers are gated on "load" having fired rather than on isStyleLoaded(): that is false
  // whenever any tiles are loading (mid-pan, mid-flyTo), and "load" fires only once, so a
  // once("load") fallback would silently drop toggles, refreshes and poll updates.
  useEffect(() => {
    const m = map.current;
    if (!loaded || !m) return;
    if (congestionOn && ENV.tomtomKey) addCongestion(m, ENV.tomtomKey, stamp);
    else removeCongestion(m);
  }, [loaded, congestionOn, stamp]);

  // Pins follow every poll and selection.
  useEffect(() => {
    if (loaded && map.current) setReportPins(map.current, reports ?? [], selectedId);
  }, [loaded, reports, selectedId]);

  useEffect(() => (map.current ? bindReportPins(map.current, onSelect) : undefined), [onSelect]);

  useImperativeHandle(
    ref,
    () => ({
      // Flies to a pin; maxBounds keeps the camera inside the Makati lock.
      show(lng, lat, coveredRight = 0) {
        const m = map.current;
        m?.flyTo({ center: [lng, lat], zoom: Math.max(m.getZoom(), 16), offset: [-coveredRight / 2, 0] });
      },
    }),
    [],
  );

  if (!ENV.mapboxToken) {
    return (
      <div className="map-missing">
        <p>No Mapbox token.</p>
        <p className="muted">
          Copy <code>.env.example</code> to <code>.env.local</code> and set{" "}
          <code>VITE_MAPBOX_TOKEN</code>, then restart <code>npm run dev</code>.
        </p>
      </div>
    );
  }

  return (
    <div className="map-wrap">
      <div ref={container} className="map-canvas" />
      <button
        className="map-reset"
        onClick={() => map.current?.fitBounds(map.current.getMaxBounds()!)} // the lock is the home view
      >
        Reset to Makati
      </button>
    </div>
  );
}
