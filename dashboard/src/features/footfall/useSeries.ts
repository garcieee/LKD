// The hourly history and forecast for one zone. Refetched when the zone changes and each new hour,
// so "now" on the chart never lags behind the clock, and every RETRY_MS after a failure (an API restart must not
// leave the chart stuck on its error).
import { useEffect, useState } from "react";
import { getSeries } from "../../api/client";
import type { Series } from "../../types/api";

const RETRY_MS = 10_000;

export function useSeries(enabled: boolean, zone: string, hourKey: number) {
  const [data, setData] = useState<Series | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0); // bumped to fetch again after a failure

  useEffect(() => {
    if (!enabled) return;
    let alive = true;
    let retry = 0;
    getSeries(zone).then(
      (s) => {
        if (!alive) return;
        setData(s);
        setError(null);
      },
      (e: unknown) => {
        if (!alive) return;
        setError(e instanceof Error ? e.message : "Request failed");
        retry = window.setTimeout(() => setAttempt((n) => n + 1), RETRY_MS);
      },
    );
    return () => {
      alive = false;
      clearTimeout(retry);
    };
  }, [enabled, zone, hourKey, attempt]);

  // A different zone's series is not this zone's: show loading, not the old chart under the new name.
  return { data: data && data.zone === zone ? data : null, error };
}
