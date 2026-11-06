# Docnelo — Effacement standard de la bêta 10

## Verdict

Le chemin d'effacement des données actives est implémenté sur
`release/docnelo-public-beta-10-20261106`, à partir de
`a3d2adb54ebfdcec19647b907e245536494efd52`.
L'autorisation est une décision Linux root locale, jamais une décision HTTP,
un reçu synthétique ou une permission accordée à l'API.

**NO-GO pour la production et l'ouverture des inscriptions.** Le provisionnement
réel du VPS, l'identité de l'autorité administrative, la politique de conservation,
le traitement des sauvegardes/logs et la CI distante restent à valider.
Aucune intervention VPS, ouverture, migration de production, création de secret
de production, fusion historique ou publication d'image n'a été effectuée.
Le chantier VSS A/B n'est pas repris.

## Architecture et sélection Git

| Chemins | Rôle |
|---|---|
| `backend/erasure.py` | Réception durable, inventaire lié à la demande, décision root, exécution/reprise, vérification et tombstones |
| `backend/erasure_admin.py` | CLI locale root ; aucune commande bulk ni autorisation HTTP |
| `backend/config.py` | Quatre paramètres explicites, optionnels ensemble et sans autorité par défaut |
| `backend/api.py`, `backend/account_api.py` | Réception 202 après authentification, propriété et mot de passe pour le compte |
| `backend/main.py`, `backend/recovery_quarantine.py` | Contrôle avant les récupérations/workers, puis à chaque requête |
| `frontend/src/services/api.ts`, `components/Workspace.tsx`, `pages/Account.tsx` | Référence persistante et attente, jamais un message « supprimé » pour une réception |
| `frontend/server/app.mjs` | Ne détruit pas la session pour une demande de compte seulement reçue |
| `compose.erasure.yaml` | Overlay volontaire ; autorité montée en lecture seule dans l'API |
| `tests/test_standard_erasure.py` | Qualification Linux/root/API non-root/PostgreSQL isolée |
| `frontend/src/test/app.test.tsx`, `frontend/server/app.test.mjs` | Non-régression des messages et du cookie sur réception 202 |
| `tests/test_deployment.py` | Assertion héritée alignée sur le plafond 10 déjà présent dans le candidat ; mode disabled inchangé |
| `.github/workflows/ci.yml` | Groupe obligatoire Linux/PostgreSQL avec zéro saut, image isolée et API réellement non-root |

Les chemins frontend abrégés dans le tableau sont sous `frontend/src`.
Aucune migration supplémentaire : le schéma 0008 reste requis.
La base du candidat comportait déjà une assertion de test attendant un plafond 0,
alors que son modèle de production indiquait 10 : seule cette attente a été corrigée.
Les sources du dépôt historique et les anciens livrables/worktrees sont conservés.

### Séparation des responsabilités

- **API non-root** : identifie le compte, vérifie son accès et reçoit un JSON privé,
  fsync fichier/répertoire, avec référence déterministe par installation et cible.
  Elle ne purge rien, ne désactive pas le compte et ne possède aucune autorité root.
- **Autorité root** : fichiers root non modifiables par l'API, distincts des
  documents, demandes et registres lifecycle. Un verrou système sérialise les
  opérations administratives. UUID d'installation et UID applicatif doivent
  correspondre aux en-têtes explicitement initialisés.
- **Exécution** : uniquement sous quarantaine root, inscriptions désactivées et
  porte SQL fermée, sans autre client PostgreSQL connecté à la base concernée.
  L'exploitante doit effectivement arrêter tous les producteurs ; le contrôle des
  connexions n'est pas une preuve d'arrêt d'un processus qui ne se connecte pas encore.
- **Vérification** : invocation CLI distincte, nouvelle session PostgreSQL,
  données/dépendances absentes et fichiers absents, puis reçu root durable.
  L'indépendance est celle de l'exécution et de la connexion ; ce n'est pas une
  deuxième autorité humaine ou une attestation externe.

