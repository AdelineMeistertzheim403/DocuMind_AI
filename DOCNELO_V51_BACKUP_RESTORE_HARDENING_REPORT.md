# Docnelo V5.1 — Durcissement backup/restore en développement

1 novembre 2026. **NO-GO production, Lifecycle 10 et sauvegarde réelle.**
Aucune autorisation S2, admission publique ou réconciliation H0 n'est accordée.

## 1. Périmètre et décision

Correctifs effectués uniquement dans le dépôt de développement, en conservant
les modifications préexistantes. Aucun accès au VPS, au laboratoire Hyper-V,
à une base distante, à un secret réel ou à un volume de production.
Aucun conteneur, déploiement ou migration exécuté.

Les deux releases V5 et V5.1 restent inchangées : **18/18 entrées de chacun
des manifestes recalculées et conformes**. Le développement corrigé n'est
pas une modification du bundle V5.1 scellé ni une nouvelle release qualifiée.
Il nécessite une révision distincte avant transfert autorisé au laboratoire.

Les résultats PostgreSQL 17.11 / pgvector 0.8.0 / 23 tables transmis par
l'opérateur sont des résultats expérimentaux externes à cette intervention :
ils n'ont pas été réexécutés ici. Ils ne prouvent pas la capture/restauration
des cinq stores, des deux clés, des documents et des gardes lifecycle.

## 2. Fichiers modifiés ou ajoutés

| Fichier | Action et changement de cette intervention |
|---|---|
| `backend\lifecycle_backup_lock.py` | Modifié : absence de lock représentée par `None`, suppression du test générique `__enter__` |
| `tools\validate_restore.py` | Modifié : quota fermé et relu, garde du parcours direct, rôle non privilégié, préparation explicite, marqueurs d'échec et interdiction de réutilisation |
| `tools\restore_pgvector.py` | Ajouté : sélection stricte TOC/SQL pgvector, préparation minimale et connexions bornées au laboratoire |
| `tools\verify_snapshot.py` | Modifié : paramètre optionnel `database_connect_args` pour la vérification SQL du restore ; comportement des autres appels conservé |
| `tests\test_lifecycle_backup_lock.py` | Ajouté : concurrence de vrais processus, régression Path/context-manager, acquisition/échec/libération et gardes POSIX |
| `tests\test_restore_pgvector.py` | Ajouté : TOC, SQL, séparation des rôles, préparation minimale et refus des redirections de connexion |
| `tests\test_restore_hardening.py` | Ajouté : quota ouvert, commit, contrôles et échecs du parcours, abandon, dérive et refus de réutilisation |
| `tests\test_restore_hardening_postgres.py` | Ajouté : intégrations PostgreSQL synthétiques opt-in ; aucune suppression automatique de DB |
| `tests\test_public_beta_snapshot.py` | Modifié : nom de DB conforme, mode labo explicite, assertion du sealer alignée et conservation des DB créées |

Le présent rapport est également ajouté. Aucun script de backup/capture,
Compose, fichier d'environnement, image ou clé existante n'est modifié.

## 3. Anomalies corrigées et garanties bornées

### Verrou Lifecycle

`Path.__enter__` n'est plus utilisé pour décider si une barrière est un
verrou. Seule l'absence de configuration optionnelle donne `None`.
Un chemin configuré emprunte désormais systématiquement l'ouverture du
fichier puis `fcntl.flock` sur POSIX, y compris Python 3.11.

Les contrôles de canonicalité, symlink, répertoire privé, fichier régulier,
hardlink, ownership, mode, lock partagé/exclusif et fermeture du descripteur
restent présents. Le comportement existant de création du lock absent n'est
pas changé ; ce n'est pas une nouvelle attestation de quiescence.
Sous Windows, la branche msvcrt reste exclusive même pour un lecteur.

### Quota et inscriptions

Le parcours impose cette séquence :

1. Restaurer sous le rôle non privilégié.
2. Vérifier l'intégrité originale, **avant toute fermeture du quota copie**.
3. Verrouiller la ligne quota, imposer `closed=true`, vérifier le résultat
   et relire après commit, sans changer `issued_count`.
4. Vérifier les documents/stores et relire le quota ; refuser une dérive
   par rapport au quota scellé.

