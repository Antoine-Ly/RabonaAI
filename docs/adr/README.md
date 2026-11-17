# Décisions d'architecture (ADR)

Format court : statut, contexte, décision, conséquences. Les mesures citées viennent des
vérifications de la phase 0 (marquées **S** quand elles sont mesurées ou sourcées, **I** quand
elles sont déduites).

| N° | Décision |
|---|---|
| [0001](0001-llm-groq-modele-fixe.md) | Groq seul, un modèle fixe : `openai/gpt-oss-120b` |
| [0002](0002-identifiants-de-competition-lisibles.md) | Identifiants de compétition lisibles pour le LLM |
| [0003](0003-donnees-football-outils-cache.md) | Données football : trois outils, fenêtres de dates, cache et limiteur |
| [0004](0004-authentification-acces-base.md) | Supabase Auth, accès sur invitation, accès à la base |
| [0005](0005-hebergement-regions-demarrage-a-froid.md) | Hébergement, régions et démarrage à froid |
| [0006](0006-phase-2-chat-sans-outils-ni-historique.md) | Phase 2 : chat sans outils, sans historique ni base |
