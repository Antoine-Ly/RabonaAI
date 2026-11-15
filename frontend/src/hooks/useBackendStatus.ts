import { useCallback, useEffect, useState } from "react";
import { pingHealth } from "../services/api";

export type BackendStatus = "waking" | "ready" | "unreachable";

/** Réveille le backend dès l'affichage de la page et expose son état. */
export function useBackendStatus(): { status: BackendStatus; retry: () => void } {
  const [status, setStatus] = useState<BackendStatus>("waking");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    void pingHealth(controller.signal).then((ok) => {
      if (!controller.signal.aborted) setStatus(ok ? "ready" : "unreachable");
    });
    return () => controller.abort();
  }, [attempt]);

  const retry = useCallback(() => {
    setStatus("waking");
    setAttempt((n) => n + 1);
  }, []);

  return { status, retry };
}
