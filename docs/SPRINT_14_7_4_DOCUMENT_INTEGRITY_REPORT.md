# Sprint 14.7.4 — Intégrité documentaire et commits incertains

26 octobre 2026. Travail exclusivement local sur
`preparation/sprint-14-5-ux-email-abuse`, HEAD
`8243e0511c5505a9cc70f76ad02392f7a816590d`. Références :
[14.7.3](SPRINT_14_7_3_RELEASE_RISK_QUALIFICATION_REPORT.md),
[14.7.2](SPRINT_14_7_2_SQLALCHEMY_INTERMITTENT_FAILURE_REPORT.md),
[14.7.1](SPRINT_14_7_1_RELEASE_CANDIDATE_REVIEW.md) et
[runbook](SPRINT_14_7_PUBLIC_BETA_OPENING_RUNBOOK.md).
La production Sprint 13/0007, inscriptions et IA fermées, est l'état annoncé par
l'opératrice ; aucune observation ni intervention distante dans cette mission.

**R14-SQL-02 corrigé et prouvé sur PostgreSQL sous les fautes définies ci-dessous.**
Go pour poursuivre la préparation locale et la revue ; **No-Go pour une RC utilisable
publiée et l'ouverture publique**, avec SQL-01/SQL-03/RF10-03 et les validations
opérationnelles restant des décisions distinctes. Aucune publication autorisée.

## 1. Cause démontrée et périmètre

`import_document()` renommait `.part` vers le nom définitif, appelait `commit()`,
puis supprimait ce fichier sur toute exception après une tentative de rollback.
Un COMMIT effectivement exécuté ne peut pas être annulé par ce rollback : la faute
synthétique « vrai COMMIT DBAPI puis OperationalError » laissait une ligne durable
sans source. Le test permanent a d'abord été exécuté sur le code initial :
**4 réussites, 1 échec**, exactement sur la conservation du fichier commité.
Le témoin rouge est conservé dans `var/s14-7-4-red.log`, jamais transformé en skip.

Autre fenêtre corrigée : `delete_document()` déplaçait le fichier vers `.deleted`
avant le COMMIT SQL. Un arrêt brutal à ce moment laissait une ligne active sans
son fichier attendu. Le nouvel ordre conserve la source jusqu'à confirmation de
la suppression SQL. Aucun nouveau tombstone n'est produit.

Ce modèle de faute est volontaire et déterministe ; il ne mesure pas la fréquence
d'une panne réelle et n'explique pas le GET 503 historique R14-SQL-01.

## 2. Invariants et politique transactionnelle

- Une ligne documentaire durable active conserve sa source sous son nom généré.
- Une exception de COMMIT ne prouve ni rollback ni succès pour le client.
- Aucun retry de COMMIT ou succès HTTP artificiel ; l'exception initiale reste
  transmise au handler SQLAlchemy, qui renvoie son 503 générique.
- Une source ne peut être nettoyée après cette exception que si l'absence SQL est
  prouvée par une connexion physique indépendante, après résolution du writer.
- Une source incertaine reste sur place, privée ; aucun déplacement qui rendrait
  une ligne durable incapable de retrouver son fichier.
- Une source sans ligne n'est ni adoptée en base ni publiée par HTTP.

| Issue | Traitement |
| --- | --- |
| Erreur avant tentative de COMMIT | Rollback ; nettoyage du `.part` et de l'éventuel fichier renommé non commité. |
| COMMIT renvoyant normalement | Import 201 ; suppression 204, puis nettoyage de la source supprimée. |
| COMMIT levant une exception | Invalidation de la session/connexion physique suspecte ; vérification indépendante, sans rejouer l'opération. |
| Ligne exacte retrouvée | Fichier conservé ; HTTP 503 initial maintenu. |
| Absence confirmée après barrière du writer | Nettoyage possible ; HTTP 503 initial maintenu. |
| Connexion, timeout, identité divergente ou autre échec de vérification | État unknown ; conservation et événement expurgé. |
| Arrêt du processus | Pas de finally présumé ; `.part`/source restent privés pour inventaire après reprise. |
| Ligne présente/source manquante préexistante | Signalement ; aucune reconstruction à partir du texte extrait ni réparation automatique. |