Les demandes ne contiennent ni e-mail, ni mot de passe, ni texte documentaire.
Le journal contient des UUID, empreintes de lignes/fichiers, métadonnées et décisions
de conservation : ce sont des données de preuve **pseudonymisées, pas anonymes**.

### États et reprise

`requested` → `planned` → `authorized` → `executing` → `files_pending`
→ `verification_pending` → `active_verified`.

Une exception conserve `failed` lorsque le journal reste inscriptible ; un SIGKILL
laisse le dernier checkpoint fsync, donc une attente. Une panne du stockage du
journal ne peut pas garantir l'écriture d'un nouveau statut : erreur de commande,
quarantaine conservée, aucun succès à annoncer.

Le plan capture les clés primaires et empreintes des données, les fichiers
(nom canonique, taille, SHA-256, inode/device), les dépendances et le compteur.
L'autorisation est liée à son empreinte. Les gels de conservation existants restent
vérifiés, sous leur fence, jusqu'à la fin des effets.

Les suppressions utilisent les objets ORM, dans l'ordre des dépendances et une
transaction ; aucune suppression SQL brute d'exploitation n'est proposée.
Le budget global et le compteur cumulatif public sont conservés. Le fence SQL
ne crée jamais de workspace : un compte supprimé n'est pas recréé par la reprise.

Un COMMIT sans accusé certain invalide la connexion et conserve les fichiers.
La reprise détermine sur une nouvelle transaction si le plan original existe encore
ou s'il est entièrement absent. Un état SQL partiel ou modifié est refusé pour revue.
L'unlink exige l'identité originale du fichier ; le répertoire est fsync, y compris
sur reprise après un unlink déjà effectué.

`execute` ne confirme jamais l'effacement vérifié. Seul `verify` peut retourner
`active_erasure_verified=true`. `completed=false` reste toujours présent : il
n'existe pas de confirmation automatique d'effacement de toutes les copies.
`status` montre l'état historique, avec vérification à refaire, pas une nouvelle preuve.
Une autorisation jamais exécutée ne suffit pas pour `verify`.

## Protocole administratif exact

### Prérequis — ne pas les créer implicitement en production

Après inventaire et autorisation d'intervention seulement :

1. Image de release revue, PostgreSQL 0008, volumes et réseau interne réellement
   identifiés ; aucun nom de volume ou réseau ci-dessous n'est à deviner.
2. Autorité root hors des volumes applicatifs restaurables, répertoire root 0755,
   ancêtres root sûrs ; lecture seule dans l'API, lecture/écriture dans le contrôleur.
3. Répertoire des demandes appartenant à l'UID réel de l'API, mode 0700,
   et documents mode 0600 sous stockage applicatif 0700.
4. Latch root existant, non modifiable par l'API, et ses ancêtres/montages vérifiés.
5. Registres lifecycle, confirmations, holds et clé HMAC existants, correctement
   provisionnés sous UID applicatif, avec répertoires séparés. Le nouveau moteur
   ne les initialise pas et ne génère pas cette clé.
6. UUID d'installation explicitement approuvé, UID non nul vérifié sur l'image,
   décision de conservation et preuve privée d'identité détenues par root.
   Politique et preuve : fichiers root 0600, ancêtres sûrs, hors accès API.
7. Journal root conservé indépendamment des sauvegardes/restaurations applicatives,
   avec copie opérateur vérifiable et procédure de récupération à jour.

Pour l'API, ajouter volontairement `-f compose.erasure.yaml` à la commande Compose
de production revue et fournir :

```text
ERASURE_AUTHORITY_HOST_DIR=<répertoire root existant et indépendant>
ERASURE_REQUESTS_HOST_DIR=<répertoire privé applicatif existant>
ERASURE_INSTANCE_ID=<UUID approuvé, jamais généré au démarrage>
ERASURE_APPLICATION_UID=<UID non-root vérifié>
```

