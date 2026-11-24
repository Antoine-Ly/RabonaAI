# 0010 — Phase 6 : déploiement

**Statut :** acceptée (23/11/2026)

## Contexte

Hébergement validé au cadrage : Vercel (frontend), Render gratuit (backend), Supabase gratuit. Contraintes mesurées en phase 0 : démarrage à froid de Render ≈ 32 s, veille après 15 min ; Supabase gratuit mis en pause après une semaine d'inactivité.

## Décision

- **Render par Blueprint** (`render.yaml` à la racine, `rootDir: backend`) : configuration versionnée, secrets saisis dans le tableau de bord (`sync: false`). Installation `uv sync --locked --no-dev` (Render fournit uv quand `uv.lock` est présent) ; Python 3.14 (`.python-version` et `PYTHON_VERSION`) ; démarrage `uv run --no-sync uvicorn … --host 0.0.0.0 --port $PORT`. Les clés du fichier ont été relues dans la documentation Render ; le fichier n'a pas pu être validé par le validateur de Render (I).
- **Région `frankfurt`** (seule région européenne de Render), à confirmer par rapport au projet Supabase avant création : elle n'est plus modifiable ensuite.
- **Déploiement automatique** seulement si la CI GitHub est verte (`autoDeployTrigger: checksPass`).
- **Migrations manuelles**, depuis le poste du porteur du projet, avant de pousser le code qui en dépend : une migration ne s'exécute pas à chaque redémarrage d'un service qui se réveille toutes les 15 minutes.
- **Pas de maintien en éveil de Render** : le démarrage à froid est accepté et géré par l'interface (état « réveil du serveur » dès la connexion). Un ping toutes les 10 minutes consommerait presque tout le quota mensuel d'heures gratuites (≈ 744 h sur 750) (I).
- **Ping Supabase** : workflow GitHub Actions tous les 3 jours vers `GET /health/db` (requête `select 1`), activé par la variable de dépôt `BACKEND_URL`. Il sert aussi de test de déploiement. Que cette activité suffise à éviter la pause est à vérifier (V).
- **Sécurité du frontend** (`vercel.json`) : `nosniff`, `X-Frame-Options: DENY`, politique de référent, et un Content-Security-Policy strict (`script-src 'self'`, connexions limitées à `*.onrender.com` et `*.supabase.co`). Le build ne contient aucun script en ligne ; le CSP n'a pas été essayé dans un navigateur (I).
- **Origine CORS unique** : `FRONTEND_URL` (normalisée, sans « / » final). Les déploiements de prévisualisation Vercel ne sont pas autorisés ; domaines `*.vercel.app` et `*.onrender.com`, sans domaine personnalisé.

## Conséquences

- Premier démarrage après 15 minutes d'inactivité : ≈ 30 s de latence, signalée dans l'interface.
- Sans la variable `BACKEND_URL`, le workflow de ping ne fait rien : à créer à l'étape 3 de `docs/deploiement.md`.
- Hors périmètre, à décider plus tard : domaine personnalisé, limiteur par IP (`slowapi`), purge des conversations inactives, supervision externe.
