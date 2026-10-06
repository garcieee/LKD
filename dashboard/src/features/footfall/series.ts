// Pure helpers for the forecast chart: which slice of the series to show, and where to draw it.
// Kept apart from the component so node --test can check them.
import type { SeriesPoint } from "../../types/api.ts";
import { DAY_LABEL, manilaNow } from "../../layers/footfall.ts";

export type Win = { id: string; label: string; past: number; future: number }; // hours either side of now
export const WINDOWS: Win[] = [
  { id: "day", label: "Day", past: 12, future: 24 },
  { id: "week", label: "Week", past: 96, future: 72 },
  { id: "all", label: "10 days", past: 168, future: 72 },
];

// The points inside the window, and where "now" (the last history point) landed in them.
export function slice(points: SeriesPoint[], w: Win): { pts: SeriesPoint[]; nowIdx: number } {
  let last = -1;
  points.forEach((p, i) => {
    if (p.kind === "history") last = i;
  });
  if (last < 0) return { pts: [], nowIdx: 0 };
  const start = Math.max(0, last - w.past);
  return { pts: points.slice(start, Math.min(points.length, last + 1 + w.future)), nowIdx: last - start };
}

// The chart's top, snapped so the axis reads cleanly: the zone's own scale, since a quiet district would be a flat line on 0-100.
export function niceMax(pts: SeriesPoint[]): number {
  const top = Math.max(1, ...pts.map((p) => p.upper ?? p.index)) * 1.05;
  return [5, 10, 20, 25, 50, 100].find((n) => n >= top) ?? 100;
}

export type Box = { w: number; h: number; l: number; r: number; t: number; b: number };

export function geometry(pts: SeriesPoint[], nowIdx: number, max: number, box: Box) {
  const n = Math.max(1, pts.length - 1);
  const x = (i: number) => box.l + (i / n) * (box.w - box.l - box.r);
  const y = (v: number) => box.t + (1 - Math.min(v, max) / max) * (box.h - box.t - box.b);
  const f = (v: number) => v.toFixed(1);
  const line = (from: number, to: number) =>
    pts
      .slice(from, to + 1)
      .map((p, k) => `${k ? "L" : "M"}${f(x(from + k))} ${f(y(p.index))}`)
      .join(" ");
  const base = y(0);
  const history = line(0, nowIdx);
  // The forecast starts at the last history point so the two lines meet.
  const forecast = nowIdx < pts.length - 1 ? line(nowIdx, pts.length - 1) : "";
  const ahead = pts.slice(nowIdx);
  const band =
    ahead.length > 1
      ? "M" +
        ahead.map((p, k) => `${f(x(nowIdx + k))} ${f(y(k ? (p.upper ?? p.index) : p.index))}`).join(" L") +
        " L" +
        [...ahead]
          .reverse()
          .map((p, k, a) => `${f(x(pts.length - 1 - k))} ${f(y(k === a.length - 1 ? p.index : (p.lower ?? p.index)))}`)
          .join(" L") +
        " Z"
      : "";
  const area = `${history} L${f(x(nowIdx))} ${f(base)} L${f(x(0))} ${f(base)} Z`;
  return { x, y, history, forecast, band, area };
}

// "Wed 18:00" in Manila time, whatever the browser's zone.
export function label(iso: string): string {
  const { day, hour } = manilaNow(new Date(iso));
  return `${DAY_LABEL[day]} ${String(hour).padStart(2, "0")}:00`;
}

// Axis ticks: every 6 h on a short window, midnights (named by weekday) on a long one.
export function ticks(pts: SeriesPoint[]): { i: number; text: string; major: boolean }[] {
  const short = pts.length <= 40;
  const out: { i: number; text: string; major: boolean }[] = [];
  pts.forEach((p, i) => {
    const { day, hour } = manilaNow(new Date(p.t));
    if (short ? hour % 6 === 0 : hour === 0) {
      out.push({ i, text: short ? (hour === 0 ? DAY_LABEL[day] : `${String(hour).padStart(2, "0")}:00`) : DAY_LABEL[day], major: hour === 0 });
    }
  });
  return out;
}

// The busiest forecast hour (the first, on a tie).
export function nextPeak(pts: SeriesPoint[], nowIdx: number): SeriesPoint | null {
  let best: SeriesPoint | null = null;
  for (const p of pts.slice(nowIdx + 1)) if (!best || p.index > best.index) best = p;
  return best;
}
