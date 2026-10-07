// The Barangays menu: a list of Makati's 23 barangays to find one by name (or district) and zoom the map to it, with how
// many tickets each has, and the switch for the boundaries and names drawn on the map. Picking one also narrows the
// queue, the pins and Insights to it (App). Docked beside the map like Insights and Forecast.
import { useMemo, useState } from "react";
import ResizeGrip from "../../panels/ResizeGrip";
import { BARANGAYS, DISTRICTS } from "../../data/barangays";
import type { Report } from "../../types/api";
import { searchBarangays, sortBarangays, tally, type Barangay, type SortBy } from "./barangays";
import "./barangays.css";

type Props = {
  reports: Report[] | null; // null until the API first answers
  selectedId: string | null;
  onSelect: (b: Barangay) => void; // zoom the map to it, and narrow the queue, pins and Insights to it
  onClear: () => void; // back to the whole city: everything shown again
  show: boolean; // the boundaries and names are drawn on the map
  onShow: (on: boolean) => void;
  onClose: () => void;
};

const Icon = ({ d }: { d: string }) => (
  <svg viewBox="0 0 20 20" aria-hidden="true">
    <path d={d} />
  </svg>
);

const SORTS: { id: SortBy; label: string }[] = [
  { id: "name", label: "A to Z" },
  { id: "busiest", label: "Busiest" },
];

const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

export default function BarangayPanel({ reports, selectedId, onSelect, onClear, show, onShow, onClose }: Props) {
  const [query, setQuery] = useState("");
  const [district, setDistrict] = useState<number | null>(null);
  const [sort, setSort] = useState<SortBy>("name");
  const counts = useMemo(() => tally(BARANGAYS, reports ?? []), [reports]);

  // The search ranks by how well a name matches; with nothing typed the chosen sort applies.
  const rows = useMemo(() => {
    const found = searchBarangays(BARANGAYS, query);
    const inDistrict = district === null ? found : found.filter((b) => b.district === district);
    return query.trim() ? inDistrict : sortBarangays(inDistrict, sort, counts);
  }, [query, district, sort, counts]);

  const selected = BARANGAYS.find((b) => b.id === selectedId) ?? null;
  const selectedTally = selected ? counts.get(selected.id) : undefined;

  return (
    <section id="barangays" className="insights barangays" aria-labelledby="barangays-title">
      <ResizeGrip />
      <header className="queue-head">
        <h2 id="barangays-title" className="panel-title" tabIndex={-1}>
          Barangays
        </h2>
        <span className="src">{BARANGAYS.length} in Makati</span>
        <button className="icon-btn close" aria-label="Close barangays" onClick={onClose}>
          <Icon d="m5.5 5.5 9 9m0-9-9 9" />
        </button>
      </header>

      <div className="queue-list">
        <label className="switch">
          <input type="checkbox" checked={show} onChange={(e) => onShow(e.target.checked)} />
          <span>Boundaries and names on the map</span>
          <span className={`chip ${show ? "on" : ""}`}>{show ? "On" : "Off"}</span>
        </label>

        <div className="brgy-tools">
          <input
            type="search"
            aria-label="Search barangays"
            placeholder="Search a barangay, e.g. Poblacion"
            value={query}
            spellCheck={false}
            autoComplete="off"
            maxLength={40}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && rows[0]) onSelect(rows[0]); // the best match
              if (e.key === "Escape" && query) {
                e.stopPropagation(); // clears the search, not the panel
                setQuery("");
              }
            }}
          />
          <div className="fchips" role="group" aria-label="District">
            <button className="fchip" aria-pressed={district === null} onClick={() => setDistrict(null)}>
              All
            </button>
            {Object.entries(DISTRICTS).map(([id, label]) => (
              <button key={id} className="fchip" title={label} aria-pressed={district === Number(id)} onClick={() => setDistrict(Number(id))}>
                District {id}
              </button>
            ))}
          </div>
          <div className="brgy-sort" role="group" aria-label="Order">
            <span>Order</span>
            {SORTS.map((s) => (
              <button key={s.id} className="fchip" aria-pressed={sort === s.id && !query.trim()} disabled={!!query.trim()} onClick={() => setSort(s.id)}>
                {s.label}
              </button>
            ))}
          </div>
        </div>

        {selected && (
          <div className="triage brgy-selected" role="status">
            <div className="triage-head">
              <b>{selected.name}</b>
              <span>{DISTRICTS[selected.district]}</span>
            </div>
            <p className="brgy-summary">
              {selectedTally
                ? `${plural(selectedTally.unresolved, "unresolved ticket")}${selectedTally.sos ? `, ${selectedTally.sos} SOS` : ""}${selectedTally.urgent ? `, ${selectedTally.urgent} urgent` : ""}.`
                : "No ticket counts yet."}{" "}
              The queue, the map's pins and Insights show only this barangay.
            </p>
            <div className="triage-actions">
              <button className="btn" onClick={() => onSelect(selected)}>
                Zoom here again
              </button>
              <button className="btn" onClick={onClear}>
                Show all of Makati
              </button>
            </div>
          </div>
        )}

        {rows.length ? (
          <ul className="brgy-list" aria-label="Barangays">
            {rows.map((b) => {
              const t = counts.get(b.id);
              return (
                <li key={b.id}>
                  <button className="brgy-row" aria-pressed={b.id === selectedId} onClick={() => onSelect(b)}>
                    <span className="brgy-name">{b.name}</span>
                    {t && t.sos > 0 && <span className="badge sos-tag">SOS {t.sos}</span>}
                    {t && t.urgent > 0 && <span className="brgy-urgent">{t.urgent} urgent</span>}
                    <span className="brgy-d">D{b.district}</span>
                    <span className="brgy-count" data-zero={!t || t.unresolved === 0 ? "" : undefined}>
                      {reports ? (t?.unresolved ?? 0) : "–"}
                      <span className="sr-only"> unresolved tickets</span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="empty">No barangay matches “{query.trim()}”. Try Poblacion, Bel-Air or District 2.</p>
        )}

        <p className="legend-note brgy-note">
          Outlines: © OpenStreetMap contributors. These are the 23 barangays the ticket system uses: the ten EMBO barangays are
          Taguig now. The number is each barangay's unresolved tickets.
        </p>
      </div>
    </section>
  );
}
