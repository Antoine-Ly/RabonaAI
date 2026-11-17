# 0005 — Hébergement, régions et démarrage à froid

**Statut :** acceptée (14/11/2026)

## Décision

- Frontend : Vercel (Hobby). Backend : Render (service web gratuit) en **Frankfurt**. Base et
  authentification : Supabase en **North EU (Stockholm)**. Tout est en Europe.
- Le backend s'endort après 15 minutes sans requête. Le frontend appelle `/health` dès l'affichage
  de la page (le backend se réveille pendant la saisie des identifiants) et affiche l'état du serveur.

## Mesuré en V4 (S, un seul essai sur une application minimale)

- Mise en veille exactement 15 minutes après la dernière requête.
- Démarrage à froid : **32,4 s** (≈ 10 s d'activation, ≈ 12 s de démarrage de Python, ≈ 10 s avant la
  prise en charge du trafic). Instance chaude : 0,15 à 0,21 s.
- Depuis Render : connexion à Supabase 256 ms (connexion + requête), accès à Groq 506 ms.

## Conséquences

- Délai d'attente du premier appel : 70 s côté frontend.
- À régler au déploiement (phase 6) : chemin de contrôle de santé `/health`, variable
  `PYTHON_VERSION`, variables d'environnement dans Render (jamais dans le dépôt).
- Ping hebdomadaire (GitHub Actions) contre la mise en pause de Supabase après une semaine d'inactivité.
