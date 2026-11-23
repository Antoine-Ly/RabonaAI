import { type KeyboardEvent, useState } from "react";
import type { ConversationEntry } from "../state/chatReducer";
import { CheckIcon, CloseIcon, CollapseIcon, PencilIcon, PlusIcon, TrashIcon } from "./icons";
import { LogoMark, Wordmark } from "./Logo";

interface Props {
  conversations: ConversationEntry[];
  activeId: string | null;
  open: boolean;
  onClose: () => void;
  onNew: () => void;
  onSelect: (id: string) => void;
  onRename: (id: string, title: string) => void;
  onRemove: (id: string) => void;
  /** Liste lue depuis le serveur. */
  loaded: boolean;
  hasMore: boolean;
  onLoadMore: () => void;
}

export function Sidebar({
  conversations,
  activeId,
  open,
  onClose,
  onNew,
  onSelect,
  onRename,
  onRemove,
  loaded,
  hasMore,
  onLoadMore,
}: Props) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [confirmId, setConfirmId] = useState<string | null>(null);

  function commitRename(id: string, value: string) {
    onRename(id, value); // un titre vide est ignoré par le réducteur
    setEditingId(null);
  }

  function handleEditKey(event: KeyboardEvent<HTMLInputElement>, id: string) {
    if (event.key === "Enter") commitRename(id, event.currentTarget.value);
    if (event.key === "Escape") setEditingId(null);
  }

  return (
    <>
      <button
        type="button"
        className="scrim"
        data-open={open}
        tabIndex={-1}
        aria-label="Fermer l'historique"
        onClick={onClose}
      />
      <aside className="sidebar" data-open={open} aria-label="Conversations" inert={!open}>
        <div className="sidebar__head">
          <div className="brand">
            <LogoMark size={36} />
            <Wordmark />
          </div>
          <button type="button" className="icon-button" aria-label="Replier la barre latérale" onClick={onClose}>
            <CollapseIcon />
          </button>
        </div>

        <button type="button" className="button button--outline" onClick={onNew}>
          <PlusIcon size={16} /> Nouvelle conversation
        </button>

        <h2 className="sidebar__title">Historique</h2>
        {conversations.length === 0 ? (
          <p className="sidebar__empty">{loaded ? "Tes conversations apparaîtront ici." : "Chargement…"}</p>
        ) : (
          <ul className="history">
            {conversations.map((c) => (
              <li key={c.id} className="history__item" data-active={c.id === activeId}>
                {editingId === c.id ? (
                  <input
                    className="history__edit"
                    aria-label="Nouveau titre"
                    defaultValue={c.title}
                    maxLength={120}
                    autoFocus
                    onKeyDown={(e) => handleEditKey(e, c.id)}
                    onBlur={(e) => commitRename(c.id, e.currentTarget.value)}
                  />
                ) : confirmId === c.id ? (
                  <div className="history__confirm" role="group" aria-label={`Supprimer « ${c.title} » ?`}>
                    <span>Supprimer ?</span>
                    <button
                      type="button"
                      className="icon-button icon-button--small icon-button--danger"
                      aria-label="Confirmer la suppression"
                      onClick={() => {
                        setConfirmId(null);
                        onRemove(c.id);
                      }}
                    >
                      <CheckIcon size={15} />
                    </button>
                    <button
                      type="button"
                      className="icon-button icon-button--small"
                      aria-label="Annuler"
                      onClick={() => setConfirmId(null)}
                    >
                      <CloseIcon size={15} />
                    </button>
                  </div>
                ) : (
                  <>
                    <button
                      type="button"
                      className="history__title"
                      aria-current={c.id === activeId ? "true" : undefined}
                      onClick={() => onSelect(c.id)}
                    >
                      {c.title}
                    </button>
                    <span className="history__actions">
                      <button
                        type="button"
                        className="icon-button icon-button--small"
                        aria-label={`Renommer « ${c.title} »`}
                        onClick={() => setEditingId(c.id)}
                      >
                        <PencilIcon size={15} />
                      </button>
                      <button
                        type="button"
                        className="icon-button icon-button--small"
                        aria-label={`Supprimer « ${c.title} »`}
                        onClick={() => setConfirmId(c.id)}
                      >
                        <TrashIcon size={15} />
                      </button>
                    </span>
                  </>
                )}
              </li>
            ))}
          </ul>
        )}
        {hasMore && (
          <button type="button" className="button button--small" onClick={onLoadMore}>
            Afficher plus
          </button>
        )}
      </aside>
    </>
  );
}