### Connexion saine et barrière de fin du writer

`Session.invalidate()` écarte la connexion suspecte **avant** toute remise en pool.
Le probe antérieur avait montré qu'un simple rollback/close pouvait laisser une
transaction native INTRANS, différente de la vue durable d'un autre engine.
Le nouveau lecteur utilise un engine `NullPool` et une connexion physique neuve,
sans passer par le pool applicatif ou le pool d'authentification.

PostgreSQL : le lecteur attend le même verrou `ai_budgets/development FOR UPDATE`
que l'import et désormais la suppression. Une requête SELECT qui constaterait
simplement l'absence, alors qu'un COMMIT serveur est encore en cours, ne suffirait
pas. Après acquisition, il compare UUID, propriétaire, nom de stockage, taille et
SHA-256 ; une divergence donne unknown. La transaction de vérification est ensuite
fermée sans mutation métier. SQLite : `BEGIN IMMEDIATE` sur la connexion indépendante
empêche de conclure avant la fin d'un writer restant.

Délais techniques de cette seule vérification : connexion PG 3 s, statement 3 000 ms,
lock 3 000 ms ; SQLite busy timeout 3 s. Ils ne modifient ni les timeouts des résumés,
ni les réglages globaux des engines, ni l'admission SEC10-02. Ce ne sont pas trois
secondes garanties de bout en bout : connexion et commandes sont successives et
la résolution DNS dépend aussi du système. Tout échec conserve le fichier.

## 3. Écriture, suppression et récupération

Le fichier nouveau est créé exclusivement, mode 0600 ; nom UUID serveur et extension
PDF/TXT, taille et SHA-256 inchangés. Flush/fsync du fichier avant extraction, rename
dans le même répertoire, fsync du répertoire sous Linux avant COMMIT. Le `.part`
est nettoyé en finally avec libération du slot même si son unlink échoue ; une erreur
de nettoyage émet l'événement existant `system.file_cleanup.failed`.
Windows n'offre pas ici le même fsync de répertoire ; les tests couvrent l'arrêt de
processus, pas une coupure électrique, un disque qui ment sur fsync ou une corruption
du système de fichiers.

La suppression conserve les guards de propriétaire, réservations IA et indexation.
Le chemin de purge d'un compte passe aussi par `delete_document()` et bénéficie du
nouvel ordre. Si le nettoyage après suppression validée échoue, une source privée
sans ligne peut rester ; il n'y a plus de ligne active à laquelle elle manquerait.
Si la vérification reste indisponible, même ce fichier n'est pas supprimé.

L'ancien `backend.maintenance.reconcile()` est **inchangé** : simulation par défaut,
restauration de tombstones et suppressions explicites avec `--apply`. Aucun appel
automatique au démarrage n'a été trouvé. Son hypothèse « API arrêtée » n'est pas
vérifiée par le CLI : **ne pas utiliser --apply pour résoudre un commit incertain**.
Il ne constitue pas un mécanisme de réconciliation sûre en ligne. Les tombstones
historiques doivent être diagnostiqués à froid, avec fin des transactions confirmée,
sauvegarde et autorisation de réparation distincte.

Une seconde requête POST après 503 n'est pas un retry idempotent : si la première
était commitée, les deux documents existent avec des identités distinctes et les
quotas habituels. Les tests le vérifient. L'application ne déduplique pas implicitement
deux imports intentionnels identiques ; aucune promesse d'idempotence nouvelle.

## 4. Conservation privée et bornes

Emplacement : `STORAGE_DIR`, normalement `/app/var/documents`, dans le volume privé
existant monté sur `/app/var`. Répertoire créé 0700 par le démarrage existant ; nouveaux
fichiers 0600 sous Linux. Pas de changement récursif des droits anciens ou de volume.
Aucun fichier conservé n'est rendu par une route statique ; accès aux lignes toujours
soumis à l'authentification et au propriétaire. Aucun endpoint de quarantaine public.

