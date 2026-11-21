import { useEffect, useState } from "react";
import { AccountMenu } from "../components/AccountMenu";
import { Composer } from "../components/Composer";
import { MenuIcon } from "../components/icons";
import { LogoMark, Wordmark } from "../components/Logo";
import { MessageList } from "../components/MessageList";
import { QuotaBadge } from "../components/QuotaBadge";
import { Sidebar } from "../components/Sidebar";
import { Welcome } from "../components/Welcome";
import { useChat } from "../hooks/useChat";
import { describeError } from "../lib/errors";

interface Props {
  email: string;
  getToken: () => Promise<string | null>;
  onSignOut: () => void;
}

const DESKTOP = "(min-width: 801px)";

export function ChatPage({ email, getToken, onSignOut }: Props) {
  const { state, dispatch, send, stop } = useChat(getToken, onSignOut);
  const [sidebarOpen, setSidebarOpen] = useState(() => window.matchMedia(DESKTOP).matches);

  const active = state.conversations.find((c) => c.id === state.activeId);
  const streaming = state.streamingId !== null;
  const blocked = state.quota?.remaining === 0;

  // Sur mobile, la barre latérale est un tiroir : on la ferme après un choix.
  const closeIfDrawer = () => {
    if (!window.matchMedia(DESKTOP).matches) setSidebarOpen(false);
  };

  // Échap ferme le tiroir (mobile).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !window.matchMedia(DESKTOP).matches) setSidebarOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="app">
      <Sidebar
        conversations={state.conversations}
        activeId={state.activeId}
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        onNew={() => {
          dispatch({ type: "new" });
          closeIfDrawer();
        }}
        onSelect={(id) => {
          dispatch({ type: "select", id });
          closeIfDrawer();
        }}
        onRename={(id, title) => dispatch({ type: "rename", id, title })}
        onRemove={(id) => {
          if (id === state.streamingId) stop();
          dispatch({ type: "remove", id });
        }}
      />

      <main className="main">
        <header className="topbar">
          <div className="topbar__left">
            {!sidebarOpen && (
              <>
                <button
                  type="button"
                  className="icon-button"
                  aria-label="Ouvrir l'historique"
                  onClick={() => setSidebarOpen(true)}
                >
                  <MenuIcon />
                </button>
                <span className="brand brand--compact">
                  <LogoMark size={30} />
                  <Wordmark />
                </span>
              </>
            )}
          </div>
          <div className="topbar__right">
            <QuotaBadge quota={state.quota} />
            <AccountMenu email={email} onSignOut={onSignOut} />
          </div>
        </header>

        {active ? (
          <MessageList messages={active.messages} toolStatus={state.toolStatus} slow={state.slow} />
        ) : (
          <div className="messages">
            <Welcome disabled={streaming || blocked} onPick={(text) => void send(text)} />
          </div>
        )}

        {state.error && (
          <div className="banner" role="alert">
            <span>{describeError(state.error)}</span>
            <button type="button" className="link-button" onClick={() => dispatch({ type: "dismissError" })}>
              Fermer
            </button>
          </div>
        )}
        <Composer streaming={streaming} blocked={blocked} onSend={(text) => void send(text)} onStop={stop} />
      </main>
    </div>
  );
}
