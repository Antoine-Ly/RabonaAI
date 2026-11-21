/**
 * Le modèle écrit parfois des espaces insécables fines (U+202F, U+2009) ou insécables (U+00A0), y compris
 * dans les noms (« Real Madrid », « Ligue 1 ») : Inter les affiche presque collées. On les ramène à
 * une espace normale à l'affichage.
 */
export function normalizeSpaces(text: string): string {
  return text.replace(/[\u00A0\u2009\u202F]/g, " ");
}
