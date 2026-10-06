// Modeled foot traffic for a day and hour, fetched whenever the layer is on and either changes.
import { useEffect, useState } from "react";
import { getFootfall } from "../../api/client";
import type { Day, Footfall } from "../../types/api";

export function useFootfall(enabled: boolean, day: Day, hour: number) {
  const [data, setData] = useState<Footfall | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!enabled) return;
    let alive = true;
    // The slider fires on every step: wait a beat so only the value it rests on is fetched.
    const id = setTimeout(() => {
      getFootfall(day, hour).then(
        (d) => {
          if (!alive) return;
          setData(d);
          setError(null);
        },
        (e: unknown) => alive && setError(e instanceof Error ? e.message : "Request failed"),
      );
    }, 120);
    return () => {
      alive = false;
      clearTimeout(id);
    };
  }, [enabled, day, hour]);

  return { data, error };
}
