import { useNow } from "../hooks/useNow";
import { formatDuration, nextUtcMidnight } from "../lib/time";
import type { QuotaInfo } from "../state/chatReducer";

const timeFormat = new Intl.DateTimeFormat("fr-FR", { hour: "2-digit", minute: "2-digit" });

/** Messages restants aujourd'hui et compte à rebours jusqu'à la réinitialisation (minuit UTC). */
export function QuotaBadge({ quota }: { quota: QuotaInfo | null }) {
  const now = useNow(30_000);
  if (!quota) return null;
  const reset = nextUtcMidnight(now);
  const countdown = formatDuration((reset.getTime() - now.getTime()) / 1000);
  const count = quota.limit === null ? `${quota.remaining}` : `${quota.remaining} / ${quota.limit}`;
  const label = quota.limit === null ? "restants aujourd'hui" : "messages aujourd'hui";
  return (
    <p
      className="quota"
      data-empty={quota.remaining === 0}
      title={`Réinitialisation à ${timeFormat.format(reset)} (heure locale)`}
    >
      <span>
        <b>{count}</b> {label}
      </span>
      <span className="quota__sep" aria-hidden="true">
        ·
      </span>
      <span>retour dans {countdown}</span>
    </p>
  );
}
