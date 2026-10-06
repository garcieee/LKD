// Modeled foot traffic for a day and hour, fetched whenever the layer is on and either changes, and again every
// RETRY_MS after a failure (an API restart must not leave the layer stuck on its error).
import { useEffect, useState } from "react";
import { getFootfall } from "../../api/client";
import type { Day, Footfall } from "../../types/api";

const RETRY_MS = 10_000;

export function useFootfall(enabled: boolean, day: Day, hour: number) {
  const [data, setData] = useState<Footfall | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0); // bumped to fetch again after a failure

  useEffect(() => {
    if (!enabled) return;
    let alive = true;
    let retry = 0;
    // The slider fires on every step: wait a beat so only the value it rests on is fetched.
    const id = setTimeout(() => {
      getFootfall(day, hour).then(
        (d) => {
          if (!alive) return;
          setData(d);
          setError(null);
        },
        (e: unknown) => {
          if (!alive) return;
          setError(e instanceof Error ? e.message : "Request failed");
          retry = window.setTimeout(() => setAttempt((n) => n + 1), RETRY_MS);
        },
      );
    }, 120);
    return () => {
      alive = false;
      clearTimeout(id);
      clearTimeout(retry);
    };
  }, [enabled, day, hour, attempt]);

  return { data, error };
}
