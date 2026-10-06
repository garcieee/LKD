// One ticket, shown in the Tickets panel: photo (an SOS: its video and who must respond), what and where, and the
// status stepper.
import { useState } from "react";
import { photoUrl, videoUrl } from "../api/client";
import type { Report, SosKind, Status } from "../types/api";
import SosKindCard from "../features/queue/SosKindCard";
import StatusStepper from "../features/queue/StatusStepper";
import TriageCard from "../features/queue/TriageCard";
import { SEVERITY_LABEL, STATUS_LABEL, isSos, ticketLabel, timeAgo } from "../features/queue/tickets";

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
  onKind: (id: string, kind: SosKind) => Promise<string | null>;
  onShowOnMap: (report: Report) => void;
};

export default function DetailPanel({ report: r, now, onStatus, onKind, onShowOnMap }: Props) {
  const [error, setError] = useState<string | null>(null);
  const label = ticketLabel(r);
  const photo = photoUrl(r.photo_url);
  const sos = isSos(r);
  const change = async (status: Status) => {
    setError(null);
    setError(await onStatus(r.id, status));
  };

  return (
    <div className="detail">
      {sos ? (
        r.video_url ? (
          // No sound by design: the app records video only. preload=metadata shows the first frame without the download.
          <video
            className="sos-video"
            src={videoUrl(r.video_url)}
            controls
            playsInline
            preload="metadata"
            aria-label={`SOS video, sent ${timeAgo(r.created_at, now)}`}
          />
        ) : (
          <p className="empty">This SOS has no video.</p>
        )
      ) : (
        <a className="photo" href={photo} target="_blank" rel="noreferrer">
          <img src={photo} alt={`${label}, reported ${timeAgo(r.created_at, now)}`} />
          <span className="sr-only"> (full size, opens in a new tab)</span>
        </a>
      )}

      <div className="detail-tags">
        {sos && <span className="badge sos-tag">SOS</span>}
        <span className="badge" data-status={r.status}>
          {STATUS_LABEL[r.status]}
        </span>
        <Severity level={r.severity} />
      </div>
      <h3 className="detail-title" tabIndex={-1}>
        {label}
      </h3>
      <p className={r.note ? "note" : "note muted"}>
        {r.note || (sos ? "Sent with the app's SOS button: a short video, no sound." : "No note from the reporter.")}
      </p>

      {sos && <SosKindCard report={r} onChange={(kind) => onKind(r.id, kind)} />}
      {/* A new ticket is reviewed first (Confirm or Reject); only then does it move along the stepper. */}
      <TriageCard report={r} onChange={change} />
      {r.status !== "open" && r.status !== "rejected" && <StatusStepper status={r.status} onChange={change} />}
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
