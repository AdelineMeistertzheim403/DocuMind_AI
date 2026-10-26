# Sprint 14.7.2 — Diagnostic de l'échec intermittent SQLAlchemy

26 octobre 2026. Travail local sur `preparation/sprint-14-5-ux-email-abuse`,
HEAD `8243e0511c5505a9cc70f76ad02392f7a816590d`. Le
[rapport 14.7.1](SPRINT_14_7_1_RELEASE_CANDIDATE_REVIEW.md) a été lu intégralement.
Les 65 fichiers candidats existants sont relevés par SHA-256 avant investigation.
La production Sprint 13/0007, inscriptions fermées et IA off, reste un état fourni
par l'opératrice ; aucune vérification distante dans ce lot.

**Incident non résolu : non reproduit dans la nouvelle référence WSL.**
Aucune correction applicative n'est appliquée. Les comparaisons finales WSL,
Docker et PostgreSQL réussissent, sans expliquer le SQLAlchemyError historique.
Une réussite sans réapparition du 503 ne suffit pas à expliquer l'incident.

## 1. Symptôme initial conservé

En 14.7.1, suite complète WSL : **795 réussis, 27 ignorés, un échec**, 1 174,33 s.
Cas : `test_worker_interruption_resume_and_owner_isolation`,
`tests/test_long_summary.py:159`. Après interruption, récupération et reprise,
le GET de suivi renvoie HTTP 503 au lieu de 200 dans `wait_job()`.
L'événement `system.database.unavailable` est présent, mais aucune exception détaillée.

Le gestionnaire de `backend/main.py` intercepte `SQLAlchemyError`, émet cet événement
et renvoie une réponse générique. Cela établit la famille d'exception, **pas** sa
classe exacte, sa cause DBAPI, sa requête ou l'existence d'un verrou SQLite.
Le timeout applicatif de suivi n'est pas l'assertion en échec dans cette occurrence.

Les trois répétitions isolées et le fichier complet avaient réussi après cet échec.
Les suites Windows et WSL initiales tournaient en parallèle, sur des bases distinctes.
Ces résultats et journaux 14.7.1 sont conservés ; aucun n'est remplacé par les nouveaux.

## 2. Parcours et cycle de vie examinés

| Fichier / fonction | Faits confirmés |
| --- | --- |
| `tests/test_long_summary.py` | Attend une première étape partial, fait `thread.join(2)`, appelle `recover()`, crée un nouveau worker, vérifie les refus inter-propriétaires puis reprend le même job. Le join de deux secondes n'est pas suivi d'une assertion d'arrêt ; ce seul constat n'établit pas la cause du 503. |
| `backend/db.py` | Un engine applicatif, `sessionmaker(expire_on_commit=False)` ; chaque appel de la factory crée une session distincte. Auth SQLite réutilise l'engine, pas la même instance de session. PostgreSQL possède un petit pool d'authentification séparé. |
| `backend/api.py:db()` | La session de requête est contenue dans un `with`, puis fermée à la fin de la dépendance. Le worker possède son propre `with app.state.sessions()`. Aucun partage intentionnel de la session ORM API avec le worker n'est identifié. |
| `backend/authentication.py:authenticate()` | Ouvre/ferme une session d'authentification ; les contrôles de propriétaire, blocage et session restent présents. Une erreur du GET de suivi peut aussi survenir dans cette dépendance ; l'ancien log ne localise pas la requête SQL fautive. |
| `backend/ai/long_api.py` | Le GET vérifie `owned_job()` puis construit `job_out()`. Reprise et annulation conservent leurs autorisations et contrats. |
| `backend/ai/long_summary.py:resume()` | Vérifie le propriétaire, verrouille le budget, contrôle réservation/état ; commit du pending avant mise en file. Des branches retournent sous transaction jusqu'à la fermeture de dépendance ; aucune attente circulaire démontrée ici. |
| `SummaryWorker.run()` | Recharge le job, marque/commit l'étape processing avant l'appel simulé ; enregistre l'usage reçu avant validation du contenu, conserve checkpoints et réservation selon les règles d'incertitude. Aucun retry SQL générique. |
| `recover()` | Réconcilie pending/processing et les étapes incertaines ; ne rejoue pas un appel fournisseur et ne remplace pas l'authentification de la reprise. |
| `SummaryWorker.loop()/stop()` | Set d'activité protégé par verrou, retrait en finally, arrêt par Event et join borné. Une exception non gérée du run émet un événement expurgé ; sa classe n'est pas exposée en production. |
| `backend/main.py:lifespan()` | Demande l'arrêt du worker avant disposal des engines ; arrêt de la file mail séparé. Le join est borné, pas une preuve universelle de terminaison de tout thread. |
| `tests/conftest.py` | Chaque fixture a sa base neuve ; PostgreSQL non vide est refusé. Nettoyage/downgrade de cette seule base après fermeture du client. SDK OpenAI réels interdits. |

