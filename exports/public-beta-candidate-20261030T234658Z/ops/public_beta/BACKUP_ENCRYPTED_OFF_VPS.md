# DocuMind AI — Public beta — Sauvegarde chiffrée hors VPS (procédure)

Objectif: réutiliser le mécanisme validé par la recette publique (backup v2 indépendant) et exporter une copie chiffrée hors VPS.

## Pré-requis
- Accès shell opérateur sur le VPS (pas d'accès public aux volumes)
- `docker` + `docker compose`
- `python3` sur l'hôte (pour exécuter `tools/backup_local.py`)
- Outil de chiffrement: `age` (recommandé) ou `gpg`

## Contrainte d'intégrité / quiescence
- Arrêter `api` et `web`
- Laisser tourner `db` uniquement

## Commandes (à exécuter sur VPS)
> Adapter `WORKDIR` et fichiers.

```bash
WORKDIR=/opt/documind-public-beta/repo
cd "$WORKDIR"

# Stop app paths; keep db running
PUBLIC_BETA_ENV_FILE=.env.public-beta docker compose -p documind-public-beta -f compose.public-beta.vps.yaml stop api web

# Ensure db is up
PUBLIC_BETA_ENV_FILE=.env.public-beta docker compose -p documind-public-beta -f compose.public-beta.vps.yaml up -d db

# Run backup (creates var/backups/<timestamp>)
PUBLIC_BETA_ENV_FILE=.env.public-beta python3 tools/backup_local.py --compose-file compose.public-beta.vps.yaml

# Restart app
PUBLIC_BETA_ENV_FILE=.env.public-beta docker compose -p documind-public-beta -f compose.public-beta.vps.yaml up -d api web
```

## Export chiffré hors VPS (age)
Sur VPS:
```bash
BACKUP_DIR=$(ls -dt var/backups/* | head -n1)
TAR=public-beta-backup-$(date -u +%Y%m%dT%H%M%SZ).tar.gz

tar -C "$BACKUP_DIR" -czf "/tmp/$TAR" .

# Chiffrement (clé publique du poste opérateur)
age -r "age1..." -o "/tmp/$TAR.age" "/tmp/$TAR"
sha256sum "/tmp/$TAR.age" > "/tmp/$TAR.age.sha256"

# Transfer
scp "/tmp/$TAR.age" "/tmp/$TAR.age.sha256" user@backup-host:/backups/documind/
```

## Notes importantes
- Une restauration peut ressusciter des données supprimées si des sauvegardes plus anciennes existent.
- Après restore: reprise fermée, revue manuelle, puis réouverture.
