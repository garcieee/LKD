// The first look at a ticket: is it real? Confirm sends a new ticket on as Verified. Reject hides it everywhere
// (queue, map, phone, routes) but keeps it on the server, and Reopen undoes that. An SOS asks once more before
// it is rejected: it may be the only record of what happened.
import { useEffect, useRef, useState } from "react";
import type { Report, Status } from "../../types/api";
import { isSos } from "./tickets";

type Props = { report: Report; onChange: (status: Status) => void };

export default function TriageCard({ report, onChange }: Props) {
  const [asking, setAsking] = useState(false);
  const keep = useRef<HTMLButtonElement>(null);
  // The safe answer is the one under the cursor when the question appears.
  useEffect(() => {
    if (asking) keep.current?.focus();
  }, [asking]);

  if (report.status === "rejected") {
    return (
      <div className="triage rejected" role="status">
        <div className="triage-head">
          <b>Rejected</b>
          <span>Hidden from the map, the phone and routes. Kept on the server.</span>
        </div>
        <div className="triage-actions">
          <button className="btn" onClick={() => onChange("open")}>
            Reopen
          </button>
        </div>
      </div>
    );
  }
  if (report.status !== "open") return null;

  const sos = isSos(report);
  return (
    <div className="triage" data-sos={sos || undefined}>
      <div className="triage-head">
        <b>{sos ? "New SOS. Is it real?" : "New ticket. Is it real?"}</b>
        <span>Confirm sends it on as Verified. Reject hides it.</span>
      </div>
      {asking ? (
        <div
          role="alertdialog"
          aria-label="Reject this SOS?"
          onKeyDown={(e) => {
            // Esc answers the question (keep it), not the panel behind it.
            if (e.key === "Escape") {
              e.stopPropagation();
              setAsking(false);
            }
          }}
        >
          <p className="triage-ask">Reject this SOS? It is hidden but kept on the server, and you can reopen it.</p>
          <div className="triage-actions">
            <button
              className="btn danger"
              onClick={() => {
                setAsking(false); // or Reopen would bring the question back
                onChange("rejected");
              }}
            >
              Yes, reject
            </button>
            <button ref={keep} className="btn" onClick={() => setAsking(false)}>
              Keep it
            </button>
          </div>
        </div>
      ) : (
        <div className="triage-actions">
          <button className="btn confirm" onClick={() => onChange("verified")}>
            Confirm
          </button>
          <button className="btn reject" onClick={() => (sos ? setAsking(true) : onChange("rejected"))}>
            Reject
          </button>
        </div>
      )}
    </div>
  );
}
