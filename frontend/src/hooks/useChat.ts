import { useCallback, useEffect, useReducer, useRef } from "react";
import { type UiError, fromApiError } from "../lib/errors";
import { streamChat } from "../services/chat";
import {
  deleteConversation,
  getConversation,
  getQuota,
  listConversations,
  renameConversation,
} from "../services/conversations";
import { ApiRequestError } from "../services/http";
import { chatReducer, initialChatState } from "../state/chatReducer";

/** Délai sans réponse au-delà duquel on suppose un démarrage à froid du serveur (≈ 32 s mesurés, phase 0). */
const SLOW_AFTER_MS = 4000;

function toUiError(error: unknown): UiError {
  if (error instanceof ApiRequestError) return fromApiError(error.error);
  return { code: "network_error", message: "", retryAfterSeconds: null };
}

type Result<T> = { ok: true; value: T } | { ok: false; error: UiError };

/**
 * Conversations, quota et envoi d'un message en streaming. Le serveur est la source de vérité :
 * l'historique est lu à l'ouverture, les identifiants définitifs arrivent avec l'événement `meta`.
 */
export function useChat(getToken: () => Promise<string | null>, onUnauthorized: () => void) {
  const [state, dispatch] = useReducer(chatReducer, initialChatState);
  const controllerRef = useRef<AbortController | null>(null);
  // Dernières valeurs, lues dans les gestionnaires : évite de relancer les effets à chaque rendu.
  const latest = useRef({ state, getToken, onUnauthorized });
  useEffect(() => {
    latest.current = { state, getToken, onUnauthorized };
  });

  /** Appel API authentifié ; une erreur d'authentification déconnecte, les autres sont renvoyées. */
  const call = useCallback(async <T>(request: (token: string) => Promise<T>): Promise<Result<T>> => {
    try {
      const token = await latest.current.getToken();
      if (!token) throw new ApiRequestError({ code: "unauthorized", message: "", retry_after_seconds: null }, 401);
      return { ok: true, value: await request(token) };
    } catch (error) {
      const uiError = toUiError(error);
      if (uiError.code === "unauthorized") latest.current.onUnauthorized();
      return { ok: false, error: uiError };
    }
  }, []);

  // Liste des conversations et quota au démarrage.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const [list, quota] = await Promise.all([call((t) => listConversations(t)), call(getQuota)]);
      if (cancelled) return;
      if (list.ok) dispatch({ type: "listLoaded", items: list.value.items, nextCursor: list.value.next_cursor });
      else dispatch({ type: "setError", error: list.error });
      if (quota.ok) {
        const q = quota.value;
        dispatch({ type: "quotaLoaded", used: q.messages_used_today, limit: q.messages_limit, available: q.service_available });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [call]);

  // Messages de la conversation ouverte, chargés à la demande.
  const { activeId } = state;
  const needsMessages = state.conversations.find((c) => c.id === activeId)?.messages === null;
  useEffect(() => {
    if (!activeId || !needsMessages) return;
    let cancelled = false;
    void (async () => {
      const result = await call((t) => getConversation(t, activeId));
      if (cancelled) return;
      if (result.ok) {
        dispatch({ type: "conversationLoaded", detail: result.value });
      } else {
        dispatch({ type: "remove", id: activeId }); // introuvable ou illisible : on la retire de l'écran
        dispatch({ type: "setError", error: result.error });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [activeId, needsMessages, call]);

  const send = useCallback(
    async (text: string) => {
      const current = latest.current.state;
      const active = current.conversations.find((c) => c.id === current.activeId);
      if (controllerRef.current || (active && active.messages === null)) return;
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
        const token = await latest.current.getToken();
        if (!token) throw new ApiRequestError({ code: "unauthorized", message: "", retry_after_seconds: null }, 401);
        const events = streamChat({
          conversationId: active?.persisted ? active.id : null,
          message: text,
          token,
          signal: controller.signal,
        });
        for await (const event of events) {
          switch (event.event) {
            case "meta":
              dispatch({
                type: "meta",
                conversationId: event.data.conversation_id,
                userMessageId: event.data.user_message_id,
                assistantMessageId: event.data.assistant_message_id,
              });
              break;
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
          if (uiError.code === "unauthorized") latest.current.onUnauthorized();
        }
      } finally {
        clearTimeout(slowTimer);
        controllerRef.current = null;
      }
    },
    [],
  );

  const stop = useCallback(() => controllerRef.current?.abort(), []);

  const rename = useCallback(
    async (id: string, title: string) => {
      const result = await call((t) => renameConversation(t, id, title));
      dispatch(result.ok ? { type: "rename", id, title: result.value.title } : { type: "setError", error: result.error });
    },
    [call],
  );

  const remove = useCallback(
    async (id: string) => {
      if (latest.current.state.streamingId === id) controllerRef.current?.abort();
      const result = await call((t) => deleteConversation(t, id));
      // Déjà supprimée côté serveur (404) : on la retire quand même de l'écran.
      if (result.ok || result.error.code === "not_found") dispatch({ type: "remove", id });
      else dispatch({ type: "setError", error: result.error });
    },
    [call],
  );

  const loadMore = useCallback(
    async (cursor: string) => {
      const result = await call((t) => listConversations(t, cursor));
      if (result.ok) dispatch({ type: "listLoaded", items: result.value.items, nextCursor: result.value.next_cursor });
      else dispatch({ type: "setError", error: result.error });
    },
    [call],
  );

  return { state, dispatch, send, stop, rename, remove, loadMore };
}
