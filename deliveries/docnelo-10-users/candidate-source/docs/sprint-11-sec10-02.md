# Sprint 11, lot 1 — Admission des uploads avant réception (SEC10-02)

## Périmètre et état

Correction et recette locales uniquement. Aucun commit, push, workflow distant, déploiement de production,
accès VPS/Registry, changement de secret ou activation IA/inscriptions.
Verdict au 21 octobre 2026 : recette fonctionnelle locale Docker/HTTPS réussie ; validation
de production non acquise. Les essais complets de capacité, les contrôles PostgreSQL
sous contrainte et la vérification de la chaîne Traefik du VPS restent à réaliser.
Les mécanismes Landlock/seccomp et les scripts/unités des Sprints 7–9 restent inchangés.
SEC10-03 n'est pas traité : les autres routes conservent leur politique Bearer/clé existante.

La garantie porte sur l'application : une session refusée ne doit provoquer aucun appel
ASGI receive, aucune création de spool, aucun parsing multipart et aucun fichier documentaire.
Les buffers TCP/TLS/HTTP des serveurs ne peuvent pas être rendus inexistants par cette correction.

## Étape 1 — Reproduction avant correction

`tests/test_upload_admission.py` a été créé avant les changements applicatifs.
Les dix variantes absent/inventé/expiré/révoqué/compte désactivé, avec/sans slash final,
échouaient sur l'ancien code : deux lectures pour le cas sans session, et redirection 307
sur le chemin avec slash, après réception du corps. La requête fictive dépasse 256 Kio.
Le test instrumente aussi le spool et vérifie l'absence de répertoire documentaire.

Les neuf premiers tests BFF de `server/upload-admission.test.mjs` échouaient avant sa
correction : pas de prévalidation, upload transmis malgré le refus attendu de session.
Ces preuves complètent la sonde historique du Sprint 10 (1 048 692 octets avant 401).

## Étape 2 — Admission indépendante dans FastAPI

- `backend/authentication.py` factorise la logique de `owner()` : SessionVault, expiration,
  utilisateur existant/actif, correspondance propriétaire, révocation et clé historique.
- `backend/upload_admission.py` installe une admission ASGI pure ; le limiteur IP est également
  ASGI pur. Ordre effectif : IP, admission upload, RequestSizeLimit, routage/parsing.
- Aucun receive ni temporaire avant authentification. Les deux variantes du chemin d'upload
  sont couvertes ; les refus ne passent pas par une redirection demandant de renvoyer le corps.
- Les limites utilisateur et uploads sont débitées une seule fois, avant réception ;
  les prévalidations et recontrôles ne débitent pas à nouveau les quotas utilisateur.
- L'endpoint interne GET `/api/v1/internal/upload-admission` exige secure_gateway et une
  session personnelle ; il retourne 204 sans corps, no-store, sans profil ou clé BYOK.
  Il n'apparaît ni dans Swagger ni dans l'allowlist publique du BFF.
- Le Bearer est revérifié après chaque lecture de corps, avant parsing métier et après
  extraction avant persistance. Une révocation pendant l'extraction interdit la création.
- L'état déjà admis est créé côté serveur dans scope.state, jamais à partir d'un en-tête client.

Les checks SQL d'identité utilisent un pool PostgreSQL dédié (2 connexions, aucun overflow,
attente de pool 1 s, connect_timeout 1 s, statement_timeout 1 s). SQLite réutilise le moteur
de l'application, notamment pour préserver les bases en mémoire. L'admission asynchrone a un
plafond de tâches ; un timeout ne libère le slot de vérification qu'à la fin réelle du thread.
Un abandon côté client ne doit donc pas créer une accumulation non bornée de tâches SQL.

## Étape 3 — BFF et transport

- Host, origine, confiance proxy/HTTPS et CSRF restent vérifiés avant toute prévalidation.
- Pour les uploads en mode authentifié (toujours activé par loadConfig en production),
  req est en pause puis le BFF interroge l'endpoint interne, sans corps ni donnée du fichier.
- Seul 204 autorise req.pipe. Session refusée : 401/403 ; API indisponible, timeout,
  redirection ou réponse inattendue : refus fermé 503 ; aucun fallback vers une clé partagée.
- Plafonds distincts de prévalidations et transferts ; timers de réception total/inactivité.
  Un abandon de requête ou fermeture de réponse annule l'appel upstream.
