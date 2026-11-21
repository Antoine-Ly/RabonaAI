import type { ApiError, ApiErrorBody, ChatEvent, ChatRequest } from "../types/api";
import { API_URL } from "./api";
import { readChatEvents } from "./sse";

/** Erreur renvoyée par l'API avant l'ouverture du flux (authentification, validation, quota). */
export class ApiRequestError extends Error {
  readonly error: ApiError;
  readonly status: number;

  constructor(error: ApiError, status: number) {
    super(error.message);
    this.error = error;
    this.status = status;
  }
}

async function toApiRequestError(response: Response): Promise<ApiRequestError> {
  try {
    const body = (await response.json()) as Partial<ApiErrorBody>;
    if (body.error) return new ApiRequestError(body.error, response.status);
  } catch {
    // corps absent ou non JSON : message générique ci-dessous
  }
  return new ApiRequestError(
    {
      code: response.status === 401 ? "unauthorized" : "internal_error",
      message: `Erreur inattendue (HTTP ${response.status}).`,
      retry_after_seconds: null,
    },
    response.status,
  );
}

interface StreamChatOptions {
  message: ChatRequest["message"];
  token: string;
  signal: AbortSignal;
}

/**
 * `POST /chat` : relaie les événements SSE du contrat. Jusqu'à la phase 5, la requête ne contient
 * que le message (un seul tour, sans `conversation_id`).
 */
export async function* streamChat({ message, token, signal }: StreamChatOptions): AsyncGenerator<ChatEvent> {
  const response = await fetch(`${API_URL}/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ message }),
    signal,
  });
  if (!response.ok || !response.body) throw await toApiRequestError(response);
  yield* readChatEvents(response.body);
}