Durée : conservation **jusqu'à décision humaine après preuve**, sans TTL de suppression.
Un incident doit être examiné avant reprise d'import si les limites sont atteintes.
Prévoir une prise en charge opératrice rapide, par exemple sous 24 h après alerte,
à faire valider avant exploitation ; ce délai d'intervention proposé n'est pas un
TTL de destruction. Une suppression de compte dont le nettoyage échoue peut
laisser une source privée et ses copies en sauvegarde : ne pas annoncer alors un
effacement physique immédiat. La durée légale et la clôture de cet incident exigent
une décision humaine documentée, distincte de la purge Restic restée en simulation.
Cette durée non automatique est bornée en espace et nombre par backpressure :

- `DOCUMENT_RETENTION_MAX_FILES=100` sources non référencées au maximum admis ;
- `DOCUMENT_RETENTION_MAX_BYTES=67108864` pour les octets non référencés et la marge
  du prochain import ; une tentative incapable de respecter cette borne est refusée ;
- contrôle sous le verrou global partagé avant déplacement en stockage définitif ;
- `.part` abandonnés comptabilisés par le budget temporaire SEC10-02 préexistant ;
- sources effectivement référencées comptabilisées par les quotas SQL habituels ;
- espace libre, taille maximale, slots et limites d'extraction conservés.

Ces deux nouveaux réglages sont des freins techniques distincts ; **aucun quota
de compte, d'inscription, d'IA ou de stockage métier n'est modifié**. Le dépassement
refuse les imports, il ne purge pas les preuves. Les limites ne réparent pas un
stockage historique déjà hors bornes, les écritures externes ou une accumulation
forcée par des interventions manuelles. Une panne de base empêchant d'obtenir le
verrou empêche aussi de créer un nouveau fichier définitif.

Ce sont des bornes d'**admission de nouveaux octets**, pas une permission d'effacer
l'excédent : une série de suppressions déjà admises dont le nettoyage échoue peut
laisser plus de 100 sources ou 64 Mio. Elle n'ajoute pas d'octets et bloque alors
les nouveaux imports. Hors intervention externe, l'enveloppe de stockage combine
les sources déjà admises sous le plafond métier global, les résidus admis sous le
frein technique et le budget temporaire. Aucun plafond ne justifie de supprimer une
source dont l'issue reste inconnue. Les bornes ne doivent pas être abaissées puis
traitées comme un ordre de purge.

Détection : événements expurgés existants, nouvel inventaire agrégé, surveillance
disque existante. Le 503/healthcheck SELECT 1 ne certifie pas l'intégrité documentaire.
Aucun nouveau timer/Gmail ni alerte temps réel exhaustive n'est installé. Un opérateur
doit examiner tout incident de commit/nettoyage et conserver un rapport privé.

Nettoyage futur sûr : application et workers arrêtés sous verrou d'exploitation,
transactions anciennes terminées, base saine autoritative, sauvegarde cohérente
contrôlée, identité exacte vérifiée, absence durable établie après barrière, décision
opératrice nominative. Si l'état est unknown, aucune suppression ni restauration.
Ne pas effacer un marqueur de maintenance pour obtenir ce verrou ou redémarrer.

## 5. Outil d'intégrité en lecture seule

`tools/check_document_integrity.py` appelle
`backend.services.document_integrity.check_document_integrity()` : engine indépendant,
transaction PG read-only/SQLite query_only, aucun INSERT/UPDATE/DELETE, création de
répertoire, renommage ou réparation. Inventorie les lignes `documents`, toutes actives
dans le schéma actuel sans champ de suppression logique, puis leurs sources.

Contrôles : nom de stockage UUID/extension strict, fichier régulier sans symlink,
présence, taille, SHA-256 en blocs de 64 Kio, sources non référencées, `.part`, anciens
`.deleted`, erreurs de lecture/base. Le contrôle Linux emploie O_NOFOLLOW. Une copie
contenant d'autres types d'entrées est signalée, pas parcourue ni réparée.
Sortie JSON avec compteurs et `consistent` seulement ; aucune identité propriétaire,
UUID documentaire, nom original, chemin, contenu, URL SQL ou message d'exception.
Exit 0 si cohérent, 1 autrement. Un rapport avec writers actifs n'est pas un snapshot
cohérent ; exiger une fenêtre quiescente pour toute décision destructive ultérieure.