Le sealer refuse DB hors `documind_restore_<12 hex>`, cluster non marqué,
URL non loopback, mode non isolé, table/ligne absente ou invalide, compteur
négatif, fermeture inefficace ou non persistée. Une absence de quota
n'est plus présentée comme une fermeture réussie.

Après un échec de pg_restore ou de vérification SQL, la fermeture est
également tentée. Si le dump partiel n'a pas créé le quota, si les droits
manquent ou si PostgreSQL est indisponible, le résultat reste **failed /
incomplete**, jamais fermé par déclaration ni validé. Pendant le chargement,
un quota ouvert peut exister transitoirement : **aucune API ne doit être
attachée**, même en laboratoire, et une copie partielle ne doit jamais
être promue. Une isolation physique est indispensable à cette garantie.

Tous les rapports conservent `opening_authorized=false`,
`s2_recovery_authorized=false` et `critical_mutations_allowed=false`.
L'ancien `api_attached=false` non mesuré est remplacé par `null` avec
`api_attachment_verified=false` : aucun inventaire d'attachement n'est inventé.

### pgvector : préparation privilégiée séparée

Le rôle de restauration doit posséder `CREATEDB`, mais ni `SUPERUSER`,
`CREATEROLE`, `REPLICATION` ni `BYPASSRLS`. Les connexions d'administration
utilisent la base autorisée `documind_restore_admin`, pas un fallback postgres.
Aucune attribution ou extension de privilèges n'est effectuée par l'outil.

Pour un dump pgvector, l'opérateur doit demander explicitement
`--prepare-pgvector-version 0.8.0` et fournir
`DOCUMIND_RESTORE_PREPARE_DATABASE_URL`, avec un rôle distinct sur le même
endpoint loopback/port que le restaurateur. Pas de préparation implicite.
Une préparation demandée pour un dump sans pgvector est refusée.

Avant CREATE DATABASE, le TOC doit être lisible, non vide, sans identifiants
dupliqués ; exactement une entrée `EXTENSION - vector` et une
`COMMENT - EXTENSION vector` sont requises. Toute autre entrée extension
ou extension-comment, absence ou duplication provoque un refus.
Les deux entrées sont ensuite rendues en SQL **sans connexion à une DB**.
Seules les définitions attendues de pgvector dans `public`, le commentaire
connu et les éléments standard explicitement admis sont acceptés.
Du SQL additionnel ou une variation non reconnue n'est pas ignoré.

La liste de restauration conserve toutes les autres entrées du TOC :
**seules ces deux entrées validées sont retirées**. Aucun filtre général
sur `EXTENSION`, `COMMENT`, `ACL`, tables ou owners n'est ajouté.
`--no-owner` et `--exit-on-error` restent utilisés.
L'intégrité SHA du dump est contrôlée par le vérificateur de capture avant
cette sélection ; elle ne remplace pas l'authentification de son origine.

Après création d'une DB neuve par le restaurateur, la connexion privilégiée
vérifie cluster, nom de DB, ownership et absence d'objets applicatifs ou
d'extension autre que plpgsql. Sa seule mutation demandée est :

```sql
CREATE EXTENSION vector WITH SCHEMA public VERSION '0.8.0';
```

Version et schema sont relus dans la même transaction. Un contrôle final
incorrect provoque son rollback. Aucun CASCADE, ALTER ROLE, GRANT, installation
de paquet serveur, DROP DATABASE ou réutilisation d'une DB existante.
La disponibilité du paquet pgvector serveur doit être préparée séparément,
par une opération privilégiée explicite sur le laboratoire autorisé.

### Échecs et quarantaine

Le dossier neuf reçoit un état `incomplete`, non validé et non réutilisable,
et un latch quarantiné **avant la création de la DB**. Les états sont écrits
via fichier temporaire, fsync et remplacement atomique du rapport créé par
cette tentative ; aucun dossier existant n'est adopté ou écrasé.

Exceptions ordinaires, refus `SystemExit`, interruption et échec de fermeture
laissent une preuve `failed` sans copier les messages susceptibles de contenir
des données sensibles. Si le disque empêche cette mise à jour, le marqueur
incomplete demeure un refus de réutilisation. DB, arbres et temporaires
partiels sont conservés ; toute nouvelle tentative exige une nouvelle cible.

