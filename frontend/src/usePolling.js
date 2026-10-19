import { useEffect, useState } from "react";

// Poll a JSON endpoint; keeps last good data and exposes connection state.
export function usePolling(url, intervalMs = 1500) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const res = await fetch(url);
        if (!res.ok) throw new Error(res.status);
        const json = await res.json();
        if (alive) { setData(json); setError(false); }
      } catch { if (alive) setError(true); }
    };
    tick();
    const id = setInterval(tick, intervalMs);
    return () => { alive = false; clearInterval(id); };
  }, [url, intervalMs]);
  return { data, error };
}
