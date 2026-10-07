// Report pins, all statuses: one teardrop per ticket, coloured by status, drawn over the congestion
// lines (those sit under the basemap labels; these go on top of everything). The selected ticket
// gets a navy ring. Clicking a pin selects its ticket (bindReportPins).
//
// An SOS that is still open is not a status-coloured pin: it is a red pin that blinks, with a ripple spreading
// under it (animateSos), drawn above every other pin so nothing hides it.
import type {
  CircleLayerSpecification,
  ExpressionSpecification,
  GeoJSONSource,
  Map as MapboxMap,
  MapMouseEvent,
  SymbolLayerSpecification,
} from "mapbox-gl";
import type { Report, Status } from "../types/api.ts";
import { toGeoJSON } from "../features/queue/tickets.ts";
import { ticketPinImage } from "./ticketPin.ts";

export const REPORTS_ID = "reports";
const RING_ID = "reports-selected";
export const SOS_ID = "reports-sos"; // the blinking red pin
const SOS_HALO_ID = "reports-sos-halo"; // the ripple under it
export const SOS_COLOR = "#d6001c"; // --sos in styles/tokens.css
const PIN_LAYERS = [REPORTS_ID, SOS_ID];

// Same values as the status tokens in styles/tokens.css and the mobile pins.
export const STATUS_COLOR: Record<Status, string> = {
  open: "#a63722",
  verified: "#8a6736",
  assigned: "#212e4a",
  fixed: "#41755e",
  rejected: "#64605b", // never drawn: App keeps rejected tickets off the map
};

const isSelected: ExpressionSpecification = ["==", ["get", "selected"], true];
const isAlert: ExpressionSpecification = ["==", ["get", "alert"], true];

const pins: SymbolLayerSpecification = {
  id: REPORTS_ID,
  type: "symbol",
  source: REPORTS_ID,
  filter: ["!=", ["get", "alert"], true], // an open SOS has its own layers
  layout: {
    "symbol-sort-key": ["case", isSelected, 1, 0],
    "icon-image": ["match", ["get", "status"], ...Object.keys(STATUS_COLOR).flatMap((s) => [s, `ticket-pin-${s}`]), "ticket-pin-open"],
    "icon-anchor": "bottom",
    "icon-size": ["interpolate", ["linear"], ["zoom"], 11, 0.65, 16, 0.9, 19, 1.1],
    "icon-allow-overlap": true,
    "icon-ignore-placement": true,
    "icon-pitch-alignment": "viewport",
  },
};

// White gap, then a navy ring, under the selected pin.
const ring: CircleLayerSpecification = {
  id: RING_ID,
  type: "circle",
  source: REPORTS_ID,
  filter: isSelected,
  paint: {
    "circle-color": "#ffffff",
    "circle-radius": ["interpolate", ["linear"], ["zoom"], 11, 10, 16, 13],
    "circle-stroke-color": STATUS_COLOR.assigned, // navy
    "circle-stroke-width": 2.5,
  },
};

// The ripple under an open SOS, and the red pin itself. animateSos moves the radius and opacities.
const sosHalo: CircleLayerSpecification = {
  id: SOS_HALO_ID,
  type: "circle",
  source: REPORTS_ID,
  filter: isAlert,
  paint: { "circle-color": SOS_COLOR, "circle-radius": 18, "circle-opacity": 0.4, "circle-pitch-alignment": "map" },
};

const sosPin: SymbolLayerSpecification = {
  id: SOS_ID,
  type: "symbol",
  source: REPORTS_ID,
  filter: isAlert,
  layout: {
    "icon-image": "ticket-pin-sos",
    "icon-anchor": "bottom",
    "icon-size": ["interpolate", ["linear"], ["zoom"], 11, 0.8, 16, 1.05, 19, 1.25],
    "icon-allow-overlap": true,
    "icon-ignore-placement": true,
    "icon-pitch-alignment": "viewport",
  },
};