`validation_complete=true` n'est émis qu'après tous les contrôles du parcours
et seulement pour l'état quarantined sans conflit. Il signifie contrôles de
ce restaurateur terminés, **pas qualification complète backup/restore**.
`reusable=false` reste explicite même après succès. Un conflit reste blocked,
non validé et non réutilisable.

Les URL refusent query parameters, endpoint non loopback et driver différent
de Psycopg. Les overrides ambiants PGHOSTADDR/PGSERVICE/PGSERVICEFILE/PGOPTIONS
font refuser les connexions SQL ; les subprocess nettoient les variables PG.
Le passfile implicite est désactivé, le hostaddr est fixé au loopback.
Un PGPASSWORD ambiant sans mot de passe explicitement fourni par URL est
refusé. TLS/GSS encryption sont désactivés pour ce seul transport loopback
de recette, évitant le chargement implicite des fichiers de certificats ;
ce profil n'est pas adapté à un endpoint distant.
Connexion SQL : 10 s ; statement : 60 s ; lock SQL : 10 s ;
TOC/rendu SQL : 60 s ; pg_restore : 3600 s.
Ces limites ne constituent pas un délai global de backup ou un RTO qualifié.

## 4. Tests réellement exécutés

Hôte : **Windows, Python 3.13.7**. Aucun runtime Linux/Python 3.11 exécuté.
La grammaire Python 3.11 de 9 fichiers a été contrôlée sans import Linux.

Résultat final : **167 réussites, 13 ignorés, 0 échec**, durée 26,33 s.
Un avertissement de dépréciation préexistant Starlette/httpx est conservé.

| Suite | Réussis | Ignorés | Couverture / limite |
|---|---:|---:|---|
| `test_lifecycle_backup_lock.py` | 6 | 4 | Vrais processus Windows et Path context-manager ; flock/permissions POSIX non exécutés |
| `test_restore_pgvector.py` | 36 | 0 | TOC/SQL/roles/connexions : composants simulés, pas pg_restore réel |
| `test_restore_hardening.py` | 26 | 0 | Parcours et quota SQL simulés, y compris initialement ouvert et défaut de commit |
| `test_restore_hardening_postgres.py` | 0 | 3 | Opt-in désactivé ; aucune connexion tentée |
| `test_lifecycle_keys_restore.py` | 2 | 0 | Extraction de clés synthétiques |
| `test_lifecycle_key_permissions_v51.py` | 52 | 0 | Non-régression de politique d'archives ; pas accès POSIX root:app qualifié |
| `test_public_beta_snapshot.py` | 7 | 6 | Inventaires unitaires ; anciens tests Docker/PG non exécutés |
| `test_snapshot_backup_integrity.py` | 5 | 0 | Snapshots SQLite synthétiques et refus d'archives altérées |
| `test_lifecycle_lot29_bundle.py` | 28 | 0 | Non-régression stores/bundle synthétiques |
| `test_backup_offline_compose.py` | 5 | 0 | Construction d'isolation offline simulée ; aucun daemon contacté |

Commande finale : `python -m pytest -q -p no:cacheprovider --tb=short`
avec ces dix fichiers, un `--basetemp` neuf dans les artefacts de session
et `--junitxml` vers `files\hardening-test-results.xml`.
`DOCUMIND_HARDENING_POSTGRES_LAB` et `TEST_SNAPSHOT_COMPOSE` ont été retirés
de l'environnement du processus de test afin d'interdire ces intégrations.
Ce réglage sélectionne la recette locale ; il ne contourne aucun garde.

Historique des tentatives, sans les présenter comme des succès :

- Première exécution : 20 réussites, 4 ignorés, 64 erreurs de setup dues à
  un répertoire temporaire pytest inaccessible (WinError 5).
- Reprise sur répertoire neuf : 98 réussites, 4 ignorés, 6 échecs ; erreur
  de parenthésage d'un mock de lecture post-commit corrigée, attentes conservées.
- Exécutions intermédiaires : 112 réussites / 13 ignorés puis
  158 réussites / 13 ignorés, puis 166 / 13 avant le refus des credentials implicites.
