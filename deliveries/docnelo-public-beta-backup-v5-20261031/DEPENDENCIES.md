# Imports et dépendances V5

Analyse des sources copiées à l'identique le 31 octobre 2026. Le détail des imports, y compris conditionnels et `__import__('time')`, est dans `SOURCE_AUDIT.json`.

| Source | Imports locaux | Dépendances hors bibliothèque standard |
| --- | --- | --- |
| tools/public_beta_backup.py | tools.backup_local, tools.verify_snapshot, tools.public_beta_restic_guard | SQLAlchemy via verify_snapshot ; fcntl Linux dans operator_lock |
| tools/public_beta_restic_guard.py | aucun | fcntl Linux lors de l'enregistrement de l'ID |
| tools/backup_local.py | aucun sur l'hôte | exécute backend.lifecycle_snapshot dans l'image API |
| tools/verify_snapshot.py | aucun | sqlalchemy.create_engine, sqlalchemy.text |
| tools/validate_restore.py | tools.verify_snapshot en module ; verify_snapshot en exécution directe | sqlalchemy.create_engine/text et sqlalchemy.engine.make_url ; Psycopg via le dialecte SQLAlchemy |
| backend/lifecycle_snapshot.py | backend.lifecycle_backup_lock | aucune ; s'exécute normalement dans l'image API |
| backend/lifecycle_backup_lock.py | aucun | fcntl sur Linux ; msvcrt uniquement dans la branche Windows |
| backend/__init__.py | aucun | aucune ; initialiseur original du package |

Bibliothèque standard recensée : __future__, argparse, contextlib, datetime, fcntl, hashlib, io, json, os, pathlib, re, shlex, shutil, sqlite3, stat, subprocess, sys, tarfile, tempfile, time, uuid. `msvcrt` n'est pas nécessaire sous Debian. Aucun import frontend, FastAPI, backend.config ou module applicatif supplémentaire n'est requis par cette fermeture d'imports.

Le répertoire `tools` est un namespace package Python dans le dépôt : il n'a pas de `__init__.py`. Le bundle conserve ce fonctionnement sans créer d'initialiseur artificiel. Lancer depuis le répertoire de livraison ; le contrôle vérifie que les modules viennent bien de ce bundle.

## Prérequis externes non livrés

- Python 3.11 sous Debian, SQLAlchemy 2.0.55, Psycopg 3.3.6 et son installation native ou binaire fonctionnelle. Les dépendances transitives de ces paquets doivent déjà être installées ; aucun `pip install`, venv, wheel ou paquet n'est livré.
- fcntl, sqlite3 et hashlib.file_digest dans le Python hôte. Les API Path.is_relative_to et str.removeprefix sont également utilisées. Toutes sont disponibles dans la version cible ; le contrôle Debian les exerce.
- Docker Engine local et Compose V2 comprenant le tag YAML `!reset` utilisé par l'override éphémère de capture. La résolution de l'override est vérifiée par le helper existant.
- Restic disponible dans PATH, dépôt B2 existant et réseau vers B2. Le transfert exige JSON backup/snapshots et cat config ; aucune initialisation ni rétention n'est effectuée.
- Release applicative Public Beta existante : compose.public-beta.vps.yaml, .env.public-beta, .env.public-beta.images, conteneurs, images et trois volumes déjà en place. Ils ne sont pas livrés.
- Configuration Restic et mot de passe Public Beta privés déjà présents ; latch opérateur existant au chemin canonique. Aucun n'est livré.
- Dans l'image API sélectionnée : Python, tar avec --no-recursion, backend/__init__.py, backend/lifecycle_snapshot.py et backend/lifecycle_backup_lock.py compatibles, variables lifecycle et accès aux deux clés. Le bundle fournit ces trois sources pour référence et contrôle, mais leur présence sur l'hôte ne met pas à jour l'image. Si l'image n'est pas compatible, arrêter la procédure ; sa reconstruction est une livraison séparée.
- Dans le conteneur DB : pg_dump, pg_restore et psql compatibles avec PostgreSQL source. Le manifeste de capture déclare actuellement database_major=17 : contrôler la version réelle, sans la déduire uniquement du manifeste.
- Pour une restauration : pg_restore local compatible avec le dump (PostgreSQL 17 pour le périmètre actuel), cluster PostgreSQL de laboratoire isolé marqué cluster_name=documind-restore-lab, extensions requises par le schéma (notamment vector selon la base) et base d'administration dédiée. Aucun laboratoire, cluster, image ou extension n'est provisionné par ce bundle.

## Points d'exploitation constatés, sans modification de code

L'orchestrateur utilise `--root` pour trouver le Compose et les fichiers privés dans la release applicative existante et y écrire la capture. Son propre module peut être chargé depuis une release d'outillage distincte : aucune copie des configurations dans ce bundle n'est nécessaire.

Le CLI de verify_snapshot utilise un Compose par défaut ; pour la sauvegarde, utiliser l'orchestrateur qui transmet explicitement le projet et la base résolus. Ne pas lancer ce CLI seul depuis la release d'outillage pour vérifier la base active.

validate_restore exige un laboratoire isolé et force le latch restauré à quarantined. Il accepte aussi des captures anciennes complètes : vérifier explicitement V5 avant un exercice V5. La fonction seal_restored_registration est définie mais n'est pas appelée par _restore : le quota restauré peut conserver closed=false. Le laboratoire doit rester sans API et sans exposition ; la fermeture effective des admissions doit être vérifiée séparément avant toute reprise. Aucune ouverture ni promotion en service n'est couverte ici.

Les runbooks copiés peuvent mentionner ops/testing/combined_restore_lab.py et une release applicative complète. Ce laboratoire et cette release complète sont volontairement exclus du bundle minimal. Pour l'installation séparée, suivre en premier README_DEPLOIEMENT.md ; les commandes de capture restent celles du module existant.
