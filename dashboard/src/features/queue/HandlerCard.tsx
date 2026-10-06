// After Confirm: who will fix it? A verified ticket asks for a handler, picked from a short roster (quick and typo-free
// for a demo) or typed with "Someone else…". Saving moves it to Assigned and greys the name out, with Change to go back
// to the pick. An assigned ticket then asks whether it is resolved; a resolved one says so.
import { useEffect, useRef, useState } from "react";
import { HANDLERS } from "../../config/handlers";
import type { Report, Status } from "../../types/api";
import { OTHER, nameOf, stageOf, startingChoice } from "./handler";

type Props = {
  report: Report;
  onAssign: (handler: string, status?: Status) => Promise<string | null>; // null when saved, else why not
  onStatus: (status: Status) => void;
};

export default function HandlerCard({ report, onAssign, onStatus }: Props) {
  const [editing, setEditing] = useState(false);
  const stage = stageOf(report);
  if (stage === null) return null;

  if (stage === "assign" || editing) {
    return (
      <AssignForm
        // A fresh form for each of "pick" and "change", so the change form opens on the current name.
        key={stage === "assign" ? "assign" : "change"}
        report={report}
        changing={stage !== "assign"}
        onAssign={onAssign}
        onDone={() => setEditing(false)}
      />
    );
  }

  if (stage === "assigned") {
    return (
      <>
        <div className="triage handler">
          <div className="triage-head">
            <b>Assigned to</b>
          </div>
          <div className="handler-row">
            {/* Greyed out: the name is only shown. Change goes back to the pick. */}
            <input className="handler-locked" type="text" value={report.handler ?? ""} readOnly disabled aria-label="Assigned handler" />
            <button className="btn" onClick={() => setEditing(true)}>
              Change
            </button>
          </div>
        </div>
        <div className="triage resolve" role="group" aria-labelledby={`resolve-${report.id}`}>
          <div className="triage-head">
            <b id={`resolve-${report.id}`}>Is this ticket resolved?</b>
            <span>Mark it resolved once the work is done.</span>
          </div>
          <div className="triage-actions">
            <button className="btn confirm" onClick={() => onStatus("fixed")}>
              Yes, mark resolved
            </button>
          </div>
        </div>
      </>
    );
  }

  return (
    <div className="triage resolved" role="status">
      <div className="triage-head">
        <b>Resolved</b>
        <span>Handled by {report.handler ?? "an unnamed handler"}.</span>
      </div>
      <div className="triage-actions">
        <button className="btn" onClick={() => onStatus("assigned")}>
          Reopen
        </button>
      </div>
    </div>
  );
}

type FormProps = {
  report: Report;
  changing: boolean; // renaming the handler of an assigned ticket, not picking the first one
  onAssign: Props["onAssign"];
  onDone: () => void;
};

function AssignForm({ report, changing, onAssign, onDone }: FormProps) {
  const start = startingChoice(changing ? report.handler : null);
  const [choice, setChoice] = useState(start.choice);
  const [typed, setTyped] = useState(start.typed);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pick = useRef<HTMLSelectElement>(null);
  const name = nameOf(choice, typed);

  // After Confirm (or Change) the next thing to do is pick: put the keyboard there.
  useEffect(() => pick.current?.focus(), []);

  const save = async () => {
    if (!name || saving) return;
    setSaving(true);
    setError(null);
    // A verified ticket moves to Assigned in the same save; an assigned one only changes its name.
    const err = await onAssign(name, report.status === "verified" ? "assigned" : undefined);
    if (err) {
      setSaving(false);
      setError(err);
    } else {
      onDone();
    }
  };

  return (
    <div
      className="triage handler"
      role="group"
      aria-label={changing ? "Change the handler" : "Assign a handler"}
      onKeyDown={(e) => {
        // Esc leaves the change form (not the panel behind it).
        if (e.key === "Escape" && changing) {
          e.stopPropagation();
          onDone();
        }
      }}
    >
      <div className="triage-head">
        <b>{changing ? "Change the handler" : "Assign a handler"}</b>
        <span>{changing ? "Pick who has this ticket now." : "Who will fix this?"}</span>
      </div>
      <select ref={pick} className="field" aria-label="Handler" value={choice} onChange={(e) => setChoice(e.target.value)}>
        <option value="">Choose a handler…</option>
        {HANDLERS.map((h) => (
          <option key={h} value={h}>
            {h}
          </option>
        ))}
        <option value={OTHER}>Someone else…</option>
      </select>
      {choice === OTHER && (
        <input
          className="field"
          type="text"
          maxLength={60}
          placeholder="Type a name"
          aria-label="Handler name"
          value={typed}
          autoFocus
          onChange={(e) => setTyped(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") save();
          }}
        />
      )}
      <div className="triage-actions">
        <button className="btn confirm" disabled={!name || saving} onClick={save}>
          {saving ? "Saving…" : changing ? "Save" : "Assign"}
        </button>
        {changing && (
          <button className="btn" disabled={saving} onClick={onDone}>
            Cancel
          </button>
        )}
      </div>
      {error && (
        <p className="error" role="alert">
          Not saved: {error}
        </p>
      )}
    </div>
  );
}