Usage local depuis un environnement fictif explicitement configuré :

```text
python -m tools.check_document_integrity
```

**Procédure future de production, NON EXÉCUTÉE et soumise à autorisation séparée :**
identifier current/digests et contrôleur approuvé ; prendre `deployment.lock` avec les
outils d'exploitation ; vérifier les marqueurs sans les altérer ; arrêter seulement
API/BFF gracieusement, ne pas arrêter/recréer PostgreSQL ; sauvegarder selon la
procédure approuvée. Exécuter le lecteur de la version corrigée, avec le même volume
privé et une connexion saine, puis archiver seulement son JSON agrégé. Le script
`tools` n'est pas copié dans l'image API ni ajouté au bundle de neuf fichiers ; le
module backend, lui, est inclus par le Dockerfile existant. Avec un préfixe Compose
réellement revu désigné ici par `dc`, l'appel équivalent dans l'image est :

```bash
dc run --rm --no-deps -T --entrypoint python api -c '
import json
from backend.config import Settings
from backend.db import make_engine
from backend.services.document_integrity import check_document_integrity
engine = None
try:
    settings = Settings()
    engine = make_engine(settings.database_url)
    report = check_document_integrity(engine, settings.storage_dir)
except Exception:
    report = {"consistent": False, "configuration_or_connection_error": True}
finally:
    if engine is not None:
        engine.dispose()
print(json.dumps(report, sort_keys=True))
raise SystemExit(0 if report["consistent"] else 1)
'
```

Ce snippet exige la version corrigée déjà approuvée, pas l'image Sprint 13 qui ne
contient pas le module. Le chemin `.env.production` reste fourni uniquement par
le Compose opératoire existant, sans afficher de configuration résolue. Reprise par
les guards approuvés seulement ; si un contrôle refuse, conserver les preuves et
traiter l'incident, jamais démarrer manuellement une ancienne version non autorisée.

Ligne sans fichier : rechercher uniquement dans une restauration indépendante
vérifiée, comparer nom/empreinte/taille, autorisation distincte avant remise en place.
Fichier sans ligne : conserver et rechercher l'historique ; ne pas l'adopter en base
ou le publier. En l'absence de preuve, rester fermé aux opérations concernées.

## 6. Tests permanents et méthode

`tests/test_document_integrity.py`, 22 cas paramétrés au total :

- import : faute avant COMMIT ORM, faute avant vrai COMMIT DBAPI avec transaction
  résiduelle, vrai COMMIT puis exception ; lecture indépendante et prochain import ;
- invalidation effective avant création d'un engine NullPool ; récupération du pool ;
- impossibilité de vérifier, connexion de vérification en échec, identité divergente ;
- double POST après 503, conservation après nouveau lifespan, refus hors propriétaire ;
- suppression commitée/non commitée et vérification indisponible, sans tombstone ;
- bornes de nombre/octets des sources abandonnées, aucun effacement ;
- contrôleur read-only : présence, taille/SHA, absence, part, tombstone, nom hostile,
  agrégats sans fuite, symlink Linux et droits 0600 ;
- barrière PostgreSQL concurrente : attente d'un writer puis état durable, sans sleep
  arbitraire ; Event et future avec délais de sécurité ;
- cinq arrêts brutaux dans un interpréteur enfant via `os._exit(73)` : après écriture
  du `.part` privé, après rename avant COMMIT, après COMMIT, suppression avant COMMIT,
  suppression après COMMIT avant nettoyage. Les finally/rollbacks ne s'exécutent pas.

`tests/document_integrity_crash_child.py` n'est qu'un harnais de test. Le parsing y
est remplacé par une valeur fictive pour cibler le cycle de vie, sans changer le code
du sandbox. Les tests d'extraction natifs sont exécutés séparément. La configuration
enfant ne contient que l'URL de la base jetable, le stockage fictif et son adaptateur
portable explicite. Aucun matériel d'authentification n'est transmis à cet enfant.

## 7. Résultats réellement exécutés

