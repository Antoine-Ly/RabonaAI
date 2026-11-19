# Jeu d'évaluation

`golden_set.jsonl` : 40 questions (outils, connaissances, tactique, hors couverture, hors football,
injections, ambiguïtés). Spécification : `docs/conception.md` §7.

Champs : `id`, `category`, `question`, `expected_tools`, `expected_args` (identifiants de compétition
lisibles, ex. `ligue-1`), `must_contain`, `must_contain_any`, `must_not_contain`, `expect`
(`answer` | `decline` | `clarify` | `redirect` | `refuse_injection`), `review` (`auto` | `manual`), `notes`.

Le harnais d'exécution (`run_eval.py`) exécute les 40 questions depuis la phase 3, avec les outils réels (vraie API football-data.org ; `FOOTBALL_DATA_API_KEY` requise). `TOOLS_AVAILABLE = False` rejoue les 26 questions sans outil de la phase 2. Détail : `docs/conception.md` §7.6.