- Le serveur HTTP partagé `http-server.mjs` remet checkContinue à l'application : pas de
  100 Continue avant admission. Les connexions HTTP/1 d'upload ne sont pas réutilisées ;
  la sortie est fermée proprement, sans req.destroy immédiat qui pouvait perdre HTTP 413.
- Les tests transport historiques peuvent injecter une configuration sans requireLogin ;
  aucun paramètre d'environnement de production ne permet cette désactivation.

La présence d'un cookie ou d'un CSRF valide n'est jamais assimilée à une session valide.
Le frontend ne reçoit aucun credential BFF, Bearer brut ou clé personnelle dans cette admission.

## Étape 4 — Multipart, budgets et nettoyage

| Paramètre | Valeur initiale |
| --- | --- |
| MAX_UPLOAD_BYTES | 10485760 (10 Mio) |
| Corps total | MAX_UPLOAD_BYTES + 65536 |
| UPLOAD_MAX_CONCURRENT | 2 |
| UPLOAD_MAX_PER_OWNER | 1 |
| UPLOAD_MAX_PREFLIGHTS | 8 |
| UPLOAD_TEMP_BUDGET_BYTES | 67108864 (64 Mio) |
| UPLOAD_MIN_FREE_BYTES | 33554432 (32 Mio) |
| UPLOAD_AUTH_TIMEOUT_SECONDS | 3 |
| UPLOAD_READ_TIMEOUT_SECONDS | 30 |
| UPLOAD_IDLE_TIMEOUT_SECONDS | 5 |
| UPLOAD_TOTAL_TIMEOUT_SECONDS (BFF) | 75 |

Chaque admission réserve 3 × MAX_UPLOAD_BYTES + 2 × 65536 octets : spool brut, fichier
multipart et .part. Les .part déjà présents sont comptés conservativement, y compris
les restes d'un arrêt brutal ; l'admission ne les supprime jamais. L'espace libre des
deux systèmes de fichiers est contrôlé avec les réservations actives et la marge.
Cette réservation applicative ne protège pas contre l'écriture simultanée d'un autre
processus : la recette doit confirmer les marges et l'absence d'OOM/ENOSPC.

`backend/uploads.py` réutilise MultiPartParser avec un fichier nommé file, zéro champ
texte, limite réelle des octets fichier et réception obligatoire de on_end. Ne pas se
reposer sur finalize() de python-multipart, qui ne contrôle pas l'état final installé.
Tous les handles créés sont fermés sur erreurs/cancellation. Les spools de requête et
réservations sont libérés en sortie ; import_document garde rollback et nettoyage .part/final.
Un arrêt forcé du processus ne peut pas exécuter finally : les .part persistants sont
conservés et empêchent une nouvelle admission si le budget est insuffisant.

Swagger conserve le champ multipart file obligatoire malgré le parsing explicite.
Codes principaux : 401 identité, 403 gateway/CSRF, 429 fréquence, 503 capacité/auth indisponible,
408 réception lente, 413 taille, 400 multipart/encadrement incomplet, 415 format non supporté.
Un client déconnecté ne reçoit naturellement pas de réponse ; les ressources sont libérées.

## Cohérence Traefik / Node / API

Compose production donne les mêmes limites de taille/réception/auth aux deux services.
Un router POST /bff/documents dédié limite les requêtes en vol (8, groupées par hôte),
sans buffering et sans modifier les entrypoints ou les autres applications du VPS.
La topologie, les volumes, les processus uniques et les protections Docker restent conservés.

Node : headersTimeout 10 s, requestTimeout 60 s ; la réception applicative est bornée à 30 s.
Le budget BFF 75 s couvre prévalidation 3 s + réception 30 s + extraction 30 s + marge.
La configuration BFF refuse un budget inférieur à auth + réception + worker + 5 s ;
elle refuse aussi les capacités non entières, un délai inactif supérieur au délai total,
et auth + réception + headers qui dépasserait les 60 s du serveur HTTP Node.
Les autres requêtes gardent leurs délais existants ; aucun délai IA n'a été modifié.

La configuration statique réelle de Traefik, ses middlewares hérités, sa version exacte
et ses protocoles ne sont pas connus depuis cette session. Ils doivent être vérifiés
avant recette/déploiement, notamment HTTP/2 et éventuel HTTP/3. Un buffering placé avant
le BFF invaliderait la garantie à cette frontière. Aucun changement global de Traefik proposé.
La recette utilise readTimeout=60 s et writeTimeout=90 s ; les valeurs de production ne
sont pas supposées identiques et doivent être confrontées au budget BFF avant déploiement.

