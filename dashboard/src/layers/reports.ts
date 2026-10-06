// Report pins, all statuses: one circle per ticket, coloured by status, drawn over the congestion
// lines (those sit under the basemap labels; these go on top of everything). The selected ticket
// gets a navy ring. Clicking a pin selects its ticket (bindReportPins).
import type {
  CircleLayerSpecification,
  ExpressionSpecification,
  GeoJSONSource,
  Map as MapboxMap,
  MapMouseEvent,
} from "mapbox-gl";
import type { Report, Status } from "../types/api.ts";
import { toGeoJSON } from "../features/queue/tickets.ts";

export const REPORTS_ID = "reports";
const RING_ID = "reports-selected";

// Same values as the status tokens in styles/tokens.css and the mobile pins.
export const STATUS_COLOR: Record<Status, string> = {
  open: "#a63722",
  verified: "#8a6736",
  assigned: "#212e4a",
  fixed: "#41755e",
};

const isSelected: ExpressionSpecification = ["==", ["get", "selected"], true];

const pins: CircleLayerSpecification = {
  id: REPORTS_ID,
  type: "circle",
  source: REPORTS_ID,
  layout: { "circle-sort-key": ["case", isSelected, 1, 0] }, // the selected pin draws on top
  paint: {
    "circle-color": ["match", ["get", "status"], ...Object.entries(STATUS_COLOR).flat(), STATUS_COLOR.open],
    "circle-radius": ["interpolate", ["linear"], ["zoom"], 11, 5, 16, 8],
    "circle-stroke-color": "#ffffff",
    "circle-stroke-width": 2,
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

export function setReportPins(map: MapboxMap, reports: Report[], selectedId: string | null): void {
  const data = toGeoJSON(reports, selectedId);
  const source = map.getSource<GeoJSONSource>(REPORTS_ID);
  if (source) {
    source.setData(data);
    return;
  }
  map.addSource(REPORTS_ID, { type: "geojson", data });
  map.addLayer(ring);
  map.addLayer(pins);
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
  map.on("click", REPORTS_ID, click);
  map.on("mouseenter", REPORTS_ID, enter);
  map.on("mouseleave", REPORTS_ID, leave);
  return () => {
    map.off("click", REPORTS_ID, click);
    map.off("mouseenter", REPORTS_ID, enter);
    map.off("mouseleave", REPORTS_ID, leave);
  };
}
