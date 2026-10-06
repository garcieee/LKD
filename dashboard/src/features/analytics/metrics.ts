// Dashboard analytics from the polled report list. No React or mapbox-gl, so `node --test` runs it (metrics.test.ts).
import type { Category, Report, Status } from "../../types/api.ts";
import { CATEGORY_LABEL, STATUSES, isRejected, isUnresolved } from "../queue/tickets.ts";

const DAY = 24 * 60 * 60_000;
const ms = (iso: string) => Date.parse(iso);

// Backlog funnel: how many reports sit at each workflow status, in stepper order.
export function funnel(reports: Report[]): { status: Status; count: number }[] {
  return STATUSES.map((status) => ({ status, count: reports.filter((r) => r.status === status).length }));
}

// What is breaking. Severity comes from the category (server/app/services/priority.py), so it rides along
// instead of being a second split. Most unresolved first.
export function byCategory(reports: Report[]) {
  const rows = new Map<Category, { category: Category; label: string; severity: Report["severity"]; total: number; unresolved: number }>();
  for (const r of reports) {
    const row = rows.get(r.category) ?? { category: r.category, label: CATEGORY_LABEL[r.category], severity: r.severity, total: 0, unresolved: 0 };
    row.total++;
    if (isUnresolved(r)) row.unresolved++;
    rows.set(r.category, row);
  }
  return [...rows.values()].sort((a, b) => b.unresolved - a.unresolved || b.total - a.total);
}

export const AGE_BUCKETS = ["< 1 d", "1-3 d", "3-7 d", "> 7 d"] as const;

// Unresolved reports by age since created_at, plus the oldest one. A server clock ahead of ours counts as new.
export function aging(reports: Report[], now: number) {
  const counts = [0, 0, 0, 0];
  let oldest: Report | null = null;
  for (const r of reports.filter(isUnresolved)) {
    const days = (now - ms(r.created_at)) / DAY;
    counts[days < 1 ? 0 : days < 3 ? 1 : days < 7 ? 2 : 3]++;
    if (!oldest || ms(r.created_at) < ms(oldest.created_at)) oldest = r;
  }
  return { buckets: AGE_BUCKETS.map((label, i) => ({ label, count: counts[i] })), oldest };
}

// Reports created vs fixed in each of the last `days` rolling 24 h windows, oldest window first.
// Fixed is dated by updated_at (there is no fixed_at yet), so a status touched after fixing shifts it.
export function throughput(reports: Report[], now: number, days = 7) {
  const out = Array.from({ length: days }, () => ({ created: 0, fixed: 0 }));
  const slot = (iso: string) => days - 1 - Math.floor((now - ms(iso)) / DAY); // -ve = older, >= days = in the future
  for (const r of reports) {
    const c = slot(r.created_at);
    if (c >= 0 && c < days) out[c].created++;
    if (r.status === "fixed") {
      const f = slot(r.updated_at);
      if (f >= 0 && f < days) out[f].fixed++;
    }
  }
  return out;
}

// Median created_at -> updated_at of fixed reports, in ms. null until something is fixed.
export function medianResponseMs(reports: Report[]): number | null {
  const t = reports
    .filter((r) => r.status === "fixed")
    .map((r) => ms(r.updated_at) - ms(r.created_at))
    .filter((d) => d >= 0)
    .sort((a, b) => a - b);
  if (!t.length) return null;
  const mid = t.length >> 1;
  return t.length % 2 ? t[mid] : (t[mid - 1] + t[mid]) / 2;
}

// Where unresolved reports pile up: a fixed grid (0.002 deg is about 220 m in Makati), busiest cells first,
// ties by total severity. ponytail: a cluster straddling a cell edge splits in two; DBSCAN if that shows up.
export function hotspots(reports: Report[], limit = 5, cell = 0.002) {
  const cells = new Map<string, { lat: number; lng: number; count: number; severity: number; ids: string[] }>();
  for (const r of reports.filter(isUnresolved)) {
    const key = `${Math.floor(r.lat / cell)},${Math.floor(r.lng / cell)}`;
    const c = cells.get(key) ?? { lat: 0, lng: 0, count: 0, severity: 0, ids: [] };
    c.lat += r.lat; // summed now, averaged below
    c.lng += r.lng;
    c.count++;
    c.severity += r.severity;
    c.ids.push(r.id);
    cells.set(key, c);
  }
  return [...cells.values()]
    .map((c) => ({ ...c, lat: c.lat / c.count, lng: c.lng / c.count }))
    .sort((a, b) => b.count - a.count || b.severity - a.severity)
    .slice(0, limit);
}

// "40 min", "5.5 h", "3 d". For the median fix time tile.
export function duration(msec: number): string {
  const min = msec / 60_000;
  if (min < 60) return `${Math.max(1, Math.round(min))} min`;
  if (min < 48 * 60) return `${Math.round(min / 6) / 10} h`;
  return `${Math.round(min / 144) / 10} d`;
}

// Everything the Insights page shows, from one report list and one clock reading. Rejected tickets were judged
// not real: they count for nothing here.
export function summarize(all: Report[], now: number) {
  const reports = all.filter((r) => !isRejected(r));
  return {
    total: reports.length,
    unresolved: reports.filter(isUnresolved).length,
    urgent: reports.filter((r) => isUnresolved(r) && r.severity === 3).length,
    funnel: funnel(reports),
    byCategory: byCategory(reports),
    aging: aging(reports, now),
    throughput: throughput(reports, now),
    medianResponseMs: medianResponseMs(reports),
    hotspots: hotspots(reports),
  };
}
