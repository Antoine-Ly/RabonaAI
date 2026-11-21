import type { ChatEvent } from "../types/api";

export interface RawSSEEvent {
  event: string;
  data: string;
}

/**
 * Analyseur incrémental de `text/event-stream`, limité aux champs `event:` et `data:`.
 * Les blocs sont séparés par une ligne vide ; un bloc incomplet reste en tampon jusqu'au morceau suivant.
 */
export function createSSEParser() {
  let buffer = "";
  return {
    push(chunk: string): RawSSEEvent[] {
      buffer += chunk;
      const events: RawSSEEvent[] = [];
      for (;;) {
        const match = /\r?\n\r?\n/.exec(buffer);
        if (!match) break;
        const block = buffer.slice(0, match.index);
        buffer = buffer.slice(match.index + match[0].length);
        let event = "message";
        const data: string[] = [];
        for (const line of block.split(/\r?\n/)) {
          if (line.startsWith(":")) continue; // commentaire (keep-alive)
          const colon = line.indexOf(":");
          const field = colon === -1 ? line : line.slice(0, colon);
          const value = colon === -1 ? "" : line.slice(colon + 1).replace(/^ /, "");
          if (field === "event") event = value;
          else if (field === "data") data.push(value);
        }
        if (data.length > 0) events.push({ event, data: data.join("\n") });
      }
      return events;
    },
  };
}

/** Convertit un bloc brut en événement typé ; `null` si l'événement est inconnu ou mal formé. */
export function toChatEvent(raw: RawSSEEvent): ChatEvent | null {
  let data: unknown;
  try {
    data = JSON.parse(raw.data);
  } catch {
    return null;
  }
  if (typeof data !== "object" || data === null) return null;
  switch (raw.event) {
    case "meta":
    case "status":
    case "done":
    case "error":
      return { event: raw.event, data } as ChatEvent;
    case "delta":
      return "text" in data && typeof data.text === "string"
        ? { event: "delta", data: { text: data.text } }
        : null;
    default:
      return null;
  }
}

/** Lit un flux d'octets SSE et produit les événements du contrat, dans l'ordre. */
export async function* readChatEvents(body: ReadableStream<Uint8Array>): AsyncGenerator<ChatEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder(); // `stream: true` : un caractère UTF-8 coupé entre deux morceaux est recollé
  const parser = createSSEParser();
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) return;
      for (const raw of parser.push(decoder.decode(value, { stream: true }))) {
        const event = toChatEvent(raw);
        if (event) yield event;
      }
    }
  } finally {
    await reader.cancel().catch(() => undefined);
  }
}
