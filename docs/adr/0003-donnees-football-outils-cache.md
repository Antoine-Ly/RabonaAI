# 0003 — Données football : trois outils, fenêtres de dates, cache et limiteur

**Statut :** acceptée (12/11/2026)

## Contexte (V2, S)

- 12 compétitions listées (`TIER_ONE`), dont 10 avec classement accessible ; l'offre gratuite
  limite à 10 appels par minute.
- Tous les matchs terminés d'une compétition : 92 à 103 Ko ; une fenêtre de quelques jours :
  9 à 10 Ko.
- Classement Ligue 1 : ≈ 5,1 Ko de JSON (≈ 1 285 tokens estimés) contre ≈ 134 tokens en format compact.
- Statuts de match observés : `FINISHED` et `TIMED`.

## Décision

- Trois outils : `get_standings`, `get_matches`, `get_top_scorers`, avec retours en texte compact.
- `get_matches` : `recent` = 7 jours passés ; `upcoming` = 14 jours à venir ; `matchday` = journée donnée.
  Jamais l'historique complet.
- Scores masqués pour les matchs en cours (pas de direct). Fenêtre vide : message explicite.
- Statistiques de joueurs non exposées (`assists`, `penalties` ignorés) ; comparaisons refusées.
- Cache TTL en mémoire (classement 15 min, matchs 10 min, buteurs 60 min) et limiteur global à
  8 appels par minute (I).

## Conséquences

- Un retour d'outil coûte une centaine de tokens, ce qui garde un échange sous 3 000 tokens.
- Le cache est perdu à chaque redémarrage de Render : acceptable en v1.