L'overlay définit les chemins internes `/run/docnelo-erasure/authority` et
`/run/docnelo-erasure/requests`. Sans ces quatre paramètres, conserver leur absence
complète, pas des variables vides : l'ancien refus strict reste actif.
Les chemins `LIFECYCLE_*_PATH` approuvés doivent être les mêmes pour l'API et le
contrôleur. Conserver :

```text
APPLICATION_PROFILE=standard
REGISTRATION_MODE=disabled
PUBLIC_REGISTRATION_LIMIT=10
PUBLIC_REGISTRATION_REQUIRES_APPROVAL=true
PUBLIC_REGISTRATION_USE_LIFECYCLE_RECEIPTS=false
LIFECYCLE_DURABLE_RECEIPTS_REQUIRED=true
LIFECYCLE_SYNTHETIC_MUTATIONS_ENABLED=false
AI_ENABLED=false
OWNER_DEMO_ENABLED=false
LEGACY_API_ENABLED=false
API_KEYS={}
```

### Préparer chaque opération

1. Conserver la référence 202 reçue. Une erreur 503 n'est pas un accusé de réception.
   Un arrêt avant l'accusé peut laisser une publication temporaire incomplète :
   revoir les permissions/liens et le journal sous maintenance, ne rien purger
   automatiquement. Les demandes répétées valides retrouvent la même référence.
2. Vérifier l'identité par le canal administratif approprié, les UUID compte/owner,
   le périmètre et les obligations de conservation. Conserver la preuve root privée.
3. Faire fermer la porte SQL par la procédure existante
   `python -m backend.account_admin public-registration close --execute`,
   après validation opérateur. Conserver `REGISTRATION_MODE=disabled`.
4. Mettre le latch root en quarantaine de manière persistante ; arrêter le web,
   l'API et tous les producteurs, attendre leur arrêt, fermer les sessions SQL
   d'inventaire. La base reste démarrée. Ne jamais compter sur un simple écran
   de maintenance du frontend.
5. Attention au bind d'un fichier : un remplacement atomique côté hôte peut laisser
   un conteneur sur l'ancien inode. Vérifier la valeur réellement montée et recréer
   le conteneur si nécessaire. Une écriture sur le fichier existant doit être fsync ;
   tout état incomplet/invalide reste bloquant.

### Contrôleur root ponctuel — commandes Linux, non exécutées sur le VPS

Les variables sont issues de l'inventaire et du fichier d'environnement privé
existants, jamais de valeurs de démonstration. La fonction suivante n'est pas un
service API ; elle ne publie aucun port et ne monte aucun socket Docker :

```sh
admin() {
  docker run --rm --user 0:0 --read-only --cap-drop ALL \
    --cap-add SETUID --cap-add DAC_OVERRIDE --security-opt no-new-privileges \
    --network "$DATA_NETWORK" --env-file "$PRODUCTION_ENV_FILE" \
    --env DATABASE_URL --env REGISTRATION_MODE=disabled \
    --env APPLICATION_PROFILE=standard --env AI_ENABLED=false \
    --env OWNER_DEMO_ENABLED=false --env LEGACY_API_ENABLED=false --env API_KEYS='{}' \
    --env LIFECYCLE_DURABLE_RECEIPTS_REQUIRED=true \
    --env LIFECYCLE_SYNTHETIC_MUTATIONS_ENABLED=false \
    --env STORAGE_DIR=/app/var/documents \
    --env RECOVERY_STATE_PATH=/run/documind/recovery-state.json \
    --env LIFECYCLE_BACKUP_LOCK_PATH=/app/lifecycle/.backup.lock \
    --env ERASURE_AUTHORITY_DIR=/run/docnelo-erasure/authority \
    --env ERASURE_REQUESTS_DIR=/run/docnelo-erasure/requests \
    --env ERASURE_INSTANCE_ID --env ERASURE_APPLICATION_UID \
    --mount "type=volume,source=$DOCUMENTS_VOLUME,target=/app/var" \
    --mount "type=volume,source=$LIFECYCLE_VOLUME,target=/app/lifecycle" \
    --mount "type=bind,source=$RECOVERY_CONTROL_FILE,target=/run/documind/recovery-state.json,readonly" \
    --mount "type=bind,source=$ERASURE_AUTHORITY_HOST_DIR,target=/run/docnelo-erasure/authority" \
    --mount "type=bind,source=$ERASURE_REQUESTS_HOST_DIR,target=/run/docnelo-erasure/requests" \
    --mount "type=bind,source=$ERASURE_REVIEW_HOST_DIR,target=/run/erasure-review,readonly" \
    --tmpfs /tmp:rw,noexec,nosuid,size=64m,mode=1777 \
    "$BACKEND_IMAGE" python -m backend.erasure_admin "$@"
}
```