Le timer BFF borne sa réponse, pas la durée physique d'un thread Python déjà dans SQL.
Une déconnexion après corps complet peut laisser un import autorisé terminer ; ses
réservations restent détenues jusqu'à sa fin. La recette PostgreSQL doit vérifier les
attentes de verrous/connexions et le nettoyage final, sans promettre une interruption
instantanée de la persistance. Les timeouts du pool dédié concernent l'authentification,
pas toutes les transactions métier existantes.

## Tests et preuves locales

Suites ciblées API : refus sans receive/spool, chemins avec slash, taille exacte/+1,
flux sans Content-Length, multipart tronqués, déconnexion, révocation pendant réception
et extraction, délais total/inactif, manque de stockage/budget/capacité, prévalidation,
limitation avant réception, concurrence réelle de propriétaires, réutilisation des slots,
OpenAPI et maintien de la politique Bearer sur les autres routes.

Suites BFF : sessions refusées, API offline/timeout/503/réponse inattendue, ordre des appels,
CSRF, cookie absent/mal formé, endpoint interne non exposé, Expect 100-continue,
capacité de prévalidation et réception lente suivie d'un nouvel upload accepté.
Le dernier test ajouté couvre aussi la déconnexion pendant un upload autorisé : réception
partielle confirmée, signal d'annulation upstream, fermeture du flux et nouvel upload 201
avec une capacité limitée à un transfert. Il utilise des événements/promesses et des
délais de sécurité, sans attente arbitraire de synchronisation.

Le test historique de course du quota SQL autorise explicitement deux admissions dans
sa seule configuration de test afin de continuer à exercer le verrou SQL. Le test des
deux workers utilise désormais deux propriétaires ; aucune politique sandbox n'est changée.

Résultats antérieurs des suites complètes, obtenus le 21 octobre 2026 :

| Contrôle | Résultat |
| --- | --- |
| Suite portable Windows / Python 3.13 | 524 réussis, aucun échec/skip, 1 avertissement |
| Suite Linux WSL Ubuntu / Python 3.12 | 564 réussis, aucun échec/skip, 1 avertissement |
| Dont admission API SEC10-02 | 35 réussis sous Windows et Linux |
| Dont preuves Linux sandbox / protocole | 40 + 32 réussis |
| BFF Node (npm run test:bff) | 41 réussis, aucun échec/skip |
| React (npm run test:ui) | 37 réussis dans 7 fichiers |
| TypeScript + Vite (npm run build) | Réussi |
| Deux fichiers Compose, syntaxe et interpolation avec credentials/digests fictifs, sans résolution d'env_file | Réussies |
| git diff --check | Réussi |

Ces résultats complets sont conservés comme preuves antérieures ; ils ne signifient pas
que toutes ces suites ont été relancées après l'ajout du dernier test de déconnexion BFF.
Les validations ciblées actuelles du 21 octobre 2026 sont :

| Contrôle ciblé | Résultat |
| --- | --- |
| BFF : `node --test .\frontend\server\upload-admission.test.mjs` | 17 réussis, 0 échec |
| API : `tests/test_upload_admission.py` | 35 réussis, 0 échec |
| Total ciblé | 52 réussis, 0 échec |
| Recherche de fichiers `.part` résiduels dans `/app/var` de l'API de recette | Aucun fichier résiduel |
| `git diff --check` | Réussi |

Les JUnit locaux ignorés sont var/sec11-windows.xml et var/sec11-linux.xml. Le contrôle
Linux a utilisé une copie de sources/dépendances dans /tmp/documind-sec11.FMt7kO,
sans .env privé ; l'identité de tous les fichiers backend Python avec le workspace
a été vérifiée après les tests. Noyau local 6.18.54.1-microsoft-standard-WSL2, amd64,
Landlock ABI 7 : cela ne certifie pas la future image Docker/Python 3.13 sur ABI 6.
Un premier run Windows avait détecté le test historique à deux uploads du même propriétaire ;
après adaptation explicite du scénario, la suite complète a été réexécutée et passe.
Le premier doublon Linux sur /mnt/c, plus lent et basé sur l'ancien test, a été interrompu
au profit du run jetable complet ci-dessus ; il n'est pas compté comme preuve de réussite.

