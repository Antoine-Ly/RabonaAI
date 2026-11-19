# 0007 — Phase 3 : boucle d'outils, évaluation sur la vraie API, chiffres historiques

**Statut :** acceptée (16/11/2026)

## Contexte

- La seconde évaluation de la phase 2 (ADR 0006) a montré des erreurs de contenu nées dans les détails non demandés (`know-004` : finale de l'Euro 2016 « aux tirs au but (1‑0 après prolongation) »).
- La conception §1 disait « aucun chiffre factuel sans résultat d'outil », alors que le prompt autorisait l'issue d'une finale passée et que `know-001` à `know-008` attendent des scores : incohérence.
- Les outils réels arrivent : il faut décider de la boucle d'outils, de l'évaluation et de l'affichage des horaires.

## Décision

- **Histoire (sans outil)** : répondre uniquement à la question posée, sans ajouter d'information non demandée (score, date, lieu, buteurs) ; si l'utilisateur demande le score, le donner, même si le modèle peut se tromper (non vérifié). Les données courantes passent toujours par un outil.
- **Boucle d'outils** : un seul tour. Si le modèle demande plusieurs appels, ils sont tous exécutés dans la limite de 3 (l'API exige un retour par appel). Le second appel garde les définitions d'outils (comme en V1) ; une nouvelle demande d'outil à ce stade est ignorée, et une réponse vide devient une erreur `llm_unavailable`.
- **Événement `status`** émis dès la phase 3 (un par outil, état `running`), pour que l'interface puisse afficher « consultation des données ».
- **Horaires** : date et heure de Paris pour un match à venir ou en cours, date seule pour un match terminé.
- **Évaluation** : les 40 questions contre la vraie API football-data.org ; les tests automatiques utilisent des fixtures (réponses réelles réduites) et `httpx.MockTransport`.
- **Prompt** : un seul prompt, le final, enrichi des consignes de la phase 2 (tutoiement, réponses courtes sans tableau sauf pour les données, prudence en tactique, refus de partager les instructions) ; le prompt temporaire est supprimé.

## Résultat (évaluation du 18/11/2026, rapport `20261118-023932`, S)

40 questions sur la vraie API : 0 erreur d'API, `tool_accuracy` 12/12 (outils et arguments attendus), 70 847 tokens (1 306 par question sans outil, 2 856 avec ; p95 3 008), délai avant premier token médian 0,54 s (p95 1,68 s). Les retours d'outils sont fidèlement repris (classements, matchs, buteurs). La règle sur l'histoire corrige `know-004` (1-0 après prolongation, sans tirs au but) ; l'erreur sur le hors-jeu de `tac-005` a disparu.

Écarts relevés (I) :

- `out-002` : l'équipe n'est pas nommée et la réponse ajoute une « forme récente V‑V‑V‑V‑V » absente du retour d'outil (le contrôle `must_contain: Arsenal` l'a détecté, pas l'heuristique sur les chiffres, car « 5 » figure ailleurs dans le retour). La consigne « ne cite que ce qui le concerne » y est probablement pour quelque chose ;
- `off-002` : la capitale de l'Australie est donnée au lieu d'un recadrage (au premier passage elle était refusée) ;
- `out-005` : « aucun match dans la période » pendant la trêve internationale (fenêtre `recent` de 7 jours) ;
- coquilles du modèle : « 4‑3‑4‑3 » (`tac-003`), « Brésilianão » (`nc-008`) ;
- l'heuristique des chiffres signalait à tort le « 1 » de « Ligue 1 » (corrigé dans le harnais).

### Seconde évaluation, après ajustement du prompt (rapports `20261118-030837` et `20261118-032138`, S)

- `out-002` : 5 exécutions sur 5 nomment l'équipe et s'en tiennent au retour d'outil (rang, points, bilan).
- 40 questions : 0 erreur d'API, `auto_ok` 18/18, `tool_accuracy` 12/12, refus respectés 8/8, 0 chiffre hors source, 73 091 tokens (p95 3 154), délai avant premier token médian 0,32 s. `off-002` est de nouveau recadrée.

Limites restantes (I, à relire par le porteur du projet), acceptées pour passer à la phase 4 :

- **Erreurs de connaissance en tactique**, malgré la consigne de rester général : `tac-004` attribue le faux 9 de Messi à « Pep Guardiola à Manchester City » (c'était à Barcelone) ; `tac-002` situe le tiki-taka « au début des années 2010 » ; `tac-005` écrit « le deuxième dernier défenseur (généralement le gardien + un défenseur) ». Le prompt ne garantit pas l'exactitude du modèle.
- **Listes tronquées sans le dire** : malgré « sauf pour présenter des données », le modèle plafonne souvent à 5 ou 6 lignes (`out-004`, `out-006`, `inj-002`), parfois avec « et ainsi de suite ». À arbitrer une fois l'interface visible (phase 4).
- **Coquille d'un champ inventé** : `inj-003` écrit « juillet 2026‑2027 » pour la saison.
- **Fenêtre `recent`** portée de 7 à 14 jours : à la trêve internationale, `out-005` répondait « aucun match dans la période » (changement non évalué sur la vraie API).

## Conséquences

- Les erreurs de connaissance du modèle persistent quand l'utilisateur demande un score historique : elles sont acceptées et documentées.
- L'évaluation consomme du quota Groq (≈ 2 700 tokens par question avec outil, I) et des appels football-data.org (limiteur : 8 par minute).
- Une seule bascule de prompt à relire avant l'évaluation complète.
