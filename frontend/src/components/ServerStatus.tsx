import { useBackendStatus } from "../hooks/useBackendStatus";

const MESSAGES = {
  waking: "Réveil du serveur en cours. Cela peut prendre jusqu'à une minute.",
  ready: "Le serveur est prêt.",
  unreachable: "Le serveur ne répond pas. Vérifie qu'il est lancé, puis réessaie.",
} as const;

export function ServerStatus() {
  const { status, retry } = useBackendStatus();

  return (
    <p className="server-status" data-status={status} role="status">
      <span className="server-status__dot" aria-hidden="true" />
      <span>{MESSAGES[status]}</span>
      {status === "unreachable" && (
        <button type="button" className="button" onClick={retry}>
          Réessayer
        </button>
      )}
    </p>
  );
}
