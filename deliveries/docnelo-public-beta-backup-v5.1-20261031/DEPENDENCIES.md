# Dépendances de la livraison V5.1

| Module | Imports locaux nécessaires | Prérequis externes |
| --- | --- | --- |
| tools.public_beta_backup | backup_local, verify_snapshot, public_beta_restic_guard ; transitivement lifecycle_key_policy | Python 3.11/Linux et fcntl, Docker Compose, Restic |
| tools.public_beta_restic_guard | aucun | fcntl lors du pinning, Restic/B2 |
| tools.backup_local | lifecycle_key_policy | Docker Compose ; appelle backend.lifecycle_snapshot dans l'image API |
| tools.verify_snapshot | lifecycle_key_policy | SQLAlchemy |
| tools.validate_restore | verify_snapshot, lifecycle_key_policy | SQLAlchemy, Psycopg via postgresql+psycopg, pg_restore local |
| tools.lifecycle_key_policy | aucun | bibliothèque standard uniquement |
| backend.lifecycle_snapshot | backend.lifecycle_backup_lock | Python/sqlite3/tar dans l'image API |
| backend.lifecycle_backup_lock | aucun | fcntl sous Linux ; msvcrt dans la branche Windows uniquement |
| backend.__init__ | aucun | initialiseur original du package |

Les six modules tools et les trois fichiers backend sont copiés à l'identique des sources corrigées du dépôt. Le namespace tools ne nécessite pas de __init__.py ajouté. La fermeture d'imports n'inclut ni frontend, ni FastAPI, ni le reste de l'application. Les sources backend livrées sont des références : leur présence sur l'hôte ne met pas à jour l'image API et aucune reconstruction n'est demandée.

Prérequis hôte déjà annoncés : Python 3.11, SQLAlchemy 2.0.55, Psycopg 3.3.6 et fcntl. Aucun environnement virtuel, wheel ou paquet n'est livré. API standard utilisée : hashlib.file_digest (3.11), Path.is_relative_to et str.removeprefix/removesuffix (3.9), os.O_NOFOLLOW et os.fchmod sous Linux. Analyse ast avec feature_version=(3,11) et compilation en mémoire des sources ; imports isolés exercés localement sous Python 3.13 Windows. Le contrôle check_python311.py fourni exerce réellement le scellement POSIX des clés synthétiques sur Debian, à exécuter par l'opérateur.

Prérequis applicatifs conservés : release Public Beta existante avec Compose et deux fichiers .env existants ; image API contenant les modules backend de capture, Python et tar ; image DB contenant pg_dump, pg_restore et psql ; Compose V2 avec !reset ; conteneurs/volumes déjà en place. Le dump et pg_restore doivent être compatibles avec PostgreSQL 17 du périmètre actuel, à confirmer sur les images réelles. Restic et les fichiers secrets existants, le latch opérateur canonique et les coordonnées B2 approuvées restent externes à ce bundle.

Le mode de groupe est borné à UID 0/GID 1000. L'appartenance effective de app à ce groupe et les accès au volume ne sont pas certifiés par une archive. Ils doivent être conformes à l'inventaire opérateur ; tout autre modèle impose une revue, sans élargissement de configuration implicite.

Pour restore : cluster PostgreSQL isolé marqué documind-restore-lab, URL loopback postgresql+psycopg avec port explicite et base documind_restore_admin, extensions du schéma disponibles, répertoire marqué .synthetic-only, DB neuve documind_restore_<12 hex>. Aucun cluster/labo n'est inclus. Les réserves sur le lecteur administratif, la propriété app de l'ascendance et la fermeture du quota sont détaillées dans le rapport V5.1. Pas de promotion vers une API en service.
