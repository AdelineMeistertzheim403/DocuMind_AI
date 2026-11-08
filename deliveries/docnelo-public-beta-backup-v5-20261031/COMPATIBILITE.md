# Vérification de compatibilité Python 3.11

## Contrôles locaux effectués

- 8 sources originales copiées octet pour octet ; les SHA-256 sources/copies sont identiques. Les scripts du dépôt n'ont pas été modifiés pour cette livraison.
- 9 fichiers Python (8 sources et le contrôle de livraison) analysés avec ast.parse(feature_version=(3, 11)) puis compilés en mémoire : 9 réussis, 0 échec.
- 8 modules du dépôt importés depuis le répertoire de livraison isolé : 8 réussis, 0 échec ; chaque chemin résolu a été contrôlé. Aucun autre module du dépôt n'a été nécessaire. SQLAlchemy a été préchargé avant le garde subprocess car sa détection de plateforme Windows appelle un outil système.
- Aides des CLI public_beta_backup et validate_restore exécutées depuis la livraison : 2 réussies, 0 échec, sans capture ni restauration.
- Aucun appel Docker, Restic ou PostgreSQL, aucune connexion réseau, aucun accès VPS lors de ces contrôles.

L'interpréteur local est Python 3.13.7 sous Windows, pas Python 3.11. L'analyse de grammaire et la compilation ne constituent pas une exécution sur 3.11. Les résultats machine sont dans LOCAL_CHECKS.json ; les imports et empreintes sources sont dans SOURCE_AUDIT.json.

## Analyse des API et bibliothèques

La syntaxe utilisée ne nécessite aucune fonctionnalité postérieure à Python 3.11. hashlib.file_digest requiert Python 3.11 ; Path.is_relative_to et str.removeprefix/removesuffix sont disponibles depuis Python 3.9. fcntl et os.O_NOFOLLOW sont des dépendances Linux intentionnelles, sans substitut ajouté. Le branchement msvcrt du verrou lifecycle ne s'exécute pas sur Debian.

SQLAlchemy est importé par verify_snapshot et validate_restore. Psycopg est chargé par SQLAlchemy lors d'une restauration avec l'URL postgresql+psycopg. Les versions cibles fournies par l'opérateur sont SQLAlchemy 2.0.55 et Psycopg 3.3.6 ; aucun paquet n'est modifié, téléchargé ou livré ici.

Conclusion statique : aucune incompatibilité Python 3.11 identifiée dans les sources livrées. Le contrôle réel sur l'interpréteur cible reste à exécuter par l'opérateur avec `python3.11 -B check_python311.py` ou le chemin du venv préparé. Ce contrôle vérifie aussi le chargement effectif de Psycopg, le dialecte SQLAlchemy, sqlite3 via les imports, les API et le verrou fcntl sur un fichier temporaire, sans connexion à une base ni appel de service.

## Contrôles restant hors de cette livraison

La disponibilité des images API/DB compatibles, la version réelle de PostgreSQL et de pg_restore, le support Compose de !reset, l'accès aux volumes/clé/latch, l'accès B2 et l'exercice de restauration isolée doivent être vérifiés en recette par l'opérateur. La fermeture du quota d'inscription après restore nécessite le contrôle séparé décrit dans DEPENDENCIES.md. Aucun test VPS n'est revendiqué et aucune image n'est remplacée.
