import { describe, expect, it } from "vitest";
import type { UiError } from "../lib/errors";
import { type ChatAction, type ChatState, chatReducer, initialChatState, makeTitle } from "./chatReducer";

const ids = { convId: "temp", userId: "u-temp", assistantId: "a-temp", now: 1000 };

function run(actions: ChatAction[], from: ChatState = initialChatState): ChatState {
  return actions.reduce(chatReducer, from);
}

const send = (text: string, extra: Partial<typeof ids> = {}): ChatAction => ({ type: "send", text, ...ids, ...extra });
const meta = (conversationId = "c1"): ChatAction => ({
  type: "meta",
  conversationId,
  userMessageId: "u1",
  assistantMessageId: "a1",
});
const networkError: UiError = { code: "network_error", message: "", retryAfterSeconds: null };
const summary = (id: string, title: string, updated_at: string) => ({ id, title, updated_at });

/** Une conversation serveur déjà ouverte, avec ses messages. */
function loadedConversation(): ChatState {
  return run([
    { type: "listLoaded", items: [summary("c1", "Titre", "2026-11-20T10:00:00Z")], nextCursor: null },
    { type: "select", id: "c1" },
    {
      type: "conversationLoaded",
      detail: {
        id: "c1",
        title: "Titre",
        created_at: "",
        updated_at: "",
        messages: [
          { id: "m1", role: "user", content: "Salut", status: "complete", created_at: "" },
          { id: "m2", role: "assistant", content: "Bonjour", status: "complete", created_at: "" },
        ],
      },
    },
  ]);
}

describe("makeTitle", () => {
  it("tronque et normalise les espaces", () => {
    expect(makeTitle("  Qui   a gagné ? ")).toBe("Qui a gagné ?");
    const title = makeTitle("a".repeat(100));
    expect(title).toHaveLength(40);
    expect(title.endsWith("…")).toBe(true);
  });
});

describe("liste et chargement", () => {
  it("fusionne la liste du serveur, du plus récent au plus ancien, sans perdre les messages déjà chargés", () => {
    const opened = loadedConversation();
    const state = run(
      [
        {
          type: "listLoaded",
          items: [summary("c2", "Récente", "2026-11-21T10:00:00Z"), summary("c1", "Renommée ailleurs", "2026-11-20T10:00:00Z")],
          nextCursor: "suite",
        },
      ],
      opened,
    );
    expect(state.conversations.map((c) => c.title)).toEqual(["Récente", "Renommée ailleurs"]);
    expect(state.conversations[1]?.messages).toHaveLength(2);
    expect(state.conversations[0]?.messages).toBeNull(); // chargés à l'ouverture
    expect(state.nextCursor).toBe("suite");
    expect(state.listLoaded).toBe(true);
  });

  it("charge les messages d'une conversation et leurs statuts", () => {
    const state = loadedConversation();
    expect(state.conversations[0]?.messages?.map((m) => [m.role, m.status])).toEqual([
      ["user", "complete"],
      ["assistant", "complete"],
    ]);
  });

  it("calcule le quota restant à partir de la consommation", () => {
    expect(run([{ type: "quotaLoaded", used: 3, limit: 10, available: true }]).quota).toEqual({
      remaining: 7,
      limit: 10,
      available: true,
    });
    expect(run([{ type: "quotaLoaded", used: 12, limit: 10, available: false }]).quota?.remaining).toBe(0);
  });

  it("refuse d'envoyer tant que l'historique de la conversation ouverte n'est pas chargé", () => {
    const state = run([
      { type: "listLoaded", items: [summary("c1", "T", "2026-11-20T10:00:00Z")], nextCursor: null },
      { type: "select", id: "c1" },
      send("trop tôt"),
    ]);
    expect(state.streamingId).toBeNull();
  });
});

