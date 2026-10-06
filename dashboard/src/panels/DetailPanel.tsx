// One ticket, shown in the Tickets panel: its ID, photo (click to enlarge; an SOS: its video and who must respond),
// what and where, then what to do next: review it (Confirm or Reject), assign a handler, say it is resolved.
import { useEffect, useRef, useState } from "react";
import { photoUrl, videoUrl } from "../api/client";
import Lightbox from "./Lightbox";
import type { Report, SosKind, Status } from "../types/api";
import HandlerCard from "../features/queue/HandlerCard";
import SosKindCard from "../features/queue/SosKindCard";
import StatusStepper from "../features/queue/StatusStepper";
import TriageCard from "../features/queue/TriageCard";
import { SEVERITY_LABEL, STATUS_LABEL, bandOf, isSos, sightingsLabel, ticketCode, ticketLabel, timeAgo } from "../features/queue/tickets";

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

// The ticket engine's band as a chip; nothing until the server's ticket loop has scored the report.
export function BandChip({ report }: { report: Report }) {
  const band = bandOf(report);
  return band && <span className="badge" data-band={band}>{band}</span>;
}

type Props = {
  report: Report;
  sightings?: ReadonlyMap<string, number>; // reports per ticket_id, to say "3 reports" on a ticket several people filed
  now: number;
  onStatus: (id: string, status: Status) => Promise<string | null>;
  onKind: (id: string, kind: SosKind) => Promise<string | null>;
  onAssign: (id: string, handler: string, status?: Status) => Promise<string | null>;
  onShowOnMap: (report: Report) => void;
};

export default function DetailPanel({ report: r, sightings, now, onStatus, onKind, onAssign, onShowOnMap }: Props) {
  const [error, setError] = useState<string | null>(null);
  const [zoomed, setZoomed] = useState(false); // the picture is open large
  const label = ticketLabel(r);
  const photo = photoUrl(r.photo_url);
  const sos = isSos(r);
  const title = useRef<HTMLHeadingElement>(null);
  // Confirm, Reject and Reopen remove themselves when the status changes, and the focus they held falls to the page:
  // bring it back to the ticket.
  useEffect(() => {
    if (document.activeElement === document.body) title.current?.focus();
  }, [r.status]);
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
        <button className="photo" aria-haspopup="dialog" onClick={() => setZoomed(true)}>
          <img src={photo} alt={`${label}, reported ${timeAgo(r.created_at, now)}`} />
          <span className="sr-only"> (enlarge)</span>
        </button>
      )}

      {!sos && (
        <Lightbox
          open={zoomed}
          src={photo}
          alt={`${label}, reported ${timeAgo(r.created_at, now)}`}
          caption={`${ticketCode(r)} · ${label}`}
          onClose={() => setZoomed(false)}
        />
      )}

      <div className="detail-tags">
        <span className="tid" title="Ticket ID">
          {ticketCode(r)}
        </span>
        {sos && <span className="badge sos-tag">SOS</span>}
        <span className="badge" data-status={r.status}>
          {STATUS_LABEL[r.status]}
        </span>
        <Severity level={r.severity} />
        <BandChip report={r} />
        {sightings && sightingsLabel(r, sightings)}
      </div>
      <h3 ref={title} className="detail-title" tabIndex={-1}>
        {label}
        <span className="ago"> · {timeAgo(r.created_at, now)}</span>
      </h3>
      <p className={r.note ? "note" : "note muted"}>
        {r.note || (sos ? "Sent with the app's SOS button: a short video, no sound." : "No note from the reporter.")}
      </p>

      {sos && <SosKindCard report={r} onChange={(kind) => onKind(r.id, kind)} />}
      {/* A new ticket is reviewed first (Confirm or Reject). A verified one gets a handler, an assigned one is
          marked resolved. The bars below only show how far it has come. */}
      <TriageCard report={r} onChange={change} />
      <HandlerCard report={r} onAssign={(handler, status) => onAssign(r.id, handler, status)} onStatus={change} />
      {r.status !== "open" && r.status !== "rejected" && <StatusStepper status={r.status} />}
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
        {r.handler && (r.status === "assigned" || r.status === "fixed") && (
          <>
            <dt>Handler</dt>
            <dd>{r.handler}</dd>
          </>
        )}
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
