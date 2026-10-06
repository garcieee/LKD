// Open → Verified → Assigned → Fixed. Four 5px bars, navy up to the current status.
// With onChange each step is a button that moves the ticket to that status; without it the bars only show how far the
// ticket has come, and the cards in the ticket (review, handler, resolved) are what move it.
import type { Status } from "../../types/api";
import { steps } from "./tickets";

type Props = { status: Status; onChange?: (status: Status) => void };

export default function StatusStepper({ status, onChange }: Props) {
  return (
    <ol className="stepper" aria-label="Status">
      {steps(status).map((s) => (
        <li key={s.status}>
          {onChange ? (
            <button
              className={s.reached ? "step reached" : "step"}
              aria-current={s.current ? "step" : undefined}
              onClick={() => {
                if (!s.current) onChange(s.status);
              }}
            >
              {s.label}
            </button>
          ) : (
            <span className={`step static${s.reached ? " reached" : ""}`} aria-current={s.current ? "step" : undefined}>
              {s.label}
            </span>
          )}
        </li>
      ))}
    </ol>
  );
}
