// Who must respond to an SOS: Police, Medical, or Fire and rescue. A person picks after watching the silent video
// (the phone does not ask). Unsorted ones are listed first (tickets.ts rank). Sorting never changes the status:
// Confirm and Reject stay in the TriageCard.
import { useState } from "react";
import type { Report, SosKind } from "../../types/api";
import { SOS_KINDS, SOS_KIND_HINT, SOS_KIND_LABEL, needsSorting } from "./tickets";

type Props = { report: Report; onChange: (kind: SosKind) => Promise<string | null> };

export default function SosKindCard({ report, onChange }: Props) {
  const [error, setError] = useState<string | null>(null);
  const pick = async (kind: SosKind) => {
    setError(null);
    setError(await onChange(kind));
  };

  return (
    <div className="triage" data-sos role="group" aria-labelledby="sos-kind-title">
      <div className="triage-head">
        <b id="sos-kind-title">Who must respond?</b>
      </div>
      <div className="sos-kinds">
        {SOS_KINDS.map((kind) => (
          <button
            key={kind}
            className="btn"
            aria-pressed={report.sos_kind === kind}
            onClick={() => {
              if (report.sos_kind !== kind) pick(kind);
            }}
          >
            <b>{SOS_KIND_LABEL[kind]}</b>
            <span>{SOS_KIND_HINT[kind]}</span>
          </button>
        ))}
      </div>
      {/* Below the buttons: when it goes, nothing moves under the pointer (a double click can't pick the next kind). */}
      {needsSorting(report) && (
        <p className="note muted">Watch the video, then pick one. Unsorted SOS calls are listed first.</p>
      )}
      {error && (
        <p className="error" role="alert">
          Not saved: {error}
        </p>
      )}
    </div>
  );
}