describe("envoi et réception", () => {
  it("crée une conversation provisoire, puis adopte les identifiants du serveur (`meta`)", () => {
    const state = run([send("Bonjour"), meta()]);
    expect(state.activeId).toBe("c1");
    expect(state.streamingId).toBe("c1");
    expect(state.accepted).toBe(true);
    const conversation = state.conversations[0];
    expect(conversation).toMatchObject({ id: "c1", persisted: true, title: "Bonjour" });
    expect(conversation?.messages?.map((m) => [m.id, m.role])).toEqual([
      ["u1", "user"],
      ["a1", "assistant"],
    ]);
  });

  it("ignore un second envoi pendant la réception", () => {
    const state = run([send("un"), send("deux", { convId: "t2", userId: "u2", assistantId: "a2" })]);
    expect(state.conversations).toHaveLength(1);
  });

  it("assemble les fragments puis termine et met à jour le quota", () => {
    const state = run([
      send("Salut"),
      meta(),
      { type: "status", tool: "get_standings", state: "running" },
      { type: "delta", text: "Bon" },
      { type: "delta", text: "jour" },
      { type: "done", remaining: 7 },
    ]);
    expect(state.conversations[0]?.messages?.at(-1)).toMatchObject({ content: "Bonjour", status: "complete" });
    expect(state).toMatchObject({ streamingId: null, accepted: false, toolStatus: null });
    expect(state.quota).toEqual({ remaining: 7, limit: null, available: true });
  });

  it("garde le quota connu quand `done` n'en donne pas", () => {
    const from = { ...initialChatState, quota: { remaining: 3, limit: 10, available: true } };
    const state = run([send("a"), meta(), { type: "done", remaining: null }], from);
    expect(state.quota).toEqual({ remaining: 3, limit: 10, available: true });
  });

  it("ajoute à la conversation ouverte, avec son identifiant serveur", () => {
    const state = run([send("Et ensuite ?"), meta("c1")], loadedConversation());
    expect(state.conversations).toHaveLength(1);
    expect(state.conversations[0]?.messages).toHaveLength(4);
  });

  it("démarre une nouvelle conversation après `new`", () => {
    const state = run([{ type: "new" }, send("autre"), meta("c2")], loadedConversation());
    expect(state.conversations.map((c) => c.id)).toEqual(["c2", "c1"]);
  });
});

describe("arrêts et erreurs", () => {
  it("conserve une réponse partielle si le serveur avait accepté le message", () => {
    const state = run([send("a"), meta(), { type: "delta", text: "Début" }, { type: "fail", error: networkError }]);
    expect(state.conversations[0]?.messages?.at(-1)).toMatchObject({ content: "Début", status: "partial" });
    expect(state.error).toEqual(networkError);
    expect(state.streamingId).toBeNull();
  });

  it("supprime la réponse vide mais garde la question quand le serveur l'a acceptée", () => {
    const failed = run([send("a"), meta(), { type: "fail", error: networkError }]);
    expect(failed.conversations[0]?.messages).toHaveLength(1);
    const stopped = run([send("a"), meta(), { type: "stop" }]);
    expect(stopped.conversations[0]?.messages).toHaveLength(1);
    expect(stopped.error).toBeNull();
  });

  it("retire entièrement une nouvelle conversation refusée avant `meta` (quota, réseau)", () => {
    const state = run([send("a"), { type: "fail", error: networkError }]);
    expect(state.conversations).toEqual([]);
    expect(state.activeId).toBeNull();
    expect(state.error).toEqual(networkError);
  });

  it("retire le tour refusé avant `meta` d'une conversation existante, sans toucher au reste", () => {
    const state = run([send("refusé"), { type: "fail", error: networkError }], loadedConversation());
    expect(state.conversations[0]?.messages?.map((m) => m.id)).toEqual(["m1", "m2"]);
    expect(state.activeId).toBe("c1");
  });

  it("une limite quotidienne atteinte met le compteur à zéro ; un service saturé le signale", () => {
    const limit: UiError = { code: "quota_user_daily", message: "", retryAfterSeconds: 3600 };
    expect(run([send("a"), { type: "fail", error: limit }]).quota).toEqual({ remaining: 0, limit: null, available: true });
    const saturated: UiError = { code: "quota_global_daily", message: "", retryAfterSeconds: 3600 };
    const from = { ...initialChatState, quota: { remaining: 4, limit: 10, available: true } };
    expect(run([send("a"), { type: "fail", error: saturated }], from).quota).toEqual({ remaining: 4, limit: 10, available: false });
  });

  it("une erreur hors flux n'interrompt pas une réponse en cours", () => {
    const state = run([send("a"), meta(), { type: "setError", error: networkError }]);
    expect(state.streamingId).toBe("c1");
    expect(state.error).toEqual(networkError);
  });
});

describe("renommer et supprimer", () => {
  it("renomme (titre nettoyé, vide refusé)", () => {
    const base = loadedConversation();
    expect(run([{ type: "rename", id: "c1", title: "  Mon   titre " }], base).conversations[0]?.title).toBe("Mon titre");
    expect(run([{ type: "rename", id: "c1", title: "   " }], base).conversations[0]?.title).toBe("Titre");
  });

  it("supprime la conversation ouverte", () => {
    const state = run([{ type: "remove", id: "c1" }], loadedConversation());
    expect(state.conversations).toEqual([]);
    expect(state.activeId).toBeNull();
  });

  it("supprimer la conversation en cours de réponse libère le flux", () => {
    const state = run([send("a"), meta(), { type: "remove", id: "c1" }, { type: "delta", text: "tardif" }]);
    expect(state).toMatchObject({ streamingId: null, accepted: false, conversations: [] });
  });
});
