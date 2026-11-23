import type { ChatEvent, ChatRequest } from "../types/api";
import { API_URL } from "./api";
import { toApiRequestError } from "./http";
import { readChatEvents } from "./sse";

interface StreamChatOptions {
  conversationId: ChatRequest["conversation_id"];
  message: ChatRequest["message"];
  token: string;
  signal: AbortSignal;
}

/**
 * `POST /chat` : relaie les événements SSE du contrat (`meta`, `status`, `delta`, `done` ou `error`).
 * `conversationId` à `null` crée une conversation ; le serveur ajoute l'historique au prompt.
 */
export async function* streamChat({
  conversationId,
  message,
  token,
  signal,
}: StreamChatOptions): AsyncGenerator<ChatEvent> {
  const response = await fetch(`${API_URL}/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ conversation_id: conversationId, message }),
    signal,
  });
  if (!response.ok || !response.body) throw await toApiRequestError(response);
  yield* readChatEvents(response.body);
}
