// Open → Verified → Assigned → Fixed. Four 5px bars, navy up to the current status.
// Each step is a button that moves the ticket to that status (backwards too, to undo a slip).
import type { Status } from "../../types/api";
import { steps } from "./tickets";

type Props = { status: Status; onChange: (status: Status) => void };

export default function StatusStepper({ status, onChange }: Props) {
  return (
    <ol className="stepper" aria-label="Status">
      {steps(status).map((s) => (
        <li key={s.status}>
          <button
            className={s.reached ? "step reached" : "step"}
            aria-current={s.current ? "step" : undefined}
            onClick={() => {
              if (!s.current) onChange(s.status);
            }}
          >
            {s.label}
          </button>
        </li>
      ))}
    </ol>
  );
}