Toutes les campagnes ci-dessous sont terminées et leurs sorties ont été relues.
Les journaux privés sont sous `var/s14-7-4-*.log`, exclus de Git.

| Campagne | Réussis | Ignorés | Échoués / état |
| --- | --- | --- | --- |
| Témoin permanent sur ancien code | 4 | 0 | 1, invariant source commitée, 11,49 s |
| Première correction, intégrité + documents | 24 | 0 | 0, 46,02 s |
| Première extension du harnais crash | 10 | 0 | 5, configuration du harnais, pas une perte de fichier applicative |
| Harnais crash corrigé, sélection intermédiaire | 15 | 0 | 0, 32,60 s |
| Windows, fichier permanent final | 20 | 2 | 0, 44,15 s |
| Docker non-root, Landlock/seccomp/protocole | 72 | 0 | 0, 10,65 s |
| PostgreSQL 17.11 / pgvector 0.8.7, campagne étendue | 355 | 8 | 0, 315,90 s |
| PostgreSQL, intégrité + transactions, confirmation indépendante | 25 | 0 | 0, 38,63 s |
| Docker root, deux preuves registre/guard | 2 | 0 | 0, deux commandes séparées, 0,57 / 0,56 s |
| CLI read-only sur SQLite fictif, inventaire sain puis corrompu | 2 contrôles | — | Exit 0 puis 1 ; hashes de tous les fichiers/base inchangés |
| Windows 3.13.7, suite complète | 775 | 70 | 0, 763,91 s |
| WSL Python 3.12.3, suite complète instrumentée | 817 | 28 | 0, 1 275,02 s |

L'erreur du premier harnais crash venait de la sérialisation de Settings qui masque
SecretStr en `**********`, valeur refusée comme clé BFF. Le harnais transmet désormais
uniquement les trois paramètres nécessaires ; aucune validation de clé n'a été
assouplie et aucun secret n'a été révélé. L'historique rouge reste conservé.

Les deux skips Windows du fichier final sont la preuve Linux de symlink/droits et
le verrou PostgreSQL. Aucun skip ni inversion de l'invariant R14-SQL-02. Les campagnes
se recouvrent ; ne pas additionner leurs totaux comme des cas distincts.
La suite Windows a été lancée pendant la campagne WSL/PG, sur des bases distinctes :
ces mesures ne sont pas une nouvelle référence sans concurrence de charge hôte
pour diagnostiquer R14-SQL-01. L'instrumentation privée précédente est réutilisée
uniquement sous WSL ; aucun SQL/paramètre n'est ajouté aux journaux de production.

La suite WSL a 845 enregistrements de diagnostic. Les erreurs SQL capturées sont
les injections volontaires des nouveaux tests et du test existant de confidentialité
des exceptions. Le cas historique de reprise/interruption réussit sans erreur SQL
capturée ; son worker est arrêté au teardown. Cela reste une non-reproduction de
SQL-01, pas l'identification de sa cause. Les 28 skips WSL sont douze cas PG, six
snapshots opt-in, huit E2E opt-in et deux preuves root ; PG/root sont testés dans les
campagnes distinctes. Windows ignore en plus les preuves Linux non applicables.

La sélection PG réelle couvre intégrité, PDF/TXT, BYOK, comptes, gateway,
admission upload, résumés longs, IA fermée, inscription publique, concurrence,
identité/email, approbation et sauvegardes/inventaires. Les huit ignorés sont six
snapshots Docker opt-in et deux preuves root, ces dernières exécutées séparément
dans des conteneurs sans réseau. Les **22 nouveaux cas permanents passent tous sous
PostgreSQL**, puis les 22 et les trois transactions historiques passent à nouveau.
Le CLI a été testé depuis un répertoire fictif neuf, sans charger le `.env` du dépôt ;
ses sorties n'incluent pas les sentinelles privées et il ne change aucun hash.
React/BFF, build frontend, recette HTTPS/navigateurs et restauration réelle B2 ne
sont pas relancés dans ce lot backend ; leurs résultats antérieurs ne sont pas
attribués à cette correction. Aucun contrôle de SMTP/Registry/VPS réel.

