import { useBackendStatus } from "../hooks/useBackendStatus";

const MESSAGES = {
  waking: "Réveil du serveur en cours, cela peut prendre jusqu'à une minute.",
  ready: "Le serveur est prêt.",
  unreachable: "Le serveur ne répond pas.",
} as const;

/** Réveille le backend (démarrage à froid Render) dès l'affichage et expose son état. */
export function ServerStatus() {
  const { status, retry } = useBackendStatus();

  return (
    <p className="server-status" data-status={status} role="status">
      <span className="server-status__dot" aria-hidden="true" />
      <span>{MESSAGES[status]}</span>
      {status === "unreachable" && (
        <button type="button" className="link-button" onClick={retry}>
          Réessayer
        </button>
      )}
    </p>
  );
}
