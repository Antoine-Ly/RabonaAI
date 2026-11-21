# RabonaAI

Assistant football : classements, résultats, buteurs, histoire et tactique. Projet étudiant
personnel, sans visée commerciale, hébergé sur des offres gratuites (budget cible : 0 €/mois).

Le chatbot ne répond que s'il peut **vérifier** l'information via ses trois outils de données
(classement, matchs, buteurs) ou s'il la maîtrise. Pour le reste (scores en direct, actualité,
statistiques de joueurs, comparaisons), il répond « Je n'ai pas accès à cette information ».

## État du projet

| Phase | Contenu | État |
|---|---|---|
| 0 | Cadrage, vérifications (Groq, football-data.org, Supabase, Render) | Terminée |
| 1 | Squelette du dépôt : backend, frontend, CI, pre-commit, documentation | Terminée |
| 2 | Chat backend sans outils : `LLMClient` (Groq), prompt temporaire, date du jour, route `/chat` en SSE (un seul tour, sans historique ni base), harnais d'évaluation | Terminée |
| 3 | Données football : client, cache, limiteur, trois outils, boucle d'appel d'outils, prompt final, évaluation complète | Terminée |
| 4 | Interface de chat : identité visuelle, connexion, chat en streaming (historique en mémoire, sans base) | Terminée (code), à valider en local |
| 5 | Base de données, authentification, quotas | À faire |
| 6 | Déploiement (Vercel, Render, Supabase) | À faire |

Feuille de route détaillée : [`docs/cadrage.md`](docs/cadrage.md) §10.

## Stack

