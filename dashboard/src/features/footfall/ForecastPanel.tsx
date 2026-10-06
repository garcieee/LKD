// Past and future foot traffic for a zone, docked beside the map. Drag along the chart (or use the arrow keys) and the map's
// heat layer shows that moment; drag back to "Now" to return to live. The past is simulated and the future is a
// seasonal forecast of it: the panel says so, because nothing here is a count.
import { useEffect, useRef, useState } from "react";
import ResizeGrip from "../../panels/ResizeGrip";
import type { FootfallDistrict } from "../../types/api";
import { useSeries } from "./useSeries";
import { WINDOWS, geometry, label, nextPeak, niceMax, slice, ticks, type Box } from "./series";

type Props = {
  districts: FootfallDistrict[];
  hourKey: number; // changes each hour: refetch so "now" stays right
  cursor: Date | null; // null: live
  onCursor: (at: Date | null) => void;
  onClose: () => void;
};

// The chart is drawn in units that are px at the dock's narrowest width (340), so text stays its real size there;
// BOX.w is replaced with the real width as the dock grows.
const BASE: Box = { w: 320, h: 200, l: 26, r: 6, t: 14, b: 22 };

const Icon = ({ d }: { d: string }) => (
  <svg viewBox="0 0 20 20" aria-hidden="true">
    <path d={d} />
  </svg>
);

