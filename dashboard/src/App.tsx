import { useEffect, useRef, useState } from "react";
import MapCanvas from "./map/MapCanvas";
import Legend from "./panels/Legend";
import { ENV } from "./config/env";
import { REFRESH_MS } from "./layers/congestion";

const clock = (d: Date) => d.toLocaleTimeString([], { hour12: false });

export default function App() {
  const [congestionOn, setCongestionOn] = useState(true);
  const [stamp, setStamp] = useState(() => Date.now());
  const [now, setNow] = useState(() => new Date());
  // Starts closed on every load, nothing is remembered.
  const [navOpen, setNavOpen] = useState(false);
  // Open on desktop; folded on phones so it does not sit over the map.
  const [panelOpen, setPanelOpen] = useState(() => !matchMedia("(max-width: 700px)").matches);
  const toggle = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    if (!congestionOn) return;
    const id = setInterval(() => setStamp(Date.now()), REFRESH_MS);
    return () => clearInterval(id);
  }, [congestionOn]);

  useEffect(() => {
    if (!navOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      setNavOpen(false);
      toggle.current?.focus();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [navOpen]);

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
          <div className="nav-link active" aria-current="page">
            Map
          </div>
        </nav>
      </div>

      <main className="stage">
        <MapCanvas congestionOn={congestionOn} stamp={stamp} />

        <div className="hud">
          <div className="status">
            <i className="dot" />
            <span>Live · {clock(now)}</span>
            <span className="refreshed">refreshed {clock(new Date(stamp))}</span>
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
        </div>

        <Legend />
      </main>
    </div>
  );
}
