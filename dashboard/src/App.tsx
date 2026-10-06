import { useEffect, useState } from "react";
import MapCanvas from "./map/MapCanvas";
import Legend from "./panels/Legend";
import { ENV } from "./config/env";
import { REFRESH_MS } from "./layers/congestion";

const clock = (d: Date) => d.toLocaleTimeString([], { hour12: false });

export default function App() {
  const [congestionOn, setCongestionOn] = useState(true);
  const [stamp, setStamp] = useState(() => Date.now());
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    if (!congestionOn) return;
    const id = setInterval(() => setStamp(Date.now()), REFRESH_MS);
    return () => clearInterval(id);
  }, [congestionOn]);

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" />
          <span>
            <b>LAKAD</b>
            <small>MAKATI OPS</small>
          </span>
        </div>
        <nav className="tabs">
          <button className="tab active">Congestion</button>
        </nav>
        <div className="clock">
          <span className="dot" /> {clock(now)}
        </div>
      </header>

      <main className="stage">
        <aside className="panel side">
          <div className="panel-title">Traffic flow</div>
          <div className="src">SRC · TOMTOM TRAFFIC</div>

          <label className="switch">
            <input
              type="checkbox"
              checked={congestionOn}
              onChange={(e) => setCongestionOn(e.target.checked)}
            />
            <span>Congestion layer</span>
            <span className={`chip ${congestionOn ? "on" : ""}`}>{congestionOn ? "ON" : "OFF"}</span>
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
        </aside>

        <section className="map-area">
          <MapCanvas congestionOn={congestionOn} stamp={stamp} />
          <Legend />
        </section>
      </main>
    </div>
  );
}
