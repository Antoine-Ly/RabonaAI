# 0004 — Supabase Auth, accès sur invitation, accès à la base

**Statut :** acceptée (14/11/2026)

## Décision

- **Accès sur invitation uniquement** : inscription libre désactivée dans Supabase, comptes créés à
  la main (e-mail + mot de passe). Aucune dépendance à l'envoi d'e-mails ni à OAuth.
- **JWT vérifié par FastAPI** : signature ES256 via les clés publiques du projet (JWKS), expiration,
  audience `authenticated`, **tolérance d'horloge de 10 s**. L'identifiant utilisateur est `sub`.
- **Base** : connexion directe du backend via la chaîne « Session pooler » ; RLS activé **sans
  politique** sur les trois tables, ce qui interdit l'accès par l'API REST publique de Supabase.
- **Quota** : réservation atomique d'un message par un `INSERT … ON CONFLICT … WHERE`.

## Vérifié en V3 (S)

- Projet en ES256 ; récupération du JWKS en 0,07 à 0,24 s.
- Jeton valide rejeté sans tolérance d'horloge (« not yet valid (iat) ») : écart local/serveur
  d'environ 1 à 2 s. D'où `JWT_LEEWAY_SECONDS=10`.
- Jeton altéré refusé (signature invalide) ; mauvaise audience refusée.
- API REST publique : liste vide avec la clé publique et avec le JWT utilisateur.
- Requête de quota : `(1,), (2,), None` pour une limite de 2.
