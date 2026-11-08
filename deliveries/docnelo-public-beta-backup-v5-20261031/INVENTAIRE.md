# Inventaire exact de livraison

19 fichiers, dont 8 sources originales et 1 contrôle Python de livraison. Les chemins sont relatifs à la racine du bundle.

| Fichier | Usage |
| --- | --- |
| tools/public_beta_backup.py | Orchestration V5 hôte |
| tools/public_beta_restic_guard.py | Configuration et destination Restic Public Beta |
| tools/backup_local.py | Capture locale hors ligne |
| tools/verify_snapshot.py | Vérification des archives, S2 et intégrité PostgreSQL |
| tools/validate_restore.py | Restauration et validation dans un laboratoire isolé |
| backend/__init__.py | Initialiseur original du package backend |
| backend/lifecycle_snapshot.py | Capture SQLite appelée dans l'image API ; source de référence |
| backend/lifecycle_backup_lock.py | Verrou lifecycle importé par la capture SQLite ; source de référence |
| ops/public_beta/BACKUP_ENCRYPTED_OFF_VPS.md | Runbook de sauvegarde chiffrée original |
| ops/public_beta/VPS_BACKUP_RESTORE_RUNBOOK.md | Runbook VPS original |
| ops/public_beta/BACKUP_RESTORE_V5_KEYS_REPORT.md | Rapport V5 original, avec résultats des tests précédents |
| README_DEPLOIEMENT.md | Transfert PowerShell/SCP, vérification Linux, installation séparée, utilisation et retour arrière |
| DEPENDENCIES.md | Fermeture d'imports, prérequis hôte/conteneurs et limites d'exploitation |
| COMPATIBILITE.md | Contrôles locaux et portée de la vérification Python 3.11 |
| check_python311.py | Contrôle Debian 3.11 sans appel de services |
| SOURCE_AUDIT.json | Imports, tailles et SHA-256 des 11 fichiers copiés du dépôt |
| LOCAL_CHECKS.json | Résultats des contrôles locaux isolés |
| INVENTAIRE.md | Présent inventaire |
| SHA256SUMS | Empreintes GNU SHA-256 des 18 autres fichiers |

Aucun fichier .env, secret Restic/lifecycle, dump, archive de données, base, document utilisateur, frontend, image Docker, code de production de sauvegarde, environnement virtuel, dépendance vendue ou bytecode Python n'est livré. Les configurations, images et services Public Beta existants restent des prérequis externes. Les trois sources backend ne sont pas injectées automatiquement dans l'image API.