`BACKEND_IMAGE` doit être le digest de release autorisé, pas le tag local de test.
`DATABASE_URL` doit être exporté depuis les secrets existants, sans l'afficher.
Le contrôleur seul peut changer temporairement son euid vers l'UID applicatif pour
les magasins lifecycle ; le processus API n'a ni cette capacité ni UID root sauvé.
Le bind du journal reste impérativement en lecture seule dans le service API.
Valider ce montage sur la préproduction Linux avant le VPS.

Première initialisation explicite, une fois seulement sous quarantaine :

```sh
admin init
```

Cette commande n'initialise que les deux en-têtes d'installation dans les
répertoires déjà provisionnés ; elle peut reprendre une initialisation identique
interrompue, mais refuse une autre instance. Aucun secret n'est créé.

Pour un compte déjà désactivé, sans contourner le refus de connexion :

```sh
admin request-account "$USER_UUID"
```

Conserver son `operation_id` comme `OPERATION_UUID`. Pour toute demande :

```sh
admin plan "$OPERATION_UUID"
admin status "$OPERATION_UUID"
# Examiner le plan root, les UUID et empreintes, les holds et les preuves privées.
admin authorize "$OPERATION_UUID" --confirm "$OPERATION_UUID" \
  --policy /run/erasure-review/policy.json \
  --identity-evidence /run/erasure-review/identity-review
admin execute "$OPERATION_UUID" --confirm "$OPERATION_UUID"
# Nouvelle invocation, nouveau processus et nouvelle connexion :
admin verify "$OPERATION_UUID"
```

La politique attend exactement les champs suivants. **Modèle non exécutable :
les durées ne sont pas choisies par le logiciel** :

```json
{
  "version": 1,
  "policy_id": "<UUID de la décision réelle>",
  "approved_by": "<UUID du responsable réellement identifié>",
  "approved_at": "<date ISO avec fuseau de la validation réelle>",
  "owner_accounting": "erase",
  "backup_retention_days": "<entier approuvé entre 1 et 3650>",
  "log_retention_days": "<entier approuvé entre 1 et 3650>",
  "receipt_retention": "until_restore_sources_expire"
}
```

`owner_accounting=erase` exige une décision réelle autorisant ce traitement.
Si certaines données doivent légalement être conservées, **ne pas fournir une
fausse décision pour débloquer** : garder la quarantaine et traiter le périmètre
juridique avec l'exploitante. Ce moteur minimal ne réalise pas un archivage légal
sélectif. Un gel actif ou à revoir n'est pas levé par cette procédure.

En échec/interruption : conserver maintenance et preuves, consulter `status`,
résoudre la cause sans modifier le plan autorisé, répéter `execute` avec la même
confirmation puis `verify`. Un SQL partiellement restauré, une source remplacée,
un schéma inconnu, une donnée non attribuée ou un compteur incohérent nécessitent
une revue, pas une suppression forcée. Une opération vérifiée ne se rejoue pas
aveuglément.