- **Frontend :** React 19, Vite, TypeScript, `@supabase/supabase-js`, `react-markdown`, police Inter auto-hébergée, tests Vitest (`frontend/`)
- **Backend :** Python 3.14, FastAPI, Pydantic, géré avec [uv](https://docs.astral.sh/uv/) (`backend/`)
- **LLM :** Groq, modèle `openai/gpt-oss-120b` (alternative d'urgence : `openai/gpt-oss-20b`)
- **Données football :** football-data.org (offre gratuite)
- **Base et authentification :** Supabase (PostgreSQL + Auth), accès sur invitation
- **Hébergement :** Vercel (frontend), Render Frankfurt (backend), Supabase Stockholm

## Structure

```text
rabona-ai/
├── backend/
│   ├── app/
│   │   ├── main.py              # application FastAPI (create_app)
│   │   ├── core/                # config (pydantic-settings), format d'erreur
│   │   ├── routes/              # /health, /chat (SSE) ; les autres routes aux phases 4 et 5
│   │   ├── schemas/             # modèles Pydantic des requêtes
│   │   ├── services/            # chat.py (orchestration), llm/ (Groq), football/ (client, cache, outils)
│   │   ├── db/                  # emplacement de la phase 5
│   │   └── prompts/             # prompt système
│   ├── eval/                    # golden_set.jsonl (40 questions), run_eval.py
│   ├── tests/                   # dont fixtures/football (réponses réelles réduites)
│   ├── pyproject.toml  uv.lock  .env.example
├── frontend/
│   ├── src/                     # components, hooks, services, types (contrat d'API), styles
│   ├── package.json  package-lock.json  .env.example
├── docs/                        # cadrage, conception (contrat d'API, SQL), adr/
├── .github/workflows/ci.yml
└── .pre-commit-config.yaml
```

## Prérequis

- Python 3.14 et [uv](https://docs.astral.sh/uv/getting-started/installation/)
- Node.js 22 (LTS) et npm

## Démarrage

### Backend

```bash
cd backend
cp .env.example .env        # PowerShell : Copy-Item .env.example .env
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

`http://localhost:8000/health` doit répondre `{"status":"ok"}` ; la documentation interactive est
sur `http://localhost:8000/docs` (désactivée avec `APP_ENV=prod`). `GROQ_API_KEY` et
`FOOTBALL_DATA_API_KEY` sont nécessaires à ce stade (route `/chat` et évaluation) ; sans la seconde,
les outils répondent « données indisponibles ». `DATABASE_URL` sert à la phase 5.

### Tester `/chat`

La route est ouverte (sans authentification) et ne garde aucun historique : usage local
uniquement, à ne pas déployer avant la phase 5.

Le plus simple : `http://localhost:8000/docs` → `POST /chat` → *Try it out*. La réponse est un flux SSE
(événements `status` quand une donnée football est consultée, `delta`, puis `done` ou `error`) ; Swagger l'affiche d'un bloc, une fois le flux terminé.

Pour voir le flux arriver au fil de l'eau (utile surtout une fois déployé, pour vérifier qu'aucun proxy
ne le met en tampon) : sous PowerShell, `curl` est un alias de `Invoke-WebRequest` ; il faut `curl.exe`,
avec le corps dans un fichier UTF-8 (les guillemets et les accents d'un `-d` en ligne sont altérés) :

```powershell
[System.IO.File]::WriteAllText("$PWD\chat-request.json",
  '{"message":"Qui a remporté la Coupe du monde 2018 ?"}', [System.Text.UTF8Encoding]::new($false))
curl.exe -N -X POST http://localhost:8000/chat -H "Content-Type: application/json" --data-binary "@chat-request.json"
```

Sous bash : `curl -N -X POST http://localhost:8000/chat -H "Content-Type: application/json" -d '{"message": "…"}'`.
Le fichier `chat-request.json` est jetable : ne pas le versionner.

### Évaluation

```bash
cd backend
uv run python -m eval.run_eval --limit 3   # essai rapide
uv run python -m eval.run_eval             # les 40 questions (vraie API football-data.org)
```

Chaque passage consomme le quota Groq de l'organisation (≈ 1 300 tokens par question sans outil,
≈ 2 900 avec : 40 questions ≈ 71 000 tokens, soit ~35 % du quota journalier ; rythme limité à 6 000 tokens/minute). Options : `--ids`, `--category`, `--limit`, `--repeat`, `--max-tokens`. Le rapport
(JSON et Markdown, à relire pour les cas manuels) est écrit dans `backend/eval/results/`, ignoré par git.
Détail : [`docs/conception.md`](docs/conception.md) §7.6.

### Frontend

```bash
cd frontend
cp .env.example .env.local  # PowerShell : Copy-Item .env.example .env.local
npm install
npm run dev
```

Ouvrir `http://localhost:5173` : la fenêtre de connexion réveille le backend (état affiché sous le formulaire).
Il faut renseigner `VITE_SUPABASE_URL` et `VITE_SUPABASE_ANON_KEY` dans `.env.local`, et se connecter avec un
compte créé dans le tableau de bord Supabase (Authentication → Users → Add user, confirmation automatique ;
inscriptions libres désactivées).

Jusqu'à la phase 5, l'historique des conversations n'existe que dans le navigateur (perdu au rechargement) et le
serveur ne reçoit que le dernier message : le modèle n'a pas la mémoire des échanges précédents. Le compteur de
quota apparaît seulement quand le serveur renvoie `quota` dans l'événement `done` (phase 5).

## Qualité

```bash
# backend
cd backend
uv run ruff check .
uv run ruff format --check .
uv run pytest

# frontend
cd frontend
npm run lint
npm run typecheck
npm run test
npm run build
```

La CI GitHub Actions (`.github/workflows/ci.yml`) exécute ces mêmes commandes à chaque push sur
`main` et à chaque pull request. Les versions des actions utilisées (`checkout@v4`, `setup-uv@v5`,
`setup-node@v4`) sont à mettre à jour si GitHub signale des versions obsolètes.

Un hook **pre-commit** (`.pre-commit-config.yaml`) exécute ces mêmes contrôles en local avant chaque
commit, après quelques vérifications de base (espaces en fin de ligne, fin de fichier, YAML, fichiers
volumineux, marqueurs de conflit). Il nécessite `uv sync` et `npm install` au préalable ; installation
unique, depuis la racine du dépôt :

```bash
uv run --directory backend python -m pre_commit install
uv run --directory backend python -m pre_commit run --all-files   # exécution manuelle sur tout le dépôt
```

Les hooks sont locaux et lancés via `python -m` : sous Windows, les lanceurs `.exe` de `pre-commit` et de ses
hooks peuvent être bloqués par Smart App Control.

## Configuration

Toutes les variables sont décrites dans [`backend/.env.example`](backend/.env.example) et
[`frontend/.env.example`](frontend/.env.example). Les fichiers `.env` ne sont **jamais** versionnés.
Le frontend n'expose que des valeurs publiques (`VITE_*`). En production (`APP_ENV=prod`), le backend
refuse de démarrer si une variable obligatoire manque.

## Contrainte de quota

Le palier gratuit de Groq limite l'application à environ **80 échanges par jour** et trois échanges
avec outil par minute (mesures de la phase 0). C'est pourquoi l'accès se fait **sur invitation** et
que des plafonds par utilisateur et globaux sont prévus (phase 5).

## Documentation

- [`docs/cadrage.md`](docs/cadrage.md) : vision, choix techniques, feuille de route
- [`docs/conception.md`](docs/conception.md) : matrice de couverture, outils, contrat d'API, schéma SQL, quotas, évaluation
- [`docs/adr/`](docs/adr/README.md) : décisions d'architecture et résultats mesurés

## Notes

- `npm audit` signale 10 alertes modérées, toutes dans l'outillage de développement (ESLint,
  `minimatch`) ; aucune dans les dépendances de production. À revoir lors des mises à jour d'ESLint.
- Le schéma SQL de référence est dans `docs/conception.md` §6 ; les migrations Alembic arrivent en phase 5.