Les avertissements Starlette/httpx historiques sont distincts de SEC10-02. Les nouveaux
tests BFF font partie de npm test:bff et sont donc exécutés par le workflow CI existant
sans nouveau workflow. L'accès esbuild aux parents requis par le build a nécessité une
exécution locale hors restriction de lecture ; aucune configuration de sécurité n'a changé.

Inventaire par étape :

| Étape | Fichiers |
| --- | --- |
| Reproduction/API | tests/test_upload_admission.py |
| Auth et admission | backend/authentication.py, backend/upload_admission.py, backend/main.py, backend/api.py, backend/db.py |
| Parser/import | backend/uploads.py, backend/services/documents.py |
| BFF | frontend/server/app.mjs, config.mjs, index.mjs, http-server.mjs, upload-admission.test.mjs ; frontend/package.json |
| Paramètres | backend/config.py, .env.example, .env.production.example, compose.production.yaml |
| Régressions | tests/conftest.py, tests/test_accounts_saas.py, tests/test_extraction_protocol.py |
| Recette/rapport | compose.upload-test.yaml, ops/testing/traefik-upload-test.yaml, ce document |

Les fins de ligne du fichier BFF app.mjs ont été harmonisées en LF pour éliminer les
avertissements de formatage du diff ; les autres modifications fonctionnelles sont
celles décrites ci-dessus. Aucun changement de dépendance ni de migration.

## Recette Docker jetable — exécutée localement le 21 octobre 2026

La recette fonctionnelle a été exécutée sous Windows 11 avec Docker Desktop et WSL,
sur une stack jetable distincte de la production. Les quatre services sont opérationnels :
PostgreSQL, API FastAPI, BFF Node et Traefik de recette.

L'accès HTTPS local fonctionne via `https://documind.test:18443`, avec un certificat
autosigné et une résolution locale du domaine. La connexion au compte fictif
`sec11-upload-test` a réussi, ainsi que l'importation d'un document TXT fictif.
Le contrôle de `/app/var` n'a trouvé aucun fichier `.part` résiduel.
Aucun identifiant de session, cookie, mot de passe réel ou clé privée n'est reproduit ici.

`compose.upload-test.windows.yaml` est une surcharge strictement locale, exclue du suivi
Git, nécessaire pour rendre le port HTTPS accessible depuis Docker Desktop. Elle ne fait
pas partie des fichiers à publier et ne modifie pas le Compose de production. Pour
reproduire cette recette Windows, ajouter `-f compose.upload-test.windows.yaml` après
`-f compose.upload-test.yaml` dans les commandes Compose locales ci-dessous ; cette
surcharge n'est pas nécessairement applicable à un poste Linux natif.

Ces résultats valident le parcours local connexion/import TXT, pas toute la matrice de
sécurité via HTTPS, les essais de charge complets, la configuration Traefik du VPS ou la
production. Les procédures ci-dessous restent utiles pour reproduire et compléter les
contrôles ; leur présence ne constitue pas une preuve d'exécution de chaque commande.
Utiliser un poste de test compatible Landlock ABI >=3, jamais les services du VPS.

Les fichiers compose.upload-test.yaml et ops/testing/traefik-upload-test.yaml utilisent :

- un projet distinct documind-sec11-upload-test, aucun réseau externe ni volume nommé ;
- PostgreSQL et documents sur tmpfs, credentials explicitement fictifs, pas d'env_file ;
- API/BFF non exposés, seul HTTPS lié à 127.0.0.1:18443, aucun socket Docker monté ;
- réseaux internes sans egress applicatif, IA/owner demo/inscriptions désactivés ;
- conteneurs non privilégiés, seccomp Docker conservé, no-new-privileges, cap-drop,
  racines read-only et limites mémoire/CPU/PID ; sandbox obligatoire ;
- Traefik séparé uniquement sur ce poste de recette, version/digest à fournir explicitement,
  certificat local vérifié, pas de resolver Let's Encrypt ni contact du domaine réel.

Avant exécution vérifier l'absence de conflit du port 18443 et du sous-réseau de test
172.30.251.0/24. Le cas échéant adapter uniquement le fichier de recette, son IP de proxy
de confiance et le sous-réseau ensemble. Vérifier que l'UID app de l'image vaut 1000 pour
le tmpfs documentaire, sinon adapter uniquement l'UID de recette au résultat observé.

Procédure de reproduction Bash sur le poste jetable, depuis la racine du dépôt, après revue
(ne pas recréer un compte déjà présent dans la recette en cours) :

