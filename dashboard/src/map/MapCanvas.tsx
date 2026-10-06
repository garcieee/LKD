// mapbox-gl map, opens pinned on Makati, draws the congestion layer.
import { useEffect, useRef } from "react";
import mapboxgl from "mapbox-gl";
import "mapbox-gl/dist/mapbox-gl.css";
import { ENV } from "../config/env";
import { MAKATI } from "../config/makati";
import { MAP_STYLES, DEFAULT_MAP_STYLE } from "../config/mapStyles";
import { addCongestion, removeCongestion } from "../layers/congestion";

type Props = { congestionOn: boolean; stamp: number };

export default function MapCanvas({ congestionOn, stamp }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<mapboxgl.Map | null>(null);

  useEffect(() => {
    if (!container.current || !ENV.mapboxToken) return;
    mapboxgl.accessToken = ENV.mapboxToken;
    map.current = new mapboxgl.Map({
      container: container.current,
      style: MAP_STYLES[DEFAULT_MAP_STYLE],
      center: MAKATI.center,
      zoom: MAKATI.zoom,
      minZoom: MAKATI.minZoom,
      maxZoom: MAKATI.maxZoom,
      attributionControl: false,
    });
    map.current.addControl(new mapboxgl.AttributionControl({ compact: true }), "bottom-right");
    return () => {
      map.current?.remove();
      map.current = null;
    };
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
        onClick={() => map.current?.flyTo({ center: MAKATI.center, zoom: MAKATI.zoom })}
      >
        Reset to Makati
      </button>
    </div>
  );
}
