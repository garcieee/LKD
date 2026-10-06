// Ticket logic with no React or mapbox-gl, so `node --test` runs it (tickets.test.ts).
import type { Category, Report, SosKind, Status } from "../../types/api.ts";

export const CATEGORY_LABEL: Record<Category, string> = {
  pothole: "Pothole",
  open_manhole: "Open manhole",
  flooded_drain: "Flooded drain",
  broken_streetlight: "Broken streetlight",
  blocked_sidewalk: "Blocked sidewalk",
  missing_ramp: "Missing or broken ramp",
  blocked_tactile_paving: "Blocked or missing tactile paving",
  broken_elevator: "Broken elevator or escalator",
  unsafe_sidewalk: "Steep or broken sidewalk",
  other: "Other",
  sos: "SOS",
};

export const SEVERITY_LABEL: Record<Report["severity"], string> = { 1: "Low", 2: "Medium", 3: "Urgent" };

// Workflow order, left to right in the stepper.
export const STATUSES: Status[] = ["open", "verified", "assigned", "fixed"];
export const STATUS_LABEL: Record<Status, string> = {
  open: "Open",
  verified: "Verified",
  assigned: "Assigned",
  fixed: "Fixed",
  rejected: "Rejected",
};

// Rejected is not a step of the workflow (STATUSES): it is the answer to "is this real?", given to a new ticket.
export const isRejected = (r: Report) => r.status === "rejected";
export const isUnresolved = (r: Report) => r.status !== "fixed" && r.status !== "rejected";

// A ticket nobody has looked at yet: the dashboard asks the receiver to Confirm (-> Verified) or Reject it.
export const needsReview = (r: Report) => r.status === "open";

// A call for help from the phone's SOS button. While nobody has marked it fixed it tops the queue and blinks on the map.
export const isSos = (r: Report) => r.category === "sos";
export const isSosActive = (r: Report) => isSos(r) && isUnresolved(r);

// Who must respond to an SOS, picked here after watching its silent video (the phone does not ask).
// Mirrors models/ticket_sos/sos.py KINDS, in the same order.
export const SOS_KINDS: SosKind[] = ["police", "medical", "fire_rescue"];
export const SOS_KIND_LABEL: Record<SosKind, string> = {
  police: "Police",
  medical: "Medical",
  fire_rescue: "Fire and rescue",
};
export const SOS_KIND_HINT: Record<SosKind, string> = {
  police: "Crime, violence or a threat",
  medical: "Injury, collapse or illness",
  fire_rescue: "Fire, flood or someone trapped",
};

// An SOS still waiting for someone to say who must respond: listed above the sorted ones.
export const needsSorting = (r: Report) => isSosActive(r) && !r.sos_kind;

// "SOS · Police", "SOS · Unsorted", or a hazard's category.
export const ticketLabel = (r: Report) =>
  isSos(r)
    ? `${CATEGORY_LABEL.sos} · ${r.sos_kind ? SOS_KIND_LABEL[r.sos_kind] : "Unsorted"}`
    : CATEGORY_LABEL[r.category];

// The fix-it order: unresolved first (rejected tickets last of all), SOS before everything else (unsorted ones on
// top), then most severe, then oldest. Times only have whole seconds, so ties are common; the API lists newest
// first, and sorting it reversed keeps ties in arrival order.
export function rank(reports: Report[]): Report[] {
  return reports.toReversed().sort(
    (a, b) =>
      Number(isUnresolved(b)) - Number(isUnresolved(a)) ||
      Number(isRejected(a)) - Number(isRejected(b)) ||
      Number(isSosActive(b)) - Number(isSosActive(a)) ||
      Number(needsSorting(b)) - Number(needsSorting(a)) ||
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