Docker Desktop ciblé explicitement par son pipe local, images cached/offline,
`documind-s14-7-4-proofs:local`, sans Registry. Rootfs readonly, utilisateur app,
cap-drop ALL, no-new-privileges, deux CPU, 1 536 Mio, 64 PID, tmpfs 256 Mio.
Confinement natif sans réseau/volume. PostgreSQL neuf `s14-7-4-pg`, base
`s14_7_4_test`, réseau interne `s14-7-4-pg-net`, aucun port/bind/volume persistant,
données tmpfs et identifiants fictifs. Les fixtures refusent une base non vide.
L'environnement Linux local n'est pas le VPS : WSL Linux/ABI local, aucune nouvelle
certification à distance de Linux 6.12/ABI 6. Les fixtures portables development
restent limitées aux tests ; aucune configuration production n'est assouplie.
Noyau Docker local relevé : `6.18.54.1-microsoft-standard-WSL2`, x86_64,
Landlock ABI **7**. Les tests natifs exigent toujours ABI >= 3 et seccomp.

Commandes principales exécutées depuis le dépôt :

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_document_integrity.py -q -p no:cacheprovider --basetemp=var/pytest-14-7-4-finaltarget --tb=short
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp=var/pytest-14-7-4-windows-full --tb=short
docker --host npipe:////./pipe/dockerDesktopLinuxEngine build --pull=false --network none -f ops/testing/Dockerfile.beta-recipe --target proofs -t documind-s14-7-4-proofs:local .
git diff --check
```

```bash
PYTHONPATH=var DOCUMIND_DIAGNOSTIC_FILE=var/s14-7-4-wsl-diagnostic.jsonl \
 /var/tmp/documind-s13-a7b75801/.venv/bin/python -m pytest \
 -p s14_7_2_worker_diagnostics -q -p no:cacheprovider \
 --basetemp=/var/tmp/documind-14-7-4-wsl-full --tb=short
