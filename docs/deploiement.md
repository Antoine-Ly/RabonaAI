# Déploiement (phase 6)

Frontend sur **Vercel** (Hobby), backend sur **Render** (Web Service gratuit), base et authentification sur **Supabase**. Décisions : ADR 0010. Légende : **(S)** documenté par le fournisseur, **(V)** à vérifier dans le tableau de bord (les libellés changent), **(I)** déduction.

## 0. Avant de commencer

- Le code est poussé sur la branche `main` de GitHub et la CI est verte.
- La migration est appliquée sur Supabase : `cd backend && uv run alembic current` doit afficher `0001 (head)`.
- Les inscriptions libres sont désactivées sur Supabase (Authentication → Sign In / Providers, « Allow new users to sign up ») (V). Elles l'étaient depuis la phase 0 ; à re-vérifier : la clé publique permet sinon à n'importe qui de créer un compte.
- Conseillé : créer une **clé Groq distincte pour la production** (révocable sans toucher à ton environnement local).

Valeurs à avoir sous la main :

| Valeur | Où la trouver |
|---|---|
| `SUPABASE_URL` | Supabase → Project Settings → API : `https://<réf>.supabase.co`, sans rien derrière |
| Clé publique (anon / publishable) | même page ; **jamais** la clé `service_role` |
| `DATABASE_URL` | Supabase → Connect → **Session pooler** (même chaîne que le `.env` local, mot de passe encodé) |
| `GROQ_API_KEY`, `FOOTBALL_DATA_API_KEY` | tes comptes Groq et football-data.org |

## 1. Render (backend)

1. Render → **New → Blueprint** → choisir le dépôt. Render lit `render.yaml` (racine du dépôt) (S).
2. Saisir les variables demandées (`sync: false`). Pour `FRONTEND_URL`, mettre pour l'instant `https://temporaire.invalid` : la vraie URL arrive à l'étape 3.
3. **Région** : `frankfurt` dans `render.yaml`, non modifiable après création (S). À aligner sur la région de ton projet Supabase (Europe de préférence). Si Supabase est ailleurs, change `region` **avant** de valider.
4. Attendre le déploiement (installation avec `uv sync --locked`, Python 3.14 via `.python-version` et `PYTHON_VERSION`) (S).
5. Noter l'URL `https://rabona-backend.onrender.com` (ou celle affichée) et vérifier :
   - `<URL>/health` → `{"status":"ok"}`
   - `<URL>/health/db` → `{"status":"ok"}` (base joignable ; sinon voir §6)

La migration n'est **pas** lancée au déploiement : elle est déjà appliquée (§0). Pour une future migration : `uv run alembic upgrade head` depuis ton poste, avec `DATABASE_URL` de production, **avant** de pousser le code qui en dépend.

## 2. Vercel (frontend)

1. Vercel → **Add New → Project** → importer le dépôt.
2. **Root Directory : `frontend`** (Framework Preset : Vite, détecté) ; `vercel.json` fournit les en-têtes de sécurité.
3. Variables d'environnement (Production) :
   - `VITE_API_URL` = URL Render de l'étape 1 (sans « / » final)
   - `VITE_SUPABASE_URL` = `SUPABASE_URL`
   - `VITE_SUPABASE_ANON_KEY` = clé publique
4. **Deploy**, puis noter l'URL de production (`https://….vercel.app`).

Les variables `VITE_*` sont figées **au moment du build** : après les avoir modifiées, il faut redéployer (Deployments → Redeploy) (I).

## 3. Relier les deux

1. Render → service → Environment → `FRONTEND_URL` = URL Vercel exacte, en `https`, sans « / » final. Le service redémarre.
2. Supabase → Authentication → URL Configuration : *Site URL* = URL Vercel (V). La connexion par mot de passe ne s'en sert pas (I), mais la valeur par défaut `localhost` n'a rien à faire en production.
3. GitHub → Settings → Secrets and variables → Actions → **Variables** → `BACKEND_URL` = URL Render. Lancer le workflow *Ping Supabase* à la main (onglet Actions → Run workflow) : il doit passer au vert.

