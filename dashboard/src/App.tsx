import { useCallback, useEffect, useRef, useState } from "react";
import MapCanvas, { type MapHandle } from "./map/MapCanvas";
import Legend from "./panels/Legend";
import QueuePanel from "./features/queue/QueuePanel";
import { useTickets } from "./features/queue/useTickets";
import { isUnresolved } from "./features/queue/tickets";
import { ENV } from "./config/env";
import { REFRESH_MS } from "./layers/congestion";
import type { Report } from "./types/api";

const clock = (d: Date) => d.toLocaleTimeString([], { hour12: false });
const PHONE = "(max-width: 700px)"; // the breakpoint in panels.css

export default function App() {
  const [congestionOn, setCongestionOn] = useState(true);
  const [stamp, setStamp] = useState(() => Date.now());
  const [now, setNow] = useState(() => new Date());
  // Starts closed on every load, nothing is remembered.
  const [navOpen, setNavOpen] = useState(false);
  // Open on desktop; folded on phones so it does not sit over the map.
  const [panelOpen, setPanelOpen] = useState(() => !matchMedia(PHONE).matches);
  // The fix-it queue is this dashboard's main job: open on desktop. On phones it is one tap away
  // on the HUD's Tickets button, so the sheet doesn't cover the map on load.
  const [queueOpen, setQueueOpen] = useState(() => !matchMedia(PHONE).matches);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const tickets = useTickets();
  const toggle = useRef<HTMLButtonElement>(null);
  const mapView = useRef<MapHandle>(null);
  const unresolved = tickets.reports?.filter(isUnresolved).length ?? 0;
  const urgent = tickets.reports?.some((r) => isUnresolved(r) && r.severity === 3) ?? false;
  const level = !tickets.reports ? "unknown" : urgent ? "urgent" : unresolved ? "waiting" : "clear";

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    if (!congestionOn) return;
    const id = setInterval(() => setStamp(Date.now()), REFRESH_MS);
    return () => clearInterval(id);
  }, [congestionOn]);

  // Esc closes the sidebar first (focus back to its toggle), then the Tickets panel.
  useEffect(() => {
    if (!navOpen && !queueOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (!navOpen) return closeQueue();
      setNavOpen(false);
      toggle.current?.focus();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [navOpen, queueOpen]);

  // A pin click opens its ticket.
  const selectPin = useCallback((id: string) => {
    setSelectedId(id);
    setQueueOpen(true);
  }, []);

  // keepSelection: the pin stays highlighted (phone "Show on map").
  function closeQueue(keepSelection = false) {
    if (document.getElementById("queue")?.contains(document.activeElement)) toggle.current?.focus();
    setQueueOpen(false);
    if (!keepSelection) setSelectedId(null);
  }

  function openView(view: "map" | "tickets") {
    setNavOpen(false);
    if (view === "map") {
      closeQueue();
      toggle.current?.focus();
      return;
    }
    setSelectedId(null); // the list, even if a ticket was open
    setQueueOpen(true);
    document.getElementById("queue-title")?.focus(); // already open: keep focus out of the closing sidebar
  }

  // Phones: the sheet covers the map, so close it first. Desktop: centre the pin left of the panel.
  function showOnMap(r: Report) {
    const phone = matchMedia(PHONE).matches;
    const left = document.getElementById("queue")?.getBoundingClientRect().left ?? innerWidth;
    if (phone) closeQueue(true);
    mapView.current?.show(r.lng, r.lat, phone ? 0 : innerWidth - left);
  }

  return (
    <div className="shell">
      <div className="chrome">
        <header className="cluster">
          <button
            ref={toggle}
            className="nav-toggle"
            aria-label="Navigation menu"
            aria-expanded={navOpen}
            aria-controls="sidebar"
            onClick={() => setNavOpen((open) => !open)}
          >
            <svg viewBox="0 0 20 20" aria-hidden="true">
              <path d="M3 6h14M3 10h14M3 14h14" />
            </svg>
          </button>
          <div className="brand">
            <b>Lakad</b>
            <small>MAKATI · LGU OPS</small>
          </div>
        </header>

        <nav id="sidebar" className={`nav${navOpen ? " open" : ""}`} aria-label="Main" inert={!navOpen}>
          <div className="nav-label">OPERATIONS</div>
          <button
            className={queueOpen ? "nav-link" : "nav-link active"}
            aria-current={queueOpen ? undefined : "page"}
            onClick={() => openView("map")}
          >
            Map
          </button>
          <button
            className={queueOpen ? "nav-link active" : "nav-link"}
            aria-current={queueOpen ? "page" : undefined}
            onClick={() => openView("tickets")}
          >
            Tickets
            {unresolved > 0 && (
              <span className="count">
                {unresolved}
                <span className="sr-only"> unresolved</span>
              </span>
            )}
          </button>
        </nav>
      </div>

      <main className="stage">
        <MapCanvas
          ref={mapView}
          congestionOn={congestionOn}
          stamp={stamp}
          reports={tickets.reports}
          selectedId={selectedId}
          onSelect={selectPin}
        />

        <div className="hud">
          <div className="hud-row">
            {/* Always on screen, so tickets are one tap away even with the panel closed. */}
            <button
              className={`status tickets-btn${tickets.fresh.length ? " fresh" : ""}`}
              aria-expanded={queueOpen}
              aria-controls="queue"
              onClick={() => (queueOpen ? closeQueue() : openView("tickets"))}
            >
              <i className="dot" data-level={level} />
              Tickets
              <b>{tickets.reports ? unresolved : "–"}</b>
              <span className="sr-only">{urgent ? " unresolved, some urgent" : " unresolved"}</span>
            </button>
            <div role="status">
              {!tickets.online && (
                <div className="status offline">
                  <i className="dot" data-status="open" />
                  API offline
                </div>
              )}
            </div>
            <div className="status live">
              <i className="dot" />
              <span>Live · {clock(now)}</span>
              <span className="refreshed">refreshed {clock(new Date(stamp))}</span>
            </div>
          </div>

          <details
            className="panel side"
            open={panelOpen}
            onToggle={(e) => setPanelOpen(e.currentTarget.open)}
          >
            <summary className="panel-title">Traffic flow</summary>
            <div className="src">Source · TomTom traffic</div>

            <label className="switch">
              <input
                type="checkbox"
                checked={congestionOn}
                onChange={(e) => setCongestionOn(e.target.checked)}
              />
              <span>Congestion layer</span>
              <span className={`chip ${congestionOn ? "on" : ""}`}>{congestionOn ? "On" : "Off"}</span>
            </label>

            <dl className="readout">
              <dt>Updated</dt>
              <dd>{clock(new Date(stamp))}</dd>
              <dt>Refresh</dt>
              <dd>every {REFRESH_MS / 1000}s</dd>
            </dl>

            <button className="btn" onClick={() => setStamp(Date.now())}>
              Refresh now
            </button>

            {!ENV.tomtomKey && (
              <p className="warn">No TomTom key. Set VITE_TOMTOM_API_KEY in .env.local.</p>
            )}
          </details>

          {queueOpen && (
            <QueuePanel
              reports={tickets.reports}
              online={tickets.online}
              fresh={tickets.fresh}
              now={now.getTime()}
              selectedId={selectedId}
              onSelect={setSelectedId}
              onClose={() => closeQueue()}
              onStatus={tickets.changeStatus}
              onShowOnMap={showOnMap}
            />
          )}
        </div>

        <Legend />

        <div className="toast" role="status">
          {tickets.toast && (
            <span key={tickets.toast.id}>
              <i className="dot" data-status="open" />
              {tickets.toast.text}
            </span>
          )}
        </div>
      </main>
    </div>
  );
}