// Whether any open SOS is drawn: with none, animateSos has nothing to move.
let hasAlert = false;

export function setReportPins(map: MapboxMap, reports: Report[], selectedId: string | null): void {
  for (const [status, color] of Object.entries({ ...STATUS_COLOR, sos: SOS_COLOR })) {
    const id = `ticket-pin-${status}`;
    if (!map.hasImage(id)) map.addImage(id, ticketPinImage(color), { pixelRatio: 3 });
  }
  const data = toGeoJSON(reports, selectedId);
  hasAlert = data.features.some((f) => f.properties.alert);
  const source = map.getSource<GeoJSONSource>(REPORTS_ID);
  if (source) {
    source.setData(data);
    return;
  }
  map.addSource(REPORTS_ID, { type: "geojson", data });
  map.addLayer(sosHalo);
  map.addLayer(ring);
  map.addLayer(pins);
  map.addLayer(sosPin);
}

export const BLINK_MS = 1000; // one full on-off of the pin
export const RIPPLE_MS = 1400; // one ripple, from the pin out to its widest

// How the SOS looks `ms` into the animation: the ripple spreads and fades, the pin fades down and back up.
export function sosFrame(ms: number) {
  const ripple = (ms % RIPPLE_MS) / RIPPLE_MS; // 0 at the pin .. 1 at the widest
  const blink = 0.5 + 0.5 * Math.cos((2 * Math.PI * ms) / BLINK_MS); // 1 on, 0 off
  return { haloRadius: 10 + 30 * ripple, haloOpacity: 0.5 * (1 - ripple), pinOpacity: 0.3 + 0.7 * blink };
}

// For people who ask for less motion: the same red pin and a still ripple, no blinking.
export const STILL_FRAME = { haloRadius: 24, haloOpacity: 0.3, pinOpacity: 1 };

export function paintSos(map: MapboxMap, frame: ReturnType<typeof sosFrame>): void {
  if (map.getLayer(SOS_HALO_ID)) {
    map.setPaintProperty(SOS_HALO_ID, "circle-radius", frame.haloRadius);
    map.setPaintProperty(SOS_HALO_ID, "circle-opacity", frame.haloOpacity);
  }
  if (map.getLayer(SOS_ID)) {
    map.setPaintProperty(SOS_ID, "icon-opacity", frame.pinOpacity);
  }
}

// Runs while the map lives: ~30 frames a second, and only when an open SOS is drawn. Returns the stop.
export function animateSos(map: MapboxMap): () => void {
  const still = typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
  let raf = 0;
  let last = -Infinity;
  const tick = (ms: number) => {
    // Still: repaint once a second, only so a freshly added layer gets its frame.
    if (hasAlert && ms - last >= (still ? 1000 : 33)) {
      last = ms;
      paintSos(map, still ? STILL_FRAME : sosFrame(ms));
    }
    raf = requestAnimationFrame(tick);
  };
  raf = requestAnimationFrame(tick);
  return () => cancelAnimationFrame(raf);
}

// Pointer cursor over pins, and a click selects the pin's ticket. Returns the unbind.
export function bindReportPins(map: MapboxMap, onSelect: (id: string) => void): () => void {
  const click = (e: MapMouseEvent) => {
    // Cast: mapbox-gl types features through @types/geojson, which this project doesn't install.
    const feature = e.features?.[0] as { properties?: { id?: unknown } } | undefined;
    const id = feature?.properties?.id;
    if (typeof id === "string") onSelect(id);
  };
  const enter = () => {
    map.getCanvas().style.cursor = "pointer";
  };
  const leave = () => {
    map.getCanvas().style.cursor = "";
  };
  for (const id of PIN_LAYERS) {
    map.on("click", id, click);
    map.on("mouseenter", id, enter);
    map.on("mouseleave", id, leave);
  }
  return () => {
    for (const id of PIN_LAYERS) {
      map.off("click", id, click);
      map.off("mouseenter", id, enter);
      map.off("mouseleave", id, leave);
    }
  };
}
