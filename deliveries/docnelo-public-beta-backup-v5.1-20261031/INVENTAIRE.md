# Inventaire V5.1

19 fichiers livrés. Aucun autre fichier n'est nécessaire dans ce répertoire d'outillage ; les images et configurations existantes restent externes. Les dépendances Python déjà installées ne sont pas copiées.

| Chemin relatif | Fonction |
| --- | --- |
| tools/public_beta_backup.py | Orchestration Public Beta inchangée |
| tools/public_beta_restic_guard.py | Garde Restic inchangé |
| tools/backup_local.py | Capture V5 corrigée |
| tools/verify_snapshot.py | Vérification V5 corrigée |
| tools/validate_restore.py | Extraction isolée corrigée |
| tools/lifecycle_key_policy.py | Nouvelle politique commune V5.1 |
| backend/__init__.py | Initialiseur backend original de référence |
| backend/lifecycle_snapshot.py | Capture SQLite exécutée dans l'image API, référence inchangée |
| backend/lifecycle_backup_lock.py | Verrou SQLite de référence inchangé |
| ops/public_beta/BACKUP_ENCRYPTED_OFF_VPS.md | Runbook V5 existant, référence opérationnelle |
| ops/public_beta/VPS_BACKUP_RESTORE_RUNBOOK.md | Runbook VPS existant, référence opérationnelle |
| ops/public_beta/BACKUP_RESTORE_V5_1_PERMISSIONS_REPORT.md | Analyse de sécurité, politique, autres blocages et rapport 101/0/6 |
| README_DEPLOIEMENT.md | Transfert SCP, empreintes, installation neuve et retour arrière |
| DEPENDENCIES.md | Imports, dépendances et limites |
| check_python311.py | Précontrôle Linux/Python 3.11 et extraction de clés synthétiques temporaires |
| SOURCE_AUDIT.json | Empreintes/tailles/imports des douze fichiers copiés du dépôt |
| RELEASE.json | Versions d'outillage/format, résultats de tests et portée des vérifications |
| INVENTAIRE.md | Présent inventaire |
| SHA256SUMS | Empreintes GNU SHA-256 des dix-huit autres fichiers |

Ne sont inclus ni secrets, ni .env, ni bases, ni captures, ni clés réelles, ni données utilisateur, ni frontend, ni image Docker, ni bytecode/venv, ni outils de production. Les sources backend ne sont pas déployées dans une image par cette livraison.

Les neuf modules du dépôt sont copiés octet pour octet à partir des sources locales corrigées. Les trois modules existants et la politique commune constituent le correctif ; les autres modules assurent une livraison autonome pour les imports hôte et la référence de capture conteneur. Le module de précontrôle est un fichier de livraison supplémentaire.
