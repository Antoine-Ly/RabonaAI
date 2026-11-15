import type { HealthResponse } from "../types/api";

export const API_URL = (import.meta.env.VITE_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

/**
 * Le backend gratuit de Render s'endort après 15 min d'inactivité : le premier appel peut durer
 * une trentaine de secondes (mesuré en phase 0) et davantage avec l'application complète.
 */
export const WAKE_UP_TIMEOUT_MS = 70_000;

/** Réveille le backend et vérifie qu'il répond. Ne lève jamais : renvoie `false` en cas d'échec. */
export async function pingHealth(signal?: AbortSignal): Promise<boolean> {
  const timeout = AbortSignal.timeout(WAKE_UP_TIMEOUT_MS);
  const combined = signal ? AbortSignal.any([signal, timeout]) : timeout;
  try {
    const response = await fetch(`${API_URL}/health`, { signal: combined });
    if (!response.ok) return false;
    const body = (await response.json()) as Partial<HealthResponse>;
    return body.status === "ok";
  } catch {
    return false;
  }
}
