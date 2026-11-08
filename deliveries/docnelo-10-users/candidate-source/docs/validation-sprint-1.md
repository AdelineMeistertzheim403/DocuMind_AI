# Validation — 19 octobre 2026

Environnement : Windows, Python 3.13.7, dépendances résolues dans `requirements.lock`.

- `python -m pytest -q` : **29 tests réussis**. Une dépréciation tierce Starlette concerne
  l'usage de HTTPX par son client de test ; elle n'empêche pas l'exécution.
- Migrations Alembic appliquées puis annulées sur SQLite pour chaque test d'API.
  `alembic check` confirme l'absence de différence entre schéma migré et modèles.
- Migration SQL PostgreSQL générée avec `alembic upgrade head --sql` ; sortie conservée
  dans `docs/migration-postgresql.sql`. Cela vérifie la génération SQL, pas son exécution sur PostgreSQL.
- Essai HTTP réel sur Uvicorn avec base temporaire : santé 200, import PDF 201,
  analyse 201 (9 mots attendus), consultation 200, suppression 204.
  Fichiers et processus temporaires nettoyés après vérification.
- `pip check` : aucune dépendance incohérente.
- Compilation Python du backend, des migrations, des tests et du code existant : réussie.
- `docker compose config --quiet` : configuration acceptée avec le `.env` local généré.

## Vérification complémentaire avec Docker opérationnel

Lors de la première validation, Docker Desktop renvoyait une erreur HTTP 500 sur `/_ping`.
Après son démarrage par l'utilisatrice, PostgreSQL fonctionne. Le diagnostic Swagger a montré
que seul le service `db` était lancé et que le port 8000 était occupé par un autre processus.

- Image API construite avec succès et migrations exécutées sur PostgreSQL 17.
- Port hôte rendu configurable par `API_PORT` ; `.env` local configuré sur **8001**.
- Swagger `/docs` et santé `/api/v1/health` : HTTP 200.
- Parcours réel Docker + PostgreSQL : import PDF 201, analyse 201 avec 9 mots attendus,
  suppression du document de vérification 204.
- Services `api` et `db` laissés démarrés pour l'utilisation de Swagger.

La suite pytest complète sur PostgreSQL reste distincte de cet essai d'intégration ;
elle peut être exécutée avec `TEST_DATABASE_URL` sur une base de test dédiée selon le README.

Le dossier initial n'étant pas un dépôt Git, aucune comparaison ou commit Git n'a été possible.
Les modules existants sont conservés ; l'ancien README est archivé dans `docs/desktop.md`.
