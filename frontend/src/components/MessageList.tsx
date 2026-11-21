import { useLayoutEffect, useRef, useState } from "react";
import Markdown from "react-markdown";
import { describeTool } from "../lib/errors";
import { normalizeSpaces } from "../lib/text";
import type { UiMessage } from "../state/chatReducer";
import { CheckIcon, CopyIcon } from "./icons";
import { LogoMark } from "./Logo";

interface Props {
  messages: UiMessage[];
  toolStatus: string | null;
  slow: boolean;
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // presse-papiers refusé (contexte non sécurisé, permission) : rien à faire
    }
  }
  return (
    <button type="button" className="button button--small" onClick={() => void copy()}>
      {copied ? <CheckIcon size={15} /> : <CopyIcon size={15} />}
      {copied ? "Copié" : "Copier"}
    </button>
  );
}

function Pending({ toolStatus, slow }: { toolStatus: string | null; slow: boolean }) {
  if (toolStatus) return <p className="pending">{describeTool(toolStatus)}</p>;
  if (slow) return <p className="pending">Le serveur se réveille, cela peut prendre jusqu'à une minute…</p>;
  return (
    <p className="pending" aria-label="Réponse en cours">
      <span className="dots" aria-hidden="true">
        <i />
        <i />
        <i />
      </span>
    </p>
  );
}

export function MessageList({ messages, toolStatus, slow }: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const streaming = messages.at(-1)?.status === "streaming";

  // Suit le bas de la conversation, sauf si la personne a remonté pour relire.
  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (el && el.scrollHeight - el.scrollTop - el.clientHeight < 160) el.scrollTop = el.scrollHeight;
  });

  return (
    <div className="messages" ref={scrollRef} role="log" aria-live="polite" aria-busy={streaming}>
      <div className="messages__col">
        {messages.map((m) =>
          m.role === "user" ? (
            <div key={m.id} className="msg msg--user">
              {m.content}
            </div>
          ) : (
            <div key={m.id} className="msg msg--assistant">
              <LogoMark size={34} />
              <div className="msg__body">
                {m.status === "streaming" && m.content === "" ? (
                  <Pending toolStatus={toolStatus} slow={slow} />
                ) : (
                  <div className="markdown">
                    <Markdown>{normalizeSpaces(m.content)}</Markdown>
                  </div>
                )}
                {m.status === "partial" && <p className="msg__note">Réponse interrompue.</p>}
                {m.status !== "streaming" && m.content !== "" && (
                  <div className="msg__actions">
                    <CopyButton text={normalizeSpaces(m.content)} />
                  </div>
                )}
              </div>
            </div>
          ),
        )}
      </div>
    </div>
  );
}
