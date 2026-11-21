/**
 * Types du contrat d'API (docs/conception.md §3).
 * Source de vérité : le contrat ; les modèles Pydantic du backend doivent rester alignés.
 */

export type Role = "user" | "assistant";
export type MessageStatus = "complete" | "partial" | "error";

export type ErrorCode =
  | "unauthorized"
  | "forbidden"
  | "not_found"
  | "validation_error"
  | "quota_user_daily"
  | "quota_global_daily"
  | "rate_limited"
  | "llm_unavailable"
  | "internal_error";

export interface ApiError {
  code: ErrorCode;
  message: string;
  retry_after_seconds: number | null;
}

export interface ApiErrorBody {
  error: ApiError;
}

/** POST /chat */
export interface ChatRequest {
  conversation_id: string | null;
  /** 1 à 2000 caractères. */
  message: string;
}

/** Événements SSE de POST /chat, dans l'ordre : meta, status*, delta*, done | error. */
export type ChatEvent =
  | {
      event: "meta";
      data: { conversation_id: string; user_message_id: string; assistant_message_id: string };
    }
  | { event: "status"; data: { tool: string; state: "running" | "done" } }
  | { event: "delta"; data: { text: string } }
  | {
      event: "done";
      data: {
        assistant_message_id: string;
        finish_reason: string;
        usage: { prompt_tokens: number; completion_tokens: number };
        /** Absent jusqu'à la phase 5 (pas de quotas côté serveur avant la base de données). */
        quota?: { messages_remaining_today: number };
      };
    }
  | { event: "error"; data: ApiError };

/** GET /conversations */
export interface ConversationSummary {
  id: string;
  title: string;
  updated_at: string;
}

export interface ConversationList {
  items: ConversationSummary[];
  next_cursor: string | null;
}

/** GET /conversations/{id} */
export interface Message {
  id: string;
  role: Role;
  content: string;
  status: MessageStatus;
  created_at: string;
}

export interface ConversationDetail {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  messages: Message[];
}

/** GET /me/quota */
export interface QuotaState {
  messages_used_today: number;
  messages_limit: number;
  service_available: boolean;
  resets_at: string;
}

/** GET /health */
export interface HealthResponse {
  status: "ok";
}
