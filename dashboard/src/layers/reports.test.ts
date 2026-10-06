import { test } from "node:test";
import assert from "node:assert/strict";
import type { Map as MapboxMap } from "mapbox-gl";
import type { Report } from "../types/api.ts";
import { toGeoJSON } from "../features/queue/tickets.ts";
import { REPORTS_ID, STATUS_COLOR, bindReportPins, setReportPins } from "./reports.ts";

type Handler = (e?: unknown) => void;
type Layer = { id: string; paint: Record<string, unknown[]> };

// Just enough of a mapbox-gl Map to record what the layer code asks of it.
function fakeMap() {
  const log: string[] = [];
  const layers: Record<string, Layer> = {};
  const handlers = new Map<string, Handler>(); // "click reports" -> handler
  const canvas = { style: { cursor: "" } };
  let data: unknown;
  const source = {
    setData(d: unknown) {
      log.push("setData");
      data = d;
    },
  };
  const map = {
    getSource: () => (data === undefined ? undefined : source),
    addSource(id: string, spec: { data: unknown }) {
      log.push(`addSource ${id}`);
      data = spec.data;
    },
    addLayer(layer: Layer) {
      log.push(`addLayer ${layer.id}`);
      layers[layer.id] = layer;
    },
    on: (type: string, id: string, fn: Handler) => handlers.set(`${type} ${id}`, fn),
    // Only the very function that was bound comes off, as in mapbox-gl.
    off: (type: string, id: string, fn: Handler) => handlers.get(`${type} ${id}`) === fn && handlers.delete(`${type} ${id}`),
    getCanvas: () => canvas,
  };
  return { map: map as unknown as MapboxMap, log, layers, handlers, canvas, data: () => data };
}

// mapbox's ["match", input, label, value, ..., fallback], evaluated for one label.
function match([, , ...arms]: unknown[], label: string) {
  for (let i = 0; i + 1 < arms.length; i += 2) if (arms[i] === label) return arms[i + 1];
  return arms.at(-1);
}

const report = (id: string, status: Report["status"]) =>
  ({ id, status, lat: 14.5547, lng: 121.0244 }) as Report;

test("setReportPins: source, then the ring under the pins, once; later polls only swap the data", () => {
  const m = fakeMap();
  setReportPins(m.map, [report("a", "open")], null);
  const next = [report("a", "open"), report("b", "fixed")];
  setReportPins(m.map, next, "b");
  assert.deepEqual(m.log, ["addSource reports", "addLayer reports-selected", "addLayer reports", "setData"]);
  assert.deepEqual(m.data(), toGeoJSON(next, "b"));
});

test("pins take their status colour, and a status the dashboard doesn't know reads as open", () => {
  const m = fakeMap();
  setReportPins(m.map, [], null);
  const color = m.layers[REPORTS_ID].paint["circle-color"];
  for (const [status, hex] of Object.entries(STATUS_COLOR)) assert.equal(match(color, status), hex);
  assert.equal(match(color, "triaged"), STATUS_COLOR.open);
});

test("bindReportPins: a click selects the pin's ticket, hover points, unbinding removes every handler", () => {
  const m = fakeMap();
  const picked: string[] = [];
  const unbind = bindReportPins(m.map, (id) => picked.push(id));
  const on = (type: string) => m.handlers.get(`${type} ${REPORTS_ID}`)!;
  on("click")({ features: [{ properties: { id: "a" } }] });
  on("click")({ features: [] });
  on("click")({ features: [{ properties: { id: 7 } }] });
  assert.deepEqual(picked, ["a"]);
  on("mouseenter")();
  assert.equal(m.canvas.style.cursor, "pointer");
  on("mouseleave")();
  assert.equal(m.canvas.style.cursor, "");
  unbind();
  assert.equal(m.handlers.size, 0);
});
