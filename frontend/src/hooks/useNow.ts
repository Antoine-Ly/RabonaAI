import { useEffect, useState } from "react";

/** Heure courante, rafraîchie à intervalle régulier (compte à rebours du quota). */
export function useNow(intervalMs: number): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);
  return now;
}
