import { describe, expect, it } from "vitest";
import type { UiError } from "../lib/errors";
import { type ChatAction, type ChatState, chatReducer, initialChatState, makeTitle } from "./chatReducer";

const ids = { convId: "c1", userId: "u1", assistantId: "a1", now: 1000 };

function run(actions: ChatAction[], from: ChatState = initialChatState): ChatState {
  return actions.reduce(chatReducer, from);
}

const send = (text: string, extra: Partial<typeof ids> = {}): ChatAction => ({
  type: "send",
  text,
  ...ids,
  ...extra,
});

const networkError: UiError = { code: "network_error", message: "", retryAfterSeconds: null };

describe("makeTitle", () => {
  it("tronque et normalise les espaces", () => {
    expect(makeTitle("  Qui   a gagné ? ")).toBe("Qui a gagné ?");
    const title = makeTitle("a".repeat(100));
    expect(title).toHaveLength(40);
    expect(title.endsWith("…")).toBe(true);
  });
});

describe("chatReducer", () => {
  it("crée une conversation à l'envoi et la place en tête", () => {
    const state = run([send("Bonjour")]);
    expect(state.activeId).toBe("c1");
    expect(state.streamingId).toBe("c1");
    expect(state.conversations[0]?.messages.map((m) => [m.role, m.status])).toEqual([
      ["user", "complete"],
      ["assistant", "streaming"],
    ]);
  });

  it("ignore un second envoi pendant la réception", () => {
    const state = run([send("un"), send("deux", { convId: "c2", userId: "u2", assistantId: "a2" })]);
    expect(state.conversations).toHaveLength(1);
  });

  it("assemble les fragments puis termine et met à jour le quota", () => {
    const state = run([
      send("Salut"),
      { type: "status", tool: "get_standings", state: "running" },
      { type: "delta", text: "Bon" },
      { type: "delta", text: "jour" },
      { type: "done", remaining: 7 },
    ]);
    const last = state.conversations[0]?.messages.at(-1);
    expect(last).toMatchObject({ content: "Bonjour", status: "complete" });
    expect(state.streamingId).toBeNull();
    expect(state.toolStatus).toBeNull();
    expect(state.quota).toEqual({ remaining: 7, limit: null });
  });

  it("garde le quota connu quand `done` n'en donne pas", () => {
    const state = run([send("a"), { type: "done", remaining: null }], {
      ...initialChatState,
      quota: { remaining: 3, limit: 10 },
    });
    expect(state.quota).toEqual({ remaining: 3, limit: 10 });
  });

  it("conserve une réponse partielle en cas d'erreur", () => {
    const state = run([send("a"), { type: "delta", text: "Début" }, { type: "fail", error: networkError }]);
    expect(state.conversations[0]?.messages.at(-1)).toMatchObject({ content: "Début", status: "partial" });
    expect(state.error).toEqual(networkError);
    expect(state.streamingId).toBeNull();
  });

  it("supprime la réponse vide en cas d'erreur ou d'arrêt", () => {
    const failed = run([send("a"), { type: "fail", error: networkError }]);
    expect(failed.conversations[0]?.messages).toHaveLength(1);
    const stopped = run([send("a"), { type: "stop" }]);
    expect(stopped.conversations[0]?.messages).toHaveLength(1);
    expect(stopped.error).toBeNull();
  });

  it("ajoute à la conversation active, sans en créer une autre", () => {
    const state = run([send("a"), { type: "done", remaining: null }, send("b", { convId: "c2", userId: "u2", assistantId: "a2" })]);
    expect(state.conversations).toHaveLength(1);
    expect(state.conversations[0]?.messages).toHaveLength(4);
  });

  it("démarre une nouvelle conversation après `new`", () => {
    const state = run([send("a"), { type: "done", remaining: null }, { type: "new" }, send("b", { convId: "c2", userId: "u2", assistantId: "a2" })]);
    expect(state.conversations.map((c) => c.id)).toEqual(["c2", "c1"]);
  });

  it("renomme (titre nettoyé, vide refusé) et supprime", () => {
    const base = run([send("Titre"), { type: "done", remaining: null }]);
    expect(run([{ type: "rename", id: "c1", title: "  Mon   titre " }], base).conversations[0]?.title).toBe("Mon titre");
    expect(run([{ type: "rename", id: "c1", title: "   " }], base).conversations[0]?.title).toBe("Titre");
    const removed = run([{ type: "remove", id: "c1" }], base);
    expect(removed.conversations).toEqual([]);
    expect(removed.activeId).toBeNull();
  });

  it("supprimer la conversation en cours de réponse libère le flux", () => {
    const state = run([send("a"), { type: "remove", id: "c1" }, { type: "delta", text: "tardif" }]);
    expect(state.streamingId).toBeNull();
    expect(state.conversations).toEqual([]);
  });
});
