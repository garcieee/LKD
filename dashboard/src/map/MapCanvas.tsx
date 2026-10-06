// mapbox-gl map, opens pinned on Makati, draws the congestion layer.
import { useEffect, useRef } from "react";
import mapboxgl from "mapbox-gl";
import "mapbox-gl/dist/mapbox-gl.css";
import { ENV } from "../config/env";
import { MAKATI, lockBounds } from "../config/makati";
import { MAP_STYLES, DEFAULT_MAP_STYLE } from "../config/mapStyles";
import { addCongestion, removeCongestion } from "../layers/congestion";

type Props = { congestionOn: boolean; stamp: number };

export default function MapCanvas({ congestionOn, stamp }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<mapboxgl.Map | null>(null);

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
  }, []);

  useEffect(() => {
    const m = map.current;
    if (!m) return;
    const apply = () => {
      if (congestionOn && ENV.tomtomKey) addCongestion(m, ENV.tomtomKey, stamp);
      else removeCongestion(m);
    };
    if (m.isStyleLoaded()) apply();
    else m.once("load", apply);
  }, [congestionOn, stamp]);

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
