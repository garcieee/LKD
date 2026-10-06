// Ranked fix-it list: unresolved first, an open SOS above everything, then most severe, then oldest. A row opens the ticket
// in place (DetailPanel); back returns to the list. Floats over the map, never resizes it.
import { useEffect, useRef, useState } from "react";
import { photoUrl } from "../../api/client";
import { ENV } from "../../config/env";
import type { Report, Status } from "../../types/api";
import DetailPanel, { Severity } from "../../panels/DetailPanel";
import { CATEGORY_LABEL, STATUS_LABEL, isSos, isSosActive, isUnresolved, rank, timeAgo } from "./tickets";

type Props = {
  reports: Report[] | null; // null until the API first answers
  online: boolean;
  fresh: string[]; // ids that just arrived, highlighted for a moment
  now: number;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  onClose: () => void;
  onStatus: (id: string, status: Status) => Promise<string | null>;
  onShowOnMap: (report: Report) => void;
};

const Icon = ({ d }: { d: string }) => (
  <svg viewBox="0 0 20 20" aria-hidden="true">
    <path d={d} />
  </svg>
);

export default function QueuePanel({
  reports,
  online,
  fresh,
  now,
  selectedId,
  onSelect,
  onClose,
  onStatus,
  onShowOnMap,
}: Props) {
  const [showFixed, setShowFixed] = useState(false);
  const panel = useRef<HTMLElement>(null);
  const last = useRef<string | null>(null);
  const all = reports ?? [];
  const selected = all.find((r) => r.id === selectedId);
  const open = all.filter(isUnresolved).length;
  const rows = rank(all).filter((r) => showFixed || isUnresolved(r));

  // Keyboard focus follows the view: into the ticket, then back to its row (or the title).
  useEffect(() => {
    const el = panel.current;
    const row = last.current && el?.querySelector<HTMLElement>(`[data-id="${CSS.escape(last.current)}"]`);
    (selectedId ? el?.querySelector<HTMLElement>(".detail-title") : row || el?.querySelector("h2"))?.focus();
    last.current = selectedId;
  }, [selectedId]);

  const empty =
    reports === null
      ? online
        ? "Loading tickets…"
        : `Can't reach the Lakad API at ${ENV.apiBaseUrl}. Retrying.`
      : all.length
        ? "Nothing left to fix."
        : "No tickets yet. Hazards snapped in the Lakad app show up here within 10 seconds.";

  return (
    <section id="queue" ref={panel} className="panel queue" aria-labelledby="queue-title">
      <header className="queue-head">
        {selected && (
          <button className="icon-btn" aria-label="Back to all tickets" onClick={() => onSelect(null)}>
            <Icon d="M12 4.5 6.5 10l5.5 5.5" />
          </button>
        )}
        <h2 id="queue-title" className="panel-title" tabIndex={-1}>
          Tickets
        </h2>
        {reports && <span className="src">{open} unresolved</span>}
        <button className="icon-btn close" aria-label="Close tickets" onClick={onClose}>
          <Icon d="m5.5 5.5 9 9m0-9-9 9" />
        </button>
      </header>

      {selected ? (
        <DetailPanel
          key={selected.id}
          report={selected}
          now={now}
          onStatus={onStatus}
          onShowOnMap={onShowOnMap}
        />
      ) : (
        <div className="queue-list">
          <div className="src">Ranked: SOS first, then most severe, oldest</div>
          <label className="switch">
            <input type="checkbox" checked={showFixed} onChange={(e) => setShowFixed(e.target.checked)} />
            <span>Show fixed</span>
            <span className="chip">{all.length - open}</span>
          </label>
          {rows.length ? (
            <ol className="tickets">
              {rows.map((r) => (
                <li key={r.id}>
                  <button
                    className={`ticket${fresh.includes(r.id) ? " fresh" : ""}${isSosActive(r) ? " sos" : ""}`}
                    data-id={r.id}
                    onClick={() => onSelect(r.id)}
                  >
                    {/* Decorative: the row's own text names the ticket and its age. An SOS has a video, not a photo. */}
                    {isSos(r) ? (
                      <span className="sos-thumb" aria-hidden="true">
                        SOS
                      </span>
                    ) : (
                      <img src={photoUrl(r.photo_url)} alt="" loading="lazy" />
                    )}
                    <b>{CATEGORY_LABEL[r.category]}</b>
                    <span className="badge" data-status={r.status}>
                      {STATUS_LABEL[r.status]}
                    </span>
                    <small>
                      <Severity level={r.severity} />·<span>{timeAgo(r.created_at, now)}</span>
                    </small>
                  </button>
                </li>
              ))}
            </ol>
          ) : (
            <>
              <p className="empty">{empty}</p>
              {!online && (
                <p className="empty">
                  Start it from the repo: <code>cd server && .venv/bin/uvicorn app.main:app --host 0.0.0.0</code>
                </p>
              )}
            </>
          )}
        </div>
      )}
    </section>
  );
}
