# Public Beta — Runbook VPS V5

Périmètre exclusif : `documind-public-beta`. Cette procédure est livrée pour une exécution opérateur ultérieure ; aucun accès VPS n'a été effectué. L'intégration graphique Docnelo est hors de cet ensemble de modifications.

## Déploiement sur VPS

1. Préparer hors VPS une release Public Beta distincte, revue, incluant `tools/public_beta_backup.py`, `tools/public_beta_restic_guard.py`, les helpers V5 (`backup_local.py`, `verify_snapshot.py`, `validate_restore.py`) et leurs dépendances compatibles. Livrer les runbooks avec cette release. Exclure les changements frontend/Docnelo et les secrets du bundle.
2. Transférer cette release dans un nouveau répertoire physique directement sous `/opt/documind-public-beta`. Conserver la release précédente. Le transfert et le choix de la release sont des actions opérateur, non exécutées ici. Ne pas déployer ce changement dans la production.
3. Vérifier l'interpréteur et ses dépendances avec la compilation et l'aide ci-dessous. Les commandes ne contactent ni Docker ni Restic.
4. Faire vérifier par l'opérateur les fichiers existants `.env.public-beta`, `.env.public-beta.images`, le Compose de la release et les images déjà présentes. Ne pas écraser les configurations de production. Les trois volumes doivent être `documind-public-beta_public_beta_database`, `documind-public-beta_public_beta_documents`, `documind-public-beta_public_beta_lifecycle`.
5. Contrôler sans afficher les secrets les permissions du fichier existant `/home/debian/.config/restic/documind-public-beta.env` et de son fichier de mot de passe. Contrôler le latch existant `/opt/documind-public-beta/recovery-state.json` et son état. L'orchestrateur refuse un latch absent ou invalide ; il ne le crée ni ne le réécrit.
6. Suivre la [procédure chiffrée](BACKUP_ENCRYPTED_OFF_VPS.md) : renseigner les coordonnées B2 approuvées indépendamment, enregistrer l'ID une fois, puis exécuter l'orchestrateur. Ne pas ajouter de tâche planifiée ni de redémarrage automatique.

```bash
set -euo pipefail
ROOT=/opt/documind-public-beta/public-beta-candidate-20261030T234818Z
cd "$ROOT"
python3 -m py_compile tools/public_beta_backup.py tools/public_beta_restic_guard.py \
  tools/backup_local.py tools/verify_snapshot.py tools/validate_restore.py
python3 -m tools.public_beta_backup --help
```

Les valeurs ROOT des exemples doivent être adaptées à la release réellement installée. Utiliser le Python de cette release si ses dépendances sont dans un environnement virtuel.

## Exécution

La [procédure chiffrée](BACKUP_ENCRYPTED_OFF_VPS.md) est l'unique chemin de capture/upload. Aucune sélection de sauvegarde par date, aucun `source` du fichier secret, aucun appel Restic manuel en chaîne. Les quatre variables B2/Restic sont transmises explicitement par Python. Le latch est fixé par l'orchestrateur dans l'environnement Compose et vérifié dans la capture.

Le succès exige `remote_verified` et un code retour nul. Conserver le chemin exact et l'ID complet retournés. `api/web` restent arrêtés jusqu'au redémarrage manuel documenté dans cette même procédure.

## Restauration de contrôle

Utiliser une machine ou un projet `documind-restore-lab-<suffix>` isolé avec des volumes et réseaux dédiés. Le laboratoire ne doit jamais monter les volumes Public Beta ou production. Utiliser le chemin exact issu du résultat d'orchestration et les helpers V5 de la même release pour l'exercice ; la recette existante est `ops/testing/combined_restore_lab.py`.

La restauration V5 doit vérifier puis restituer les deux clés dans l'arbre du laboratoire. Le latch restauré doit être forcé à `quarantined`, les admissions doivent rester fermées et l'API ne doit pas être ouverte. Une capture S2 complète ne constitue pas une autorisation de reprise : fraîcheur externe, identités et cohérence exigent une revue opérateur indépendante.

## Retour arrière

- Si la vérification de release échoue avant la capture, ne pas lancer l'orchestrateur ; conserver la release antérieure comme référence opérateur.
- Si la capture ou l'upload échoue, conserver tous les répertoires locaux et les preuves disponibles ; contrôler l'état réel des services et laisser `api/web` arrêtés après la phase d'arrêt. Ne pas lancer de reprise automatique.
- Pour revenir au code antérieur, sélectionner la release Public Beta précédente pour les futures opérations, après revue de compatibilité. Ne pas recopier une ancienne configuration sur les fichiers secrets existants, ne pas retirer l'ID du dépôt et ne pas modifier le latch. Aucun remplacement d'image ni redémarrage n'est requis pour retirer cet outil opérateur.
- Les captures V5 déjà créées restent à traiter avec les vérificateurs V5 ; conserver la release qui les comprend. Un ancien outil ne doit pas les considérer valides par défaut.
- Aucun retour arrière de données n'est automatique. Une restauration reste limitée au laboratoire isolé. Ne supprimer ni volumes ni snapshots Restic pour revenir en arrière.

Pour l'observation locale des services, sans dump de configuration ni affichage des environnements :

```bash
RECOVERY_CONTROL_FILE=/opt/documind-public-beta/recovery-state.json \
  docker compose --project-directory "$ROOT" -p documind-public-beta \
  --env-file "$ROOT/.env.public-beta" --env-file "$ROOT/.env.public-beta.images" \
  -f "$ROOT/compose.public-beta.vps.yaml" ps
```