## 4. Test de recette (URL publique, navigateur privé)

1. Ouvrir l'URL Vercel : fenêtre de connexion, ligne « Réveil du serveur… » puis « Le serveur est prêt ».
2. Se connecter avec un compte existant ; un mauvais mot de passe affiche « E-mail ou mot de passe incorrect ».
3. Poser une question de données (« Où en est la Ligue 1 au classement ? ») : libellé « Consultation du classement… », réponse en flux, compteur de quota décrémenté.
4. Poser une relance dans la même conversation : le contexte est repris.
5. Recharger la page : la conversation est dans l'historique ; la renommer ; la supprimer.
6. Console du navigateur (F12) : **aucune** erreur CORS ni de Content-Security-Policy (le CSP de `vercel.json` n'a pas été testé dans un navigateur : voir §6).
7. Attendre 15 minutes sans rien envoyer, rouvrir l'URL : le serveur se rendort et se réveille en ≈ 30 s (mesuré en phase 0 : 32 s) ; l'interface l'indique.
8. Quota : épuiser les 10 messages (ou baisser temporairement `USER_DAILY_MESSAGES` sur Render) : message « limite atteinte » et compte à rebours.

## 5. Exploitation

- **Journaux** : Render → Logs (les JWT refusés y apparaissent avec le type d'erreur, jamais le jeton).
- **Retour arrière** : Render → Deploys → *Rollback* ; Vercel → Deployments → *Promote to Production* sur un ancien déploiement.
- **Ajouter un utilisateur** : Supabase → Authentication → Users → *Add user* → *Create new user* (e-mail, mot de passe, confirmation automatique). **Le supprimer** efface ses conversations et son compteur (cascade).
- **Limites gratuites** : Render Free ≈ 750 h d'instance par mois (un seul service ne les épuise pas), mise en veille après 15 min, cache football perdu à chaque redémarrage ; Supabase en pause après une semaine d'inactivité (le workflow *Ping Supabase* l'évite ; GitHub désactive les workflows planifiés d'un dépôt resté 60 jours sans activité (S) : lance-le à la main de temps en temps).
- **Rotation d'une clé** : la changer dans Render (le service redémarre) ; pour la clé publique Supabase, aussi dans Vercel puis redéployer.
- **Secrets** : jamais dans Git ni dans une conversation. Une valeur exposée est à régénérer.

## 6. Dépannage

| Symptôme | Cause probable | Remède |
|---|---|---|
| Erreur CORS dans la console | `FRONTEND_URL` ≠ origine réelle (http, « / » final, déploiement de prévisualisation Vercel) | Corriger `FRONTEND_URL` ; les URL de prévisualisation Vercel ne sont pas autorisées (ADR 0010) |
| Service Render « Failed » au démarrage, journal « Variables obligatoires en production » | variable manquante | La renseigner (Environment) |
| `401 unauthorized` après une connexion réussie | `SUPABASE_URL` côté Render ≠ projet utilisé par le frontend, ou horloge | Comparer les deux `SUPABASE_URL` ; journal « JWT refusé : InvalidIssuerError / InvalidAudienceError » |
| `/health/db` en erreur | chaîne `DATABASE_URL` (mode du pooler, mot de passe mal encodé) ou projet Supabase en pause | Reprendre la chaîne « Session pooler » ; réveiller le projet dans Supabase |
| Page blanche + erreur « Content Security Policy » | une origine manque dans `connect-src` (ex. domaine Supabase personnalisé) | L'ajouter dans `frontend/vercel.json`, redéployer |
| Première réponse très lente | démarrage à froid | Normal (≈ 30 s) : l'interface l'indique |
| Build Render : « no open ports detected » | commande de démarrage modifiée | Reprendre `render.yaml` : `--host 0.0.0.0 --port $PORT` |