```bash
umask 077
mkdir -p var/sec11-upload-test/tls
read -r -p 'Image Traefik de recette approuvée, épinglée par digest : ' TRAEFIK_TEST_IMAGE
printf 'TRAEFIK_TEST_IMAGE=%s\nUPLOAD_TEST_UID=%s\nUPLOAD_TEST_GID=%s\n' \
  "$TRAEFIK_TEST_IMAGE" "$(id -u)" "$(id -g)" > var/sec11-upload-test/recipe.env
openssl req -x509 -newkey rsa:2048 -nodes -days 2 \
  -keyout var/sec11-upload-test/tls/documind.test.key \
  -out var/sec11-upload-test/tls/documind.test.crt \
  -subj '/CN=documind.test' -addext 'subjectAltName=DNS:documind.test'
dc() { docker compose --env-file var/sec11-upload-test/recipe.env \
  -p documind-sec11-upload-test -f compose.upload-test.yaml "$@"; }
dc config --quiet
dc build
dc up -d db
dc run --rm --no-deps api alembic upgrade head
dc up -d api web traefik
dc exec -T api python - <<'PY'
from uuid import uuid4
from backend.main import app
from backend.auth import User, hash_password
with app.state.sessions() as db:
    db.add(User(owner_id=uuid4(), username='sec11-upload-test',
                password_hash=hash_password('fictitious-upload-password-123')))
    db.commit()
PY
curl --fail --cacert var/sec11-upload-test/tls/documind.test.crt \
  --resolve documind.test:18443:127.0.0.1 https://documind.test:18443/bff/health
```

Ne pas utiliser -k, .env.production, un credential réel ou un document existant.
Utiliser curl avec le certificat, un cookie jar de test sous var/, GET /bff/auth/csrf,
puis POST /bff/auth/login et le compte fictif ; renouveler le CSRF après connexion.
Le parcours TXT et la connexion ont été exécutés ; restent à compléter via HTTPS :
PDF synthétique, sessions inventées/révoquées et l'ensemble
des cas de la matrice ci-dessus via HTTPS. La révocation réelle se fait par logout, la
désactivation uniquement dans la base tmpfs de recette. Ajouter des essais HTTP/1.1 et
HTTP/2 si supportés ; ne pas déduire leur succès des tests ASGI.

Validation complémentaire restant à réaliser dans l'image Linux : construire --target isolation-tests,
et lancer avec --network none, --read-only, --cap-drop ALL, --security-opt no-new-privileges,
--memory 1536m, --cpus 2, --pids-limit 64 et un tmpfs /tmp de 256 Mio ; commande pytest
tests/test_upload_admission.py tests/test_extraction_linux.py tests/test_extraction_protocol.py.
Les fixtures y créent uniquement leurs propres SQLite temporaires ; ne pas injecter TEST_DATABASE_URL.

Campagne de capacité restant à réaliser : au plus trois uploads fictifs à la fois, jusqu'à
10 Mio chacun. Vérifier une admission maximum de deux globalement et un par propriétaire,
refus avant réception des excédents, mémoire/tmpfs/disque/PID, santé disponible, puis
retour des ressources au niveau initial après succès, erreur, timeout et déconnexion.
Exécuter aussi la suite contre une base PostgreSQL 17/pgvector jetable vide distincte
du compte de recette, pour vérifier le pool d'auth, les timeouts et les quotas transactionnels.

Arrêt explicite de ce seul projet : `dc down`. Aucun down -v, prune ou suppression de
volume existant nécessaire ; la recette ne possède aucun volume persistant nommé.

## Critères de décision

- Accepter le code local seulement avec suites finales sans échec non résolu, zéro lecture
  préauth prouvé, absence de fuite de handles/slots/fichiers sur les erreurs couvertes.
- La recette fonctionnelle Docker/HTTPS locale est réussie ; ne pas déclarer le lot validé
  pour production avant les contrôles complémentaires Docker/PostgreSQL, la confirmation
  des marges de ressources et l'examen de la chaîne Traefik réelle du VPS.
- Refuser si un chemin d'upload accepté contourne l'admission, si la capacité est dépassée,
  si une déconnexion laisse des réservations, ou si le sandbox exige un assouplissement.
- Retour arrière éventuel : version applicative précédente compatible schéma 0006, selon
  la procédure approuvée de déploiement, sans downgrade SQL ni changement de volumes.
  Ce document ne donne aucune autorisation de publication ou de déploiement.
