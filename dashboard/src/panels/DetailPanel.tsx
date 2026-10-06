// One ticket, shown in the Tickets panel: photo, what and where, and the status stepper.
import { useState } from "react";
import { photoUrl } from "../api/client";
import type { Report, Status } from "../types/api";
import StatusStepper from "../features/queue/StatusStepper";
import { CATEGORY_LABEL, SEVERITY_LABEL, STATUS_LABEL, timeAgo } from "../features/queue/tickets";

const when = (iso: string) =>
  new Date(iso).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false });

// Three bars, filled up to the severity, then its name.
export function Severity({ level }: { level: Report["severity"] }) {
  return (
    <span className="sev">
      <span className="sev-bars" aria-hidden="true">
        {[1, 2, 3].map((n) => (
          <i key={n} className={n <= level ? "on" : undefined} />
        ))}
      </span>
      {SEVERITY_LABEL[level]}
    </span>
  );
}

type Props = {
  report: Report;
  now: number;
  onStatus: (id: string, status: Status) => Promise<string | null>;
  onShowOnMap: (report: Report) => void;
};

export default function DetailPanel({ report: r, now, onStatus, onShowOnMap }: Props) {
  const [error, setError] = useState<string | null>(null);
  const label = CATEGORY_LABEL[r.category];
  const photo = photoUrl(r.photo_url);
  const change = async (status: Status) => {
    setError(null);
    setError(await onStatus(r.id, status));
  };

  return (
    <div className="detail">
      <a className="photo" href={photo} target="_blank" rel="noreferrer">
        <img src={photo} alt={`${label}, reported ${timeAgo(r.created_at, now)}`} />
        <span className="sr-only"> (full size, opens in a new tab)</span>
      </a>

      <div className="detail-tags">
        <span className="badge" data-status={r.status}>
          {STATUS_LABEL[r.status]}
        </span>
        <Severity level={r.severity} />
      </div>
      <h3 className="detail-title" tabIndex={-1}>
        {label}
      </h3>
      <p className={r.note ? "note" : "note muted"}>{r.note || "No note from the reporter."}</p>

      <StatusStepper status={r.status} onChange={change} />
      {error && (
        <p className="error" role="alert">
          Status not changed: {error}
        </p>
      )}

      <dl className="readout">
        <dt>Reported</dt>
        <dd>
          <time dateTime={r.created_at}>
            {timeAgo(r.created_at, now)} · {when(r.created_at)}
          </time>
        </dd>
        <dt>Updated</dt>
        <dd>
          <time dateTime={r.updated_at}>
            {timeAgo(r.updated_at, now)} · {when(r.updated_at)}
          </time>
        </dd>
        <dt>Coordinates</dt>
        <dd>
          {r.lat.toFixed(5)}, {r.lng.toFixed(5)}
        </dd>
      </dl>

      <button className="btn" onClick={() => onShowOnMap(r)}>
        Show on map
      </button>
    </div>
  );
}