export default function ForecastPanel({ districts, hourKey, cursor, onCursor, onClose }: Props) {
  const [zone, setZone] = useState("all");
  const [winId, setWinId] = useState("week");
  const { data, error } = useSeries(true, zone, hourKey);
  const svg = useRef<SVGSVGElement>(null);
  const panel = useRef<HTMLElement>(null);

  // Dragging the dock wider does two things: text and controls grow a little (--k, a zoom on the body), and the
  // chart gets more width to draw in, at the same height, so it stretches sideways instead of just growing taller.
  const [dockW, setDockW] = useState(340);
  useEffect(() => {
    const el = panel.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setDockW(el.offsetWidth));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const k = Math.min(1.8, 1 + Math.max(0, dockW / 340 - 1) / 2);
  const BOX = { ...BASE, w: Math.max(300, Math.round(dockW / k - 28)) }; // 28: the body's side padding

  const win = WINDOWS.find((w) => w.id === winId) ?? WINDOWS[1];
  const { pts, nowIdx } = data ? slice(data.points, win) : { pts: [], nowIdx: 0 };
  const max = niceMax(pts);
  const g = pts.length ? geometry(pts, nowIdx, max, BOX) : null;

  // Where the cursor sits in this window; live (or a time the window no longer holds) sits on "now".
  const found = cursor ? pts.findIndex((p) => new Date(p.t).getTime() === cursor.getTime()) : -1;
  const at = found >= 0 ? found : nowIdx;

  // A window or zone change can leave the cursor outside the chart: go back to live rather than point at nothing.
  useEffect(() => {
    if (cursor && pts.length && found < 0) onCursor(null);
  }, [cursor, pts.length, found, onCursor]);

  const select = (i: number) => {
    const k = Math.min(pts.length - 1, Math.max(0, i));
    onCursor(k === nowIdx ? null : new Date(pts[k].t));
  };
  const fromPointer = (e: React.PointerEvent) => {
    const r = svg.current!.getBoundingClientRect();
    const x = ((e.clientX - r.left) / r.width) * BOX.w;
    select(Math.round(((x - BOX.l) / (BOX.w - BOX.l - BOX.r)) * (pts.length - 1)));
  };

  const cur = pts[at];
  const peak = pts.length ? nextPeak(pts, nowIdx) : null;
  const nowPt = pts[nowIdx];
  const zoneLabel = zone === "all" ? "All of Makati" : (districts.find((d) => d.id === zone)?.name ?? zone).replace(/ \(.*\)$/, "");

  return (
    <section id="forecast" className="insights forecast" aria-labelledby="forecast-title" ref={panel} style={{ "--k": k } as React.CSSProperties}>
      <ResizeGrip />
      <header className="queue-head">
        <h2 id="forecast-title" className="panel-title" tabIndex={-1}>
          Forecast
        </h2>
        <span className="src">Foot traffic · predicted</span>
        <button className="icon-btn close" aria-label="Close forecast" onClick={onClose}>
          <Icon d="m5.5 5.5 9 9m0-9-9 9" />
        </button>
      </header>

      <div className="queue-list">
        <div className="fc-controls">
          <label className="fc-zone">
            <span className="sr-only">Zone</span>
            <select value={zone} onChange={(e) => setZone(e.target.value)}>
              <option value="all">All of Makati</option>
              {districts.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name.replace(/ \(.*\)$/, "")}
                </option>
              ))}
            </select>
          </label>
          <div className="seg" role="group" aria-label="Time range">
            {WINDOWS.map((w) => (
              <button key={w.id} aria-pressed={w.id === winId} onClick={() => setWinId(w.id)}>
                {w.label}
              </button>
            ))}
          </div>
        </div>

        {!data || !g || !cur ? (
          <p className="empty">{error ?? "Loading the forecast…"}</p>
        ) : (
          <>
            <dl className="tiles fc-tiles">
              <div>
                <dt>Now</dt>
                <dd>{Math.round(nowPt.index)}</dd>
                <small>{label(nowPt.t)}</small>
              </div>
              <div>
                <dt>Next peak</dt>
                <dd>{peak ? Math.round(peak.index) : "–"}</dd>
                <small>{peak ? label(peak.t) : "beyond this range"}</small>
              </div>
              <div title="Forecasting the last simulated week from the three before it. It scores the forecast against simulated history, not real counts.">
                <dt>Typical miss</dt>
                <dd>±{Math.round(data.backtest_smape_pct)}%</dd>
                <small>vs simulated</small>
              </div>
            </dl>

            <div className="fc-read" role="status" aria-live="polite">
              <b>{label(cur.t)}</b>
              <span className="fc-kind" data-kind={at === nowIdx ? "live" : cur.kind}>
                {at === nowIdx ? "Live" : cur.kind === "history" ? "Past" : "Forecast"}
              </span>
              <span className="fc-val">
                {Math.round(cur.index)}
                {cur.kind === "forecast" && cur.lower != null && cur.upper != null && (
                  <small>
                    {" "}
                    ({Math.round(cur.lower)}–{Math.round(cur.upper)})
                  </small>
                )}
              </span>
              {cursor && (
                <button className="fc-live" onClick={() => onCursor(null)}>
                  Back to live
                </button>
              )}
            </div>

            <svg
              ref={svg}
              className="fc-chart"
              viewBox={`0 0 ${BOX.w} ${BOX.h}`}
              role="slider"
              tabIndex={0}
              aria-valuemin={0}
              aria-valuemax={pts.length - 1}
              aria-valuenow={at}
              aria-valuetext={`${label(cur.t)}, ${cur.kind === "history" ? "past" : "forecast"}, ${Math.round(cur.index)}`}
              aria-label={`${zoneLabel}: foot traffic index, past and forecast. Now ${Math.round(nowPt.index)}${peak ? `, next peak ${Math.round(peak.index)} at ${label(peak.t)}` : ""}.`}
              onPointerDown={(e) => {
                e.currentTarget.setPointerCapture(e.pointerId);
                fromPointer(e);
              }}
              onPointerMove={(e) => e.buttons && fromPointer(e)}
              onKeyDown={(e) => {
                const step = { ArrowLeft: -1, ArrowDown: -1, ArrowRight: 1, ArrowUp: 1, PageDown: -6, PageUp: 6 }[e.key];
                if (step) {
                  e.preventDefault();
                  select(at + step);
                } else if (e.key === "Home" || e.key === "End") {
                  e.preventDefault();
                  select(e.key === "Home" ? 0 : pts.length - 1);
                }
              }}
            >
              {[0, 0.5, 1].map((f) => (
                <g key={f}>
                  <line className="fc-grid" x1={BOX.l} x2={BOX.w - BOX.r} y1={g.y(max * f)} y2={g.y(max * f)} />
                  <text className="fc-axis" x={BOX.l - 6} y={g.y(max * f) + 3} textAnchor="end">
                    {Math.round(max * f)}
                  </text>
                </g>
              ))}
              {ticks(pts).map((t) => (
                <g key={t.i}>
                  {t.major && <line className="fc-day" x1={g.x(t.i)} x2={g.x(t.i)} y1={BOX.t} y2={BOX.h - BOX.b} />}
                  <text className="fc-axis" x={g.x(t.i)} y={BOX.h - 6} textAnchor="middle">
                    {t.text}
                  </text>
                </g>
              ))}
              <path className="fc-area" d={g.area} />
              {g.band && <path className="fc-band" d={g.band} />}
              <path className="fc-line history" d={g.history} />
              {g.forecast && <path className="fc-line forecast" d={g.forecast} />}
              <line className="fc-now" x1={g.x(nowIdx)} x2={g.x(nowIdx)} y1={BOX.t} y2={BOX.h - BOX.b} />
              <text className="fc-now-label" x={g.x(nowIdx)} y={BOX.t - 2} textAnchor="middle">
                Now
              </text>
              {at !== nowIdx && <line className="fc-cursor" x1={g.x(at)} x2={g.x(at)} y1={BOX.t} y2={BOX.h - BOX.b} />}
              <circle className="fc-dot" data-kind={cur.kind} cx={g.x(at)} cy={g.y(cur.index)} r={4.5} />
            </svg>

            <ul className="fc-key" aria-label="Chart key">
              <li>
                <i data-k="history" /> Past (simulated)
              </li>
              <li>
                <i data-k="forecast" /> Forecast
              </li>
              <li>
                <i data-k="band" /> 80% range
              </li>
            </ul>
            <p className="fc-note">
              Predicted, not measured. The index is relative: 100 is Ayala CBD at its busiest, so {zoneLabel === "All of Makati" ? "the city average" : zoneLabel} reads lower. The
              past is simulated from the model, and the forecast projects its weekly pattern. Both come from research and assumptions, and neither is a head count.
            </p>
          </>
        )}
      </div>
    </section>
  );
}
