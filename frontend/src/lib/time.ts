/** Début du prochain jour UTC : la journée des quotas est en UTC (docs/conception.md §5.1). */
export function nextUtcMidnight(now: Date): Date {
  return new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() + 1));
}

/** Durée lisible en français, arrondie par excès : « 45 s », « 12 min », « 4 h 12 ». */
export function formatDuration(totalSeconds: number): string {
  if (totalSeconds < 60) return `${Math.max(1, Math.ceil(totalSeconds))} s`;
  const minutes = Math.ceil(totalSeconds / 60);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest === 0 ? `${hours} h` : `${hours} h ${String(rest).padStart(2, "0")}`;
}