```

## 8. Sauvegardes et restauration

`backup_local.py` archive tout `documents`, donc aussi les sources retenues, parts
et anciens tombstones. Le format v2, les SHA-256 des archives et l'inventaire SQL
0007 restent inchangés. Le quota public n'est ni remboursé ni réinitialisé.
Une archive fidèle peut conserver une incohérence antérieure : le succès Restic
ne remplace pas la correspondance fichier/ligne. `validate_restore.py` compare déjà
les fichiers référencés, tailles et SHA sur la copie indépendante ; le nouvel outil
signale en plus les sources non référencées et résidus.

Un orphelin retenu accompagne donc les sauvegardes et ne doit pas être publié après
restauration. Toujours vérifier les empreintes et l'inventaire avant de fermer le
verrou d'inscription de la copie restaurée, selon le runbook. Ne pas utiliser les
defaults du CLI historique contre une base existante. Aucune restauration B2 réelle
ou réécriture de sauvegarde n'est faite ici. Les six snapshots Docker opt-in de
l'ancien harnais ne sont pas déclarés réussis s'ils restent ignorés.

Le verrou de livraison, les deux scripts ops root, le registre indépendant, les
marqueurs et les refus de rollback/redémarrage non approuvés restent inchangés.
La première version corrigée ne doit pas revenir automatiquement au Sprint 13 qui
possède toujours R14-SQL-02. Lors de la revue ultérieure du registre, tout candidat
de secours doit contenir ce correctif en plus des garanties 14.2–14.6.1 ; le nom
du profil seul n'est pas une preuve que ce nouveau correctif y figure.

## 9. Fichiers et préservation

Modifications ciblées de ce lot :

```text
backend/config.py
backend/services/documents.py
backend/services/document_integrity.py                         nouveau
tools/check_document_integrity.py                             nouveau
tests/test_document_integrity.py                              nouveau
tests/document_integrity_crash_child.py                        nouveau
docs/SPRINT_14_7_4_DOCUMENT_INTEGRITY_REPORT.md                  nouveau
```

Comparaison SHA-256 : **67/67 candidats préexistants identiques**. Aucun ancien
rapport n'est réécrit comme une correction de SQL-01.
Pas de migration, changement de dépendance, de workflow, Compose, Dockerfile,
confinement, secret, quota métier ou fichier de production. Les nouveaux réglages
restent des valeurs par défaut du code, pas une modification d'env en production.
L'outil reste en dehors du bundle neuf fichiers ; son moteur est dans l'image API.
Inventaire final : **34 suivis modifiés + 40 non suivis = 74 candidats**, dont les
sept chemins de ce lot ; index vide, même branche/HEAD. `git diff --check`, les six
analyses AST et le contrôle séparé des blancs des sept fichiers réussissent.
`var/` contient les seuls journaux, sondes privées et données fictives générées ;
il reste ignoré. Aucun document, dump, certificat ou fichier privé ajouté aux candidats.
Le PostgreSQL neuf et son réseau ont été supprimés après contrôle des labels et de
l'absence de montages persistants. Les filtres Docker de cette mission sont vides ;
les images de preuves et fichiers fictifs restent locaux. Aucun nettoyage d'une
ressource préexistante, aucun changement de droit global ou de volume existant.

## 10. Risques distincts et limites

| Risque | État |
| --- | --- |
| R14-SQL-01, ancien GET 503 | Cause historique toujours inconnue. Une suite verte ne constitue pas sa correction. |
| R14-SQL-02, source perdue après COMMIT | Corrigé ; 22 tests permanents réussis sous PG, puis 25 avec les transactions historiques, suites Windows/WSL vertes. Preuve sous fautes définies, sans prétendre couvrir toute défaillance matérielle. |
| R14-SQL-03, inscription commitée malgré 503/mail absent | Inchangé : compteur cumulatif et renvoi protégé, sans compensation automatique. Décision opératrice distincte. |
| RF10-03, supply chain | Inchangé : transitifs/build tools/bases/source pgvector à qualifier. Aucune acceptation étendue automatiquement, aucun audit CVE actualisé. |

L'invalidation après faute de COMMIT est locale aux opérations documentaires. La
sonde pré-driver d'inscription révélant INTRANS en 14.7.3 n'est pas un cas corrigé
globalement par cette intervention : ni le parcours d'inscription ni les engines
communs ne sont modifiés. Ne pas étendre la preuve de récupération documentaire à
tous les commits de l'application.

Les limites de conservation peuvent rendre les imports indisponibles tant que le
stockage n'est pas diagnostiqué ; c'est préférable à détruire une source potentiellement
commitée. Il n'y a pas de transaction atomique commune SQL/système de fichiers, de
garantie contre une suppression administrative externe, de restauration automatique,
de preuve de coupure électrique ou de réparation de pertes antérieures.
L'outil historique `--apply` demeure une opération manuelle à risque hors quiescence.
Une source sans ligne reste une donnée privée à gérer, pas une preuve d'import réussi.

## 11. Verdict et prochaines décisions

**Go pour poursuivre la préparation locale et la revue de la correction. Le défaut
R14-SQL-02 est corrigé et prouvé sur un vrai PostgreSQL 17 jetable**, avec contrôle
du COMMIT effectif, de la lecture indépendante, du pool et des arrêts brutaux.
Les suites complètes Windows/WSL et les 72 preuves de confinement sont vertes.

**No-Go maintenu pour publier une RC utilisable et pour ouvrir la bêta publique.**
Les décisions documentées sur SQL-01/SQL-03 et RF10-03, la qualification des images
CI exactes et les préconditions opératoires du runbook ne sont pas obtenues par ce
correctif. La restauration B2 réelle, la conformité des textes, SMTP/alertes réels,
le registre et le bootstrap VPS restent non exécutés dans ce lot. Aucun risque
n'est accepté au nom de l'opératrice. Une PR de revue nécessite toujours les
autorisations explicites de commit/push/PR ; ce Go technique n'en tient pas lieu.

Après ce lot : revue Git de l'inventaire exact et des nouveaux tests, décisions
distinctes sur SQL-01/SQL-03/RF10-03, CI des SHA réels et digests, recette des images
publiées, approbation indépendante et bootstrap coordonné, avant toute livraison
fermée autorisée. Inscriptions publiques et IA restent désactivées. Aucun commit,
push, merge, appel VPS/Registry, déploiement ou modification de production.
