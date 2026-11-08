# Docnelo — Public & Bêta Deployment Plan (No Auto-Deploy)

Date (locale): 2026-10-31 (Europe/Paris)

## Principes (non négociables)
- Ne pas modifier les secrets existants (seulement vérifier qu’ils sont présents).
- Ne jamais supprimer les volumes (interdiction: `docker compose down -v`).
- Ne pas réinitialiser PostgreSQL.
- Ne pas changer les noms de services/volumes/réseaux "documind*" pour des raisons esthétiques.
- Déployer d’abord en Bêta, valider, puis seulement ensuite en Public.

---

## Étape A — Déploiement Bêta (d’abord)

### A1) Pré-requis
- Une sauvegarde récente de l’environnement bêta (si applicable) est disponible.
- Le fichier `.env.public-beta` (sur VPS) est inchangé, sauf ajout optionnel:
  - `UI_ENVIRONMENT_LABEL=Bêta` (facultatif, pour afficher le badge "Bêta" côté UI)

### A2) Construction / image
Deux options selon vos pratiques (à choisir, mais ne pas exécuter automatiquement):

Option 1 — Build sur CI (recommandé):
- Construire et publier une image `BACKEND_IMAGE` et `FRONTEND_IMAGE` taguées (ne pas écraser un tag existant utilisé pour rollback).

Option 2 — Build sur VPS (si contrôlé):
- Build des images à partir du dépôt et tagging unique.

### A3) Déploiement contrôlé (VPS)
Commandes indicatives (adapter chemins et tags):

```bash
export PUBLIC_BETA_ENV_FILE=.env.public-beta

# Toujours vérifier le compose ciblé.
docker compose --env-file "$PUBLIC_BETA_ENV_FILE" -p documind-public-beta -f compose.public-beta.vps.yaml config > /tmp/documind-public-beta.rendered.yaml

# Mise à jour sans supprimer les volumes.
docker compose --env-file "$PUBLIC_BETA_ENV_FILE" -p documind-public-beta -f compose.public-beta.vps.yaml pull

docker compose --env-file "$PUBLIC_BETA_ENV_FILE" -p documind-public-beta -f compose.public-beta.vps.yaml up -d

# Health checks
# - vérifier traefik router
# - vérifier /bff (UI)
# - vérifier /bff/ui-config
```

### A4) Vérifications post-déploiement (Bêta)
- Accès UI, chargement logo + favicon.
- Badge "Bêta" (si `UI_ENVIRONMENT_LABEL=Bêta`).
- Authentification.
- Upload + consultation doc.
- Vérifier que la bêta n’utilise pas les volumes de prod.

### A5) Rollback Bêta
- Conserver le tag/digest précédent des images.
- `docker compose up -d` en re-pointant `BACKEND_IMAGE` / `FRONTEND_IMAGE` vers les images précédentes.

---

## Étape B — Déploiement Public (uniquement après validation explicite)

### B1) Pré-requis
- Vérifier qu’une sauvegarde récente de la prod existe.
- Valider que les inscriptions restent fermées (configuration `registration_mode=disabled` en prod).

### B2) Déploiement contrôlé (VPS)
Commandes indicatives:

```bash
export PRODUCTION_ENV_FILE=.env.production

# Toujours vérifier le compose ciblé.
docker compose --env-file "$PRODUCTION_ENV_FILE" -p documind-prod -f compose.production.yaml config > /tmp/documind-prod.rendered.yaml

# Mise à jour sans supprimer les volumes.
docker compose --env-file "$PRODUCTION_ENV_FILE" -p documind-prod -f compose.production.yaml pull

docker compose --env-file "$PRODUCTION_ENV_FILE" -p documind-prod -f compose.production.yaml up -d
```

### B3) Vérifications post-déploiement (Public)
- Logo + favicon.
- Authentification.
- Accès documents + lecture.
- Vérifier que les inscriptions publiques restent fermées.

### B4) Rollback Public
- Revenir aux tags/digests précédents des images via `docker compose up -d`.
- Ne pas toucher aux volumes.
