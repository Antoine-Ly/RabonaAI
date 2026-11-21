import type { ApiError, ErrorCode } from "../types/api";
import { formatDuration } from "./time";

/** Erreurs affichées à l'utilisateur : celles du contrat d'API, plus deux cas propres au client. */
export type UiErrorCode = ErrorCode | "network_error" | "interrupted";

export interface UiError {
  code: UiErrorCode;
  message: string;
  retryAfterSeconds: number | null;
}

export function fromApiError(error: ApiError): UiError {
  return { code: error.code, message: error.message, retryAfterSeconds: error.retry_after_seconds };
}

function retryHint(seconds: number | null): string {
  return seconds === null ? "" : ` Réessaie dans ${formatDuration(seconds)}.`;
}

/** Message français affiché dans le bandeau d'erreur. */
export function describeError(error: UiError): string {
  switch (error.code) {
    case "quota_user_daily":
      return `Tu as atteint ta limite de messages pour aujourd'hui.${retryHint(error.retryAfterSeconds)}`;
    case "quota_global_daily":
      return `Le service est saturé pour aujourd'hui.${retryHint(error.retryAfterSeconds)}`;
    case "rate_limited":
      return `Trop de messages en peu de temps.${retryHint(error.retryAfterSeconds)}`;
    case "llm_unavailable":
      return "Le modèle de langage est momentanément indisponible. Réessaie dans un instant.";
    case "unauthorized":
    case "forbidden":
      return "Ta session a expiré ou ton accès est refusé. Reconnecte-toi.";
    case "network_error":
      return "Impossible de joindre le serveur. Vérifie ta connexion, puis réessaie.";
    case "interrupted":
      return "La connexion a été interrompue avant la fin de la réponse.";
    case "validation_error":
      return error.message;
    default:
      return "Une erreur est survenue. Réessaie dans un instant.";
  }
}

/** Libellé affiché pendant qu'un outil de données est consulté (événement SSE `status`). */
export function describeTool(tool: string): string {
  switch (tool) {
    case "get_standings":
      return "Consultation du classement…";
    case "get_matches":
      return "Consultation des matchs…";
    case "get_top_scorers":
      return "Consultation des buteurs…";
    default:
      return "Consultation des données…";
  }
}
