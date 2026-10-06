// Ticket logic with no React or mapbox-gl, so `node --test` runs it (tickets.test.ts).
import type { Band, Category, Report, SosKind, Status } from "../../types/api.ts";

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
// The ticket's ID as people read it out: "LKD-" and the first six characters of its id, in capitals. A ticket's id
// is its first report's, so every sighting of one hazard shows the same code.
export const ticketCode = (r: Pick<Report, "id" | "ticket_id">) => `LKD-${(r.ticket_id ?? r.id).slice(0, 6).toUpperCase()}`;

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

// The ticket engine's score (0..100, higher is more urgent), once the server's ticket loop has set it. Anything else,
// including NaN, counts as not scored yet.
export const hasPriority = (r: Report): r is Report & { priority: number } => Number.isFinite(r.priority);

// The engine's band, when it is one of the four the dashboard knows (null before the loop has scored the report).
export const BANDS: Band[] = ["Critical", "High", "Medium", "Low"];
export const bandOf = (r: Report): Band | null => BANDS.find((b) => b === r.band) ?? null;

// An unresolved ticket that needs doing first: Critical or High on the engine's band, or, until the loop has scored it,
// Urgent on the category's severity. One definition for the badge, the HUD dot and the Insights count, so they agree
// (severity and band say the same thing in two scales: every severity-3 ticket is Critical or High).
export const isUrgent = (r: Report) => isUnresolved(r) && (bandOf(r) ? bandOf(r) === "Critical" || bandOf(r) === "High" : r.severity === 3);

// How many reports each ticket has, by ticket_id (reports of one hazard share it). Not-yet-ticketed reports are left out.
export function sightings(reports: Report[]): Map<string, number> {
  const count = new Map<string, number>();
  for (const r of reports) if (r.ticket_id) count.set(r.ticket_id, (count.get(r.ticket_id) ?? 0) + 1);
  return count;
}

// "3 reports" for a ticket reported more than once, "" otherwise.
export function sightingsLabel(r: Report, count: ReadonlyMap<string, number>): string {
  const n = (r.ticket_id && count.get(r.ticket_id)) || 0;
  return n > 1 ? `${n} reports` : "";
}

// The fix-it order: unresolved first (rejected tickets last of all), SOS before everything else (unsorted ones on
// top), then the engine's priority (scored tickets above ones not scored yet, so the order stays consistent when the
// two mix), then most severe, then oldest. Times only have whole seconds, so ties are common; the API lists newest
// first, and sorting it reversed keeps ties in arrival order.
export function rank(reports: Report[]): Report[] {
  return reports.toReversed().sort(
    (a, b) =>
      Number(isUnresolved(b)) - Number(isUnresolved(a)) ||
      Number(isRejected(a)) - Number(isRejected(b)) ||
      Number(isSosActive(b)) - Number(isSosActive(a)) ||
      Number(needsSorting(b)) - Number(needsSorting(a)) ||
      Number(hasPriority(b)) - Number(hasPriority(a)) ||
      (hasPriority(a) && hasPriority(b) ? b.priority - a.priority : 0) ||
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
