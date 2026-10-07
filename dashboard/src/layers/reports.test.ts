import { test } from "node:test";
import assert from "node:assert/strict";
import type { Map as MapboxMap } from "mapbox-gl";
import type { Report } from "../types/api.ts";
import { toGeoJSON } from "../features/queue/tickets.ts";
import { RIPPLE_MS, REPORTS_ID, SOS_ID, STATUS_COLOR, STILL_FRAME, bindReportPins, paintSos, setReportPins, sosFrame } from "./reports.ts";

type Handler = (e?: unknown) => void;
type Layer = { id: string; type: string; paint: Record<string, unknown[]>; layout: Record<string, unknown> };

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
  const paint: string[] = [];
  const images = new Map<string, unknown>();
  const map = {
    hasImage: (id: string) => images.has(id),
    addImage: (id: string, data: unknown) => images.set(id, data),
    getLayer: (id: string) => layers[id],
    setPaintProperty: (id: string, name: string, value: unknown) => paint.push(`${id} ${name} ${value}`),
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
  return { map: map as unknown as MapboxMap, log, layers, handlers, canvas, paint, data: () => data };
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
  assert.deepEqual(m.log, [
    "addSource reports",
    "addLayer reports-sos-halo", // an open SOS: the ripple under everything,
    "addLayer reports-selected",
    "addLayer reports",
    "addLayer reports-sos", // and its red pin over every other pin
    "setData",
  ]);
  assert.deepEqual(m.data(), toGeoJSON(next, "b"));
});

test("pins take their status colour, and a status the dashboard doesn't know reads as open", () => {
  const m = fakeMap();
  setReportPins(m.map, [], null);
  const color = m.layers[REPORTS_ID].layout["icon-image"] as unknown[];
  assert.equal(m.layers[REPORTS_ID].type, "symbol");
  assert.equal(m.layers[REPORTS_ID].layout["icon-anchor"], "bottom");
  for (const status of Object.keys(STATUS_COLOR)) assert.equal(match(color, status), `ticket-pin-${status}`);
  assert.equal(match(color, "triaged"), "ticket-pin-open");
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

const sosReport = (id: string, status: Report["status"] = "open") => ({ ...report(id, status), category: "sos" }) as Report;

test("an open SOS is drawn by its own red layers, and the ordinary pins leave it out", () => {
  const m = fakeMap();
  setReportPins(m.map, [sosReport("s")], null);
  assert.equal(m.layers[SOS_ID].layout["icon-image"], "ticket-pin-sos");
  assert.deepEqual((m.layers[SOS_ID] as unknown as { filter: unknown }).filter, ["==", ["get", "alert"], true]);
  assert.deepEqual((m.layers[REPORTS_ID] as unknown as { filter: unknown }).filter, ["!=", ["get", "alert"], true]);
});

test("sosFrame: the ripple restarts and fades, the pin fades down and back up, all in range", () => {
  assert.equal(sosFrame(0).haloRadius, 10);
  assert.equal(sosFrame(0).haloOpacity, 0.5);
  assert.ok(sosFrame(RIPPLE_MS / 2).haloRadius > sosFrame(0).haloRadius);
  assert.ok(sosFrame(RIPPLE_MS / 2).haloOpacity < sosFrame(0).haloOpacity);
  assert.equal(sosFrame(RIPPLE_MS).haloRadius, 10, "and starts over");
  assert.equal(sosFrame(0).pinOpacity, 1, "on");
  assert.ok(Math.abs(sosFrame(500).pinOpacity - 0.3) < 1e-9, "dimmed half a blink later, never fully off");
  for (let ms = 0; ms < 5000; ms += 37) {
    const f = sosFrame(ms);
    assert.ok(f.pinOpacity >= 0.3 - 1e-9 && f.pinOpacity <= 1 + 1e-9);
    assert.ok(f.haloOpacity >= 0 && f.haloRadius >= 10 && f.haloRadius <= 40);
  }
});

test("paintSos moves the ripple and the pin, and does nothing until the layers exist", () => {
  const m = fakeMap();
  paintSos(m.map, sosFrame(0));
  assert.deepEqual(m.paint, [], "no layers yet");
  setReportPins(m.map, [sosReport("s")], null);
  paintSos(m.map, STILL_FRAME);
  assert.deepEqual(m.paint, [
    "reports-sos-halo circle-radius 24",
    "reports-sos-halo circle-opacity 0.3",
    "reports-sos icon-opacity 1",
  ]);
});

test("bindReportPins: an SOS pin is clickable too", () => {
  const m = fakeMap();
  const picked: string[] = [];
  const unbind = bindReportPins(m.map, (id) => picked.push(id));
  m.handlers.get(`click ${SOS_ID}`)!({ features: [{ properties: { id: "s" } }] });
  assert.deepEqual(picked, ["s"]);
  unbind();
  assert.equal(m.handlers.size, 0);
});
