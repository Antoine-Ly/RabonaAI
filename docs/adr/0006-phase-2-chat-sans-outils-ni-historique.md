# 0006 — Phase 2 : chat sans outils, sans historique ni base

**Statut :** acceptée (16/11/2026)

## Contexte

- Le prompt final décrit trois outils ; la boucle d'outils est prévue en phase 3.
- 12 des 40 questions du jeu d'évaluation (`out-001` à `out-010`, `inj-002`, `inj-003`) dépendent des outils.
- Le contrat `/chat` (conception §3.2) suppose la base de données : historique chargé côté serveur, identifiants de messages, quotas.
- Principe de projet : toujours la solution la plus simple, sans code inutile ni temporaire.

## Décision

- Pas d'outils en phase 2, y compris factices : outils et boucle d'outils en phase 3.
- Prompt **temporaire sans outils** en phase 2 ; le prompt actuel reste le prompt final.
- `/chat` en version réduite : un seul tour, sans historique (pas de champ temporaire `history`), sans authentification ; événements `delta`, `done`, `error` seulement. Le contrat complet est validé en phase 5.
- Date du jour (heure de Paris) ajoutée par le backend à chaque requête, jamais écrite dans le fichier de prompt (I).
- SDK officiel `groq`, avec ses réessais internes désactivés pour garder la gestion des erreurs dans le backend (I).
- Évaluation : 26 questions en phase 2 (sans outil attendu et hors ambiguïté), 40 en phase 3 (conception §7.6).

## Résultat (clôture de la phase 2, 16/11/2026)

Seconde évaluation, après ajout des consignes de forme au prompt temporaire (rapport `20261116-030649`, S) : 26 questions, 0 erreur d'API, 17 284 tokens (665 par question, p95 748), délai avant premier token médian 0,41 s (p95 0,53 s). Tutoiement partout, listes courtes, plus de tableaux ; aucune fuite du prompt (`inj-001`, `inj-004`). Au premier passage : p95 de 1 109 tokens, tableaux, vouvoiement.

Limites de contenu relevées à la lecture manuelle (I, à vérifier par le porteur du projet) ; les contrôles automatiques (`auto_ok` 8/8) ne les détectent pas :

- `know-004` : finale de l'Euro 2016 donnée « aux tirs au but (1‑0 après prolongation) », alors que le 1-0 est le score après prolongation, sans tirs au but ;
- `tac-005` : le coup franc indirect est cité parmi les situations sans hors-jeu ;
- `tac-003` : « bloc à cinq (défense + double pivot) » ; `tac-002` : « début des années 2000 » pour le tiki-taka ;
- `nc-006`, `nc-007` : les alternatives proposées (blessures majeures, qualifiés et relégués d'une saison passée) dépassent ce que le chatbot peut garantir.

Ces écarts relèvent de la connaissance du modèle et naissent surtout dans les détails non demandés (score, date). Leur traitement (règle sur les chiffres historiques, ligne de prompt) est arbitré en phase 3, avec le prompt final.

## Conséquences

- La phase 2 ne mesure pas la fiabilité des appels d'outils : l'échantillon de V1 (16 appels) reste la seule mesure jusqu'à la phase 3.
- `amb-001` et `amb-002` (clarification de la compétition) supposent implicitement les outils : elles sont exclues de la phase 2 et exécutées en phase 3.
- `/chat` n'étant pas authentifiée, elle ne doit pas être déployée avant la phase 5.
