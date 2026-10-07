// Filtering the ticket list: by status (unverified or verified, and the rest), by category, and a search by ticket ID;
// the barangay picked in the Barangays menu narrows it before any of these (poolFor). No React, so `node --test` runs it
// (filters.test.ts). The list is ranked first (tickets.ts rank), then filtered, so the order never changes.
import type { Category, Report } from "../../types/api.ts";
import { isUnresolved, ticketCode } from "./tickets.ts";

// "Unverified" is a ticket nobody has confirmed yet (status open); "Verified" is one that was confirmed and is being
// handled (verified or assigned); "Active" is both of those, the default view.
export type StatusFilter = "active" | "unverified" | "verified" | "resolved" | "rejected";

export const STATUS_FILTERS: { id: StatusFilter; label: string; hint: string }[] = [
  { id: "active", label: "Active", hint: "Unverified and verified tickets that are not resolved" },
  { id: "unverified", label: "Unverified", hint: "New tickets waiting to be confirmed or rejected" },
  { id: "verified", label: "Verified", hint: "Confirmed tickets: verified or assigned to a handler" },
  { id: "resolved", label: "Resolved", hint: "Fixed tickets" },
  { id: "rejected", label: "Rejected", hint: "Tickets judged not real" },
];

export type Filters = { status: StatusFilter; category: Category | "all"; query: string };

export const DEFAULT_FILTERS: Filters = { status: "active", category: "all", query: "" };

export function matchesStatus(r: Report, f: StatusFilter): boolean {
  switch (f) {
    case "active":
      return isUnresolved(r);
    case "unverified":
      return r.status === "open";
    case "verified":
      return r.status === "verified" || r.status === "assigned";
    case "resolved":
      return r.status === "fixed";
    case "rejected":
      return r.status === "rejected";
  }
}

// What a person typed, as the start of an id: "LKD-3F2A9C", "lkd3f2a", "#3f2a" and "3F2A" all mean "3f2a...".
export function idQuery(text: string): string {
  return text
    .trim()
    .toLowerCase()
    .replace(/^#/, "")
    .replace(/^lkd[-\s]?/, "")
    .replace(/\s+/g, "");
}

// Whether the ticket's ID starts with the search. The code people read is the first six characters of the ticket's id,
// and a longer search narrows further. Every sighting of one ticket matches, as they share it.
export function matchesId(r: Report, text: string): boolean {
  const q = idQuery(text);
  if (!q) return true;
  return (r.ticket_id ?? r.id).toLowerCase().startsWith(q) || r.id.toLowerCase().startsWith(q);
}

// A search looks at every ticket whatever its status or category: someone with an ID wants that ticket, even a
// resolved one, and a filter that hid it would read as "not found".
export const isSearching = (f: Filters) => idQuery(f.query) !== "";

// The tickets the list starts from. `scoped` is those in the barangay picked in the Barangays menu (every ticket when none
// is). A search looks at every ticket in Makati: just as it ignores status and category, it ignores the barangay, so an
// ID that is typed finds its ticket wherever it is, and the list says so (filterSummary).
export const poolFor = (f: Filters, all: Report[], scoped: Report[]): Report[] => (isSearching(f) ? all : scoped);

// The line under the filters: what is shown, out of what, and where. `barangay` is the name picked, if any.
export function filterSummary(o: { searching: boolean; shown: number; total: number; barangay: string | null }): string {
  if (o.searching) {
    return o.barangay ? `Searching all of Makati, not just ${o.barangay}: ${o.shown} found` : `Searching all tickets: ${o.shown} found`;
  }
  return `Showing ${o.shown} of ${o.total} tickets${o.barangay ? ` in ${o.barangay}` : ""}`;
}

export function applyFilters(ranked: Report[], f: Filters): Report[] {
  if (isSearching(f)) return ranked.filter((r) => matchesId(r, f.query));
  return ranked.filter((r) => matchesStatus(r, f.status) && (f.category === "all" || r.category === f.category));
}

// Whether anything differs from the default view, to offer "Clear filters".
export const isFiltered = (f: Filters) => f.status !== DEFAULT_FILTERS.status || f.category !== "all" || f.query.trim() !== "";

// How many tickets each status chip would show, for the category chosen (a search ignores both, so it is left out).
export function statusCounts(reports: Report[], category: Category | "all"): Record<StatusFilter, number> {
  const counts: Record<StatusFilter, number> = { active: 0, unverified: 0, verified: 0, resolved: 0, rejected: 0 };
  for (const r of reports) {
    if (category !== "all" && r.category !== category) continue;
    for (const { id } of STATUS_FILTERS) if (matchesStatus(r, id)) counts[id]++;
  }
  return counts;
}

// "LKD-3F2A9C" for a search box's example.
export const exampleCode = (r: Report | undefined) => (r ? ticketCode(r) : "LKD-3F2A9C");
