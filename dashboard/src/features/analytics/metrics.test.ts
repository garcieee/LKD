import { test } from "node:test";
import assert from "node:assert/strict";
import type { Report } from "../../types/api.ts";
import { aging, byCategory, duration, funnel, hotspots, medianResponseMs, summarize, throughput } from "./metrics.ts";

const NOW = Date.parse("2026-10-07T00:00:00Z");
const HOUR = 3_600_000;
const ago = (hours: number) => new Date(NOW - hours * HOUR).toISOString();
const report = (id: string, over: Partial<Report> = {}): Report => ({
  id,
  category: "pothole",
  severity: 2,
  lat: 14.5547,
  lng: 121.0244,
  heading: null,
  note: "",
  photo_url: `/photos/${id}.jpg`,
  status: "open",
  created_at: ago(1),
  updated_at: ago(1),
  ...over,
});

test("funnel: every status in workflow order, zeros included", () => {
  const f = funnel([report("a"), report("b"), report("c", { status: "fixed" })]);
  assert.deepEqual(f, [
    { status: "open", count: 2 },
    { status: "verified", count: 0 },
    { status: "assigned", count: 0 },
    { status: "fixed", count: 1 },
  ]);
});

test("byCategory: counts total and unresolved, most unresolved first", () => {
  const rows = byCategory([
    report("a", { category: "open_manhole", severity: 3 }),
    report("b", { category: "pothole", status: "fixed" }),
    report("c", { category: "pothole" }),
    report("d", { category: "pothole" }),
  ]);
  assert.deepEqual(rows.map((r) => [r.category, r.total, r.unresolved]), [
    ["pothole", 3, 2],
    ["open_manhole", 1, 1],
  ]);
  assert.equal(rows[1].severity, 3);
});

test("aging: bucket edges land in the older bucket; fixed reports are skipped; oldest is reported", () => {
  const a = aging(
    [
      report("fresh", { created_at: ago(23.9) }),
      report("one-day", { created_at: ago(24) }),
      report("three-day", { created_at: ago(72) }),
      report("week", { created_at: ago(24 * 7) }),
      report("fixed-old", { created_at: ago(24 * 30), status: "fixed" }),
      report("future", { created_at: ago(-5) }),
    ],
    NOW,
  );
  assert.deepEqual(a.buckets.map((b) => b.count), [2, 1, 1, 1]);
  assert.equal(a.oldest?.id, "week");
  assert.equal(aging([], NOW).oldest, null);
});

test("throughput: rolling 24 h windows, oldest first; fixed counted by updated_at; out-of-range ignored", () => {
  const t = throughput(
    [
      report("today", { created_at: ago(2) }),
      report("yesterday", { created_at: ago(30) }),
      report("fixed-today", { created_at: ago(50), status: "fixed", updated_at: ago(3) }),
      report("too-old", { created_at: ago(24 * 10) }),
      report("future", { created_at: ago(-5) }),
    ],
    NOW,
    3,
  );
  assert.deepEqual(t, [
    { created: 1, fixed: 0 }, // fixed-today, created 50 h ago
    { created: 1, fixed: 0 }, // yesterday
    { created: 1, fixed: 1 }, // today (fixed-today fixed 3 h ago)
  ]);
});

test("medianResponseMs: odd, even, none, and ignores unfixed or negative spans", () => {
  const fixed = (id: string, hours: number) => report(id, { status: "fixed", created_at: ago(10), updated_at: ago(10 - hours) });
  assert.equal(medianResponseMs([report("open")]), null);
  assert.equal(medianResponseMs([fixed("a", 1), fixed("b", 5), fixed("c", 2)]), 2 * HOUR);
  assert.equal(medianResponseMs([fixed("a", 1), fixed("b", 3)]), 2 * HOUR);
  assert.equal(medianResponseMs([fixed("a", 4), fixed("skew", -2)]), 4 * HOUR);
});

test("hotspots: groups nearby unresolved reports, busiest first, centroid location, limit applied", () => {
  const h = hotspots(
    [
      report("a", { lat: 14.5501, lng: 121.0201 }),
      report("b", { lat: 14.5503, lng: 121.0203 }),
      report("fixed", { lat: 14.5502, lng: 121.0202, status: "fixed" }),
      report("far", { lat: 14.5701, lng: 121.0301, severity: 3 }),
    ],
    5,
  );
  assert.equal(h.length, 2);
  assert.deepEqual(h[0].ids, ["a", "b"]);
  assert.equal(h[0].count, 2);
  assert.ok(Math.abs(h[0].lat - 14.5502) < 1e-9 && Math.abs(h[0].lng - 121.0202) < 1e-9);
  assert.equal(hotspots([report("a"), report("b", { lat: 14.58 })], 1).length, 1);
});

test("summarize: urgent counts unresolved severity-3 reports only", () => {
  const s = summarize(
    [report("a", { severity: 3 }), report("b", { severity: 3, status: "fixed" }), report("c", { severity: 2 })],
    NOW,
  );
  assert.equal(s.urgent, 1);
  assert.equal(s.unresolved, 2);
});

test("summarize: empty list gives zeros and nulls, not NaN or a throw", () => {
  const s = summarize([], NOW);
  assert.equal(s.total, 0);
  assert.equal(s.unresolved, 0);
  assert.equal(s.medianResponseMs, null);
  assert.deepEqual(s.hotspots, []);
  assert.equal(s.throughput.length, 7);
});

test("duration: minutes under an hour, hours under two days, then days", () => {
  assert.equal(duration(0), "1 min");
  assert.equal(duration(40 * 60_000), "40 min");
  assert.equal(duration(5.5 * HOUR), "5.5 h");
  assert.equal(duration(47 * HOUR), "47 h");
  assert.equal(duration(72 * HOUR), "3 d");
});
