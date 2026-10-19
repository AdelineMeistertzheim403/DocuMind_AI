# Validation Sprint 4 et résumés longs — 19 octobre 2026

## Livraison

Le Sprint 4 ajoute l’indexation explicite par embeddings, la recherche exacte pgvector/cosinus combinée au lexical par RRF, les questions multi-documents, la comparaison locale de versions et sa synthèse IA facultative. Interfaces : **https://localhost:8443/library** et **https://localhost:8443/compare**.

La correction demandée ensuite ajoute le résumé approfondi hiérarchique, sa confirmation chiffrée, un worker dédié, des étapes persistées, la reprise et l’annulation. Résumés courts, analyses classiques et application desktop sont conservés.

PostgreSQL reste en version majeure **17 Alpine**, avec **pgvector 0.8.7** compilé dans `Dockerfile.db`. Le volume original est conservé. La base locale est en migration **0005**.

## Sauvegardes et migrations vérifiées

- Avant 0004 : `var/backups/sprint4-20261019-082016`. Restauration sur base jetable, puis 0003 → 0004 → 0003 : **11 tables antérieures inchangées**.
- Avant 0005 : `var/backups/sprint4-20261019-084446`. Restauration sur base jetable, puis 0004 → 0005 → 0004 : **16 tables antérieures inchangées**.

Les archives incluent PostgreSQL et les documents privés. Les empreintes ont aussi été contrôlées après les migrations locales. Aucune suppression/recréation du volume n’a été effectuée. Les bases jetables sont distinctes de la base documentaire.

Migrations : `0004_rag_vectors_jobs_and_results.py` ajoute vecteurs, tâches d’indexation, résultats/liens RAG et documents des opérations budgétaires ; `0005_persistent_long_summary_steps.py` ajoute tâches et étapes de résumé. Les migrations antérieures ne sont pas modifiées.

## Tests exécutés

| Vérification | Résultat |
|---|---|
| pytest sur SQLite temporaire avec migrations | **85 réussis** |
| Même suite sur PostgreSQL 17/pgvector, base dédiée vide | **85 réussis** |
| React/Vitest | **33 réussis** |
| BFF/Node | **19 réussis** |
| Playwright, vrais services Docker, ordinateur et mobile | **10 réussis** |
| TypeScript/Vite, images Docker, compilation Python et `pip check` | Réussis |

Des tests ciblés supplémentaires ont vérifié la relance après annulation sans retraitement de la partie validée et le fournisseur Responses après durcissement des journaux SDK. L’avertissement connu Starlette/TestClient concernant httpx reste présent, sans échec.

Couverture nouvelle : indexation par lots, versions distinctes, déduplication, réindexation idempotente, erreurs et reprise ; dimensions de vecteurs invalides avec usage conservé ; véritable opérateur cosinus PostgreSQL ; lexical, vectoriel sans correspondance lexicale, hybride, multi-documents et cache ; contrôles de propriété avant coût ; suppression ; budgets BYOK concurrents et expiration entre lots ; comparaison identique, ajout, suppression, modification, déplacement, pages PDF et 300 paragraphes ; références inventées rejetées.

Les résumés couvrent petits documents, PDF synthétiques de 20, 53 et 200 pages, pages vides, frontières de paragraphes, plusieurs niveaux, réservation globale, concurrence, coût modifié avant confirmation, panne connue/ambiguë, interruption/reprise, annulation, isolation et BYOK. Les appels internes ne consomment qu’un seul quota résumé utilisateur.

