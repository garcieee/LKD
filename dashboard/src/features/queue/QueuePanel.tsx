// Ranked fix-it list: unresolved first, an open SOS above everything (unsorted ones on top), then the ticket engine's
// priority, then most severe, then oldest. A row opens the ticket in place (DetailPanel); back returns to the list. Floats over the map, never resizes it.
import { useEffect, useRef, useState } from "react";
import { photoUrl } from "../../api/client";
import { ENV } from "../../config/env";
import type { Report, SosKind, Status } from "../../types/api";
import DetailPanel, { BandChip, Severity } from "../../panels/DetailPanel";
import { STATUS_LABEL, isRejected, isSos, isSosActive, isUnresolved, needsReview, rank, sightings, sightingsLabel, ticketLabel, timeAgo } from "./tickets";

type Props = {
  reports: Report[] | null; // null until the API first answers
  online: boolean;
  fresh: string[]; // ids that just arrived, highlighted for a moment
  now: number;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  onClose: () => void;
  onStatus: (id: string, status: Status) => Promise<string | null>;
  onKind: (id: string, kind: SosKind) => Promise<string | null>;
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
  onKind,
  onShowOnMap,
}: Props) {
  const [showFixed, setShowFixed] = useState(false);
  const [showRejected, setShowRejected] = useState(false);
  const panel = useRef<HTMLElement>(null);
  const last = useRef<string | null>(null);
  const all = reports ?? [];
  const selected = all.find((r) => r.id === selectedId);
  const open = all.filter(isUnresolved).length;
  const review = all.filter(needsReview).length;
  const fixed = all.filter((r) => r.status === "fixed").length;
  const rejected = all.filter(isRejected).length;
  const count = sightings(all);
  const rows = rank(all).filter((r) => isUnresolved(r) || (r.status === "fixed" ? showFixed : showRejected));

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
        {reports && (
          <span className="src">
            {open} unresolved{review ? ` · ${review} to review` : ""}
          </span>
        )}
        <button className="icon-btn close" aria-label="Close tickets" onClick={onClose}>
          <Icon d="m5.5 5.5 9 9m0-9-9 9" />
        </button>
      </header>

      {selected ? (
        <DetailPanel
          key={selected.id}
          report={selected}
          sightings={count}
          now={now}
          onStatus={onStatus}
          onKind={onKind}
          onShowOnMap={onShowOnMap}
        />
      ) : (
        <div className="queue-list">
          <div className="src">Ranked: SOS first (unsorted on top), then by priority, severity, oldest</div>
          <label className="switch">
            <input type="checkbox" checked={showFixed} onChange={(e) => setShowFixed(e.target.checked)} />
            <span>Show fixed</span>
            <span className="chip">{fixed}</span>
          </label>
          <label className="switch">
            <input type="checkbox" checked={showRejected} onChange={(e) => setShowRejected(e.target.checked)} />
            <span>Show rejected</span>
            <span className="chip">{rejected}</span>
          </label>
          {rows.length ? (
            <ol className="tickets">
              {rows.map((r) => (
                <li key={r.id}>
                  <button
                    className={`ticket${fresh.includes(r.id) ? " fresh" : ""}${isSosActive(r) ? " sos" : ""}${isRejected(r) ? " rejected" : ""}`}
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
                    <b>{ticketLabel(r)}</b>
                    <span className="badge" data-status={r.status}>
                      {needsReview(r) ? "To review" : STATUS_LABEL[r.status]}
                    </span>
                    <small>
                      <Severity level={r.severity} />·<span>{timeAgo(r.created_at, now)}</span>
                      <BandChip report={r} />
                      {sightingsLabel(r, count)}
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
