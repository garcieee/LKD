// The hourly history and forecast for one zone. Refetched when the zone changes and each new hour,
// so "now" on the chart never lags behind the clock.
import { useEffect, useState } from "react";
import { getSeries } from "../../api/client";
import type { Series } from "../../types/api";

export function useSeries(enabled: boolean, zone: string, hourKey: number) {
  const [data, setData] = useState<Series | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!enabled) return;
    let alive = true;
    getSeries(zone).then(
      (s) => {
        if (!alive) return;
        setData(s);
        setError(null);
      },
      (e: unknown) => alive && setError(e instanceof Error ? e.message : "Request failed"),
    );
    return () => {
      alive = false;
    };
  }, [enabled, zone, hourKey]);

  // A different zone's series is not this zone's: show loading, not the old chart under the new name.
  return { data: data && data.zone === zone ? data : null, error };
}
