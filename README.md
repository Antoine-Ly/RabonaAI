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
| 2 | Chat backend sans outils : `LLMClient` (Groq), prompt temporaire, date du jour, route `/chat` en SSE (un seul tour, sans historique ni base), harnais d'évaluation | À faire |
| 3 | Données football : client, cache, limiteur, trois outils, boucle d'appel d'outils, prompt final, évaluation complète | À faire |
| 4 | Interface de chat | À faire |
| 5 | Base de données, authentification, quotas | À faire |
| 6 | Déploiement (Vercel, Render, Supabase) | À faire |


## Stack

- **Frontend :** React 19, Vite, TypeScript (`frontend/`)
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
│   │   ├── routes/              # /health (les autres routes arrivent aux phases 2 à 5)
│   │   ├── schemas/  services/  db/    # emplacements des phases suivantes
│   │   └── prompts/             # football_system_prompt.txt
│   ├── eval/                    # golden_set.jsonl (40 questions)
│   ├── tests/
│   ├── pyproject.toml  uv.lock  .env.example
├── frontend/
│   ├── src/                     # components, hooks, services, types (contrat d'API), styles
│   ├── package.json  package-lock.json  .env.example
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
sur `http://localhost:8000/docs` (désactivée avec `APP_ENV=prod`). Les clés (`GROQ_API_KEY`,
`FOOTBALL_DATA_API_KEY`, `DATABASE_URL`…) ne sont pas nécessaires à ce stade.

### Frontend

```bash
cd frontend
cp .env.example .env.local  # PowerShell : Copy-Item .env.example .env.local
npm install
npm run dev
```

Ouvrir `http://localhost:5173` : la page réveille le backend et affiche son état.

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
uv run --directory backend pre-commit install
uv run --directory backend pre-commit run --all-files   # exécution manuelle sur tout le dépôt
```

## Configuration

Toutes les variables sont décrites dans [`backend/.env.example`](backend/.env.example) et
[`frontend/.env.example`](frontend/.env.example). Les fichiers `.env` ne sont **jamais** versionnés.
Le frontend n'expose que des valeurs publiques (`VITE_*`). En production (`APP_ENV=prod`), le backend
refuse de démarrer si une variable obligatoire manque.

## Contrainte de quota

Le palier gratuit de Groq limite l'application à environ **80 échanges par jour** et trois échanges
avec outil par minute (mesures de la phase 0). C'est pourquoi l'accès se fait **sur invitation** et
que des plafonds par utilisateur et globaux sont prévus (phase 5).
