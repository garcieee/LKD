// "Showing: Poblacion ✕": the pill wherever the data is narrowed to the barangay picked in the Barangays menu (the map,
// the Tickets queue, Insights), and the way back to all of Makati. Nothing when no barangay is picked. On the map it
// also says when an SOS call is open elsewhere, as it is hidden from the queue and the pins while narrowed.
import type { Barangay } from "./barangays";
import "./barangays.css";

type Props = {
  barangay: Barangay | null;
  sosElsewhere?: number; // open SOS calls outside the barangay
  onClear: () => void; // back to the whole city
};

export default function ScopeChip({ barangay, sosElsewhere = 0, onClear }: Props) {
  if (!barangay) return null;
  return (
    <div className="scope-chip">
      <span>Showing:</span>
      <b>{barangay.name}</b>
      {sosElsewhere > 0 && <em className="scope-sos">{sosElsewhere} SOS elsewhere</em>}
      <button className="icon-btn" aria-label="Show all of Makati" title="Show all of Makati" onClick={onClear}>
        <svg viewBox="0 0 20 20" aria-hidden="true">
          <path d="m5.5 5.5 9 9m0-9-9 9" />
        </svg>
      </button>
    </div>
  );
}
