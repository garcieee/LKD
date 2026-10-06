// HUD panel for the foot-traffic layer. Switching it on means live: the map shows the estimate for this hour in
// Manila and follows the clock. Past and future live in the Forecast panel, which can pin the map to another moment.
import { DAY_LABEL, FOOTFALL_RAMP } from "../../layers/footfall";
import type { Day, Footfall, FootfallDistrict } from "../../types/api";

type Props = {
  on: boolean;
  onToggle: (on: boolean) => void;
  when: { day: Day; hour: number };
  pinned: boolean; // the Forecast panel has moved the map off live
  onLive: () => void;
  data: Footfall | null;
  error: string | null;
  onShow: (d: FootfallDistrict) => void;
  forecastOpen: boolean;
  onForecast: () => void;
};

const GRADIENT = `linear-gradient(90deg, ${FOOTFALL_RAMP.map(([s, c]) => `${c} ${s * 100}%`).join(", ")})`;

export default function FootfallPanel({ on, onToggle, when, pinned, onLive, data, error, onShow, forecastOpen, onForecast }: Props) {
  const top = data?.districts.slice(0, 5) ?? [];
  const at = `${DAY_LABEL[when.day]} ${String(when.hour).padStart(2, "0")}:00`;
  return (
    <details className="panel side footfall">
      <summary className="panel-title">Foot traffic</summary>
      <div className="src">Predicted · transit hubs and districts</div>

      <label className="switch">
        <input type="checkbox" checked={on} onChange={(e) => onToggle(e.target.checked)} />
        <span>Live layer</span>
        <span className={`chip ${on ? "on" : ""}`}>{on ? "On" : "Off"}</span>
      </label>

      {on && (
        <>
          <div className="ff-state" data-pinned={pinned || undefined}>
            {pinned ? (
              <>
                <span>Showing {at}</span>
                <button className="fc-live" onClick={onLive}>
                  Back to live
                </button>
              </>
            ) : (
              <span>
                <i className="ff-pulse" aria-hidden="true" /> Live estimate · {at}
              </span>
            )}
          </div>

          <div className="legend-bar" style={{ background: GRADIENT }} />
          <div className="legend-ends">
            <span>Quiet</span>
            <span>Busiest</span>
          </div>

          {error && <p className="warn">{error}</p>}
          {top.length > 0 && (
            <ol className="ff-list" aria-label="Busiest districts">
              {top.map((d) => (
                <li key={d.id}>
                  <button onClick={() => onShow(d)} title={d.basis}>
                    <span className="ff-tier" data-tier={d.tier}>
                      {d.tier}
                    </span>
                    <span className="ff-name">{d.name.replace(/ \(.*\)$/, "")}</span>
                    <b>{Math.round(d.index)}</b>
                  </button>
                </li>
              ))}
            </ol>
          )}

          <button className="btn ff-open" aria-pressed={forecastOpen} onClick={onForecast}>
            {forecastOpen ? "Close forecast" : "Past & forecast"}
          </button>
          <p className="legend-note">Predicted from research and assumptions, not counted. Relative 0–100.</p>
        </>
      )}
    </details>
  );
}
