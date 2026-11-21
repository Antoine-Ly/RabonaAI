import { useCallback, useReducer, useRef } from "react";
import { type UiError, fromApiError } from "../lib/errors";
import { ApiRequestError, streamChat } from "../services/chat";
import { chatReducer, initialChatState } from "../state/chatReducer";

/** Délai sans réponse au-delà duquel on suppose un démarrage à froid du serveur (≈ 32 s mesurés, phase 0). */
const SLOW_AFTER_MS = 4000;

function toUiError(error: unknown): UiError {
  if (error instanceof ApiRequestError) return fromApiError(error.error);
  return { code: "network_error", message: "", retryAfterSeconds: null };
}

/**
 * Conversations en mémoire et envoi d'un message en streaming. Jusqu'à la phase 5 (base de données),
 * l'historique n'existe que dans le navigateur et le serveur ne reçoit que le dernier message.
 */
export function useChat(getToken: () => Promise<string | null>, onUnauthorized: () => void) {
  const [state, dispatch] = useReducer(chatReducer, initialChatState);
  const controllerRef = useRef<AbortController | null>(null);

  const send = useCallback(
    async (text: string) => {
      if (controllerRef.current) return;
      const controller = new AbortController();
      controllerRef.current = controller;
      dispatch({
        type: "send",
        text,
        convId: crypto.randomUUID(),
        userId: crypto.randomUUID(),
        assistantId: crypto.randomUUID(),
        now: Date.now(),
      });
      const slowTimer = setTimeout(() => dispatch({ type: "slow" }), SLOW_AFTER_MS);
      let finished = false;
      try {
        const token = await getToken();
        if (!token) throw new ApiRequestError({ code: "unauthorized", message: "", retry_after_seconds: null }, 401);
        for await (const event of streamChat({ message: text, token, signal: controller.signal })) {
          switch (event.event) {
            case "status":
              dispatch({ type: "status", tool: event.data.tool, state: event.data.state });
              break;
            case "delta":
              dispatch({ type: "delta", text: event.data.text });
              break;
            case "done":
              finished = true;
              dispatch({ type: "done", remaining: event.data.quota?.messages_remaining_today ?? null });
              break;
            case "error":
              finished = true;
              dispatch({ type: "fail", error: fromApiError(event.data) });
              break;
            case "meta":
              break;
          }
        }
        if (!finished) {
          dispatch({ type: "fail", error: { code: "interrupted", message: "", retryAfterSeconds: null } });
        }
      } catch (error) {
        if (controller.signal.aborted) {
          dispatch({ type: "stop" });
        } else {
          const uiError = toUiError(error);
          dispatch({ type: "fail", error: uiError });
          if (uiError.code === "unauthorized") onUnauthorized();
        }
      } finally {
        clearTimeout(slowTimer);
        controllerRef.current = null;
      }
    },
    [getToken, onUnauthorized],
  );

  const stop = useCallback(() => controllerRef.current?.abort(), []);

  return { state, dispatch, send, stop };
}
