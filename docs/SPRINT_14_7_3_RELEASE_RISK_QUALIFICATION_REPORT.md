# Sprint 14.7.3 — Qualification des risques avant release candidate

26 octobre 2026. Branche `preparation/sprint-14-5-ux-email-abuse`, HEAD
`8243e0511c5505a9cc70f76ad02392f7a816590d`. Références : rapports
[14.7.1](SPRINT_14_7_1_RELEASE_CANDIDATE_REVIEW.md),
[14.7.2](SPRINT_14_7_2_SQLALCHEMY_INTERMITTENT_FAILURE_REPORT.md) et
[runbook 14.7](SPRINT_14_7_PUBLIC_BETA_OPENING_RUNBOOK.md).
Les 66 fichiers candidats préexistants sont relevés par SHA-256 avant intervention.
Aucune opération distante ou acceptation de risque faite au nom de l'exploitante.

## 1. Synthèse et trois décisions distinctes

| Décision | Recommandation technique, sans autorisation d'exécution |
| --- | --- |
| **A — PR en brouillon pour revue** | **Go technique sous conditions de transparence** : risques et témoins en échec explicités, pas de fusion, pas de présentation comme RC validée, aucun push/PR sans autorisation. La CI de PR ne publie pas d'image. |
| **B — Publication CI privée comme RC utilisable** | **No-Go en l'état** : nouvelle incohérence documentaire démontrée sous faute contrôlée, à corriger avant validation RC ; décisions humaines encore nécessaires sur l'incident historique et RF10-03. Une publication d'inspection non promouvable serait une autre décision explicite, non recommandée ni autorisée automatiquement par cette revue. |
| **C — Ouverture publique** | **No-Go** : validations réelles du runbook non réalisées, nouveau correctif requis, aucune autorisation d'ouverture ou d'activation IA. |

L'incident initial reste **inexpliqué et non reproduit spontanément**. Ce lot n'en
identifie pas la cause. Il démontre en revanche qu'une erreur SQL ne peut pas être
qualifiée globalement d'indisponibilité sans risque de données : un échec remonté
après commit documentaire confirmé entraîne, dans la sonde, la suppression du fichier
source malgré la persistance de sa ligne SQL. Ce constat est distinct du GET 503 initial.

RF10-03 reste ouvert : quatre dépendances transitives Linux non contraintes,
outils de build isolés non verrouillés, bases/paquets système et source pgvector
insuffisamment figés. Une proposition privée de contraintes ferme la couverture des
**métadonnées installées**, sans prétendre certifier une reconstruction complète.

## 2. Incident historique : faits, fréquence et limites

Symptôme confirmé en 14.7.1 : un GET de suivi de résumé repris renvoie 503 et
`system.database.unavailable` dans
`test_worker_interruption_resume_and_owner_isolation`. Classe SQLAlchemy précise,
erreur DBAPI et requête fautive inconnues. La réponse du gestionnaire SQL ne démontre
ni SQLITE_BUSY, ni pool épuisé, ni responsabilité de WSL ou Windows.

Fréquence **observée**, sans estimation de probabilité de production :

- 14.7.1 : une occurrence dans une campagne complète WSL de 823 cas ; le cas ciblé
  échoue une fois dans cette campagne, puis réussit isolément et dans les confirmations.
- 14.7.2 : aucune réapparition dans la campagne complète WSL de référence de 823 cas,
  le fichier ciblé, ses répétitions, Docker et PostgreSQL documentés dans ce rapport.
- 14.7.3 : le même cas passe dans les deux sélections WSL/PG ; les nouvelles fautes
  SQL sont **injectées volontairement**, pas des réapparitions spontanées du défaut.
- Nombre de requêtes HTTP comparables et exposition réelle en production inconnus.
  Ne pas calculer un taux d'erreur à partir du total des cas pytest ni extrapoler
  les passages isolés en garantie de fiabilité.