React vérifie confirmation du coût, progression persistée et reprise. Le BFF vérifie HTTPS, sessions et liste de routes autorisées. Playwright vérifie recherche, pages sources surlignées, comparaison, absence de débordement mobile et plan de résumé long avant confirmation. Il crée puis supprime ses comptes/documents synthétiques et ne lance aucun POST de génération longue.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
$env:TEST_DATABASE_URL='postgresql+psycopg://documind:documind@127.0.0.1:5432/BASE_JETABLE_VIDE?connect_timeout=5'
.\.venv\Scripts\python.exe -m pytest -q
Remove-Item Env:TEST_DATABASE_URL
cd frontend
npm.cmd test
npm.cmd run build
$env:BYOK_E2E='1'
npm.cmd run test:e2e
Remove-Item Env:BYOK_E2E
```

La suite backend refuse une base contenant des tables métier, applique les migrations puis les annule à chaque cas. Ici, la validation PostgreSQL a utilisé des `--basetemp` neufs et `-p no:cacheprovider` pour contourner les permissions du dossier temporaire Windows existant.

## Mémoire réel et consommation

Deux documents de 53 pages présents dans la base contiennent actuellement environ **93142 caractères extraits** chacun, au lieu des 92319 signalés initialement. Aucune réextraction n’a été effectuée pour masquer cet écart. Leur plan est accepté : **16 parties, 31 étapes, cinq niveaux**, réservation maximale **0,33728 USD** selon les paramètres locaux vérifiés.

**Aucun appel OpenAI réel n’a été lancé par ces travaux ou tests.** Le mémoire a seulement fait l’objet d’une planification locale en lecture seule. Sa génération, sa qualité et son coût réellement facturé attendent une confirmation explicite dans l’interface.

Le `.env` utilisateur est préservé ; son `AI_ENABLED` était déjà à `true` lors de la vérification finale. L’exemple reste désactivé et sans secret. Le redémarrage invalide les sessions éphémères : se reconnecter puis reconnecter sa clé BYOK avant un essai réel.

## Routes et validation manuelle

Les huit routes RAG/indexation/comparaison sont détaillées dans le [guide Sprint 4](sprint-4-rag.md#routes-api). Les six routes de planification et de tâches sont dans le [guide des résumés approfondis](long-document-summary.md#api-et-interface). Le POST historique `/documents/{id}/summarize` conserve 200 en direct et renvoie désormais 202 pour une tâche longue.

Suivre le [parcours RAG](sprint-4-rag.md#validation-manuelle-volontaire) pour indexer et rechercher, et le [parcours du mémoire](long-document-summary.md#validation-et-mémoire-local) pour confirmer sa réservation. Commencer par les opérations locales sans IA ; toute génération réelle est volontaire.

## Fichiers ajoutés ou modifiés

Liste propre à ces travaux, hors artefacts générés et sauvegardes privées :

| Ensemble | Fichiers |
|---|---|
| Configuration | `.env.example`, `.dockerignore`, `compose.yaml`, `Dockerfile.db`, `pyproject.toml`, `requirements.lock` |
| Backend existant | `backend/config.py`, `models.py`, `main.py`, `auth.py`, `services/documents.py`, `ai/api.py`, `ai/service.py`, `ai/providers.py`, `ai/settings_api.py` |
| Nouveau RAG | `backend/rag/__init__.py`, `models.py`, `schemas.py`, `providers.py`, `billing.py`, `indexing.py`, `retrieval.py`, `comparison.py`, `service.py`, `api.py` |
| Résumé long | `backend/ai/long_models.py`, `long_plan.py`, `long_summary.py`, `long_api.py` |
| Migrations | `migrations/versions/0004_rag_vectors_jobs_and_results.py`, `0005_persistent_long_summary_steps.py` |
| Sauvegarde | `tools/backup_local.py`, `tools/verify_snapshot.py` |
| React | `frontend/src/App.tsx`, `components/Layout.tsx`, `Assistant.tsx`, `RagShared.tsx`, `LongSummary.tsx`, `pages/IntelligentLibrary.tsx`, `CompareDocuments.tsx`, `DocumentDetail.tsx`, `services/rag.ts`, `longSummary.ts`, `styles.css` |
| BFF | `frontend/server/app.mjs`, `app.test.mjs` |
| Tests | `tests/test_ai.py`, `test_rag.py`, `test_long_summary.py`, `frontend/src/pages/Rag.test.tsx`, `components/LongSummary.test.tsx`, `Assistant.test.tsx`, `test/app.test.tsx`, `frontend/e2e/rag.spec.ts` |
| Documentation | `README.md`, `docs/sprint-4-rag.md`, `long-document-summary.md`, `validation-sprint-4.md` |

Le dossier n’est pas initialisé comme dépôt Git ; aucun commit n’est créé.

## Limites et Sprint 5

Le coffre BYOK impose un seul processus API. Le worker de résumé est un thread dédié ; l’indexation utilise les tâches de fond FastAPI. Les états sont persistants, mais la reprise après redémarrage demande une reconnexion et une action explicite. Les appels ambigus nécessitent une réconciliation conservatrice. Les plafonds restent estimatifs, sans garantie de plafond absolu OpenAI.

La recherche est exacte, bornée et sans HNSW. La comparaison est heuristique et sensible à la segmentation/pagination. La synthèse de comparaison peut être partielle, avec couverture affichée. Les résumés peuvent perdre des détails ou contenir des erreurs : une référence valide ne prouve pas toute affirmation. Les permissions et coûts réels du compte OpenAI ne sont pas validés. L’authentification publique gérée, la récupération de compte et une politique de conservation de production restent à prévoir.

Sprint 5 suggéré : corpus de référence pour mesurer rappel/latence, FTS et reranking, HNSW seulement sur mesures, coffre éphémère distribué avant séparation des workers en services, meilleure segmentation, observabilité sans contenu privé et politique de purge/sauvegarde.
