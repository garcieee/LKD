import { test } from "node:test";
import assert from "node:assert/strict";
import type { Report } from "../../types/api.ts";
import { BARANGAYS } from "../../data/barangays.ts";
import { inBarangay } from "../barangays/barangays.ts";
import { DEFAULT_FILTERS, STATUS_FILTERS, applyFilters, filterSummary, idQuery, isFiltered, isSearching, matchesId, matchesStatus, poolFor, statusCounts } from "./filters.ts";
import { rank } from "./tickets.ts";

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
  created_at: "2026-10-07T00:00:00Z",
  updated_at: "2026-10-07T00:00:00Z",
  ...over,
});

// One ticket in each state, and two categories, in the order the queue would list them.
const tickets = [
  report("a1b2c3d4e5", { status: "open" }),
  report("b2c3d4e5f6", { status: "verified", category: "open_manhole" }),
  report("c3d4e5f6a1", { status: "assigned", category: "open_manhole", handler: "Ana Reyes" }),
  report("d4e5f6a1b2", { status: "fixed" }),
  report("e5f6a1b2c3", { status: "rejected", category: "blocked_sidewalk" }),
];
const ids = (rs: Report[]) => rs.map((r) => r.id[0]);

test("each status filter shows the tickets it names: unverified is new, verified is confirmed and being handled", () => {
  const shown = (f: (typeof STATUS_FILTERS)[number]["id"]) => ids(tickets.filter((r) => matchesStatus(r, f)));
  assert.deepEqual(shown("active"), ["a", "b", "c"], "everything still to do");
  assert.deepEqual(shown("unverified"), ["a"]);
  assert.deepEqual(shown("verified"), ["b", "c"], "verified and assigned");
  assert.deepEqual(shown("resolved"), ["d"]);
  assert.deepEqual(shown("rejected"), ["e"]);
});

test("the default view is the active queue: fixed and rejected tickets are out of the way", () => {
  assert.deepEqual(ids(applyFilters(tickets, DEFAULT_FILTERS)), ["a", "b", "c"]);
});

test("a category filter narrows the status one, and the ranking order is kept", () => {
  assert.deepEqual(ids(applyFilters(tickets, { ...DEFAULT_FILTERS, category: "open_manhole" })), ["b", "c"]);
  assert.deepEqual(ids(applyFilters(tickets, { status: "verified", category: "open_manhole", query: "" })), ["b", "c"]);
  assert.deepEqual(ids(applyFilters(tickets, { status: "unverified", category: "open_manhole", query: "" })), []);
  assert.deepEqual(ids(applyFilters([...tickets].reverse(), DEFAULT_FILTERS)), ["c", "b", "a"], "filtering never reorders");
});

test("a search takes the code as people read it, in any of its spellings", () => {
  for (const typed of ["LKD-A1B2C3", "lkd-a1b2c3", "lkda1b2c3", "LKD A1B2C3", "#a1b2c3", "a1b2c3", " A1B2C3 "]) {
    assert.equal(idQuery(typed), "a1b2c3", typed);
    assert.deepEqual(ids(applyFilters(tickets, { ...DEFAULT_FILTERS, query: typed })), ["a"], typed);
  }
});

test("a search matches the start of an id, so a few characters narrow the list and the full id finds one", () => {
  assert.deepEqual(ids(applyFilters(tickets, { ...DEFAULT_FILTERS, query: "b" })), ["b"]);
  assert.deepEqual(ids(applyFilters(tickets, { ...DEFAULT_FILTERS, query: "a1b2c3d4e5" })), ["a"]);
  assert.deepEqual(ids(applyFilters(tickets, { ...DEFAULT_FILTERS, query: "2c3d4e" })), [], "the middle of an id is not a code");
  assert.deepEqual(ids(applyFilters(tickets, { ...DEFAULT_FILTERS, query: "zzzzzz" })), []);
});

test("a search looks at every ticket: a resolved or rejected one is found even with another filter on", () => {
  assert.deepEqual(ids(applyFilters(tickets, { status: "active", category: "pothole", query: "LKD-D4E5F6" })), ["d"]);
  assert.deepEqual(ids(applyFilters(tickets, { status: "active", category: "pothole", query: "e5f6a1" })), ["e"]);
  assert.ok(isSearching({ ...DEFAULT_FILTERS, query: "a1" }));
  assert.ok(!isSearching({ ...DEFAULT_FILTERS, query: "   " }), "spaces are not a search");
  assert.ok(!isSearching({ ...DEFAULT_FILTERS, query: "LKD-" }), "just the prefix is not a search either");
});

test("every sighting of one ticket matches its code, since they share it", () => {
  const first = report("3f2a9c01aa", { ticket_id: "3f2a9c01aa" });
  const second = report("b7e1ffaa00", { ticket_id: "3f2a9c01aa" });
  assert.ok(matchesId(first, "LKD-3F2A9C") && matchesId(second, "LKD-3F2A9C"));
  assert.ok(matchesId(second, "b7e1ff"), "or its own id");
  assert.ok(!matchesId(second, "LKD-ZZZZZZ"));
});

test("statusCounts: what each chip would show, for the chosen category", () => {
  assert.deepEqual(statusCounts(tickets, "all"), { active: 3, unverified: 1, verified: 2, resolved: 1, rejected: 1 });
  assert.deepEqual(statusCounts(tickets, "open_manhole"), { active: 2, unverified: 0, verified: 2, resolved: 0, rejected: 0 });
  assert.deepEqual(statusCounts([], "all"), { active: 0, unverified: 0, verified: 0, resolved: 0, rejected: 0 });
});

