# 0002 — Identifiants de compétition lisibles pour le LLM

**Statut :** acceptée (12/11/2026)

## Contexte

Lors de la première passe de V1, `gpt-oss-120b` a appelé la compétition `BL1` (Bundesliga) à la
question « classement de la Ligue 1 » (code attendu : `FL1`), puis a présenté les données comme
celles de la Ligue 1 (S, un cas sur six). Des codes opaques et proches favorisent ce type d'erreur (I).

## Décision

Le modèle ne voit que des identifiants lisibles : `premier-league`, `championship`, `la-liga`,
`serie-a`, `bundesliga`, `ligue-1`, `eredivisie`, `primeira-liga`, `champions-league`,
`brasileirao`. Le backend les convertit en codes football-data.org (`PL`, `ELC`, `PD`, `SA`, `BL1`,
`FL1`, `DED`, `PPL`, `CL`, `BSA`). `EC` et `WC` sont exclus (classement en 404 hors tournoi).

## Conséquences

- Avec les identifiants lisibles : 0 compétition erronée sur 32 appels des deux `gpt-oss` (S, V1).
- Le nom complet de la compétition figure dans l'en-tête de chaque retour d'outil ; le prompt
  demande de signaler toute incohérence avec la question.
- La table de correspondance est à placer dans le backend (phase 3) et testée.
