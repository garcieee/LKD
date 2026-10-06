import { test } from "node:test";
import assert from "node:assert/strict";
import type { SeriesPoint } from "../../types/api.ts";
import { WINDOWS, geometry, label, nextPeak, niceMax, slice, ticks } from "./series.ts";

// 6 h of history then 6 h of forecast, hourly from Tue 15:00 Manila (07:00 UTC).
const pts: SeriesPoint[] = Array.from({ length: 12 }, (_, i) => ({
  t: new Date(Date.UTC(2026, 9, 6, 7 + i)).toISOString(),
  index: i < 6 ? 10 + i : 30 - i,
  kind: i < 6 ? "history" : "forecast",
  ...(i < 6 ? {} : { lower: 20 - i, upper: 40 - i }),
}));

test("the window keeps hours either side of now, and says where now landed", () => {
  const day = WINDOWS[0];
  const long = Array.from({ length: 100 }, (_, i) => ({ t: "2026-10-06T00:00:00+08:00", index: i, kind: i < 60 ? "history" : "forecast" }) as SeriesPoint);
  const s = slice(long, day);
  assert.equal(s.pts.length, 12 + 1 + 24, "12 h back, now, 24 h ahead");
  assert.equal(s.pts[s.nowIdx].index, 59);
  assert.equal(s.pts[s.nowIdx + 1].kind, "forecast");
});

test("a window longer than the data just shows all of it", () => {
  const s = slice(pts, WINDOWS[2]);
  assert.equal(s.pts.length, 12);
  assert.equal(s.nowIdx, 5);
});

test("no history means an empty chart, not a crash", () => {
  assert.deepEqual(slice(pts.filter((p) => p.kind === "forecast"), WINDOWS[0]), { pts: [], nowIdx: 0 });
});

test("the y axis snaps to a clean top above the band, per zone", () => {
  assert.equal(niceMax([{ t: "", index: 4, kind: "history" }]), 5);
  assert.equal(niceMax(pts), 50);
  assert.equal(niceMax([{ t: "", index: 99, kind: "history" }]), 100);
});

test("the forecast line starts where the history ends, and the band starts as a point", () => {
  const g = geometry(pts, 5, 50, { w: 100, h: 50, l: 0, r: 0, t: 0, b: 0 });
  assert.ok(g.history.startsWith("M0.0"));
  const nowXY = g.history.split(" L").at(-1)!.replace("M", "");
  assert.ok(g.forecast.startsWith(`M${nowXY}`), "the two lines meet");
  assert.ok(g.band.startsWith(`M${nowXY}`) && g.band.endsWith("Z"));
});

test("a series with no forecast has no forecast path", () => {
  const g = geometry(pts.slice(0, 6), 5, 50, { w: 100, h: 50, l: 0, r: 0, t: 0, b: 0 });
  assert.equal(g.forecast, "");
  assert.equal(g.band, "");
});

test("labels read in Manila time", () => {
  assert.equal(label("2026-10-06T20:00:00+08:00"), "Tue 20:00");
  assert.equal(label("2026-10-06T16:00:00Z"), "Wed 00:00");
});

test("short windows tick every six hours, long ones at midnight", () => {
  assert.deepEqual(ticks(pts).map((t) => t.text), ["18:00", "Wed"], "15:00 to 02:00 holds 18:00 and midnight");
  const days = Array.from({ length: 72 }, (_, i) => ({ t: new Date(Date.UTC(2026, 9, 5, 16 + i)).toISOString(), index: 1, kind: "history" }) as SeriesPoint);
  assert.deepEqual(ticks(days).map((t) => t.text), ["Tue", "Wed", "Thu"]);
});

test("the next peak is the busiest forecast hour", () => {
  const p = nextPeak(pts, 5)!;
  assert.equal(p.kind, "forecast");
  assert.equal(p.index, Math.max(...pts.filter((q) => q.kind === "forecast").map((q) => q.index)));
  assert.equal(nextPeak(pts.slice(0, 6), 5), null);
});
