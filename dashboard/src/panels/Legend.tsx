// Bottom-left legend for the congestion colours and the ticket pins.
import { CONGESTION_RAMP } from "../layers/congestion";
import { STATUSES, STATUS_LABEL } from "../features/queue/tickets";

// Built from the same stops as the map lines (free flow on the left), so it cannot drift from what is drawn.
const GRADIENT = `linear-gradient(90deg, ${[...CONGESTION_RAMP]
  .reverse()
  .map(([level, color]) => `${color} ${Math.round((1 - level) * 100)}%`)
  .join(", ")})`;

export default function Legend() {
  return (
    <div className="panel legend">
      <div className="panel-title">Traffic flow</div>
      <div className="legend-bar" style={{ background: GRADIENT }} />
      <div className="legend-ends">
        <span>Free flow</span>
        <span>Standstill</span>
      </div>
      <div className="legend-note">Speed vs free flow · Traffic © TomTom</div>
      <ul className="legend-pins" aria-label="Ticket pins">
        {STATUSES.map((s) => (
          <li key={s}>
            <i className="dot" data-status={s} />
            {STATUS_LABEL[s]}
          </li>
        ))}
        <li>
          <i className="dot" data-level="sos" />
          SOS
        </li>
      </ul>
    </div>
  );
}