Ne relever la quarantaine qu'après vérification fraîche de **toutes** les opérations
autorisées/en attente, revue du journal et des copies à conserver, puis redémarrage
contrôlé et santé HTTPS. Le redémarrage perd les sessions mémoire ; les autres
utilisateurs doivent se reconnecter. Les inscriptions restent fermées, y compris
après cette remise en service. Aucun outil ici ne rétablit automatiquement `ready`.

## Sauvegardes, restauration et conservation

- `active_verified` établit l'absence des objets du périmètre dans la base active
  et du fichier original/résidus connus du stockage actif. Les dépendances
  documentaires sont contrôlées aussi par identifiant de document, et les comptes
  par owner ; les tokens e-mail orphelins sont contrôlés par empreinte d'adresse.
  Un inventaire de stockage complet est exigé en maintenance et au redémarrage.
- Ce n'est **pas** un effacement forensique des blocs SSD, des pages PostgreSQL MVCC,
  WAL, snapshots, réplicas, exports, caches externes ou sauvegardes. Aucun VACUUM
  destructif, écrasement de disque, purge de sauvegarde ou VSS n'est lancé.
- Les durées approuvées sont enregistrées, pas appliquées par un ordonnanceur
  nouveau. L'exploitante doit inventorier les copies, responsables, échéances,
  gels et preuves d'expiration/destruction. Tant que ces preuves manquent,
  `backups=retention_pending`, `logs=retention_pending`, `completed=false`.
  Les envois SMTP et leurs journaux, s'ils contiennent des données personnelles,
  appartiennent également à cette revue.
- Conserver les tombstones, autorisations et preuves minimales tant qu'une source
  de restauration peut réintroduire les données, puis décider leur fin de
  conservation légalement. La preuve privée d'identité doit avoir sa propre durée
  justifiée ; ne pas conserver une pièce complète inutilement.
- Restaurer uniquement en quarantaine, sans API/workers ni inscriptions.
  Ne jamais remplacer le journal root indépendant par la version d'une ancienne
  sauvegarde applicative. Rejouer la revue de chaque tombstone avec `verify`
  avant toute remise en service. Les identités/fichiers restaurés et un compteur
  sous le plancher enregistré bloquent l'API avant les récupérations et aux requêtes.
- Une restauration partielle ou dont les données diffèrent du plan autorisé reste
  bloquée ; elle nécessite une nouvelle décision de réconciliation contrôlée.
  Cette version ne fabrique pas une autorisation de réécriture du plan.
- La perte ou le rollback conjoint de **toute la machine et de l'autorité root**
  n'est pas détectable sans preuve indépendante plus récente. Si cette preuve est
  indisponible, maintenir le NO-GO ; ne pas réinitialiser une autorité vide pour
  remettre en service. La copie opérateur du journal doit être récupérable et vérifiée.
- Une réinscription avec l'adresse d'un compte effacé peut recréer des tokens
  appartenant au périmètre protégé et bloquer la reprise : requiert revue opérateur,
  pas une désactivation du contrôle. Le quota public n'est jamais recyclé.

## Qualification

Uniquement données fictives, PostgreSQL 17/pgvector jetable sans port hôte publié,
stockage tmpfs et images locales ; aucune donnée VPS.
Le contrôleur tourne réellement root. Chaque acteur API abandonne irréversiblement
UID réel/effectif/sauvé vers 65534 et prouve que `seteuid(0)` est refusé.
La vérification CLI est exécutée dans un nouveau processus.

