import { type KeyboardEvent, useLayoutEffect, useRef, useState } from "react";
import { SendIcon, StopIcon } from "./icons";

/** Longueur maximale d'un message (docs/conception.md §3.2). */
export const MAX_MESSAGE_CHARS = 2000;

interface Props {
  streaming: boolean;
  blocked: boolean;
  onSend: (text: string) => void;
  onStop: () => void;
}

export function Composer({ streaming, blocked, onSend, onStop }: Props) {
  const [value, setValue] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);
  const canSend = !streaming && !blocked && value.trim() !== "";

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [value]);

  function submit() {
    if (!canSend) return;
    onSend(value.trim());
    setValue("");
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <div className="composer">
      <div className="composer__box">
        <textarea
          ref={ref}
          className="composer__input"
          rows={1}
          maxLength={MAX_MESSAGE_CHARS}
          value={value}
          placeholder={blocked ? "Limite de messages atteinte pour aujourd'hui" : "Pose ta question sur le football…"}
          aria-label="Ton message"
          disabled={blocked}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
        />
        {streaming ? (
          <button type="button" className="send" aria-label="Arrêter la réponse" onClick={onStop}>
            <StopIcon />
          </button>
        ) : (
          <button type="button" className="send" aria-label="Envoyer" disabled={!canSend} onClick={submit}>
            <SendIcon />
          </button>
        )}
      </div>
      {value.length > MAX_MESSAGE_CHARS - 200 && (
        <p className="composer__count" data-limit={value.length >= MAX_MESSAGE_CHARS}>
          {value.length} / {MAX_MESSAGE_CHARS}
        </p>
      )}
      <p className="composer__legal">
        RabonaAI est une IA et peut faire des erreurs. Pas de scores en direct, d'actualité ni de statistiques de
        joueurs.
      </p>
    </div>
  );
}
