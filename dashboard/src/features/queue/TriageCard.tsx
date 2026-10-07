// The first look at a ticket: is it real? Confirm sends a new ticket on as Verified. Reject hides it everywhere
// (queue, map, phone, routes) but keeps it on the server, and Reopen undoes that. A note for the reporter goes with
// the decision: optional to confirm, required to reject (the reporter reads why in the phone's My tickets).
// An SOS asks once more before it is rejected: it may be the only record of what happened.
import { useEffect, useId, useRef, useState } from "react";
import type { Report, Status } from "../../types/api";
import { NOTE_MAX, canReject, cleanNote, rejectedReason } from "./notes";
import { isSos } from "./tickets";

type Props = { report: Report; onChange: (status: Status, note?: string) => void };

export default function TriageCard({ report, onChange }: Props) {
  const [asking, setAsking] = useState(false);
  const [note, setNote] = useState("");
  const keep = useRef<HTMLButtonElement>(null);
  const hint = useId();
  // The safe answer is the one under the cursor when the question appears.
  useEffect(() => {
    if (asking) keep.current?.focus();
  }, [asking]);

  if (report.status === "rejected") {
    const reason = rejectedReason(report);
    return (
      <div className="triage rejected" role="status">
        <div className="triage-head">
          <b>Rejected</b>
          <span>Hidden from the map, the phone and routes. Kept on the server.</span>
        </div>
        {reason && (
          <p className="triage-reason">
            <b>Reason given:</b> {reason}
          </p>
        )}
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
  const reasonGiven = canReject(note);
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
                onChange("rejected", cleanNote(note));
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
        <>
          <label className="note-field">
            <span>Note for the reporter</span>
            <textarea
              rows={2}
              maxLength={NOTE_MAX}
              value={note}
              aria-describedby={hint}
              placeholder="Optional to confirm. Say why to reject."
              onChange={(e) => setNote(e.target.value)}
            />
          </label>
          <p id={hint} className="note-hint">
            {reasonGiven ? "The reporter will see this note." : "A reason is required to reject. It is optional to confirm."}
          </p>
          <div className="triage-actions">
            <button className="btn confirm" onClick={() => onChange("verified", cleanNote(note))}>
              Confirm
            </button>
            <button
              className="btn reject"
              disabled={!reasonGiven}
              title={reasonGiven ? undefined : "Write why it is rejected first"}
              onClick={() => (sos ? setAsking(true) : onChange("rejected", cleanNote(note)))}
            >
              Reject
            </button>
          </div>
        </>
      )}
    </div>
  );
}
