// Ticket logic with no React or mapbox-gl, so `node --test` runs it (tickets.test.ts).
import type { Category, Report, Status } from "../../types/api.ts";

export const CATEGORY_LABEL: Record<Category, string> = {
  pothole: "Pothole",
  open_manhole: "Open manhole",
  flooded_drain: "Flooded drain",
  broken_streetlight: "Broken streetlight",
  blocked_sidewalk: "Blocked sidewalk",
  other: "Other",
  sos: "SOS · Crime signal",
};

export const SEVERITY_LABEL: Record<Report["severity"], string> = { 1: "Low", 2: "Medium", 3: "Urgent" };

// Workflow order, left to right in the stepper.
export const STATUSES: Status[] = ["open", "verified", "assigned", "fixed"];
export const STATUS_LABEL: Record<Status, string> = {
  open: "Open",
  verified: "Verified",
  assigned: "Assigned",
  fixed: "Fixed",
};

export const isUnresolved = (r: Report) => r.status !== "fixed";

// A call for help from the phone's SOS button. While nobody has marked it fixed it tops the queue and blinks on the map.
export const isSos = (r: Report) => r.category === "sos";
export const isSosActive = (r: Report) => isSos(r) && isUnresolved(r);

// The fix-it order: unresolved first, SOS before everything else, then most severe, then oldest. Times only
// have whole seconds, so ties are common; the API lists newest first, and sorting it reversed keeps ties in
// arrival order.
export function rank(reports: Report[]): Report[] {
  return reports.toReversed().sort(
    (a, b) =>
      Number(isUnresolved(b)) - Number(isUnresolved(a)) ||
      Number(isSosActive(b)) - Number(isSosActive(a)) ||
      b.severity - a.severity ||
      Date.parse(a.created_at) - Date.parse(b.created_at),
  );
}

// "just now", "12 min ago", "3 h ago", "2 d ago". A server clock ahead of ours reads "just now".
export function timeAgo(iso: string, now: number): string {
  const min = Math.floor((now - Date.parse(iso)) / 60_000);
  if (Number.isNaN(min)) return "";
  if (min < 1) return "just now";
  if (min < 60) return `${min} min ago`;
  if (min < 24 * 60) return `${Math.floor(min / 60)} h ago`;
  return `${Math.floor(min / (24 * 60))} d ago`;
}

// Every step up to the current one is reached.
export function steps(current: Status) {
  const at = STATUSES.indexOf(current);
  return STATUSES.map((status, i) => ({
    status,
    label: STATUS_LABEL[status],
    reached: i <= at,
    current: i === at,
  }));
}

// Reports whose id the last poll did not have. The first poll (known = null) has nothing new.
export function newReports(known: ReadonlySet<string> | null, reports: Report[]): Report[] {
  return known ? reports.filter((r) => !known.has(r.id)) : [];
}

// Map pins: one GeoJSON point per report, [lng, lat], flagged when it is the selected ticket, and `alert` when
// it is an SOS still open (those blink red, layers/reports.ts).
export function toGeoJSON(reports: Report[], selectedId: string | null) {
  return {
    type: "FeatureCollection" as const,
    features: reports.map((r) => ({
      type: "Feature" as const,
      geometry: { type: "Point" as const, coordinates: [r.lng, r.lat] },
      properties: { id: r.id, status: r.status, selected: r.id === selectedId, alert: isSosActive(r) },
    })),
  };
}