Gravité plausible de l'occurrence GET : échec d'affichage/suivi au moment observé,
sans perte de données démontrée dans cet ancien incident. Son état final n'est pas
reconstitué : les fixtures ont nettoyé la base fictive. Les nouveaux tests réussis
ne permettent pas d'affirmer rétroactivement que son checkpoint ou son worker était sain.

## 3. Périmètre réel d'une bêta sans IA

### Connexions communes et sauvegardes distinctes

`backend/db.py` crée l'engine et les factories de sessions. Inscription/vérification,
profils, documents, budgets et jobs utilisent le même engine applicatif ; les
instances de session API et worker sont distinctes. Un défaut commun d'engine,
de serveur SQL ou de ressources pourrait donc toucher des fonctions non IA.
La séparation de session n'est pas une isolation de disponibilité.

Sous PostgreSQL, l'authentification possède un petit pool indépendant : elle évite
de dépendre entièrement du pool applicatif pour l'admission, mais utilise le même
serveur/base. Sous SQLite, l'authentification réutilise l'engine applicatif. Les erreurs
SQL refusent l'accès ; elles ne deviennent pas une validation implicite de session.

Les sauvegardes emploient `psql` et `pg_dump`, pas les sessions ORM/pools du worker.
Un problème limité au pool Python n'affecte donc pas directement ces processus.
Une panne PostgreSQL, disque ou réseau commune peut toutefois empêcher le préflight,
le dump ou la reprise des services. Le script tente la reprise en finally mais ses
guards peuvent la refuser : ne pas promettre un redémarrage réussi malgré une base
indisponible. Marqueurs, rapports, alertes et correction en avant restent nécessaires.

### IA fermée : ce qui est effectivement interdit

Les nouvelles générations, connexions/validations de clé BYOK et embeddings passent
les guards de 14.3 avant construction/émission SDK ; les workers et retries revérifient
le flag courant. Une requête HTTP forgée ne dépend pas des boutons React. La matrice
API de refus a été exécutée avec espions SDK ; une clé BYOK ne réactive pas le flag global.

Cela **ne ferme pas toutes les routes portant un nom IA** : statut, historique,
lecture de checkpoints, plans locaux, annulation et suppression de clé restent permis
selon autorisations. Certains caches peuvent être rendus sans nouveau fournisseur.
Des lectures SQL ou réconciliations locales restent possibles sur ces parcours ;
un incident SQL peut donc les affecter même si toute nouvelle génération est refusée.
Le réseau sortant de l'API de production n'est pas supprimé par le flag ; les guards
audités ne sont pas une garantie contre un code arbitraire compromis.

L'IA off réduit l'exposition au scénario de génération/reprise du test, **sans isoler
les routes classiques d'une défaillance DB**. La configuration réelle du VPS n'est
pas relue ici ; sa fermeture reste l'état annoncé par l'opératrice.

## 4. Qualification transactionnelle : nouvelles preuves

Les sondes privées sous `var/test_s14_7_3_database_risks.py` utilisent des bases neuves,
les mêmes handlers, limites publiques 5/3 par heure/difficulté 12, et un faux envoi mail.
Elles ne modifient pas les handlers ou journaux de production. La faute est armée
sur le flush du type de modèle ciblé, une seule fois, puis tous les hooks sont retirés.

| Scénario contrôlé | Résultat qualifié |
| --- | --- |
| Inscription, exception avant le COMMIT ORM | HTTP 503 ; lecture par engine indépendant : aucun compte/workspace/membership/token ni place consommée. Nouvelle demande avec nouvelle preuve possible, vérification et login réussis. |
| Inscription, COMMIT DBAPI exécuté puis OperationalError remontée | HTTP 503 **mais** compte/jeton/workspace et quota à un persistants ; mail non mis en file. Nouvelle inscription identique générique sans double admission ; renvoi explicite puis vérification/login réussis, compteur toujours un. |
| Upload, exception avant COMMIT ORM | HTTP 503 ; pas de ligne document, nettoyage des fichiers temporaires/final, import suivant réussi. |
| Lecture documentaire, exception SQL une fois | 503 puis consultation réussie après retrait de la faute ; ligne et fichier conservés ; santé SELECT 1 peut rester 200. |
| Lecture SQL d'authentification personnelle en échec | 503 sans accès accordé ; session utilisable après retrait de la faute ; logout/révocation puis 401 correctement conservés, IA off. |
| Upload, COMMIT DBAPI exécuté puis OperationalError remontée | **Échec de l'invariant de conservation** : ligne document visible par un engine indépendant, fichier source absent après HTTP 503. Reproduit Windows/SQLite, WSL/SQLite et PostgreSQL neuf. |

