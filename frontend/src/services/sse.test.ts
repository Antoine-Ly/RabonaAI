import { describe, expect, it } from "vitest";
import { createSSEParser, readChatEvents, toChatEvent } from "./sse";

const DELTA = 'event: delta\ndata: {"text":"Bonjour"}\n\n';

describe("createSSEParser", () => {
  it("lit plusieurs événements dans un même morceau", () => {
    const parser = createSSEParser();
    const events = parser.push(`${DELTA}event: done\ndata: {"finish_reason":"stop"}\n\n`);
    expect(events.map((e) => e.event)).toEqual(["delta", "done"]);
  });

  it("recolle un événement coupé en plein milieu, y compris dans le séparateur", () => {
    const parser = createSSEParser();
    expect(parser.push("event: delta\ndata: {\"te")).toEqual([]);
    expect(parser.push('xt":"Bonjour"}\r')).toEqual([]);
    expect(parser.push("\n\r\n")).toEqual([{ event: "delta", data: '{"text":"Bonjour"}' }]);
  });

  it("ignore les commentaires et joint les lignes data", () => {
    const parser = createSSEParser();
    const events = parser.push(": keep-alive\nevent: x\ndata: a\ndata: b\n\n");
    expect(events).toEqual([{ event: "x", data: "a\nb" }]);
  });

  it("garde en tampon un bloc non terminé", () => {
    const parser = createSSEParser();
    expect(parser.push(DELTA.trimEnd())).toEqual([]);
    expect(parser.push("\n\n")).toHaveLength(1);
  });

  it("conserve les accents et les caractères multi-octets", () => {
    const parser = createSSEParser();
    const [event] = parser.push('event: delta\ndata: {"text":"Équipe ⚽"}\n\n');
    expect(event && toChatEvent(event)).toEqual({ event: "delta", data: { text: "Équipe ⚽" } });
  });
});

describe("toChatEvent", () => {
  it("rejette un JSON invalide, un événement inconnu et un delta sans texte", () => {
    expect(toChatEvent({ event: "delta", data: "{" })).toBeNull();
    expect(toChatEvent({ event: "inconnu", data: "{}" })).toBeNull();
    expect(toChatEvent({ event: "delta", data: '{"text":3}' })).toBeNull();
  });

  it("accepte status, done et error", () => {
    expect(toChatEvent({ event: "status", data: '{"tool":"get_standings","state":"running"}' })?.event).toBe(
      "status",
    );
    expect(toChatEvent({ event: "error", data: '{"code":"llm_unavailable"}' })?.event).toBe("error");
  });
});

describe("readChatEvents", () => {
  it("décode un flux d'octets découpé au milieu d'un caractère UTF-8", async () => {
    const bytes = new TextEncoder().encode(`${DELTA}event: delta\ndata: {"text":"é"}\n\n`);
    const cut = bytes.indexOf(0xc3) + 1; // sépare les deux octets de « é »
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(bytes.slice(0, cut));
        controller.enqueue(bytes.slice(cut));
        controller.close();
      },
    });
    const texts: string[] = [];
    for await (const event of readChatEvents(stream)) {
      if (event.event === "delta") texts.push(event.data.text);
    }
    expect(texts).toEqual(["Bonjour", "é"]);
  });
});
