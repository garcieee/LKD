import { test } from "node:test";
import assert from "node:assert/strict";
import type { Report } from "../../types/api.ts";
import { newReports, rank, steps, timeAgo, toGeoJSON } from "./tickets.ts";

const T0 = Date.parse("2026-10-06T07:00:00Z");
const at = (min: number) => new Date(T0 + min * 60_000).toISOString();
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
  created_at: at(0),
  updated_at: at(0),
  ...over,
});

test("rank: unresolved first, then severity high to low, then oldest first", () => {
  const input = [
    report("fixed-urgent", { status: "fixed", severity: 3 }),
    report("low-old", { severity: 1, created_at: at(-60) }),
    report("medium-new", { created_at: at(-5) }),
    report("medium-old", { created_at: at(-30), status: "assigned" }),
    report("urgent-new", { severity: 3, created_at: at(-1), status: "verified" }),
  ];
  const ids = rank(input).map((r) => r.id);
  assert.deepEqual(ids, ["urgent-new", "medium-old", "medium-new", "low-old", "fixed-urgent"]);
  assert.equal(input[0].id, "fixed-urgent", "sorts a copy, not the caller's list");
});

test("rank: reports from the same second keep arrival order (the API lists newest first)", () => {
  const newestFirst = [report("third", { severity: 3 }), report("second", { severity: 3 }), report("first", { severity: 3 })];
  assert.deepEqual(rank(newestFirst).map((r) => r.id), ["first", "second", "third"]);
});

test("timeAgo: minutes, hours, days", () => {
  assert.equal(timeAgo(at(-0.5), T0), "just now");
  assert.equal(timeAgo(at(-12), T0), "12 min ago");
  assert.equal(timeAgo(at(-59), T0), "59 min ago");
  assert.equal(timeAgo(at(-60), T0), "1 h ago");
  assert.equal(timeAgo(at(-23 * 60 - 59), T0), "23 h ago");
  assert.equal(timeAgo(at(-3 * 24 * 60), T0), "3 d ago");
});

test("timeAgo: a server clock ahead of ours, or a bad date, never shows nonsense", () => {
  assert.equal(timeAgo(at(5), T0), "just now");
  assert.equal(timeAgo("not a date", T0), "");
});

test("steps: Open → Verified → Assigned → Fixed, reached up to the current one", () => {
  const s = steps("assigned");
  assert.deepEqual(s.map((x) => x.label), ["Open", "Verified", "Assigned", "Fixed"]);
  assert.deepEqual(s.map((x) => x.reached), [true, true, true, false]);
  assert.deepEqual(s.map((x) => x.current), [false, false, true, false]);
  assert.deepEqual(steps("open").map((x) => x.reached), [true, false, false, false]);
});

test("newReports: nothing on the first poll, then only ids the last poll lacked", () => {
  const a = report("a");
  const b = report("b");
  assert.deepEqual(newReports(null, [a, b]), []);
  assert.deepEqual(newReports(new Set(["a"]), [b, a]), [b]);
  assert.deepEqual(newReports(new Set(["a", "b"]), [a]), [], "a ticket that went away is not new");
});

test("toGeoJSON: [lng, lat] points with status, only the selected one flagged", () => {
  const fc = toGeoJSON([report("a", { status: "verified" }), report("b", { lat: 14.56, lng: 121.01 })], "b");
  assert.equal(fc.type, "FeatureCollection");
  assert.deepEqual(fc.features[1].geometry, { type: "Point", coordinates: [121.01, 14.56] });
  assert.deepEqual(
    fc.features.map((f) => f.properties),
    [
      { id: "a", status: "verified", selected: false },
      { id: "b", status: "open", selected: true },
    ],
  );
  assert.deepEqual(toGeoJSON([], null).features, []);
});