### R14-SQL-02 — Suppression du fichier après résultat de commit incertain

Cause de ce **nouveau témoin déterministe**, pas de l'incident historique :
`backend/services/documents.py:import_document()` déplace `.part` vers le fichier final,
puis appelle `session.commit()`. Son `except BaseException` tente rollback puis
`final.unlink()`. Si le commit est déjà effectif, le rollback ne l'annule pas et la
suppression rend la base et le stockage incohérents. Le fichier est inchangé depuis
HEAD Sprint 13 ; ce n'est pas une régression attribuée sans preuve aux phases 14.

Modèle de faute explicite : le wrapper appelle le vrai `dialect.do_commit()` avec
succès, puis lève `dialect.dbapi.OperationalError`. C'est une simulation d'issue
incertaine pour l'appelant, **pas une coupure réseau réelle** ni la preuve qu'un
driver donné lèverait naturellement après avoir reçu un succès. La sonde démontre
le comportement du code sous ce contrat de faute, pas la fréquence d'une panne réelle.
Elle n'a utilisé que des TXT fictifs ; aucune perte de document réel n'est observée.

Le test exige que le fichier d'une ligne confirmée existe et échoue volontairement
sur le code actuel ; il n'est ni xfail, ni ignoré, ni inversé pour produire du vert.
Le texte extrait peut rester en base, mais cela ne reconstitue pas nécessairement
le document binaire original. Gravité plausible **élevée : intégrité/stockage source**.

Les probes préliminaires coupaient aussi COMMIT avant l'appel au driver et lisaient
avec le pool applicatif : deux campagnes ont donné 2 réussites/2 échecs. Elles ne
prouvaient pas une persistance externe. Une observation complémentaire SQLite établit
`independent_user_count=0` et `pooled_user_count=1` : vue transactionnelle du pool et
état durable ne doivent pas être confondus. La qualification finale ci-dessus emploie
une faute **avant préparation du commit ORM** et un engine indépendant pour l'état durable.

