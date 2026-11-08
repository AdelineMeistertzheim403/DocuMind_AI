# Docnelo — Rollback Plan

Date (locale): 2026-10-31 (Europe/Paris)

## Règles
- Ne jamais supprimer de volumes (`docker compose down -v` interdit).
- Le rollback se fait uniquement en re-pointant les images (`BACKEND_IMAGE`, `FRONTEND_IMAGE`, `POSTGRES_IMAGE`) vers les digests/tags précédents.
- Conserver au moins:
  - N-1 (prod) et N-1 (bêta) des images backend/frontend.

---

## 1) Préparation (avant déploiement)

Pour chaque environnement (Bêta, puis Public):
- Exporter la config effective:

```bash
# Beta
export PUBLIC_BETA_ENV_FILE=.env.public-beta
docker compose --env-file "$PUBLIC_BETA_ENV_FILE" -p documind-public-beta -f compose.public-beta.vps.yaml config > /tmp/documind-public-beta.pre.yaml

# Prod
export PRODUCTION_ENV_FILE=.env.production
docker compose --env-file "$PRODUCTION_ENV_FILE" -p documind-prod -f compose.production.yaml config > /tmp/documind-prod.pre.yaml
```

- Noter les digests/tags actuellement utilisés:
  - `BACKEND_IMAGE`
  - `FRONTEND_IMAGE`
  - `POSTGRES_IMAGE`

---

## 2) Rollback Bêta

### Commandes indicatives
```bash
export PUBLIC_BETA_ENV_FILE=.env.public-beta

# Reconfigurer BACKEND_IMAGE / FRONTEND_IMAGE vers les valeurs N-1
# (dans l'env-file ou via export/override local)

docker compose --env-file "$PUBLIC_BETA_ENV_FILE" -p documind-public-beta -f compose.public-beta.vps.yaml pull
docker compose --env-file "$PUBLIC_BETA_ENV_FILE" -p documind-public-beta -f compose.public-beta.vps.yaml up -d
```

### Contrôles
- Charger l’UI
- Auth
- Upload / documents

---

## 3) Rollback Public

### Commandes indicatives
```bash
export PRODUCTION_ENV_FILE=.env.production

# Reconfigurer BACKEND_IMAGE / FRONTEND_IMAGE vers les valeurs N-1

docker compose --env-file "$PRODUCTION_ENV_FILE" -p documind-prod -f compose.production.yaml pull
docker compose --env-file "$PRODUCTION_ENV_FILE" -p documind-prod -f compose.production.yaml up -d
```

### Contrôles
- Auth
- Documents
- Confirmer que les inscriptions restent fermées
