/** Décor flouté derrière la fenêtre de connexion : aucune donnée, aucun appel réseau. */
export function FauxChat() {
  return (
    <div className="faux-chat" aria-hidden="true">
      <div className="faux-chat__sidebar">
        <i />
        <i />
        <i />
        <i />
        <i />
      </div>
      <div className="faux-chat__main">
        <i className="faux-chat__user" />
        <b />
        <i className="faux-chat__user" />
        <b />
      </div>
    </div>
  );
}
