# 0009 — Phase 5 : base de données, authentification, historique et quotas

**Statut :** acceptée (21/11/2026)

## Contexte

La phase 3 laissait `/chat` ouvert, sans historique ni base. La phase 0 avait validé le JWT en ES256, la connexion PostgreSQL par le pooler de session et la requête de quota atomique (V3, `[PASS]`).

## Décision

- **Accès aux données** : SQL direct (SQLAlchemy asynchrone, pilote psycopg 3), sans ORM, derrière une interface `Store` (comme `LLMClient`). `PgStore` est l'implémentation de production ; les routes sont testées avec un faux en mémoire, et `PgStore` avec un vrai PostgreSQL (service de la CI, variable `TEST_DATABASE_URL`, garde-fou sur le nom de base).
- **Connexions** : aucune connexion n'est gardée pendant le streaming ; un tour utilise une transaction avant (quotas, conversation, message de l'utilisateur, historique) et une après (réponse, tokens). `prepare_threshold=None` : compatible avec les deux modes du pooler Supabase.
- **Migrations** : Alembic, une migration initiale **idempotente** (`create … if not exists`) : le schéma de la phase 0 est adopté sans `stamp`.
- **JWT** : signature (ES256/RS256 uniquement), expiration, audience et **émetteur** (`<SUPABASE_URL>/auth/v1`, ajout par rapport à la conception), tolérance d'horloge de 10 s, clés JWKS en cache avec rechargement sur `kid` inconnu. Le `sub` est la seule source d'identité. Toute erreur : `401 unauthorized`.
- **Ordre des contrôles** dans `/chat` : conversation (404) → budget global → réservation du message de l'utilisateur. Le budget global passe **avant** la réservation (écart avec la conception §5.4) : un service saturé ne consomme pas le message de l'utilisateur, et un 404 ne consomme rien.
- **Historique** : les 6 derniers messages de la conversation, hors réponses en erreur (`HISTORY_MAX_MESSAGES=6`, décision du porteur du projet ; la conception en prévoyait 4).
- **Enregistrement des réponses** : à la fin du flux (`complete`). Un flux interrompu (erreur du modèle, bouton Stop, onglet fermé) est enregistré `partial`, via une écriture protégée de l'annulation ; une réponse vide n'est pas enregistrée. Les tokens d'une réponse sans `usage` sont estimés (4 caractères par token) (I).
- **Suppression** : définitive (cascade), pour une conversation comme pour un compte.
- **Contrat** : ajout de `PATCH /conversations/{id}` (renommage, `updated_at` inchangé) ; `PATCH` ajouté au CORS. Le titre est dérivé du premier message côté serveur (même règle qu'au frontend).
- **Frontend** : le serveur est la source de vérité (liste paginée par curseur, messages chargés à l'ouverture, identifiants définitifs via `meta`). Un message refusé avant `meta` (quota, réseau) est retiré de l'écran, puisqu'il n'existe pas côté serveur.

## Conséquences

- Écarts d'estimation à surveiller : avec 6 messages d'historique au lieu de 4, le coût moyen par échange augmente d'environ 400 tokens (I) ; à confirmer sur l'usage réel avant de modifier `GLOBAL_DAILY_TOKENS`.
- Non traités : limiteur par IP (`slowapi`) et purge des conversations inactives (phases 6 et 7).
- À valider avec le vrai projet Supabase : migration, connexion JWKS réelle (le jeton ES256 est vérifié ici avec une clé locale), échange complet.
