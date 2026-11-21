import type { UiError } from "../lib/errors";
import type { MessageStatus, Role } from "../types/api";

export type UiMessageStatus = MessageStatus | "streaming";

export interface UiMessage {
  id: string;
  role: Role;
  content: string;
  status: UiMessageStatus;
}

export interface ConversationEntry {
  id: string;
  title: string;
  updatedAt: number;
  messages: UiMessage[];
}

export interface QuotaInfo {
  remaining: number;
  /** Inconnue tant que `GET /me/quota` n'existe pas (phase 5). */
  limit: number | null;
}

export interface ChatState {
  conversations: ConversationEntry[];
  /** `null` : nouvelle conversation (écran d'accueil). */
  activeId: string | null;
  /** Conversation dont la réponse est en cours de réception ; une seule à la fois. */
  streamingId: string | null;
  toolStatus: string | null;
  /** Aucune réponse après quelques secondes : probablement un démarrage à froid du serveur. */
  slow: boolean;
  error: UiError | null;
  quota: QuotaInfo | null;
}

export const initialChatState: ChatState = {
  conversations: [],
  activeId: null,
  streamingId: null,
  toolStatus: null,
  slow: false,
  error: null,
  quota: null,
};

export type ChatAction =
  | { type: "new" }
  | { type: "select"; id: string }
  | { type: "rename"; id: string; title: string }
  | { type: "remove"; id: string }
  | { type: "send"; text: string; convId: string; userId: string; assistantId: string; now: number }
  | { type: "delta"; text: string }
  | { type: "status"; tool: string; state: "running" | "done" }
  | { type: "slow" }
  | { type: "done"; remaining: number | null }
  | { type: "fail"; error: UiError }
  | { type: "stop" }
  | { type: "dismissError" };

export const TITLE_MAX = 40;
const TITLE_STORED_MAX = 120; // check (char_length(title) <= 120), docs/conception.md §6

/** Titre dérivé des premiers caractères du premier message (conception §3.4). */
export function makeTitle(text: string): string {
  const flat = text.replace(/\s+/g, " ").trim();
  return flat.length > TITLE_MAX ? `${flat.slice(0, TITLE_MAX - 1).trimEnd()}…` : flat;
}

function withLastAssistant(
  conversation: ConversationEntry,
  update: (message: UiMessage) => UiMessage | null,
): ConversationEntry {
  const last = conversation.messages.at(-1);
  if (!last || last.role !== "assistant" || last.status !== "streaming") return conversation;
  const updated = update(last);
  const head = conversation.messages.slice(0, -1);
  return { ...conversation, messages: updated ? [...head, updated] : head };
}

function mapStreaming(state: ChatState, update: (message: UiMessage) => UiMessage | null): ConversationEntry[] {
  return state.conversations.map((c) => (c.id === state.streamingId ? withLastAssistant(c, update) : c));
}

/** Arrêt du flux (erreur ou bouton Stop) : réponse partielle conservée, réponse vide supprimée. */
function endStream(state: ChatState, error: UiError | null): ChatState {
  return {
    ...state,
    conversations: mapStreaming(state, (m) => (m.content === "" ? null : { ...m, status: "partial" })),
    streamingId: null,
    toolStatus: null,
    slow: false,
    error,
  };
}

export function chatReducer(state: ChatState, action: ChatAction): ChatState {
  switch (action.type) {
    case "new":
      return { ...state, activeId: null, error: null };
    case "select":
      return state.conversations.some((c) => c.id === action.id)
        ? { ...state, activeId: action.id, error: null }
        : state;
    case "rename": {
      const title = action.title.replace(/\s+/g, " ").trim().slice(0, TITLE_STORED_MAX);
      if (!title) return state;
      return {
        ...state,
        conversations: state.conversations.map((c) => (c.id === action.id ? { ...c, title } : c)),
      };
    }
    case "remove":
      return {
        ...state,
        conversations: state.conversations.filter((c) => c.id !== action.id),
        activeId: state.activeId === action.id ? null : state.activeId,
        streamingId: state.streamingId === action.id ? null : state.streamingId,
        toolStatus: state.streamingId === action.id ? null : state.toolStatus,
        slow: state.streamingId === action.id ? false : state.slow,
      };
    case "send": {
      if (state.streamingId) return state;
      const user: UiMessage = { id: action.userId, role: "user", content: action.text, status: "complete" };
      const assistant: UiMessage = { id: action.assistantId, role: "assistant", content: "", status: "streaming" };
      const existing = state.activeId ? state.conversations.find((c) => c.id === state.activeId) : undefined;
      const conversation: ConversationEntry = existing
        ? { ...existing, updatedAt: action.now, messages: [...existing.messages, user, assistant] }
        : { id: action.convId, title: makeTitle(action.text), updatedAt: action.now, messages: [user, assistant] };
      return {
        ...state,
        conversations: [conversation, ...state.conversations.filter((c) => c.id !== conversation.id)],
        activeId: conversation.id,
        streamingId: conversation.id,
        toolStatus: null,
        slow: false,
        error: null,
      };
    }
    case "delta":
      if (!state.streamingId) return state;
      return {
        ...state,
        conversations: mapStreaming(state, (m) => ({ ...m, content: m.content + action.text })),
        toolStatus: null,
        slow: false,
      };
    case "status":
      if (!state.streamingId) return state;
      return { ...state, toolStatus: action.state === "running" ? action.tool : null, slow: false };
    case "slow":
      return state.streamingId ? { ...state, slow: true } : state;
    case "done":
      if (!state.streamingId) return state;
      return {
        ...state,
        conversations: mapStreaming(state, (m) => ({ ...m, status: "complete" })),
        streamingId: null,
        toolStatus: null,
        slow: false,
        quota:
          action.remaining === null
            ? state.quota
            : { remaining: action.remaining, limit: state.quota?.limit ?? null },
      };
    case "fail":
      return state.streamingId ? endStream(state, action.error) : { ...state, error: action.error };
    case "stop":
      return state.streamingId ? endStream(state, null) : state;
    case "dismissError":
      return { ...state, error: null };
  }
}
