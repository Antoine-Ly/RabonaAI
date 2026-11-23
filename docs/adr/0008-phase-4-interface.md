# 0008 — Phase 4 : interface de chat

**Statut :** acceptée (20/11/2026). L'historique en mémoire et le modèle sans mémoire décrits ici ont été remplacés par l'ADR 0009 (phase 5).

## Contexte

- Le cadrage fixait un fond noir et un vert fluo ; le logo généré et les maquettes utilisent des bleus et un turquoise.
- Le contrat `/chat` complet (historique, `meta`, quotas) et les endpoints `/conversations` et `/me/quota` n'existent qu'à partir de la phase 5. Jusqu'alors `/chat` est ouvert, sans historique.
- Principe de projet : la solution la plus simple, sans code inutile.

## Décision

- **Identité (I, choix du porteur du projet)** : thème sombre uniquement ; nuances de noir et de bleu nuit/marine ; un seul accent turquoise `#2dd4a7` (tiré du logo) ; police Inter variable auto-hébergée (`@fontsource-variable/inter`, aucun appel à un CDN de polices). Jetons dans `frontend/src/styles/tokens.css`.
- **Logo** : symbole seul (personnage en « R » et ballon) pour le favicon, l'avatar de l'assistant et les icônes d'installation (tuile bleu nuit) ; le nom « RabonaAI » est du texte, pas une image. Le croisement de jambes de la rabona n'est pas redessiné.
- **Deux écrans** : une fenêtre de connexion (e-mail et mot de passe, sans création de compte ni « mot de passe oublié ») au-dessus d'un décor flouté, puis le chat. Pas de routeur : l'affichage dépend de la session Supabase.
- **Comptes** créés directement dans le tableau de bord Supabase (pas d'e-mail d'invitation, donc pas d'écran « définir le mot de passe »).
- **Chat** : `fetch` + `ReadableStream` (analyseur SSE testé), libellés d'outils, bouton Stop (réponse partielle conservée), rendu Markdown sans HTML brut ni tableaux, copie d'une réponse. Pas de retour d'appréciation, pas de régénération.
- **Historique** : état en mémoire (réducteur testé) ; renommage (édition en place) et suppression avec confirmation. Remplacé par `GET/DELETE/PATCH /conversations` en phase 5 ; `PATCH /conversations/{id}` est à ajouter au contrat **et** à `allow_methods` du CORS.
- **Quota** : compteur toujours visible dès que le serveur le fournit, avec compte à rebours jusqu'à minuit UTC.
- **Installable** : `manifest.webmanifest` et icônes, sans service worker ni mode hors ligne.
- **Tests** : Vitest limité à la logique risquée (analyseur SSE, réducteur, durées) ; aucun test de composants.

## Conséquences

- Sans base, le modèle ne voit que le dernier message : une relance (« et le deuxième ? ») n'a aucun contexte avant la phase 5.
- Le cadrage §2 (couleurs, logo, typographie) est mis à jour.
- Non vérifié visuellement dans un navigateur au moment de la rédaction : à relire en local (I).