- Suite finale ci-dessus : 167 / 13 / 0. Aucun résultat ignoré n'est crédité PASS.

Contrôles complémentaires : `--help` du CLI, grammaire 3.11, sceaux V5/V5.1,
et `git diff --check` avec reconnaissance des CRLF existants.
Le premier diff-check sans cette reconnaissance signalait les fins de ligne
préexistantes ; aucun reformatage global n'a été effectué.

## 5. Reprise de qualification sur Debian Hyper-V — non exécutée

1. Conserver V5.1 scellée et les preuves expérimentales comme références.
   Constituer une révision de développement distincte, avec les quatre modules
   tools nécessaires et leur fermeture d'imports ; vérifier SHA avant/après.
   Ne pas remplacer les modules backend de l'image scellée existante.
2. Confirmer matériellement l'isolation : aucune donnée/clé réelle, aucun
   montage/daemon/tunnel/route de production, réseau externe absent, aucune
   API attachée aux DB de recette. Consigner inventaire et autorisation.
3. Vérifier Python 3.11 Debian, fcntl, sqlite3, SQLAlchemy/Psycopg, tar et
   les binaires exacts PG 17.11/pgvector 0.8.0. Rejouer les tests du verrou
   avec concurrence POSIX réelle ; comparer aussi les cinq snapshots SQLite.
4. Utiliser un rôle de restore synthétique CREATEDB sans les privilèges
   refusés ; un rôle préparateur distinct, autorisé seulement pour la
   préparation explicitement demandée. Paquet serveur pgvector disponible.
   Base admin marquée et credentials synthétiques uniquement dans les URL
   d'environnement, jamais dans les arguments/logs ou le dépôt.
   Authentification de laboratoire synthétique, sans service/passfile,
   certificats ou identité GSS de production ; transport loopback non TLS
   uniquement dans la machine isolée.
5. Préparer un root absolu privé, propriétaire restaurateur, mode 0700,
   marqueur `.synthetic-only` de contenu exact
   `documind-isolated-restore-lab-v1` suivi d'un LF. Choisir chaque DB avec
   12 hex uniques ; aucune base préexistante ne sera adoptée par `_restore`.
6. Lancer les tests unitaires de développement sur Linux sans anciennes
   intégrations Docker Windows. Exiger `--require-no-skips` pour la sélection
   du verrou et des deux nouvelles suites unitaires de restore/pgvector.
7. Pour les **trois intégrations PostgreSQL de composants** seulement,
   renseigner `DOCUMIND_HARDENING_POSTGRES_LAB=isolated`,
   `DOCUMIND_RESTORE_LAB=isolated`, `DOCUMIND_HARDENING_EVIDENCE_ROOT`,
   `DOCUMIND_RESTORE_DATABASE_URL` et la URL distincte de préparation.
   Puis, dans le checkout de développement autorisé :

   ```text
   python -m pytest -q -p no:cacheprovider --require-no-skips tests/test_restore_hardening_postgres.py
   ```

   Ces tests créent uniquement des DB neuves synthétiques, vérifient quota
   initialement ouvert/fermé et un vrai dump vector restauré sans SUPERUSER.
   Ils conservent les DB et les preuves avec indication INCOMPLETE : aucun
   résultat de composant ne transforme ces ressources en copie réutilisable.
8. Pour le round-trip V5 complet, capturer réellement avec la chaîne autorisée,
   les cinq stores et deux clés synthétiques, jamais avec un faux manifeste
   de quiescence. Préparer une nouvelle image de laboratoire contenant le
   verrou corrigé, liée à cette révision : le module livré sur l'hôte ne
   corrige pas celui d'une image préexistante. Ne pas changer l'image scellée.
9. Sur cette capture vérifiée et une cible unique du root marqué, invoquer
   le CLI de développement avec `--prepare-pgvector-version 0.8.0`.
   Contrôler les deux listes TOC, les 23 tables **avant** fermeture, le quota
   **après** commit, documents, cinq stores, deux clés et latch. Aucun certificat
   de capture complète ne doit être créé en remplacement des contrôles réels.
