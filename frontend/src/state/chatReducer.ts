import type { UiError } from "../lib/errors";
import type { ConversationDetail, ConversationSummary, MessageStatus, Role } from "../types/api";

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
  /** `false` tant que le serveur n'a pas confirmé la création (événement `meta`). */
  persisted: boolean;
  /** `null` : pas encore chargés depuis le serveur (conversation vue dans la liste seulement). */
  messages: UiMessage[] | null;
}

export interface QuotaInfo {
  remaining: number;
  /** Inconnue seulement si le quota n'a pas pu être lu au démarrage. */
  limit: number | null;
  /** `false` quand le budget global du jour est épuisé (service saturé). */
  available: boolean;
}

export interface ChatState {
  conversations: ConversationEntry[];
  /** `null` : nouvelle conversation (écran d'accueil). */
  activeId: string | null;
  /** Conversation dont la réponse est en cours de réception ; une seule à la fois. */
  streamingId: string | null;
  /** Le serveur a accepté le message (événement `meta` reçu) : il est enregistré côté serveur. */
  accepted: boolean;
  nextCursor: string | null;
  listLoaded: boolean;
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
  accepted: false,
  nextCursor: null,
  listLoaded: false,
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
  | { type: "listLoaded"; items: ConversationSummary[]; nextCursor: string | null }
  | { type: "conversationLoaded"; detail: ConversationDetail }
  | { type: "quotaLoaded"; used: number; limit: number; available: boolean }
  | { type: "send"; text: string; convId: string; userId: string; assistantId: string; now: number }
  | { type: "meta"; conversationId: string; userMessageId: string; assistantMessageId: string }
  | { type: "delta"; text: string }
  | { type: "status"; tool: string; state: "running" | "done" }
  | { type: "slow" }
  | { type: "done"; remaining: number | null }
  | { type: "fail"; error: UiError }
  | { type: "stop" }
  | { type: "setError"; error: UiError }
  | { type: "dismissError" };

export const TITLE_MAX = 40;
const TITLE_STORED_MAX = 120; // check (char_length(title) <= 120), docs/conception.md §6

/** Titre dérivé des premiers caractères du premier message (même règle que le backend). */
export function makeTitle(text: string): string {
  const flat = text.replace(/\s+/g, " ").trim();
  return flat.length > TITLE_MAX ? `${flat.slice(0, TITLE_MAX - 1).trimEnd()}…` : flat;
}

function byRecent(a: ConversationEntry, b: ConversationEntry): number {
  return b.updatedAt - a.updatedAt;
}

function updateConversation(
  state: ChatState,
  id: string | null,
  update: (conversation: ConversationEntry) => ConversationEntry | null,
): ConversationEntry[] {
  return state.conversations.flatMap((c) => {
    if (c.id !== id) return [c];
    const updated = update(c);
    return updated ? [updated] : [];
  });
}

function withLastAssistant(
  conversation: ConversationEntry,
  update: (message: UiMessage) => UiMessage | null,
): ConversationEntry {
  const messages = conversation.messages;
  const last = messages?.at(-1);
  if (!messages || !last || last.role !== "assistant" || last.status !== "streaming") return conversation;
  const updated = update(last);
  const head = messages.slice(0, -1);
  return { ...conversation, messages: updated ? [...head, updated] : head };
}

function mapStreaming(state: ChatState, update: (message: UiMessage) => UiMessage | null): ConversationEntry[] {
  return updateConversation(state, state.streamingId, (c) => withLastAssistant(c, update));
}

const idle = { streamingId: null, accepted: false, toolStatus: null, slow: false } as const;

/**
 * Arrêt du flux (erreur ou bouton Stop). Si le serveur n'a rien accepté (erreur avant `meta` : quota,
 * authentification, réseau), le tour est retiré de l'écran, puisqu'il n'existe pas côté serveur.
 * Sinon la réponse partielle est conservée, et une réponse vide supprimée.
 */
function endStream(state: ChatState, error: UiError | null): ChatState {
  const base = { ...state, ...idle, error };
  if (!state.accepted) {
    const dropTurn = (c: ConversationEntry): ConversationEntry | null =>
      c.persisted && c.messages ? { ...c, messages: c.messages.slice(0, -2) } : null;
    return {
      ...base,
      conversations: updateConversation(state, state.streamingId, dropTurn),
      activeId: state.activeId === state.streamingId && !isPersisted(state, state.streamingId) ? null : state.activeId,
    };
  }
  return {
    ...base,
    conversations: mapStreaming(state, (m) => (m.content === "" ? null : { ...m, status: "partial" })),
  };
}

function isPersisted(state: ChatState, id: string | null): boolean {
  return state.conversations.find((c) => c.id === id)?.persisted ?? false;
}

function quotaAfterError(quota: QuotaInfo | null, error: UiError): QuotaInfo | null {
  if (error.code === "quota_user_daily") return { remaining: 0, limit: quota?.limit ?? null, available: quota?.available ?? true };
  if (error.code === "quota_global_daily" && quota) return { ...quota, available: false };
  return quota;
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
      return { ...state, conversations: updateConversation(state, action.id, (c) => ({ ...c, title })) };
    }
    case "remove": {
      const wasStreaming = state.streamingId === action.id;
      return {
        ...state,
        conversations: state.conversations.filter((c) => c.id !== action.id),
        activeId: state.activeId === action.id ? null : state.activeId,
        ...(wasStreaming ? idle : {}),
      };
    }
    case "listLoaded": {
      const known = new Map(state.conversations.map((c) => [c.id, c]));
      const fromServer: ConversationEntry[] = action.items.map((item) => ({
        id: item.id,
        title: item.title,
        updatedAt: Date.parse(item.updated_at),
        persisted: true,
        messages: known.get(item.id)?.messages ?? null,
      }));
      const serverIds = new Set(action.items.map((i) => i.id));
      const rest = state.conversations.filter((c) => !serverIds.has(c.id));
      return {
        ...state,
        conversations: [...fromServer, ...rest].sort(byRecent),
        nextCursor: action.nextCursor,
        listLoaded: true,
      };
    }
    case "conversationLoaded":
      return {
        ...state,
        conversations: updateConversation(state, action.detail.id, (c) => ({
          ...c,
          title: action.detail.title,
          messages: action.detail.messages.map((m) => ({
            id: m.id,
            role: m.role,
            content: m.content,
            status: m.status,
          })),
        })),
      };
    case "quotaLoaded":
      return {
        ...state,
        quota: { remaining: Math.max(0, action.limit - action.used), limit: action.limit, available: action.available },
      };
    case "send": {
      if (state.streamingId) return state;
      const existing = state.conversations.find((c) => c.id === state.activeId);
      if (existing && existing.messages === null) return state; // historique encore en cours de chargement
      const user: UiMessage = { id: action.userId, role: "user", content: action.text, status: "complete" };
      const assistant: UiMessage = { id: action.assistantId, role: "assistant", content: "", status: "streaming" };
      const conversation: ConversationEntry = existing
        ? { ...existing, updatedAt: action.now, messages: [...(existing.messages ?? []), user, assistant] }
        : {
            id: action.convId,
            title: makeTitle(action.text),
            updatedAt: action.now,
            persisted: false,
            messages: [user, assistant],
          };
      return {
        ...state,
        conversations: [conversation, ...state.conversations.filter((c) => c.id !== conversation.id)],
        activeId: conversation.id,
        streamingId: conversation.id,
        accepted: false,
        toolStatus: null,
        slow: false,
        error: null,
      };
    }
    case "meta": {
      const tempId = state.streamingId;
      if (!tempId) return state;
      return {
        ...state,
        conversations: updateConversation(state, tempId, (c) => ({
          ...c,
          id: action.conversationId,
          persisted: true,
          messages: (c.messages ?? []).map((m, index, all) =>
            index === all.length - 2
              ? { ...m, id: action.userMessageId }
              : index === all.length - 1
                ? { ...m, id: action.assistantMessageId }
                : m,
          ),
        })),
        activeId: state.activeId === tempId ? action.conversationId : state.activeId,
        streamingId: action.conversationId,
        accepted: true,
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
        ...idle,
        conversations: mapStreaming(state, (m) => ({ ...m, status: "complete" })),
        quota:
          action.remaining === null
            ? state.quota
            : { remaining: action.remaining, limit: state.quota?.limit ?? null, available: true },
      };
    case "fail": {
      const quota = quotaAfterError(state.quota, action.error);
      return state.streamingId
        ? { ...endStream(state, action.error), quota }
        : { ...state, error: action.error, quota };
    }
    case "stop":
      return state.streamingId ? endStream(state, null) : state;
    case "setError":
      return { ...state, error: action.error };
    case "dismissError":
      return { ...state, error: null };
  }
}