test("isFiltered: only a change from the default view offers Clear filters", () => {
  assert.ok(!isFiltered(DEFAULT_FILTERS));
  assert.ok(isFiltered({ ...DEFAULT_FILTERS, status: "verified" }));
  assert.ok(isFiltered({ ...DEFAULT_FILTERS, category: "pothole" }));
  assert.ok(isFiltered({ ...DEFAULT_FILTERS, query: "a1" }));
  assert.ok(!isFiltered({ ...DEFAULT_FILTERS, query: "   " }));
});

test("the status filters are the five the chips show, each with a hint", () => {
  assert.deepEqual(STATUS_FILTERS.map((f) => f.id), ["active", "unverified", "verified", "resolved", "rejected"]);
  for (const f of STATUS_FILTERS) assert.ok(f.label && f.hint);
});

// Two barangays' tickets and one far outside Makati. Greenbelt is in San Lorenzo, Makati Avenue and Jupiter in Poblacion.
const lorenzo = report("1a1a1a1a1a", { lng: 121.0235, lat: 14.5528 });
const lorenzoFixed = report("2b2b2b2b2b", { lng: 121.0235, lat: 14.5528, status: "fixed" });
const poblacion = report("3c3c3c3c3c", { lng: 121.03, lat: 14.564, category: "open_manhole" });
const poblacionFixed = report("4d4d4d4d4d", { lng: 121.03, lat: 14.564, status: "fixed" });
const faraway = report("5e5e5e5e5e", { lng: 121.1, lat: 14.6 });
const city = [lorenzo, lorenzoFixed, poblacion, poblacionFixed, faraway];

// What the queue does with the barangay picked in the Barangays menu: narrow first (poolFor), then rank and filter.
const listed = (f: typeof DEFAULT_FILTERS, barangayId: string | null) =>
  ids(applyFilters(rank(poolFor(f, city, inBarangay(BARANGAYS, barangayId, city))), f));

test("a barangay picked narrows the list to its tickets: the others, and those outside all 23, are not listed", () => {
  assert.deepEqual(listed(DEFAULT_FILTERS, null).sort(), ["1", "3", "5"], "no barangay: every active ticket, even outside the 23");
  assert.deepEqual(listed(DEFAULT_FILTERS, "san-lorenzo"), ["1"]);
  assert.deepEqual(listed(DEFAULT_FILTERS, "poblacion"), ["3"]);
  assert.deepEqual(listed({ ...DEFAULT_FILTERS, status: "resolved" }, "poblacion"), ["4"], "the status chips work inside it");
  assert.deepEqual(listed({ ...DEFAULT_FILTERS, category: "open_manhole" }, "san-lorenzo"), [], "and the category");
  assert.deepEqual(listed(DEFAULT_FILTERS, "bangkal"), [], "a barangay with no tickets lists none");
});

test("the status chips count only the picked barangay's tickets", () => {
  assert.deepEqual(statusCounts(inBarangay(BARANGAYS, "san-lorenzo", city), "all"), { active: 1, unverified: 1, verified: 0, resolved: 1, rejected: 0 });
  assert.deepEqual(statusCounts(inBarangay(BARANGAYS, null, city), "all"), { active: 3, unverified: 3, verified: 0, resolved: 2, rejected: 0 });
});

test("a search ignores the barangay too: an ID finds its ticket, resolved or in another barangay", () => {
  assert.deepEqual(listed({ ...DEFAULT_FILTERS, query: "LKD-3C3C3C" }, "san-lorenzo"), ["3"], "a ticket in Poblacion, with San Lorenzo picked");
  assert.deepEqual(listed({ ...DEFAULT_FILTERS, query: "4d4d" }, "san-lorenzo"), ["4"], "a resolved one as well");
  assert.deepEqual(listed({ ...DEFAULT_FILTERS, query: "5e5e5e" }, "poblacion"), ["5"], "and one outside all 23 barangays");
  assert.deepEqual(listed({ ...DEFAULT_FILTERS, query: "1a1a" }, "poblacion"), ["1"]);
  assert.equal(poolFor({ ...DEFAULT_FILTERS, query: "1a" }, city, []), city, "a search starts from every ticket");
  assert.equal(poolFor(DEFAULT_FILTERS, city, []).length, 0, "anything else starts from the barangay's");
  assert.deepEqual(listed({ ...DEFAULT_FILTERS, query: "   " }, "poblacion"), ["3"], "spaces are not a search, so the barangay still narrows");
});

test("filterSummary says what is shown, out of what, and where, and that a search left the barangay", () => {
  const sum = (o: Partial<Parameters<typeof filterSummary>[0]> = {}) => filterSummary({ searching: false, shown: 3, total: 9, barangay: null, ...o });
  assert.equal(sum(), "Showing 3 of 9 tickets");
  assert.equal(sum({ barangay: "Poblacion" }), "Showing 3 of 9 tickets in Poblacion");
  assert.equal(sum({ searching: true }), "Searching all tickets: 3 found");
  assert.equal(sum({ searching: true, barangay: "Poblacion" }), "Searching all of Makati, not just Poblacion: 3 found");
});
