// Tickets from the Lakad API: polled every 10 s, status changes applied optimistically.
import { useEffect, useMemo, useRef, useState } from "react";
import { listReports, patchSosKind, patchStatus } from "../../api/client";
import type { Report, SosKind, Status } from "../../types/api";
import { CATEGORY_LABEL, isSosActive, newReports } from "./tickets";

export const POLL_MS = 10_000;
const FRESH_MS = 5_000; // how long the toast and the new-row highlight stay

export function useTickets() {
  const [reports, setReports] = useState<Report[] | null>(null); // null until the first answer
  const [online, setOnline] = useState(true);
  const [pending, setPending] = useState<Partial<Record<string, Status>>>({}); // PATCHes in flight
  const [fresh, setFresh] = useState<string[]>([]);
  const [toast, setToast] = useState<{ id: number; text: string; sos?: boolean } | null>(null);
  const known = useRef<Set<string> | null>(null);

  useEffect(() => {
    let alive = true;
    let delay = POLL_MS;
    let timer = 0;
    let hide = 0;
    const poll = async () => {
      try {
        const next = await listReports();
        if (!alive) return;
        const added = newReports(known.current, next);
        known.current = new Set(next.map((r) => r.id));
        // Same answer as last time: keep the old array so the map and list don't redo work.
        setReports((prev) => (JSON.stringify(prev) === JSON.stringify(next) ? prev : next));
        setOnline(true);
        delay = POLL_MS;
        if (added.length) {
          const sos = added.some(isSosActive);
          const text = sos
            ? "SOS received"
            : added.length === 1
              ? `New ticket · ${CATEGORY_LABEL[added[0].category]}`
              : `${added.length} new tickets`;
          setToast({ id: Date.now(), text, sos });
          setFresh(added.map((r) => r.id));
          clearTimeout(hide);
          hide = window.setTimeout(() => {
            setToast(null);
            setFresh([]);
          }, FRESH_MS);
        }
      } catch {
        // No logging: the HUD shows "API offline" instead.
        if (!alive) return;
        setOnline(false);
        // ponytail: back off to 30 s while offline so the browser doesn't log a failed request every 10 s.
        delay = Math.min(delay * 2, 30_000);
      }
      timer = window.setTimeout(poll, delay);
    };
    poll();
    return () => {
      alive = false;
      clearTimeout(timer);
      clearTimeout(hide);
    };
  }, []);

  // Optimistic: shows the new status at once. Resolves to null when saved, or the error message
  // when the server refused, in which case the old status comes back (the override is dropped).
  const changeStatus = async (id: string, status: Status): Promise<string | null> => {
    setPending((p) => ({ ...p, [id]: status }));
    try {
      const saved = await patchStatus(id, status);
      setReports((rs) => rs && rs.map((r) => (r.id === id ? saved : r)));
      return null;
    } catch (e) {
      return e instanceof Error ? e.message : String(e);
    } finally {
      // Unless a newer click on the same ticket replaced this one.
      setPending((p) => {
        if (p[id] !== status) return p;
        const rest = { ...p };
        delete rest[id];
        return rest;
      });
    }
  };

  // Who must respond to an SOS. Not optimistic: the server's answer replaces the ticket. Resolves to null when
  // saved, else the error message.
  const changeKind = async (id: string, kind: SosKind): Promise<string | null> => {
    try {
      const saved = await patchSosKind(id, kind);
      setReports((rs) => rs && rs.map((r) => (r.id === id ? saved : r)));
      return null;
    } catch (e) {
      return e instanceof Error ? e.message : String(e);
    }
  };

  const shown = useMemo(
    () =>
      reports &&
      reports.map((r) => {
        const status = pending[r.id];
        return status ? { ...r, status } : r;
      }),
    [reports, pending],
  );

  return { reports: shown, online, fresh, toast, changeStatus, changeKind };
}