`lock_budget()` commence par rollback, puis `BEGIN IMMEDIATE` sur SQLite ; PostgreSQL
utilise le verrouillage de ligne. Les garanties de réservation ne doivent pas être
remplacées par une suppression de ce verrou. Les lectures, commits, rollbacks et
changements d'état ont été examinés sans modifier les paramètres transactionnels.

Environnement de référence WSL : Python **3.12.3**, SQLite **3.45.1**, SQLAlchemy
**2.0.55**, DBAPI threadsafety 3. Code sous `/mnt/c`, bases neuves sous `/var/tmp` :
ne pas attribuer une contention à une base placée sur NTFS dans cette campagne.
La documentation distingue transaction ORM et transaction réelle du pilote SQLite ;
`session.in_transaction()` ne prouve pas à lui seul la possession d'un verrou fichier.
Voir la [documentation SQLAlchemy SQLite](https://docs.sqlalchemy.org/en/20/dialects/sqlite.html).

## 3. Instrumentation réservée aux tests

Harnais sous `var/`, ignoré par Git, sans import depuis le code applicatif :

- `s14_7_2_diagnostics.py` : plugin pytest opt-in ; événement Engine `handle_error`,
  événements Session de début/fin de transaction et flush, wrapper du gestionnaire
  SQLAlchemy des applications de fixture. Le wrapper appelle le gestionnaire original :
  même HTTP 503 et même événement de production expurgé.
- `s14_7_2_worker_diagnostics.py` : complément pour les campagnes ciblées ; observe
  `Thread.join()` des seuls threads nommés `documind-long-summary`, sans changer
  l'argument timeout ni le comportement d'attente. Capture alive avant/après et
  nombre de threads de résumé encore vivants. Un JSONL compagnon conserve les joins
  indépendamment du buffer circulaire : celui-ci pouvait évincer le join initial
  d'un travail de 93 étapes. Une répétition WSL supplémentaire qualifie ce complément.
- `check_s14_7_2_instrumentation.py` : étalonnage avec erreur de contrainte SQLite
  synthétique, TimeoutError synthétique et objet de job contenant une sentinelle fictive.
- `s14-7-2-diagnostic-image/` : extension de l'image de preuves locale existante,
  uniquement pour ajouter ces plugins et leur runner. Aucun changement de Dockerfile
  de production ou nouvelle infrastructure applicative.

Données conservées : classes SQLAlchemy/DBAPI, `sqlite_errorname`, noms de fonctions
de traceback sans source ni variables, transaction/invalidated, type et compteurs du
pool, état du worker, status/completed_steps/error_code technique du job au flush,
durées monotoniques et catégorie de thread. Les valeurs de paramètres des noms de
tests sont exclues. Chronologie bornée aux **256 derniers événements** par test ;
les longues suites de checkpoints peuvent en évincer le début.

Ne sont jamais sérialisés : texte d'exception, SQL, paramètres SQL, URL de connexion,
identité utilisateur/job, document, prompt, email, clé, cookie ou token. Les états
ORM sont lus dans le dictionnaire déjà chargé pour ne pas déclencher une requête
de diagnostic par accès à un attribut expiré. Le verrou d'activité est lu sans attente.

Les fichiers JSONL restent privés dans `var/`. Les preuves de pool après teardown
décrivent le pool courant, éventuellement recréé par `dispose()` ; un compteur zéro
n'est donc pas une preuve absolue d'absence de connexion ancienne encore référencée.
L'instrumentation peut modifier l'ordonnancement : une non-reproduction instrumentée
ne permet pas d'exclure une course.

**Étalonnage : trois contrôles réussis.** Le callback retrouve IntegrityError/
IntegrityError et SQLITE_CONSTRAINT_PRIMARYKEY ; un TimeoutError sans orig reste
identifié sans DBAPI inventée ; les sentinelles/SQL/paramètres et plan du job ne
figurent pas dans la sortie. Ces fautes synthétiques valident l'instrumentation,
**elles ne reproduisent pas l'incident initial**.

## 4. Hypothèses et niveau de preuve

| Hypothèse | Évaluation |
| --- | --- |
| Verrou SQLite / SQLITE_BUSY | Possible ; BEGIN IMMEDIATE est réellement utilisé. La classe DBAPI du 503 initial n'est pas disponible : cause non confirmée. Aucun WAL, busy_timeout ou retry ajouté pour contourner l'hypothèse. |
| Pool épuisé / TimeoutError | Possible tant que l'exception initiale n'est pas capturée. Les snapshots des passages réussis ne prouvent pas le passé ; taille 5 et absence de checkout après cleanup ne suffisent pas à exclure un épuisement ponctuel. |
| Même session utilisée simultanément API/worker | Pas de partage identifié dans les factories/contextes lus. Cela n'est pas une preuve formelle de toutes les interactions ni une explication confirmée. |
| Ancien worker toujours actif après join(2) | Le test ne vérifiait pas explicitement le booléen de terminaison. Les campagnes ciblées l'instrumentent ; ne pas transformer cette fragilité potentielle en cause sans trace d'un join expiré. |
| Fermeture/disposal trop précoce | Lifespan et fixture demandent bien l'arrêt avant disposal ; un join borné peut échouer à terminer. Pas d'entrelaçage fautif démontré. |
| Contention externe Windows/WSL | Campagne de référence réalisée sans suite Windows/Docker concurrente. Un passage vert dans ces conditions ne prouve pas que la concurrence externe causait l'échec. |
| Régression PostgreSQL | Aucune conclusion à partir d'un 503 sur une fixture SQLite. Campagne dédiée sur PG neuf, distincte de la référence WSL. |

## 5. Campagnes et commandes

Toutes les bases et dossiers temporaires sont neufs ; aucun fournisseur réel,
secret ou service de production. Aucune suite Windows parallèle à la campagne
complète WSL de référence. Les tests IA utilisent les mocks existants, jamais un
appel externe ou une activation de l'IA en production.

| Campagne 14.7.2 | Réussis | Ignorés | Échoués / état |
| --- | --- | --- | --- |
| WSL, suite complète instrumentée de référence | 796 | 27 | 0, 1 052,56 s |
| WSL, cas isolé avec plugin de joins initial | 1 | 0 | 0, 10,87 s |
| WSL, fichier complet des résumés longs avec plugin de joins initial | 14 | 0 | 0, 109,90 s |
| WSL, cas isolé avec flux compagnon conservant les joins précoces | 1 | 0 | 0, 10,75 s |
| Docker Linux, premier lanceur temporaire incorrect | 0 | 0 | 14, erreur de harnais ; 124,80 s |
| Docker Linux, résumés longs instrumentés, lanceur corrigé | 14 | 0 | 0, 72,87 s |
| PostgreSQL neuf, résumés/BYOK/IA fermée et sécurité associée | 84 | 0 | 0, 222,82 s |
| Étalonnage privé du diagnostic | 3 contrôles | 0 | 0 |

La suite Windows complète **n'a pas été relancée** : aucun code applicatif n'a été
modifié. Le résultat 14.7.1 de 755 réussis/68 ignorés reste antérieur, jamais attribué
à ce lot. Les suites frontend/BFF et la recette complète HTTPS/SMTP de 14.7.1 ne sont
pas répétées pour ce diagnostic SQL ; leurs résultats historiques restent distincts.
Les campagnes se recouvrent, leurs totaux ne s'additionnent pas comme des tests uniques.

Commande de référence exécutée, shell WSL, depuis le dépôt local :

```bash
PYTHONPATH="$PWD/var" \
DOCUMIND_DIAGNOSTIC_FILE=var/s14-7-2-full-diagnostic.jsonl \
/var/tmp/documind-s13-a7b75801/.venv/bin/python -m pytest \
  -q -p no:cacheprovider -p s14_7_2_diagnostics \
  --basetemp=/var/tmp/documind-s14-7-2-reference --tb=short \
  > var/s14-7-2-full-linux.log 2>&1
```

Les campagnes ciblées emploient `-p s14_7_2_worker_diagnostics`, un JSONL et un
basetemp distincts ; aucun écrasement du journal de référence ou des preuves 14.7.1.
Docker est dirigé explicitement vers le pipe local Desktop, jamais un contexte distant.

### Erreur de harnais Docker distincte de l'incident

Le premier runner temporaire exécutait `pytest.main()` au niveau module, sans garde
`if __name__ == '__main__'`. Les sous-processus d'extraction démarrés par spawn
réimportaient donc ce runner et relançaient pytest. Preuves : traces de suites
imbriquées pendant les imports, échecs d'upload 422/500 avant les résumés, 210 records
techniques au lieu de 14, aucune erreur SQL collectée. La campagne de premier niveau
compte 14 échecs ; les traces imbriquées ne sont pas des tests applicatifs distincts.

Correction limitée à `var/s14-7-2-diagnostic-image/run_diagnostics.py` : déplacer
l'exécution dans `main()` protégé par la garde standard. Mêmes tests et restrictions
Docker, nouveau conteneur/tmpfs ; résultat 14 réussites, exactement 14 records et
aucune erreur SQL. Cet échec de lanceur est conservé dans
`var/s14-7-2-summary-docker.log`, confirmation dans `...-docker-final.log`.
Il n'est ni une reproduction du 503 initial ni une correction du moteur applicatif.

Runtime Docker : Python **3.13.17**, SQLite **3.46.1**, SQLAlchemy **2.0.55**.
Image de diagnostic non publiable basée sur `documind-s14-7-1-proofs:local`, sources
applicatives inchangées, ajout des seuls plugins/runner. Rootfs readonly, utilisateur
applicatif, cap-drop ALL, no-new-privileges, mémoire 1 536 Mio, deux CPU, 64 PID,
tmpfs 256 Mio. Comparaison SQLite sans réseau ni volume. Les fixtures fonctionnelles
conservent leur adaptateur portable development pour les documents fictifs ; aucune
configuration production ni politique du sandbox n'est assouplie.

Les commandes ciblées WSL sont pilotées par `var/run_s14_7_2_wsl_targets.py`, qui
appelle `python -m pytest` dans deux processus distincts et garde les logs séparés.
La répétition complémentaire du join utilise un troisième basetemp neuf.
Pour Docker, la construction hors ligne utilise le contexte ne contenant que les
quatre fichiers de diagnostic sous `var/s14-7-2-diagnostic-image/` :

```powershell
docker --host npipe:////./pipe/dockerDesktopLinuxEngine build --pull=false --network none -f var/s14-7-2-diagnostic-image/Dockerfile -t documind-s14-7-2-diagnostics:local var/s14-7-2-diagnostic-image
docker --host npipe:////./pipe/dockerDesktopLinuxEngine run --rm --pull never --network none --read-only --cap-drop ALL --security-opt no-new-privileges --memory 1536m --cpus 2 --pids-limit 64 --tmpfs /tmp:rw,noexec,nosuid,size=256m,mode=1777 documind-s14-7-2-diagnostics:local tests/test_long_summary.py -q -p no:cacheprovider --tb=short
```

## 6. Cause démontrée ou incertitudes

Aucune anomalie causale démontrée dans le code applicatif. La référence WSL seule
termine les 823 cas : 796 réussites et 27 skips (11 PostgreSQL, six snapshots,
huit E2E opt-in et deux preuves root). Son JSONL contient 823 enregistrements.
Le seul SQLAlchemyError collecté provient de l'injection volontaire de
`test_sql_and_unexpected_exceptions_never_serialize_messages`, sans erreur DBAPI :
ce n'est pas une reproduction du 503 initial. Le test de reprise concerné termine
à completed, sans erreur capturée. Le snapshot courant après teardown indique
worker arrêté, file/set d'activité vides, zéro checkout, avec les limites de preuve
sur le pool disposé indiquées plus haut.

Dans la répétition WSL avec flux compagnon, le join(2) de l'ancien worker commence
avec alive=false et se termine avec zéro thread de résumé vivant. Le join(35)
de teardown du nouveau worker se termine aussi avec alive=false et zéro thread.
Cela ne démontre ni fuite ni dépassement de join dans ce passage, sans exclure
leur possibilité lors de l'incident historique. Aucune attente n'a été augmentée.
La comparaison Docker confirme aussi l'ancien worker déjà terminé avant join(2),
puis un join de teardown réussi ; aucune erreur SQL dans les 14 records.
PostgreSQL apporte la même observation pour le cas concerné et aucune erreur SQL
dans les 84 records ; aucune reproduction dans ce contexte non plus.

La réussite de la campagne sans Windows concurrent ne prouve pas la causalité de
la concurrence externe. La classe exacte du SQLAlchemyError initial reste inconnue :
verrouillage, pool ou autre cause ne peuvent être sélectionnés sur ces preuves.

## 7. Correction et régression

Aucune correction métier, modification d'engine/pool, retry, délai, test ignoré ou
changement de sécurité n'est appliqué. Aucun test de régression causale nouveau
n'est revendiqué tant que la cause n'est pas établie. Les tests existants de reprise,
annulation, isolation, comptabilisation unique, checkpoints et IA fermée restent
les contrôles de non-régression ; l'étalonnage du plugin ne les remplace pas.

## 8. Fichiers et préservation

Le seul nouveau candidat Git ajouté est ce rapport. Plugins, étalonnage, contexte
Docker et journaux restent dans `var/`, exclus de publication. Aucun des 65 fichiers
existants n'a été corrigé ou réinitialisé. Le rapport 14.7.1 conserve son
incident et son verdict historique ; il n'est pas réécrit comme une campagne verte.

Comparaison finale : **65/65 empreintes identiques**. L'état développé fichier par
fichier compte maintenant **32 suivis modifiés et 34 non suivis, soit 66 candidats**,
sur la même branche ; index vide. `git diff --check` réussit, contrôle des blancs
du nouveau rapport effectué séparément. Aucun fichier des phases antérieures supprimé.
Les filtres Docker de cette mission ne retournent plus de conteneur ou réseau.

Les JSONL WSL ont 823/1/14/1 records selon la campagne ; le scan séparé ne trouve
ni adresse email ni UUID de données dans ces diagnostics. Les sorties finales
Docker et PG annoncent respectivement 14 et 84 records, sans erreur SQL. Les
preuves complètes et le lanceur initial défaillant restent sous `var/` ; ne pas
les ajouter au futur commit sous prétexte de documenter un test vert.

## 9. Impact PostgreSQL et production

Aucune migration, quota, inscription, secret, verrou de maintenance, sauvegarde,
workflow ou configuration de production modifié. Les réservations et consommations
dans les tests restent fictives et sur bases neuves. Aucune connexion VPS, Registry,
B2, SMTP externe ou API IA. Les mécanismes Landlock/seccomp ne sont pas modifiés.
La campagne Docker de ce lot est fonctionnelle ; les preuves natives de confinement
14.7.1 restent des résultats antérieurs, pas une nouvelle certification.

PostgreSQL **17.11**, pgvector disponible **0.8.7**, conteneur neuf
`s14-7-2-pg-74c2`, réseau dédié `s14-7-2-sql-74c2`, aucun port publié, aucun bind ou
volume persistant, données sur tmpfs, utilisateur OS 70:70, rôle/mot de passe fictifs.
Le conteneur applicatif de tests rejoint ce seul réseau interne. La sélection réelle :

```text
tests/test_long_summary.py
tests/test_ai_disabled_enforcement.py
tests/test_ai.py
tests/test_byok.py
tests/test_rag.py
tests/test_accounts_saas.py
```

Les 84 cas couvrent reprises/annulations/checkpoints, réservations et comptabilisation,
sessions/révocations, isolation, traitements RAG et refus IA. Cette sélection ne vaut
pas suite PostgreSQL complète ou preuve générale d'absence de régression. Aucun
correctif transactionnel n'ayant été appliqué, aucun effet de correction sur la
production ne peut être revendiqué. L'absence de reproduction PG ne démontre pas
que le défaut initial ne pourrait jamais concerner le moteur en production.

Après contrôle des labels de mission et de l'absence de montages persistants, le
PostgreSQL neuf et son réseau sont arrêtés/supprimés ; les conteneurs de preuve sont
`--rm`. Aucune ressource préexistante modifiée. Images de test et fichiers fictifs
de preuve conservés localement ; aucune publication.

## 10. Verdict

**No-Go tant que l'incident initial reste sans cause démontrée.** Une campagne verte
serait une non-reproduction, pas une résolution. RF10-03 reste par ailleurs une
décision indépendante avant publication de la RC. Aucun commit, push, merge,
déploiement ni ouverture n'est entrepris.

**État final précis : incident historique toujours ouvert, non reproduit dans les
nouvelles campagnes applicatives valides ; cause non identifiée, aucune correction
applicative ni régression causale nouvelle.** Le seul défaut corrigé est celui du
nouveau lanceur Docker de diagnostic ; il n'existait pas dans la campagne WSL initiale.

Prochaine investigation proposée, sans présumer d'une correction : conserver les
deux hooks API/DBAPI au prochain passage complet avec flux de joins persistant ;
si le 503 revient, relever classe exacte, pile de fonctions et état transactionnel
au même instant. Si nécessaire, étendre les compteurs checkout/checkin à l'ancien
pool avant disposal et attribuer les transactions à des sessions techniques locales,
sans conserver SQL/paramètres. Une classe de verrouillage ne prouverait pas encore
quel acteur détient le verrou : reproduire l'entrelaçage avec événements/barrières
avant tout correctif. Si le moteur change, exiger une régression déterministe et
les suites WSL/Windows/PostgreSQL pertinentes, sans retry ni timeout de confort.

La charge système globale n'a pas été mesurée : l'absence de suite Windows parallèle
ne vaut pas mesure d'une machine sans contention. La revue RC peut continuer en
diagnostic, mais **le blocage de validation/publication n'est pas levé**.
Les inscriptions publiques et l'IA demeurent fermées ; aucune étape VPS autorisée.
