// Insights: backlog funnel, what is breaking, aging, throughput, hotspots, from the polled reports.
// Docked on the right: the map keeps the other 70% of the screen (phones: a full sheet over the map).
import { useMemo } from "react";
import ResizeGrip from "../../panels/ResizeGrip";
import type { Report } from "../../types/api";
import { CATEGORY_LABEL, STATUS_LABEL, timeAgo } from "../queue/tickets";
import { duration, summarize } from "./metrics";

type Props = {
  reports: Report[] | null; // null until the API first answers
  online: boolean;
  now: number;
  onClose: () => void;
  onShow: (spot: { lat: number; lng: number }) => void; // fly the map to a hotspot
};

const Icon = ({ d }: { d: string }) => (
  <svg viewBox="0 0 20 20" aria-hidden="true">
    <path d={d} />
  </svg>
);

const SEV_COLOR = { 1: "var(--faint)", 2: "var(--warn)", 3: "var(--danger)" } as const;

// Older is worse: calm for under a day, red past a week.
const AGE_COLOR: Record<string, string> = { "< 1 d": "var(--ok)", "1-3 d": "var(--accent)", "3-7 d": "var(--warn)", "> 7 d": "var(--danger)" };

type Row = { label: string; value: number; color?: string; status?: string };

// One labelled bar per row, scaled to the largest value.
function Bars({ rows, unit }: { rows: Row[]; unit?: string }) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  return (
    <ul className="bars">
      {rows.map((r) => (
        <li key={r.label} data-status={r.status} style={r.color ? ({ "--c": r.color } as React.CSSProperties) : undefined}>
          <span>{r.label}</span>
          <i style={{ width: `${(r.value / max) * 100}%` }} aria-hidden="true" />
          <b>
            {r.value}
            {unit && <span className="sr-only"> {unit}</span>}
          </b>
        </li>
      ))}
    </ul>
  );
}

export default function AnalyticsPanel({ reports, online, now, onClose, onShow }: Props) {
  // Re-derived on each poll and each minute, not each second of the HUD clock.
  const minute = Math.floor(now / 60_000);
  const s = useMemo(() => reports && summarize(reports, minute * 60_000), [reports, minute]);
  const peak = s ? Math.max(1, ...s.throughput.map((d) => Math.max(d.created, d.fixed))) : 1;

  return (
    <section id="insights" className="insights" aria-labelledby="insights-title">
      <ResizeGrip />
      <header className="queue-head">
        <h2 id="insights-title" className="panel-title" tabIndex={-1}>
          Insights
        </h2>
        {s && <span className="src">{s.total} reports</span>}
        <button className="icon-btn close" aria-label="Close insights" onClick={onClose}>
          <Icon d="m5.5 5.5 9 9m0-9-9 9" />
        </button>
      </header>

      <div className="queue-list">
        {!s ? (
          <p className="empty">{online ? "Loading reports…" : "Can't reach the Lakad API. Retrying."}</p>
        ) : !s.total ? (
          <p className="empty">No reports yet. Insights fill in as hazards come in from the Lakad app.</p>
        ) : (
          <>
            <dl className="tiles">
              <div data-alert={s.urgent ? "" : undefined}>
                <dt>Unresolved</dt>
                <dd>{s.unresolved}</dd>
                <small>{s.urgent ? `${s.urgent} urgent` : "none urgent"}</small>
              </div>
              <div>
                <dt>Median fix time</dt>
                <dd>{s.medianResponseMs === null ? "–" : duration(s.medianResponseMs)}</dd>
                <small>{s.funnel[3].count} fixed so far</small>
              </div>
              <div>
                <dt>Oldest open</dt>
                <dd>{s.aging.oldest ? timeAgo(s.aging.oldest.created_at, now).replace(" ago", "") : "–"}</dd>
                <small>{s.aging.oldest ? CATEGORY_LABEL[s.aging.oldest.category] : "all clear"}</small>
              </div>
            </dl>

            <div className="cards">
              <section className="card">
                <h3 className="sec">Backlog</h3>
                <div className="src">Every report, by workflow step</div>
                <Bars rows={s.funnel.map((f) => ({ label: STATUS_LABEL[f.status], value: f.count, status: f.status }))} unit="reports" />
              </section>

              <section className="card">
                <h3 className="sec">What is breaking</h3>
                <div className="src">Unresolved, colour by severity</div>
                <Bars rows={s.byCategory.map((c) => ({ label: c.label, value: c.unresolved, color: SEV_COLOR[c.severity] }))} unit="unresolved" />
              </section>

              <section className="card">
                <h3 className="sec">How long they have waited</h3>
                <div className="src">Unresolved, by age</div>
                <Bars rows={s.aging.buckets.map((b) => ({ label: b.label, value: b.count, color: AGE_COLOR[b.label] }))} unit="unresolved" />
              </section>

              <section className="card">
                <h3 className="sec">Last 7 days</h3>
                <div className="src">
                  <span className="key" data-key="created" />
                  Reported <span className="key" data-key="fixed" />
                  Fixed
                </div>
                <ol className="days">
                  {s.throughput.map((d, n) => (
                    <li key={n}>
                      <span className="pair">
                        <i data-key="created" style={{ height: `${(d.created / peak) * 100}%` }}>
                          {d.created > 0 && <em>{d.created}</em>}
                        </i>
                        <i data-key="fixed" style={{ height: `${(d.fixed / peak) * 100}%` }}>
                          {d.fixed > 0 && <em>{d.fixed}</em>}
                        </i>
                      </span>
                      <small>{n === s.throughput.length - 1 ? "today" : `-${s.throughput.length - 1 - n}d`}</small>
                      <span className="sr-only">
                        {d.created} reported, {d.fixed} fixed
                      </span>
                    </li>
                  ))}
                </ol>
              </section>

              <section className="card">
                <h3 className="sec">Hotspots</h3>
                <div className="src">Where unresolved reports pile up (within about 220 m)</div>
                {s.hotspots.length ? (
                  <ol className="spots">
                    {s.hotspots.map((h) => (
                      <li key={h.ids[0]}>
                        <button className="spot" onClick={() => onShow(h)}>
                          <b>{h.count}</b>
                          <span>
                            unresolved near {h.lat.toFixed(4)}, {h.lng.toFixed(4)}
                          </span>
                          <small>Show on map</small>
                        </button>
                      </li>
                    ))}
                  </ol>
                ) : (
                  <p className="empty">Nothing unresolved.</p>
                )}
              </section>

              <section className="card pending">
                <h3 className="sec">Walking routes</h3>
                <div className="src">Not recorded yet: the server answers GET /route/walk but does not log the routes people take</div>
                <ul>
                  <li>Mode share: Fastest, Walkable, Accessible</li>
                  <li>Detour accepted to take the Walkable route</li>
                  <li>Meters of road without a sidewalk avoided</li>
                  <li>Open hazards steered around, to rank the fix-it queue</li>
                </ul>
              </section>
            </div>
          </>
        )}
      </div>
    </section>
  );
}