| Groupe | Résultat |
|---|---|
| Effacement Linux/PostgreSQL, image immuable read-only, zéro saut | 30 réussis |
| Bêta PostgreSQL : approbation, comptes, authentification, quota/concurrence, abus et audit | 201 réussis, zéro saut |
| Durabilité/lifecycle/quarantaine/déploiement portables | 148 réussis ; 16 sauts PostgreSQL/POSIX attendus dans cette passe Windows |
| UI complète | 67 réussis |
| BFF | 54 réussis |
| TypeScript et Vite | Réussis |
| Images backend/proofs et refus root du runtime non-root | Réussis |
| Composition production + overlay, avec valeurs fictives, sans démarrage | Valide ; mode fermé conservé |
| CI distante et installation VPS | Non exécutées |

Images locales finales, toutes deux `USER app` :

```text
docnelo-erasure-local:20261106
sha256:af2c4b3382c24fb12098c1f8e4815f2bfc11e73c9f987fc3091fcdb4be4a4071
docnelo-erasure-proofs-local:20261106
sha256:115389de27a7260b13c026988438fcda9e8db10907a10793b93d58cfee095454
```

Les cas natifs couvrent documents/comptes et dérivés enregistrés
(pages/chunks, analyses, embeddings, jobs, résumés, interactions, RAG, réservations
et usages), compte désactivé, demandes répétées, mauvais mot de passe/propriété,
refus root/confirmation/politique, holds, autre client SQL, source modifiée,
COMMIT incertain, SIGKILL avant/après COMMIT et après unlink, échecs de nettoyage,
vérification distincte et absence de workspace recréé.
Ils couvrent aussi SQL/fichier/compteur restaurés, token orphelin avec une autre clé,
copie renommée non attribuée, réintroduction pendant que l'API tourne, absence
de récupération avant les tombstones, et refus de colonnes/schémas/vues
matérialisées/triggers/clés étrangères non pris en charge.

La commande obligatoire de CI est :

```sh
python -m pytest -q -p no:cacheprovider --require-no-skips \
  --basetemp=/tmp/erasure-tests tests/test_standard_erasure.py
```

Elle s'exécute dans l'image `isolation-tests`, root, filesystem read-only,
tmpfs `/tmp`, réseau du seul PostgreSQL jetable et
`TEST_ERASURE_POSTGRES_DSN=postgresql://erasure_test:isolated-test-only@127.0.0.1:5432/postgres`.
Chaque cas crée puis détruit sa propre base `erasure_case_<UUID>` sur ce serveur
de test explicitement identifié ; ce rôle de test n'est jamais un rôle de production.
Les preuves locales de build et de la passe native sont conservées sous `var/`
ignoré du worktree de release, pas livrées comme données applicatives.
La mise en forme finale normalise les nouveaux fichiers en LF ; les AST Python
avant/après sont identiques. Aucun changement fonctionnel ne suit la passe native.

## Checklist GO / NO-GO

- [x] Autorité locale root distincte de l'API ; aucune auto-autorisation synthétique.
- [x] Réception persistante et messages d'attente sans faux succès.
- [x] Maintenance, gate SQL, holds et durabilité conservés.
- [x] Reprise contrôlée et vérification physique du stockage actif dans un processus distinct.
- [x] Contrôles de réintroduction avant reprise et pendant le service.
- [x] Tests Linux/PostgreSQL isolés, UI/BFF et régressions pertinentes.
- [ ] CI distante réussie sur le commit livré, images publiées/revues par digest.
- [ ] Autorité, UID, chemins et montages réels validés en préproduction puis autorisés sur VPS.
- [ ] Politique légale réelle approuvée, absence/revue des gels et conservation comptable décidée.
- [ ] Inventaire des sauvegardes/logs/copies, échéances et preuve indépendante du journal validés.
- [ ] Répétition opérateur de restauration/quarantaine avec la stack réelle, SMTP/HTTPS validés.
- [ ] Autorisation explicite d'intervention puis, séparément, d'ouverture des inscriptions.

**Le code ne transforme pas ces prérequis manquants en autorisation :
la production reste NO-GO et `REGISTRATION_MODE=disabled`.**
