// Ranked fix-it list: unresolved first, an open SOS above everything (unsorted ones on top), then the ticket engine's
// priority, then most severe, then oldest. A row opens the ticket in place (DetailPanel); back returns to the list. Floats over the map, never resizes it.
import { useEffect, useRef, useState } from "react";
import { photoUrl } from "../../api/client";
import { ENV } from "../../config/env";
import type { Category, Report, SosKind, Status } from "../../types/api";
import DetailPanel, { Urgency } from "../../panels/DetailPanel";
import { CATEGORY_LABEL, STATUS_LABEL, isRejected, isSos, isSosActive, isUnresolved, needsReview, rank, sightings, sightingsLabel, ticketCode, ticketLabel, timeAgo } from "./tickets";
import { DEFAULT_FILTERS, STATUS_FILTERS, applyFilters, isFiltered, isSearching, statusCounts, type Filters } from "./filters";

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
  onAssign: (id: string, handler: string, status?: Status) => Promise<string | null>;
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
  onAssign,
  onShowOnMap,
}: Props) {
  // What the list shows: by status, by category, or a search by ticket ID. Kept while a ticket is open and back.
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const panel = useRef<HTMLElement>(null);
  const last = useRef<string | null>(null);
  const all = reports ?? [];
  const selected = all.find((r) => r.id === selectedId);
  const open = all.filter(isUnresolved).length;
  const review = all.filter(needsReview).length;
  const count = sightings(all);
  const rows = applyFilters(rank(all), filters);
  const counts = statusCounts(all, filters.category);
  const searching = isSearching(filters);

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
        ? isFiltered(filters)
          ? searching
            ? "No ticket has an ID starting with that."
            : "No tickets match these filters."
          : "Nothing left to fix."
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
          onAssign={onAssign}
          onShowOnMap={onShowOnMap}
        />
      ) : (
        <div className="queue-list">
          <div className="src">Ranked: SOS first (unsorted on top), then by priority, severity, oldest</div>
          <div className="filters">
            <input
              type="search"
              aria-label="Search tickets by ID"
              placeholder="Search by ticket ID, e.g. LKD-3F2A9C"
              value={filters.query}
              maxLength={40}
              spellCheck={false}
              autoComplete="off"
              onChange={(e) => setFilters({ ...filters, query: e.target.value })}
            />
            {/* A search looks at every ticket, so while one is typed no status chip is pressed. Picking a chip or a
                category leaves the search. */}
            <div className="fchips" role="group" aria-label="Show tickets">
              {STATUS_FILTERS.map((f) => (
                <button
                  key={f.id}
                  className="fchip"
                  title={f.hint}
                  aria-pressed={!searching && filters.status === f.id}
                  onClick={() => setFilters({ ...filters, status: f.id, query: "" })}
                >
                  {f.label}
                  <b>{counts[f.id]}</b>
                </button>
              ))}
            </div>
            <select
              className="filter-cat"
              aria-label="Category"
              value={filters.category}
              onChange={(e) => setFilters({ ...filters, category: e.target.value as Category | "all", query: "" })}
            >
              <option value="all">All categories</option>
              {(Object.keys(CATEGORY_LABEL) as Category[]).map((c) => (
                <option key={c} value={c}>
                  {CATEGORY_LABEL[c]}
                </option>
              ))}
            </select>
            <div className="filter-status" role="status">
              <span>
                {searching ? `Searching all tickets: ${rows.length} found` : `Showing ${rows.length} of ${all.length} tickets`}
              </span>
              {isFiltered(filters) && (
                <button className="linklike" onClick={() => setFilters(DEFAULT_FILTERS)}>
                  Clear filters
                </button>
              )}
            </div>
          </div>
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
                    <b>
                      {ticketLabel(r)}
                      <span className="ago"> · {timeAgo(r.created_at, now)}</span>
                    </b>
                    <span className="badge" data-status={r.status}>
                      {needsReview(r) ? "To review" : STATUS_LABEL[r.status]}
                    </span>
                    <small>
                      <span className="tid">{ticketCode(r)}</span>·<Urgency report={r} />
                      {sightingsLabel(r, count)}
                      {r.handler && (r.status === "assigned" || r.status === "fixed") && (
                        <>
                          ·<span className="row-handler">{r.handler}</span>
                        </>
                      )}
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