Le même probe de frontière pré-driver sous PostgreSQL produit un `ProgrammingError`
au checkout/pre-ping du pool : impossible de changer autocommit en état natif INTRANS.
Il est conservé comme un échec supplémentaire de sonde de récupération, sous faute
artificielle ; pas comme reproduction spontanée du 503 initial. Cela justifie d'examiner
aussi remise en état/invalidation des connexions après échec de COMMIT, sans ajouter
un retry global ni conclure que pre_ping répare toute opération. La documentation
[SQLAlchemy sur les déconnexions](https://docs.sqlalchemy.org/en/20/faq/connections.html)
ne présente pas pre_ping comme une reprise transparente de transaction en cours.

### Détection et récupération réellement disponibles

Les réponses et événements SEC10-04 signalent l'erreur SQL sans SQL/paramètres/secrets.
Le logger est borné et best effort ; des événements peuvent être abandonnés, avec
signal de perte. La santé FastAPI est un SELECT 1, celle du BFF relaie l'API : une
panne ciblée ou une incohérence fichier/ligne peut ne pas rendre la santé rouge.
Les monitors ne constituent pas un collecteur exhaustif de ces événements applicatifs.

Le backup quotidien valide archives, digests et inventaire des tables ; ces contrôles
n'établissent pas à eux seuls une correspondance exhaustive entre chaque storage_name
SQL et chaque membre de l'archive. Une archive peut être fidèle à un stockage déjà
incomplet. La recette indépendante 14.6 comparait ses documents fictifs, mais cela
n'est pas un contrôle de production réalisé ici. Le CLI `validate_restore.py`
compare également noms, tailles et SHA-256 des fichiers restaurés avec les lignes SQL :
il peut détecter cette absence lorsqu'il est exécuté explicitement sur une copie
isolée, pas lors du seul backup quotidien. Ses defaults ne doivent pas être utilisés
aveuglément sur la production. Aucun auto-réparateur de fichier
manquant n'est identifié dans les chemins examinés. Ne pas annoncer que l'healthcheck
ou le succès Restic détectera nécessairement ce nouveau cas.

## 5. Fiches de risque et critères de décision humaine

| Risque | Gravité plausible / incertitude | Réduction et critère de correction préalable |
| --- | --- | --- |
| **R14-SQL-01**, GET 503 historique | Disponibilité au point observé ; portée générale inconnue ; une occurrence, aucune probabilité de production déduite. | Garder diagnostic privé, corrélation classes/pool/joins ; aucune attribution SQLite/WSL sans preuve. Correction préalable si réapparition spontanée, état persistant incorrect, session autorisée à tort ou échec reproductible sur PostgreSQL. Acceptation humaine possible uniquement pour poursuivre une revue/CI privée sans usage public, avec seuil d'arrêt explicite. |
| **R14-SQL-02**, ligne commitée/fichier supprimé | Élevée, intégrité source ; démontré sous faute synthétique sur trois environnements ; incidence réelle inconnue. | **Correctif obligatoire avant validation d'une RC utilisable/déploiement.** Préserver/quarantainer le fichier si le commit est indéterminé, puis vérifier par une connexion saine avant nettoyage ; tester aussi suppression/tombstone et arrêt brutal. Ne pas remplacer cela par un retry de COMMIT. |
| **R14-SQL-03**, admission commitée malgré 503 et mail absent | Place cumulative consommée, parcours temporairement bloqué ; récupération testée par renvoi ; aucun double compte/quota constaté. | Conserver UI générique, renvoi protégé, surveillance mail et compteur ; ne pas promettre qu'un 503 signifie aucune admission. Risque soumis à acceptation explicite pour cinq places, jamais remboursement/reset automatique. |
| Frontière de COMMIT/pool | Connexion encore en transaction sous faute pré-driver ; vue SQLite interne distincte, ProgrammingError PG observé. Pas une preuve de panne naturelle. | Qualifier explicitement rollback/invalidation du pool dans le correctif et ajouter une régression déterministe ; ne pas considérer la fermeture de contexte ou pre_ping comme une preuve suffisante de récupération. |
| **RF10-03**, entrées de build | Substitution/drift de dépendances ou outils possibles, aucune CVE précise confirmée par ce lot. | Contraintes complètes par plateforme, artefacts/hashes et build tools figés, bases et source pgvector vérifiées, provenance revue ; à défaut acceptation limitée à une publication privée d'inspection, avec refus de promotion. |

Ces critères sont des recommandations techniques. Une acceptation doit identifier
risque, version/SHA, portée, une exécution CI/attempt, expiration, compensations,
opératrice et critères d'arrêt. Elle ne vaut jamais permission de déploiement,
d'ouverture, de relance ou d'activation IA. Aucune acceptation n'est enregistrée ici.

## 6. RF10-03 : audit des entrées de construction

| Entrée | Qualification locale |
| --- | --- |
| `requirements.lock` | Versions exactes pour les lignes présentes, sans hashes ; **partiellement verrouillé**, pas un lock exhaustif de toutes les plateformes. |
| `pyproject.toml` | Plages de dépendances et extras ; contraintes fournies par CI/Docker. Build `setuptools>=75` non fixé ; projet local `.` non attesté par un hash de wheel. |
| Transitifs observés Windows | Fermeture runtime/test de 50 distributions : argon2-cffi-bindings 26.1.0, cffi 2.1.1, pycparser 3.11 non contraints ; aucun autre écart de pin ou distribution manquante dans cette fermeture installée. |
| Transitifs observés Linux Docker | Fermeture de 49 distributions : mêmes bindings/cffi, pycparser **3.12**, uvloop **0.23.0** non contraints ; aucun écart sur les versions effectivement épinglées. La différence de pycparser est un constat, pas la cause du 503. |
| Build isolé | Setuptools absent des runtimes audités ; sa version réellement choisie lors d'un futur build n'est pas obtenue ici. Les contraintes runtime ne certifient pas l'environnement PEP 517. |
| `frontend/package-lock.json` | Lock v3 : 368 entrées de paquets hors racine, toutes avec intégrité et resolved HTTPS ; npm ci utilisé. Scripts d'installation déclarés pour esbuild et fsevents. Intégrité d'archive ne signifie ni absence de vulnérabilité ni identité d'éditeur certifiée. |
| Dockerfiles / OS | Bases `python:3.13-slim`, `node:22-alpine`, `postgres:17-alpine` mutables ; paquets APT/APK et toolchain de compilation non verrouillés. Construction non reproductible intégralement. |
| pgvector serveur | Version déclarée 0.8.7, clone du tag Git v0.8.7, pas de commit source complet ni archive hachée ; compilation C dans la base PostgreSQL alpine. Le paquet Python pgvector et l'extension serveur sont deux artefacts distincts. |
| Actions | Huit références d'actions uniques, toutes épinglées par SHA de 40 caractères ; authenticité de ces commits et correspondance des commentaires de version non revérifiées à distance. Runners, version Python 3.13/Node 22 et outils internes restent évolutifs. |
| Images finales | Trois builds linux/amd64 séquentiels ; références finales par digest, contrôles de tags SHA et bundle attesté. Le digest fixe la sortie, pas les entrées de construction. |
| Provenance | Bundle de neuf fichiers, statement lié aux huit autres fichiers et approbation root indépendante préservés. Pas de certification cryptographique autonome. SBOM/materials/provenance BuildKit ne sont pas explicitement exigés et vérifiés par les scripts ; une attestation automatiquement générée par Buildx n'est pas supposée absente ou suffisante sans inspection CI. |

Inspection Docker strictement locale : les tags de base python/node ne sont pas
présents comme images autonomes, aucun pull effectué. La base PostgreSQL locale
amd64 possède le RepoDigest
`postgres@sha256:b0f9560a2de083e2cc7382e75f808c7381a32852a7ec49117deedb300e552b24`.
C'est une valeur effectivement lue, **pas une nouvelle vérification indépendante
d'origine ni une recommandation automatique de pin**. Aucun digest python/node,
commit pgvector ou hash de wheel n'est inventé.

Surfaces à auditer : parseurs/extensions natifs, bibliothèques Python/Node,
scripts d'installation, OS, toolchain C et actions à privilèges de CI. Il n'y a
**pas d'audit CVE actualisé ni de scan Registry** dans ce lot ; aucun numéro de CVE,
score ou constat historique obsolète n'est présenté comme une vulnérabilité actuelle.

## 7. Correction ciblée proposée, portée du test local

Un candidat **privé, non appliqué** est créé sous
`var/s14-7-3-constraints-proposal.lock` : copie du lock actuel complétée uniquement
avec des versions réellement observées, sans mise à jour de paquet :

```text
argon2-cffi-bindings==26.1.0
cffi==2.1.1
pycparser==3.11; sys_platform == "win32"
pycparser==3.12; sys_platform == "linux"
uvloop==0.23.0; sys_platform == "linux"
```

Audit hors ligne de métadonnées sur Windows, WSL et Docker Linux : aucun transitif
runtime/test installé laissé sans contrainte, aucun pin divergent, aucune distribution
manquante dans les fermetures examinées. Ce test ne résout ni ne télécharge quoi que
ce soit, ne modifie pas les environnements et **ne prouve pas** qu'un build neuf
résoudra tous les artefacts. La proposition vise ces environnements CPython observés,
pas macOS/PyPy/arm64 ou toutes les versions Python permises par le projet.

Elle n'est pas copiée dans `requirements.lock`, car build isolé, hashes de distributions,
bases et source pgvector restent à qualifier. Ajouter des nombres exacts sans preuve
de build complet masquerait la portée réelle du correctif. Les fichiers de production
et dépendances installées restent inchangés.

Étape suivante proposée, sous autorisation dédiée : obtenir les wheels exacts et
leurs SHA-256, versions/hashes de pip/setuptools/wheel, digests de bases avec plateforme
et commit pgvector vérifié sur origine officielle ; construire deux fois dans un
environnement contrôlé et conserver les matériaux/SBOM. Ne pas utiliser les hashes
RECORD installés comme hashes d'archives, ni un image ID local comme digest de manifeste.
Le pip du runtime Docker est **26.2.2**, celui Windows précédemment observé 25.2 :
ne pas ajouter aveuglément une option de build non prise en charge sur tous les chemins.

Les [contraintes de build pip](https://pip.pypa.io/en/latest/user_guide/#build-constraints)
sont distinctes des contraintes runtime. Le
[mode hashes pip](https://pip.pypa.io/en/stable/topics/secure-installs/)
nécessite des distributions épinglées et couvertes ; ajouter `--require-hashes` à
l'installation actuelle du répertoire local `.` n'est pas un correctif complet.
Préparer séparément une wheel projet issue du SHA revu et les dépendances hachées.
Les [bases Docker par digest](https://docs.docker.com/build/building/best-practices/#pin-base-image-versions)
doivent être vérifiées puis entretenues, pas figées sur une valeur supposée sûre.

## 8. Tests réellement exécutés

L'instrumentation privée 14.7.2 est conservée et réutilisée. Elle ne sérialise ni SQL,
paramètres, documents, prompts, emails ou secrets. Les fautes sont one-shot, sans
augmentation de délai/retry et sans charge ou saturation externe.

| Campagne | Réussis | Ignorés | Échoués / interprétation |
| --- | --- | --- | --- |
| Premiers probes Windows, erreur générique dans COMMIT driver | 2 | 0 | 2 ; lecture initiale du même pool insuffisante pour qualifier l'état durable. |
| Probes Windows, erreur DBAPI dans COMMIT driver | 2 | 0 | 2 ; mêmes limites de lecture, logs conservés. |
| Windows, quatre cas recalibrés : avant commit ORM / après commit confirmé | 3 | 0 | 1 ; invariant fichier commité/source absent. |
| Windows, six cas qualifiés avec lecture indépendante, authentification et lecture | 5 | 0 | 1 ; même invariant documentaire. |
| WSL, six cas privés + IA off/résumés/état public/email | 65 | 0 | 1 ; même invariant documentaire, 261,37 s. |
| PostgreSQL, sélection étendue Sprint 14 + six cas privés | 294 | 8 | 1 ; même invariant documentaire, 239,06 s. |
| Observation complémentaire pré-driver Windows | 1 | 0 | 0 ; révèle vue du pool 1 contre lecture indépendante 0, 3,15 s. |
| Observation complémentaire pré-driver PostgreSQL | 0 | 0 | 1 ; ProgrammingError INTRANS au pool après faute injectée, 2,00 s. |
| BFF Node, protections et proxy | 50 | 0 | 0. |
| Couverture proposée des contraintes, métadonnées | 3 environnements | — | Windows 50, WSL 49, Docker Linux 49 distributions couvertes ; aucun build complet revendiqué. |

Les campagnes se recouvrent. Les échecs ne sont pas des tests ignorés ou transformés
en succès. Les deux probes de frontière driver ne sont pas des incidents spontanés.
La sélection WSL comporte les 60 tests existants tous réussis et les six nouveaux
cas privés (5/1). La sélection PG comporte 289 tests existants réussis, huit ignorés,
et six cas privés (5/1). Les huit skips sont les deux preuves root et les six snapshots
Docker nécessitant leur ancien projet opt-in ; aucune de ces validations n'est
déclarée passée par substitution.

La sélection PostgreSQL réelle couvre public/quota/identité/email/anti-abus, neuf
entrelacements de concurrence, IA désactivée, résumés longs, comptes/sessions,
sécurité de release/autorisation et sauvegardes/inventaire. Le cas initial passe ;
les erreurs supplémentaires sont les injections décrites et l'IntegrityError de
doublon volontaire des tests de concurrence, traitée sans compte/place orphelin.
Ces campagnes ne constituent pas une nouvelle suite complète Windows/WSL/PG.

Les suites complètes 14.7.1/14.7.2 restent historiques. Aucun code applicatif n'a
évolué : pas de suite complète Windows relancée, de nouveaux tests React/build,
de nouvelle recette HTTPS intégrale, de nouvelle certification Landlock/seccomp,
de restauration réelle B2 ni d'appel fournisseur. Le sandbox n'est pas assoupli.

Commandes principales exécutées :

```powershell
.\.venv\Scripts\python.exe -m pytest var/test_s14_7_3_database_risks.py -q -p no:cacheprovider --basetemp=var/pytest-14-7-3-risk-final --tb=short
npm.cmd run test:bff
.\.venv\Scripts\python.exe var/audit_s14_7_3_dependencies.py var/s14-7-3-constraints-proposal.lock
```

```bash
PYTHONPATH="$PWD/var" DOCUMIND_DIAGNOSTIC_FILE=var/s14-7-3-wsl-diagnostic.jsonl \
 /var/tmp/documind-s13-a7b75801/.venv/bin/python -m pytest \
 var/test_s14_7_3_database_risks.py tests/test_ai_disabled_enforcement.py \
 tests/test_long_summary.py tests/test_public_beta_state.py tests/test_public_beta_email_abuse.py \
 -q -p no:cacheprovider -p s14_7_2_worker_diagnostics \
 --basetemp=/var/tmp/documind-s14-7-3-qualification --tb=short
```

Un septième cas privé d'observation du pool est ajouté après les campagnes à six
cas et exécuté séparément, jamais attribué rétroactivement aux sélections. Les logs
restent distincts sous `var/s14-7-3-*.log` et JSON/JSONL ; aucune preuve rouge effacée.

## 9. Garanties conservées et limites d'exploitation

Quota cinq cumulatif, verrou, blocage administratif, vérification email à usage
unique, sessions/révocations, propriétaires, CSRF/BFF, refus IA, backup/inventaires,
rollback sécurisé et registre root restent présents. Les sélections les exercent ;
elles n'annulent pas le nouveau témoin d'intégrité documentaire en échec.
Pas de reset de quota, migration ou modification de fichier de configuration réel.

Docker Desktop est ciblé explicitement par son pipe local. Image de preuve dérivée
du harnais 14.7.2 déjà validé, sans lancer les Dockerfiles de production ou télécharger
de dépendance. API de tests readonly/non-root, capacités supprimées, no-new-privileges,
1536 Mio, deux CPU, 64 PID et tmpfs ; PostgreSQL neuf sur tmpfs, réseau interne dédié,
aucun port publié, aucun montage existant. La seconde sonde PG reçoit une autre base
neuve dans ce même serveur de test. Les documents sont des TXT générés ; faux SMTP,
aucun email réel ni clé réelle. Les adaptations development des fixtures portables
ne changent aucune règle de confinement production.

La production n'est pas inspectée, modifiée ou testée. Les états effectifs des flags,
TLS/proxy, règles GitHub, Registry, sauvegardes B2, SMTP réel et alerte applicative
ne sont pas certifiés par ce lot. La fermeture d'urgence du runbook reste une
opération future autorisée séparément, pas un remède automatique à un fichier manquant.

## 10. Conditions de PR et de publication

**A — Brouillon de revue :** le dossier peut être proposé à la revue GitHub après
autorisation de commit/push/PR, avec les trois risques SQL distincts, RF10-03 et le
témoin rouge explicitement présentés. Rendre la reproduction du défaut accessible
au reviewer après revue de sa source de test ; ne pas joindre des logs privés ou
ajouter tout `var/`. Les gates actuels ne collectent pas cette sonde privée : une CI
verte sans elle ne prouverait pas la correction. Aucune fusion automatique.

**B — RC publiée et utilisable :** demander d'abord un lot correctif local sur
commit incertain/stockage et pool, avec test permanent de l'invariant, validation PG
et non-régressions Windows/WSL. Puis traiter RF10-03 ou obtenir une acceptation
nouvelle et bornée pour une publication privée précise ; statuer séparément sur
R14-SQL-01 resté inconnu. Revalider les trois jobs python/windows/frontend sur SHA
exact, les trois builds amd64 et le bundle neuf fichiers. Publication partielle :
arrêt, conservation des digests/preuves, aucune relance/suppression/retag automatique.
La Registry privée n'est pas un environnement de validation applicative ou une
autorisation de déploiement. Aucune approbation root du candidat dans ce lot.

**C — Public :** corriger les blocages, recette des images CI exactes sur Linux/ABI
accepté, bootstrap root/backup coordonné, secours ou correction en avant qualifiés,
SMTP/textes/alertes/B2/restauration réels validés, risques résiduels explicitement
acceptés, capacité et fermeture vérifiées ; décision d'ouverture séparée, IA toujours off.
Ces prérequis ne sont pas accomplis par une publication privée ou un Go de brouillon.

## 11. Préparation de la prochaine étape et clôture

1. Faire valider le périmètre correctif **R14-SQL-02** et la récupération des erreurs
   de COMMIT ; promouvoir la sonde en test permanent avec des lectures indépendantes,
   puis corriger sans suppression aveugle de fichier ni retry global. Examiner aussi
   la suppression/tombstone et les états d'arrêt/crash dans ce lot ciblé. Une éventuelle
   quarantaine doit rester privée, bornée et comptée dans les budgets disque ; préserver
   un fichier en cas d'incertitude ne doit pas créer un stockage orphelin illimité.
2. Revoir la proposition de contraintes et obtenir les matériaux de build manquants
   par une étape CI/audit explicitement autorisée ; ne pas épingler un hash supposé.
3. Documenter les décisions humaines sur R14-SQL-01, admission après 503/RAM mail et
   RF10-03 ; aucune signature ou acceptation inventée par l'assistant.
4. Reprendre l'inventaire Git, l'index explicite et la revue avant tout commit/push.
   Aucun report ancien n'est réécrit pour présenter l'incident comme corrigé.

Le seul ajout au périmètre Git est ce rapport. Les sondes, propositions et images
locales restent des preuves privées sous `var/` ; aucune correction applicative,
modification de dépendance ou workflow appliquée. Contrôle final : **66/66 empreintes
préexistantes identiques**, même branche, **32 suivis modifiés + 35 non suivis = 67
candidats**, index vide ; seul ce rapport est nouveau dans le périmètre Git.
`git diff --check` et le contrôle séparé des blancs de ce nouveau Markdown réussissent.
Le serveur PostgreSQL de mission et son réseau ont été supprimés après contrôle des
labels/montages ; les conteneurs de preuve étaient `--rm`, les filtres finaux propres
à cette mission sont vides. Aucune autre ressource Docker ni preuve locale existante
n'est supprimée. Les images de tests restent locales et non publiables.
Aucun commit, push, merge, accès VPS,
publication Registry, déploiement, ouverture d'inscription ou activation IA.

**Verdict : brouillon de revue possible sous autorisation ; pas de RC utilisable
validée ni d'ouverture publique. Cause du 503 initial toujours inconnue ; risque
d'intégrité documentaire distinct désormais démontré sous faute contrôlée.**
