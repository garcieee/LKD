import { test } from "node:test";
import assert from "node:assert/strict";
import type { Report } from "../../types/api.ts";
import { CATEGORY_LABEL, SOS_KINDS, SOS_KIND_HINT, SOS_KIND_LABEL, STATUSES, STATUS_LABEL, isRejected, isSos, isSosActive, isUnresolved, needsReview, needsSorting, newReports, rank, steps, ticketLabel, timeAgo, toGeoJSON } from "./tickets.ts";

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

test("timeAgo: just under and exactly on each boundary, and the server's +00:00 timestamps", () => {
  const ago = (ms: number) => timeAgo(new Date(T0 - ms).toISOString(), T0);
  assert.equal(ago(59_999), "just now");
  assert.equal(ago(60_000), "1 min ago");
  assert.equal(ago(24 * 3_600_000 - 1), "23 h ago");
  assert.equal(ago(24 * 3_600_000), "1 d ago");
  assert.equal(timeAgo("2026-10-06T05:00:00+00:00", T0), "2 h ago");
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

test("newReports: after an empty first poll, the first ticket is new (the demo starts empty)", () => {
  assert.deepEqual(newReports(new Set(), [report("a")]).map((r) => r.id), ["a"]);
});

test("toGeoJSON: a pin for every status, fixed included, and none flagged without a live selection", () => {
  const all = STATUSES.map((status) => report(status, { status }));
  for (const selected of [null, "gone"]) {
    const fc = toGeoJSON(all, selected);
    assert.deepEqual(fc.features.map((f) => f.properties.status), STATUSES);
    assert.ok(fc.features.every((f) => !f.properties.selected));
  }
});

test("toGeoJSON: [lng, lat] points with status, only the selected one flagged", () => {
  const fc = toGeoJSON([report("a", { status: "verified" }), report("b", { lat: 14.56, lng: 121.01 })], "b");
  assert.equal(fc.type, "FeatureCollection");
  assert.deepEqual(fc.features[1].geometry, { type: "Point", coordinates: [121.01, 14.56] });
  assert.deepEqual(
    fc.features.map((f) => f.properties),
    [
      { id: "a", status: "verified", selected: false, alert: false },
      { id: "b", status: "open", selected: true, alert: false },
    ],
  );
  assert.deepEqual(toGeoJSON([], null).features, []);
});

const sos = (id: string, over: Partial<Report> = {}) => report(id, { category: "sos", severity: 3, photo_url: "", video_url: `/videos/${id}.mp4`, ...over });

test("an SOS is labelled, and only one nobody has fixed counts as active", () => {
  assert.equal(CATEGORY_LABEL.sos, "SOS", "not only a crime: who must respond is sorted at the dashboard");
  assert.ok(isSos(sos("a")) && !isSos(report("b")));
  assert.ok(isSosActive(sos("a")));
  for (const status of ["verified", "assigned"] as const) assert.ok(isSosActive(sos("a", { status })), status);
  assert.ok(!isSosActive(sos("a", { status: "fixed" })), "a fixed SOS stops blinking");
  assert.ok(!isSosActive(report("b", { severity: 3 })), "an urgent hazard is not an SOS");
});

test("rank: an open SOS tops the queue, even over an older urgent hazard", () => {
  const input = [
    report("urgent-old", { severity: 3, created_at: at(-120) }),
    sos("sos-new", { created_at: at(-1) }),
    report("medium", { created_at: at(-60) }),
    sos("sos-old", { created_at: at(-10), status: "assigned" }),
    sos("sos-fixed", { status: "fixed", created_at: at(-200) }),
  ];
  assert.deepEqual(rank(input).map((r) => r.id), ["sos-old", "sos-new", "urgent-old", "medium", "sos-fixed"]);
});

test("toGeoJSON: only an unfixed SOS is an alert, which is what makes its pin blink", () => {
  const props = toGeoJSON([sos("a"), sos("b", { status: "fixed" }), report("c", { severity: 3 })], null).features.map(
    (f) => f.properties.alert,
  );
  assert.deepEqual(props, [true, false, false]);
});

test("a new ticket needs review; Confirm (verified) and Reject (rejected) both end that", () => {
  assert.ok(needsReview(report("a")));
  for (const status of ["verified", "assigned", "fixed", "rejected"] as const) assert.ok(!needsReview(report("a", { status })), status);
});

test("a rejected ticket is not unresolved, not an active SOS, and is not a step of the workflow", () => {
  const rejected = report("r", { status: "rejected" });
  assert.ok(isRejected(rejected) && !isUnresolved(rejected));
  assert.ok(!isSosActive(sos("s", { status: "rejected" })), "a rejected SOS stops blinking");
  assert.equal(STATUS_LABEL.rejected, "Rejected");
  assert.ok(!STATUSES.includes("rejected"), "the stepper stays Open, Verified, Assigned, Fixed");
  assert.ok(steps("rejected").every((s) => !s.reached && !s.current));
});

test("rank: rejected tickets go last, after fixed ones, even an urgent or SOS one", () => {
  const input = [
    report("rejected-urgent", { status: "rejected", severity: 3, created_at: at(-500) }),
    report("fixed", { status: "fixed", severity: 1 }),
    sos("rejected-sos", { status: "rejected" }),
    report("open", { severity: 1 }),
  ];
  assert.deepEqual(rank(input).map((r) => r.id), ["open", "fixed", "rejected-urgent", "rejected-sos"]);
});

test("SOS kinds: Police, Medical, Fire and rescue, in that order, each with what it covers", () => {
  assert.deepEqual(
    SOS_KINDS.map((k) => [k, SOS_KIND_LABEL[k], SOS_KIND_HINT[k]]),
    [
      ["police", "Police", "Crime, violence or a threat"],
      ["medical", "Medical", "Injury, collapse or illness"],
      ["fire_rescue", "Fire and rescue", "Fire, flood or someone trapped"],
    ],
  );
});

test("ticketLabel: an SOS by who must respond, Unsorted until someone picks; a hazard by its category", () => {
  const kinds = [...SOS_KINDS, null, undefined].map((sos_kind) => ticketLabel(sos("a", { sos_kind })));
  assert.deepEqual(kinds, ["SOS · Police", "SOS · Medical", "SOS · Fire and rescue", "SOS · Unsorted", "SOS · Unsorted"]);
  assert.equal(ticketLabel(report("b", { category: "open_manhole" })), "Open manhole");
});

test("needsSorting: an active SOS nobody has sorted; not a sorted, fixed or rejected one, nor a hazard", () => {
  assert.ok(needsSorting(sos("a")) && needsSorting(sos("a", { status: "assigned", sos_kind: null })));
  assert.ok(!needsSorting(sos("a", { sos_kind: "medical" })));
  for (const status of ["fixed", "rejected"] as const) assert.ok(!needsSorting(sos("a", { status })), status);
  assert.ok(!needsSorting(report("b", { severity: 3 })));
});

test("rank: an unsorted SOS above an older sorted one, both above an urgent hazard; a closed SOS is not lifted", () => {
  const input = [
    report("urgent-old", { severity: 3, created_at: at(-120) }),
    sos("sorted-old", { sos_kind: "police", created_at: at(-30) }),
    sos("unsorted-new", { status: "verified", created_at: at(-1) }),
    sos("fixed-unsorted", { status: "fixed", created_at: at(-200) }),
    report("fixed-older", { status: "fixed", severity: 3, created_at: at(-400) }),
    sos("rejected-unsorted", { status: "rejected" }),
  ];
  assert.deepEqual(rank(input).map((r) => r.id), [
    "unsorted-new",
    "sorted-old",
    "urgent-old",
    "fixed-older",
    "fixed-unsorted",
    "rejected-unsorted",
  ]);
});