10. Exercer espace insuffisant, corruption, timeout, quota absent, privilèges
    refusés et interruption. Conserver toutes les copies partielles ;
    nouvelle cible pour rejouer, nettoyage éventuel seulement par décision
    séparée sur ressources nommément identifiées.

Cette procédure ne modifie ni la release V5.1 du laboratoire ni la production.
Les tests PostgreSQL ajoutés ne constituent pas un runner des lots L1–L17
ni une preuve de reprise applicative.

## 6. Risques résiduels / refus maintenus

| Risque | Qualification encore nécessaire |
|---|---|
| flock Python 3.11 et effets physiques | Exécution POSIX native, concurrence, lock absent/occupé, WAL/SHM, temporaires, interruptions et espace |
| PostgreSQL et pgvector réels | Nouvelle séparation de rôles/TOC à tester sur dump 17.11 ; commentaires et SQL attendus volontairement stricts |
| Version source de pgvector | Pas authentifiable à partir du seul SQL CREATE EXTENSION rendu ; inventaire source indépendant requis |
| Dump et provenance | SHA/TOC/SQL sélectionné ne sont pas un audit de tout SQL du dump ni une signature d'origine ; source synthétique contrôlée indispensable |
| Quota partiel inaccessible | Fermeture non démontrable si DB/table/ligne absente ou service perdu ; copie failed/incomplete, aucune API ni réutilisation |
| Isolation externe | Loopback, marqueur et cluster_name ne prouvent pas l'absence de tunnel ou de réseau externe ; attestation d'inventaire séparée requise |
| Chemins lifecycle / ownership | Les trois divergences de paths restaurés et clés restaurateur 0400 restent à qualifier ; aucun mapping/chown silencieux ajouté |
| Chaîne Compose / image de capture | Couverture overrides, identité effective et image contenant le nouveau verrou restent non qualifiées |
| Restic, reprises et RPO/RTO | Récupération de l'ID exact, octets, restauration complète et reprise doivent être exercées ; aucun délai global de backup corrigé ici |
| Crash / filesystem | fsync du fichier et remplacement atomique ne prouvent pas toute la durabilité après panne d'alimentation ; marqueurs et partiels à inventorier |
| HMAC/fraîcheur / H0 | Lecteurs applicatifs et cinq magasins nécessaires ; provenance historique non résolue par ce durcissement |

**Verdict : NO-GO maintenu.** Le développement a passé la suite locale ciblée ;
la qualification Linux complète, une éventuelle sauvegarde réelle et toute
intervention de production nécessitent leurs preuves et autorisations distinctes.

## 7. Empreintes de la révision locale testée

SHA-256 des octets, fins de ligne comprises. Aucun manifeste de release
existante n'est régénéré.

| Fichier | SHA-256 |
|---|---|
| `backend\lifecycle_backup_lock.py` | `efca36c25a7ffb372edaee7120a57aa68b926da9801bada5bb41dc24753f6433` |
| `tools\restore_pgvector.py` | `4848d95793f86e27fa06f35036f2db49f7b14bc58cdb2e835a246ddb7aef5292` |
| `tools\validate_restore.py` | `92edaabbf1ca48f62687156c9f7e4c6d31629546be20ea1d26107a18d15357ff` |
| `tools\verify_snapshot.py` | `f7cead2c1fa8e623e3b6c52c81d584ac0addee4e7a0fba26846650d5681fae8e` |
| `tests\test_lifecycle_backup_lock.py` | `990206c685868ed036e8a004891c87418c9e46347f9815ca87d029695fabbfbb` |
| `tests\test_restore_pgvector.py` | `94f2514c265314454b3808aa2d6017b68cada0dd1bd36cae5c3c937e61eea3ea` |
| `tests\test_restore_hardening.py` | `5b16abbab6b4c6466a6db374b3cbaf2dd3223804daf85bfff547b74ab7d70afc` |
| `tests\test_restore_hardening_postgres.py` | `8a0c6927e81d6ec02a3528cb9140c0136cf55f1c05682b22b291e3c49142985b` |
| `tests\test_public_beta_snapshot.py` | `99cd6178467bed1cbde24b45a5b16cf2a661c09a878055238b0cd4acd6b098ae` |
