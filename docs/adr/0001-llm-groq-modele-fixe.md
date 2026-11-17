# 0001 — Groq seul, un modèle fixe : `openai/gpt-oss-120b`

**Statut :** acceptée (12/11/2026)

## Contexte

- Gemini abandonné : les conditions de l'API imposent les services payants pour une application
  accessible dans l'EEE, en Suisse ou au Royaume-Uni (vérifié par le porteur du projet).
- `llama-3.3-70b-versatile`, prévu au départ, a été **retiré par Groq le 16/08/2026** (page de
  dépréciation Groq). Il n'apparaît plus dans les limites de la console.
- Limites gratuites de la console pour les trois candidats : 30 RPM, 1 000 RPD, 8 000 TPM,
  200 000 TPD (S).

## Décision

Modèle fixe `openai/gpt-oss-120b` pour tout le projet. Alternative d'urgence `openai/gpt-oss-20b`,
par changement **manuel** de `GROQ_MODEL`. Interface `LLMClient` avec une seule implémentation
(`GroqClient`), sans bascule automatique. `qwen/qwen3.8-27b` écarté.

## Résultats V1 (prompt réel, 12 cas × 2 répétitions, données d'outils fictives)

| Mesure | `gpt-oss-120b` | `gpt-oss-20b` | `qwen3.8-27b` |
|---|---|---|---|
| Outil et arguments corrects (16 appels) | 16/16 | 16/16 | 10/16 (6 erreurs 400 de validation) |
| Refus « pas accès » (4 cas) | 4/4 | 2/4 | 4/4 |
| Tokens moyens avec outil / sans outil | 2 662 / 1 108 | 2 679 / 1 089 | 3 175 / 1 334 |
| Premier token : médiane / maximum | 0,53 s / 4,2 s | 0,42 s / 1,8 s | 0,27 s / 10,5 s |

## Paramètres de l'appel (V1, S, script `v1_groq_tools.py`)

`temperature` 0,2 ; `max_completion_tokens` 1500 ; `tool_choice` automatique ; effort de raisonnement non défini (défaut du modèle) ; `usage` lu dans `x_groq.usage` du dernier fragment. Repris tels quels en phase 2 pour que les mesures ci-dessus restent valides.

## Conséquences

- Capacité de l'ordre de 80 échanges par jour sur 170 000 tokens, soit ≈ 85 % du plafond (I).
- Une erreur 400 de validation d'appel d'outil est réessayée une fois, puis renvoyée comme
  `llm_unavailable`.
- Groq retire des modèles : vérifier au démarrage que `GROQ_MODEL` figure dans la liste des
  modèles de l'API, et surveiller la page de dépréciation.
- Limite de l'échantillon : 16 appels d'outils par modèle. L'évaluation complète (40 questions,
  `backend/eval/golden_set.jsonl`) confirmera ou non le 100 %.
