# Sprint 4 — Recherche hybride et comparaison documentaire

## Audit et intégration

Le Sprint 3 conserve déjà, dans `document_chunks`, un UUID, le document, la page, l’ordre, les positions `start_char`/`end_char` et le texte exact. Ces données sont réutilisées sans modifier l’extraction ou le moteur desktop. `backend/ai/retrieval.py` fournissait une recherche lexicale française normalisée ; ses règles de tokenisation sont réutilisées dans le nouveau classement multi-documents.

`AIProvider`, le fournisseur Responses, les sessions BYOK, les verrous budgétaires et le journal `AIUsage` sont conservés. `EmbeddingProvider` est séparé du fournisseur de génération. Les nouveaux appels utilisent les mêmes portefeuilles `development` et `byok:{owner}:openai`, avec des quotas propres aux opérations du Sprint 4. Aucun second système de facturation ni stockage de clé n’est introduit.

La base utilisait `postgres:17-alpine`. `Dockerfile.db` ajoute pgvector **0.8.7** à cette même famille PostgreSQL 17 Alpine, en compilant l’extension pour son installation PostgreSQL. Le chemin des données et le volume Compose `postgres_data` sont conservés. Il n’y a ni suppression du volume, ni changement de version majeure ou de libc. Le [projet pgvector](https://github.com/pgvector/pgvector) documente compilation, distance cosinus et recherche exacte.

Le plan annoncé avant modification a été suivi : stockage et tâches, facturation par lots, recherche hybride, comparaison locale puis IA facultative, interfaces React, tests sur une base jetable et vérification de sauvegarde avant migration locale.

## Sauvegarder avant mise à niveau

Les sauvegardes peuvent contenir des documents sensibles et des hachages de mots de passe. Elles restent dans `var/backups`, exclu des builds et du suivi Git. Les protéger comme les données originales ; prévoir aussi une sauvegarde séparée appropriée à votre environnement. La clé BYOK n’est pas sauvegardée : elle n’est jamais persistée.

Depuis la racine du projet, avec l’ancienne application encore installée :

```powershell
docker compose stop web api
.\.venv\Scripts\python.exe tools/backup_local.py
```

Le script crée un dossier horodaté contenant :

- `database.dump` : archive PostgreSQL au format personnalisé ;
- `documents.tar.gz` : documents du volume privé ;
- `integrity.json` : nombres de lignes et empreintes des tables préexistantes contrôlées ;
- `manifest.json` : date et description.

Les services d’écriture doivent rester arrêtés pendant la sauvegarde et la vérification. Le script ne lit pas les mots de passe à haute voix et n’affiche aucun secret. Il utilise les identifiants déjà présents dans le conteneur PostgreSQL.

Construire l’image, puis démarrer les services :

```powershell
docker compose build db api web
docker compose --profile https up -d
```

L’API applique `alembic upgrade head` au démarrage. En production avec un rôle SQL restreint, faire installer l’extension `vector` par l’administrateur avant la migration. **Ne pas utiliser `docker compose down -v`.** Pour revenir au backend du Sprint 3, arrêter les écritures, sauvegarder, exécuter `alembic downgrade 0003` avec les fichiers du Sprint 4 encore présents, puis réinstaller l’ancien backend en gardant l’image PostgreSQL enrichie. La descente supprime les données propres au Sprint 4 ; elle conserve celles des Sprints 1–3 et laisse l’extension installée, car elle peut servir à d’autres tables.

Pour vérifier les anciennes tables après migration :

```powershell
.\.venv\Scripts\python.exe tools/verify_snapshot.py var/backups/VOTRE_DOSSIER
```

`--database NOM` permet de vérifier une restauration sur une autre base. L’outil est en lecture seule ; des écritures légitimes depuis la sauvegarde feront naturellement différer les empreintes.

Une restauration complète doit d’abord être éprouvée sur une base et un volume jetables : `createdb`, puis `pg_restore --exit-on-error` depuis l’archive, et extraction de l’archive des fichiers dans un volume neuf. Sous Windows PowerShell, transmettre les archives binaires par un flux fichier Python ou par `docker compose cp`, plutôt que par une redirection textuelle PowerShell. Vérifier les empreintes et les fichiers avant toute restauration décidée sur une installation réelle. Le script de sauvegarde ne remplace et ne supprime aucune base.

## Modèles et migration 0004

La migration `0004_rag_vectors_jobs_and_results.py` ajoute :

| Table | Fonction |
|---|---|
| `chunk_embeddings` | UUID chunk/document/propriétaire, vecteur, modèle, dimensions, version et date |
| `index_jobs` | État persistant d’indexation d’un document et d’une configuration, génération, progression et erreur contrôlée |
| `rag_results` | Résultats de recherche payante, réponses multi-documents, comparaisons et admissions idempotentes d’indexation |
| `rag_documents` | Documents associés aux résultats, pour autorisations et suppression |
| `ai_operation_documents` | Tous les documents d’une réservation active, pour protéger la suppression |

L’unicité `(chunk_id, model, dimensions, version)` interdit les doublons d’une configuration. Les vecteurs validés sont les points de reprise ; l’état et les erreurs des passages manquants sont portés par la tâche. Les anciens vecteurs ne sont jamais convertis silencieusement vers un nouveau modèle ou une nouvelle dimension. Plusieurs configurations peuvent coexister ; seule la configuration courante est recherchée.

La recherche PostgreSQL utilise `<=>`, la distance cosinus native, avec filtrage du propriétaire et des documents. Aucun index HNSW ou IVFFlat n’est créé : la recherche est exacte. Il faudra mesurer latence, taille et rappel avant d’introduire un index approximatif. SQLite utilise JSON et une distance Python uniquement pour les tests portables.

Les vecteurs sont supprimés par cascade. La suppression applicative d’un document retire aussi tous les résultats RAG qui lui sont liés, même s’ils citent d’autres documents. Elle refuse les tâches actives et les réservations multi-documents en cours. Les écritures financières sans texte restent conservées pour empêcher une remise à zéro des plafonds par suppression. Utiliser l’API de suppression ; une manipulation SQL directe des tables d’association n’est pas une procédure de purge applicative.

## Indexation explicite et reprise

Ouvrir **https://localhost:8443/library** et se connecter à un compte personnel depuis les paramètres IA. Le certificat HTTPS et le secret de liaison doivent être configurés selon le [guide BYOK](sprint-3-ai-byok.md). Le partage HTTP classique continue de fonctionner ; les nouvelles recherches web utilisent HTTPS pour identifier le compte.

1. Importer les PDF/TXT normalement. Aucun embedding n’est généré à l’import.
2. Sélectionner les documents dans la bibliothèque intelligente.
3. Lire l’information d’envoi et cocher le consentement.
4. Cliquer **Indexer / reprendre les passages manquants** pour chaque document.
5. Suivre la progression et les éventuels codes d’erreur. Les budgets sont contrôlés avant chaque lot.

La tâche et ses points de reprise sont persistants. L’exécution se fait après la réponse HTTP, dans les tâches de fond FastAPI. Quatre tâches actives au maximum sont admises ; le plafond existant des réservations limite également les appels simultanés. Il s’agit d’un exécuteur local avec reprise explicite, pas d’une file distribuée avec livraison automatique.

À chaque lot, la session, la clé, le mode de financement et les tarifs sont revérifiés. Une déconnexion, une expiration ou un changement de mode met la tâche en pause. Après redémarrage, les tâches `queued`/`running` deviennent `paused` et attendent une reconnexion puis un clic de reprise. Aucun token de session ou secret n’est stocké avec la tâche.

Un clic normal ne recalcule pas les vecteurs présents. Une reprise traite uniquement les passages manquants. **Réindexer explicitement** demande confirmation et efface les vecteurs de la configuration courante avant recalcul ; cela peut être facturé à nouveau. Une retransmission du même UUID de demande ne redéclenche pas une réindexation.

Une interruption pendant un appel peut laisser une réservation incertaine. Elle n’est pas relancée automatiquement. Utiliser la procédure de réconciliation conservatrice du Sprint 3, API arrêtée ; une nouvelle réindexation explicite peut ensuite être nécessaire pour recalculer le lot dont la réponse a été perdue. Elle peut entraîner une seconde charge. Une réconciliation ne rembourse jamais une charge inconnue.

Pour les gros documents, la limitation de débit peut mettre l’indexation en pause : attendre une minute, puis reprendre. Le plafond ou le quota peut également demander une intervention. Une clé nouvelle ne remet pas les compteurs à zéro. Le mode BYOK reste limité à un seul processus API et à la durée de session de 30 minutes par défaut.

## Recherche hybride et réponses multi-documents

La bibliothèque permet une recherche lexicale sans appel fournisseur. Avec l’option vectorielle et le consentement, le texte de la recherche est envoyé au fournisseur d’embeddings, puis le vecteur est comparé aux chunks autorisés. Les listes lexicale et vectorielle sont fusionnées par **Reciprocal Rank Fusion**, avec `k=60`. Les résultats exposent rangs, score RRF et distance cosinus ; ce ne sont pas des probabilités de vérité.

Chaque résultat contient UUID du chunk, document et nom, page, positions et extrait exact. « Ouvrir le passage » ouvre le texte extrait à la bonne page et surligne le fragment. Les résultats affichent du texte échappé, sans HTML exécuté.

Sans index compatible ou avec IA désactivée/non configurée, la recherche revient au lexical. Une panne du fournisseur d’embeddings produit également un résultat lexical pour la recherche simple, avec avertissement et réservation éventuellement maintenue. Les chunks non indexés restent présents dans la branche lexicale. Une indexation partielle est signalée ; elle n’est pas assimilée à une couverture sémantique complète.

**Demander une réponse sourcée** utilise les passages sélectionnés, dans la borne de contexte. La recherche peut être lexicale ou hybride. Les références de sortie doivent appartenir exactement au contexte fourni ; une référence inventée fait rejeter le résultat. Si aucun passage pertinent n’est disponible, une réponse locale d’information insuffisante peut être rendue sans génération. Les anciennes conversations ne sont pas envoyées.

Le contrôle de propriété est réalisé sur tous les documents avant tout appel et dans les requêtes SQL. Un seul document non autorisé fait échouer la sélection avec 404, sans embedding de la question. Aucun UUID propriétaire n’est fourni par le navigateur. Les limites documents/passages/chunks bornent le travail et le contexte. Le texte des documents est traité comme des données non fiables ; les instructions ne lui donnent ni outils ni accès aux secrets. La fidélité factuelle d’une réponse doit toujours être vérifiée humainement.

## Comparaison de versions

Ouvrir **https://localhost:8443/compare**, sélectionner A puis B et cliquer **Comparer A → B sans appel IA**. Le résultat reçoit une URL persistante `/comparisons/{id}`.

La couche déterministe :

- construit des paragraphes par page, conserve leur texte source et leurs pages ;
- normalise Unicode et les espaces/retours de ligne, sans effacer casse, nombres ou ponctuation ;
- aligne les blocs avec `SequenceMatcher` ;
- rapproche les suppressions/ajouts identiques pour reconnaître les déplacements, y compris des occurrences répétées ;
- rapproche heuristiquement les paragraphes ressemblants pour signaler une modification ; les autres restent des ajouts ou suppressions.

Les vues A/B utilisent des libellés textuels et des couleurs distinctes. Les pages sources restent navigables. Des différences de pagination ou de segmentation peuvent produire des écarts supplémentaires : ce n’est pas une comparaison sémantique garantie des intentions. Le calcul est borné en caractères et en blocs, sans prétendre traiter silencieusement des documents dépassant ces limites.

La synthèse IA est séparée, facultative et soumise au consentement. Seules les différences détectées sont transmises, avec leurs extraits A/B et pages. Le modèle renvoie des observations par thème, chacune liée à un `change_id` existant, ainsi qu’un point de vérification et des limites. La synthèse ne peut pas créer de référence vers une différence absente. Une affirmation générée peut néanmoins être inexacte : les extraits déterministes restent la preuve à consulter, et aucune conclusion juridique définitive n’est donnée.

Au maximum 30 changements entrent dans une synthèse, dans la limite de contexte. Le nombre réellement transmis est affiché. Si le premier changement ne tient pas, la génération est refusée avant appel. Les documents identiques n’ont pas besoin de génération.

## Configuration et coûts

Les variables sont dans `.env.example`, sans secret. Les nouvelles valeurs initiales sont :

| Variable | Défaut |
|---|---|
| `EMBEDDING_MODEL`, `EMBEDDING_DIMENSIONS` | `text-embedding-3-small`, `1536` |
| `EMBEDDING_VERSION`, `EMBEDDING_BATCH_SIZE` | `chunks-v1`, `16` |
| `EMBEDDING_INPUT_USD_PER_MILLION` | `0.02` |
| `EMBEDDING_PRICING_MODEL`, `EMBEDDING_PRICING_VERIFIED_ON` | `text-embedding-3-small`, `2026-10-19` |
| `EMBEDDING_BATCH_QUOTA` | `500` lots cumulés par propriétaire |
| `RAG_SEARCH_QUOTA`, `RAG_QUESTION_QUOTA`, `RAG_COMPARISON_QUOTA` | `200`, `100`, `20` |
| `RAG_MAX_DOCUMENTS`, `RAG_MAX_PASSAGES`, `RAG_MAX_CHUNKS` | `10`, `8`, `10000` |
| `COMPARISON_MAX_CHARS`, `COMPARISON_MAX_BLOCKS` | `200000` par document, `2000` |

La [fiche officielle du modèle](https://developers.openai.com/api/docs/models/text-embedding-3-small) et le [guide des embeddings](https://developers.openai.com/api/docs/guides/embeddings), consultés le 19 octobre 2026, indiquent 1536 dimensions par défaut et un tarif d’entrée standard de 0,02 USD par million de tokens. La disponibilité pour votre compte n’a pas été testée par un appel réel. Le bouton de validation BYOK du Sprint 3 vérifie le modèle de génération ; les permissions spécifiques aux embeddings peuvent encore être refusées lors de leur utilisation.

Le prix et le modèle doivent correspondre, avec une date de vérification de moins de 90 jours. Changer de modèle exige de vérifier ses prix et capacités. Les entrées sont bornées à 8000 octets UTF-8 par passage pour rester sous la borne de tokens du modèle ; un chunk trop grand est refusé, sans découpage silencieux différent des données originales.

Une réservation atomique couvre chaque lot avant son appel. Les tokens réellement retournés alimentent le journal commun avec le modèle d’embeddings. Une recherche avec réponse réserve ensemble le coût maximal de l’embedding de requête éventuel et de la génération bornée. Les échecs connus libèrent le reliquat ; les échecs ambigus conservent la réservation. Le SDK d’embeddings ne réessaie pas automatiquement. Les appels de génération conservent la politique du Sprint 3.

Les plafonds sont communs aux opérations du compte, et ne constituent toujours pas un plafond absolu de facturation OpenAI. Une réindexation est un nouvel usage. Les paramètres IA affichent les tokens/coûts par appel, et les nouvelles pages affichent budget et quotas cumulés. Les compteurs historiques `requests` du statut Sprint 3 concernent ses résumés/questions ; les quatre quotas supplémentaires sont consultables sur `/search/status` et dans les nouvelles pages.

## Routes API

| Route `/api/v1` | Réponse |
|---|---|
| `POST /documents/{id}/index` | 202, tâche persistée, consentement et UUID requis ; `force` facultatif |
| `GET /documents/{id}/index` | 200, toutes les configurations et leurs états |
| `GET /search/status` | 200, configuration et quotas du propriétaire |
| `POST /search/semantic` | 200, passages lexicaux ou hybrides ; sélection de documents et UUID |
| `POST /search/ask` | 200, réponse structurée avec sources vérifiées |
| `POST /documents/compare` | 200, comparaison locale de `document_a` et `document_b` |
| `GET /comparisons/{id}` | 200, comparaison persistée du propriétaire |
| `POST /comparisons/{id}/summarize` | 200, synthèse facultative avec consentement et UUID |

Erreurs principales : 401 authentification ; 403 génération désactivée/session révoquée ; 402 budget ; 404 ressource non autorisée ; 409 conflit/idempotence ou traitement actif ; 413 limites ; 422 paramètres/consentement ; 429 quota/débit/concurrence ; 502 sortie invalide ; 503 fournisseur/tarifs/charge incertaine. Une tâche acceptée en 202 peut ensuite être `failed` ou `paused` : consulter son état. Les messages d’erreur ne reproduisent pas les exceptions fournisseur.

Le BFF autorise uniquement ces routes précises. Les POST d’indexation, recherche et synthèse exigent une session HTTPS ; il ne s’agit pas d’un proxy OpenAI ouvert. Swagger direct reste réservé aux clés administratives locales et au mode propriétaire. Les comptes BYOK utilisent le parcours HTTPS du BFF.

## Validation manuelle volontaire

1. Vérifier le certificat HTTPS, se reconnecter après le redémarrage de l’API et importer deux documents fictifs. A : budget Atlas 120 euros ; B : budget Atlas 150 euros et une phrase ajoutée.
2. Comparer A/B et ouvrir les références de pages, sans IA.
3. En gardant l’IA désactivée, effectuer une recherche lexicale sur les deux documents depuis la bibliothèque ; vérifier l’extrait et le surlignage.
4. Pour un essai payant volontaire seulement : configurer `AI_ENABLED=true`, `AI_PROVIDER=openai`, un petit plafond BYOK (par exemple 0,05 USD), une clé connectée/validée et des quotas bas. Recréer l’API puis se reconnecter. Aucun changement de modèle n’est nécessaire.
5. Autoriser et indexer A/B, vérifier état terminé et coûts dans les paramètres. Cliquer à nouveau sur l’indexation normale : pas de nouvel appel pour les passages présents.
6. Activer la recherche vectorielle, rechercher le budget, puis poser une question multi-documents. Vérifier les passages et les références. Contrôler aussi l’usage dans le compte OpenAI.
7. Autoriser la synthèse de comparaison. Vérifier chaque observation contre les extraits A/B et la couverture annoncée.
8. Tester un plafond à zéro : aucun nouvel appel. Déconnecter la clé et remettre `AI_ENABLED=false` si l’essai est terminé.

Les tests automatisés ne font aucun appel OpenAI réel. Ils utilisent des embeddings simulés, y compris dans la véritable intégration PostgreSQL/pgvector. Le [rapport de validation](validation-sprint-4.md) donne les commandes, résultats, fichiers et limites restantes, ainsi que les pistes du Sprint 5.
