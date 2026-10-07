// The barangays menu's logic, with no React or mapbox-gl so `node --test` runs it (barangays.test.ts): finding a
// barangay by what someone types, which barangay a ticket is in, and how many tickets each one has. The boundaries
// are data/barangays.ts (Makati's 23 barangays, OpenStreetMap), built by scripts/build_barangays.py.
import type { Report } from "../../types/api.ts";
import { isRejected, isSosActive, isUnresolved, isUrgent } from "../queue/tickets.ts";

export type LngLat = [number, number];
export type Ring = LngLat[]; // closed: the first point repeats at the end

export type Barangay = {
  id: string; // "bel-air"
  name: string; // "Bel-Air"
  district: number; // 1 or 2
  center: LngLat; // where its name goes: the spot furthest inside the shape
  bbox: [number, number, number, number]; // west, south, east, north
  rank: number; // 0 is the biggest: bigger names are placed first when labels collide
  rings: Ring[]; // the outline(s), each its own area
};

// The corners a map zooms to to show the whole barangay.
export const boundsOf = (b: Barangay): [LngLat, LngLat] => [
  [b.bbox[0], b.bbox[1]],
  [b.bbox[2], b.bbox[3]],
];

// What a person typed, or a name, as plain lower-case words: accents, punctuation and "Brgy"/"Barangay" ignored, "Sta."
// read as Santa. "Dasmariñas", "dasmarinas" and "DASMARIÑAS" are one spelling, as are "Bel-Air" and "bel air".
export function norm(text: string): string {
  const words = text
    .normalize("NFD")
    .replace(/\p{M}/gu, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim()
    .split(" ")
    .filter(Boolean)
    .map((w) => (w === "sta" ? "santa" : w === "sto" ? "santo" : w));
  return (words[0] === "brgy" || words[0] === "barangay" ? words.slice(1) : words).join(" ");
}

const compact = (s: string) => s.replace(/ /g, "");

// "district 2", "d2" or "2": every barangay of that district.
function districtOf(query: string): number | null {
  const m = /^(?:district|dist|d)?\s*([12])$/.exec(query);
  return m ? Number(m[1]) : null;
}

// The barangays that match what was typed, best first: the exact name, then names that start with it, then names with a
// word that does, then names that contain it. Nothing typed is every barangay, A to Z.
export function searchBarangays(list: readonly Barangay[], text: string): Barangay[] {
  const q = norm(text);
  const alphabetical = [...list].sort((a, b) => a.name.localeCompare(b.name, "en"));
  if (!q) return alphabetical;
  const district = districtOf(q);
  if (district !== null) return alphabetical.filter((b) => b.district === district);
  const scored: [number, Barangay][] = [];
  for (const b of alphabetical) {
    const name = norm(b.name);
    const rank =
      name === q || compact(name) === compact(q)
        ? 0
        : name.startsWith(q) || compact(name).startsWith(compact(q))
          ? 1
          : name.split(" ").some((w) => w.startsWith(q))
            ? 2
            : compact(name).includes(compact(q))
              ? 3
              : -1;
    if (rank >= 0) scored.push([rank, b]);
  }
  return scored.sort((a, b) => a[0] - b[0]).map(([, b]) => b); // the sort is stable: equal ranks stay A to Z
}

// Whether a point is inside a closed ring (ray casting).
export function pointInRing(lng: number, lat: number, ring: Ring): boolean {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    if (yi > lat !== yj > lat && lng < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

// The barangay a point is in, or null outside all 23 (beyond Makati, or in a barangay that is Taguig now).
export function barangayAt(list: readonly Barangay[], lng: number, lat: number): Barangay | null {
  for (const b of list) {
    const [w, s, e, n] = b.bbox;
    if (lng < w || lng > e || lat < s || lat > n) continue; // the box rules most out before any ring is walked
    if (b.rings.some((r) => pointInRing(lng, lat, r))) return b;
  }
  return null;
}

// The reports in one barangay, by the same rule tally counts them (barangayAt), so a barangay's count in the menu and the
// tickets shown for it always agree. null is no barangay picked: every report, outside the 23 or not, and the very same
// array, so whatever is memoised on it keeps its work. A report outside every barangay is in none, so it is left out
// while one is picked.
export function inBarangay(list: readonly Barangay[], id: string | null, reports: Report[]): Report[] {
  if (id === null) return reports;
  return reports.filter((r) => barangayAt(list, r.lng, r.lat)?.id === id);
}

// What the map draws: the reports in the picked barangay (`scoped`), plus the open ticket even when it is outside (an ID
// search finds tickets anywhere, and Show on map needs its pin), and never a rejected one: those were judged not real.
export function pinReports(all: Report[], scoped: Report[], openId: string | null): Report[] {
  const open = all.find((r) => r.id === openId);
  return (open && !scoped.includes(open) ? [...scoped, open] : scoped).filter((r) => !isRejected(r));
}

// How many open SOS calls are outside the picked barangay, so hidden by it: the one thing narrowing must never hide
// quietly. `scoped` is inBarangay's answer for `all`; with no barangay picked it is `all` and this is 0.
export const sosElsewhere = (all: Report[], scoped: Report[]): number => all.filter(isSosActive).length - scoped.filter(isSosActive).length;

export type Tally = {
  unresolved: number; // tickets still to do (not fixed, not rejected)
  urgent: number; // of those, the Critical and High ones
  sos: number; // SOS calls still open
  total: number; // every ticket there, whatever its status
};

const empty = (): Tally => ({ unresolved: 0, urgent: 0, sos: 0, total: 0 });

// How many tickets each barangay has, by id. A barangay with none is in the map with zeros. Tickets outside every
// barangay count nowhere.
export function tally(list: readonly Barangay[], reports: readonly Report[]): Map<string, Tally> {
  const counts = new Map(list.map((b) => [b.id, empty()]));
  for (const r of reports) {
    const t = counts.get(barangayAt(list, r.lng, r.lat)?.id ?? "");
    if (!t) continue;
    t.total++;
    if (isUnresolved(r)) t.unresolved++;
    if (isUrgent(r)) t.urgent++;
    if (isSosActive(r)) t.sos++;
  }
  return counts;
}

export type SortBy = "name" | "busiest";

// The list in the order asked: A to Z, or the barangays with the most unresolved tickets first (SOS counts before it,
// then urgent ones, A to Z among equals).
export function sortBarangays(list: readonly Barangay[], by: SortBy, counts: ReadonlyMap<string, Tally>): Barangay[] {
  if (by === "name") return [...list];
  const t = (b: Barangay) => counts.get(b.id) ?? empty();
  return [...list].sort(
    (a, b) =>
      t(b).sos - t(a).sos ||
      t(b).unresolved - t(a).unresolved ||
      t(b).urgent - t(a).urgent ||
      a.name.localeCompare(b.name, "en"),
  );
}
