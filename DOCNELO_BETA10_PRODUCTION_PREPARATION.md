# Docnelo — Préparation opérationnelle de la bêta 10

Date de préparation : 6 novembre 2026.
Référence : `DOCNELO_BETA10_ERASURE_IMPLEMENTATION.md`.

## Décision et périmètre

**GO pour soumettre la branche à revue et, après accord de publication, exécuter
sa CI de qualification. NO-GO pour le déploiement et l'ouverture.**
Le moteur standard est qualifié localement ; cela ne qualifie ni l'installation
existante, ni ses autorités, ni sa conservation, ni une image publiée.

Travail réalisé : lectures Git locales, métadonnées GitHub non secrètes et lecture
des sources/configurations livrées ; rédaction de ce rapport uniquement.
**Aucune connexion VPS, commande de production, publication de branche, CI
déclenchée, fusion, publication d'image ou ouverture n'a été effectuée.**
Aucun secret ni autorité de production n'est créé. Aucun travail VSS A/B.

Les commandes VPS ci-dessous sont du **Bash Linux**, pas du PowerShell Windows.
Elles sont préparées, non exécutées. Les variables inconnues sont à renseigner
par l'opérateur depuis l'inventaire privé ; leur nom n'est pas une valeur par défaut.
Ne pas copier les sorties privées, identités utilisateur ou fichiers de configuration
réels dans Git, une issue ou un journal de CI.

| Marque | Effet et autorisation |
|---|---|
| **L-local / L-GitHub** | Lecture locale ou de métadonnées GitHub ; réalisée pour ce rapport |
| **L-VPS** | Diagnostic métier en lecture seule ; nécessite encore une autorisation d'accès VPS |
| **M-GitHub** | Push, lancement CI, intégration/publication ; accord explicite avant exécution |
| **M-VPS** | Toute modification de configuration, conteneur, répertoire, schéma, compte ou latch ; accord distinct |
| **M-ouverture** | Réouverture SQL ; dernière autorisation, indépendante du déploiement |

Une lecture peut laisser une trace d'accès/statistique réseau. « Lecture seule »
ne signifie pas absence de journaux techniques. Un envoi d'e-mail, même de test,
une inscription ou une suppression est une action mutante.

## 1. État Git et CI vérifié

| Élément | Observation |
|---|---|
| Worktree | `deliveries\docnelo-public-beta-release-20261106\source` |
| Branche | `release/docnelo-public-beta-10-20261106` |
| Commit exact du moteur et de ses tests | `fd86d4ebe878033dbf35050edfc938904aa20bfa` |
| Parent du moteur | `a3d2adb54ebfdcec19647b907e245536494efd52` |
| État au début de cette préparation | Worktree propre, aucun fichier non suivi non ignoré |
| Fichiers nécessaires | Moteur, CLI, tests, migration 0008, Dockerfiles, lock frontend, assets publics, Compose et outils de livraison suivis |
| Branche distante | Absente lors de la lecture des références GitHub |
| CI distante de cette branche | Aucune exécution trouvée |
| Workflow CI | `ci.yml`, actif, ID `389532488` |
| `main` distant observé | `9b26006a2f8cfa3185580de66c671d419ad24dd6` ; aucune compatibilité de fusion déduite |
| Environnement GitHub `production` | Règles `branch_policy` et `required_reviewers`, reviewers obligatoires configurés ; aucune approbation d'intervention déduite |

Le présent document peut être un commit documentaire descendant de `fd86d4e`.
La CI doit alors viser le **HEAD complet de la branche publiée**, pas seulement
réutiliser le SHA du moteur ou une ancienne exécution verte.
Le dépôt historique, ses modifications locales et ses branches ne sont pas nettoyés
ou fusionnés par cette préparation.

### Couverture du workflow livré

| Contrôle | Présence vérifiée dans `ci.yml` |
|---|---|
| Effacement | Image `isolation-tests`, root contrôleur, acteurs API irréversiblement non-root, PostgreSQL isolé, `test_standard_erasure.py`, `--require-no-skips` |
| Bêta serveur | Approbation, concurrence PostgreSQL au dernier quota, historique et authentification ; suite PostgreSQL complète |
| Parcours réel de test | Navigateur, HTTPS et SMTP locaux, `test_public_beta_email_e2e.py`, zéro saut requis |
| Frontend | `npm run test:ui`, TypeScript et build Vite |
| BFF | `npm run test:bff`, proxy, sessions, CSRF et audit |
| Sécurité existante | Confinement Linux Landlock/seccomp, durabilité, permissions root/non-root, historique de release, tests Windows |
| Publication | Job `publish` après les trois jobs, seulement hors PR **et sur `refs/heads/main`** |
| Déploiement | Workflow séparé `deploy.yml`, manuel, job limité à `main`, environnement protégé et contrôles SHA/attestation |

Les résultats locaux déjà consignés sont 30 tests natifs d'effacement, 201 tests
bêta PostgreSQL, 148 régressions portables (16 sauts attendus), 67 tests UI et
54 tests BFF. Ils ne sont pas de nouveaux résultats de CI distante.
Le workflow complet distant reste à exécuter ; son succès n'est pas présumé.

### Publication de branche et CI — M-GitHub, après accord seulement

Depuis le worktree de livraison, PowerShell :

```powershell
$repo = 'AdelineMeistertzheim403/DocuMind_AI'
$branch = 'release/docnelo-public-beta-10-20261106'
if ((git branch --show-current) -ne $branch) { throw 'Mauvais worktree' }
if (git status --porcelain) { throw 'Worktree non propre' }
git merge-base --is-ancestor fd86d4ebe878033dbf35050edfc938904aa20bfa HEAD
if ($LASTEXITCODE -ne 0) { throw 'Moteur qualifie absent de HEAD' }
$sha = git rev-parse HEAD
git push --set-upstream origin "HEAD:refs/heads/$branch"
if ($LASTEXITCODE -ne 0) { throw 'Publication refusee ; ne pas forcer ni fusionner' }
gh workflow run ci.yml --repo $repo --ref $branch
if ($LASTEXITCODE -ne 0) { throw 'CI non declenchee' }
```

Le push de cette branche ne déclenche pas automatiquement `ci.yml` : son trigger
`push` vise seulement `main`. Le dispatch explicite ci-dessus cible la branche,
donc `publish` doit être **skipped**. Les images construites dans les jobs de test
ne sont pas poussées au registre.

Lecture des résultats après le lancement autorisé :

```powershell
gh run list --repo $repo --workflow ci.yml --branch $branch --commit $sha --limit 5 --json databaseId,headSha,status,conclusion,url
# Renseigner $runId depuis la ligne correspondant exactement a $sha.
if (-not $runId) { throw 'Identifiant CI explicite requis' }
gh run watch $runId --repo $repo --exit-status
if ($LASTEXITCODE -ne 0) { throw 'Qualification CI en echec' }
$run = gh run view $runId --repo $repo --json headSha,status,conclusion,jobs | ConvertFrom-Json
if ($run.headSha -ne $sha -or $run.status -ne 'completed' -or $run.conclusion -ne 'success') { throw 'Mauvaise execution ou CI incomplete' }
$run.jobs | Select-Object name,conclusion
```

Exiger les jobs Python, Windows et frontend réussis, les groupes obligatoires sans
saut et `publish` absent de l'exécution effective ou skipped.
**Ne pas lancer ce workflow sur `main` pour « seulement tester » : une CI verte
sur `main` autorise automatiquement sa publication d'images.**
Une future intégration `main` nécessite donc une validation couvrant aussi cette
publication, puis une nouvelle CI sur le SHA intégré. Aucune fusion automatique.
La CI de branche ne produit pas le bundle de release publiable du job `publish`.

## 2. Inventaire de l'installation `/srv/documind-ai` — L-VPS préparé

### 2.1 Identifier sans recréer la stack

Après autorisation d'accès, dans un shell opérateur privé :

```bash
ROOT=/srv/documind-ai
cd -- "$ROOT"
pwd -P
ls -ld -- . current releases .env.production
readlink -- "$ROOT/current"
docker version --format '{{.Server.Version}}'
docker compose version
docker info --format '{{json .SecurityOptions}}'
uname -r
df -h -- "$ROOT"
docker compose ls --all --format json
docker ps -a --format '{{.ID}} {{.Names}} {{.Image}} {{.Status}}'
```

L'absence de `current` ou d'autres chemins est une observation, pas une permission
de les créer. Déterminer le projet et les IDs de **cette** installation avant de
renseigner `PROJECT`, `API_CONTAINER`, `DB_CONTAINER` et `WEB_CONTAINER`.
Les libellés de service peuvent différer : ne pas adopter silencieusement
`documind-prod`, créer un second projet ou supposer les noms de volumes Compose.

Pour chacun des trois IDs identifiés :

```bash
: "${API_CONTAINER:?}" "${DB_CONTAINER:?}" "${WEB_CONTAINER:?}"
for c in "$API_CONTAINER" "$DB_CONTAINER" "$WEB_CONTAINER"; do
  docker inspect --format 'project={{index .Config.Labels "com.docker.compose.project"}} service={{index .Config.Labels "com.docker.compose.service"}} directory={{index .Config.Labels "com.docker.compose.project.working_dir"}} files={{index .Config.Labels "com.docker.compose.project.config_files"}}' "$c"
  docker inspect --format 'image_ref={{.Config.Image}} image_id={{.Image}} user={{.Config.User}} state={{.State.Status}} readonly={{.HostConfig.ReadonlyRootfs}} privileged={{.HostConfig.Privileged}} cap_add={{json .HostConfig.CapAdd}} cap_drop={{json .HostConfig.CapDrop}} security={{json .HostConfig.SecurityOpt}}' "$c"
  docker inspect --format '{{range .Mounts}}{{println .Type .Name .Source .Destination .RW}}{{end}}' "$c"
  docker inspect --format '{{range $name,$net := .NetworkSettings.Networks}}{{println $name $net.IPAddress}}{{end}}' "$c"
  image_id=$(docker inspect --format '{{.Image}}' "$c") || exit 1
  docker image inspect --format 'id={{.Id}} digests={{json .RepoDigests}} revision={{index .Config.Labels "org.opencontainers.image.revision"}} profile={{index .Config.Labels "io.documind.security-profile"}}' "$image_id"
done
docker port "$API_CONTAINER"
docker port "$DB_CONTAINER"
docker top "$API_CONTAINER" -eo pid,uid,comm
```

Conserver en privé la correspondance projet/services, références, IDs locaux,
`RepoDigests`, révision et réseaux. Un ID local sans `RepoDigest` n'est pas un digest
de distribution attesté. Ne jamais utiliser un tag mouvant comme preuve de release.
Ne pas imprimer les commandes de processus, les healthcheck logs ou toutes les labels.

À relever depuis les montages : volume ou bind PostgreSQL et son chemin, stockage
documentaire réel, lifecycle, latch, éventuel journal root et demandes.
Les chemins du candidat sont `/app/var`, `/app/lifecycle` et
`/run/documind/recovery-state.json` ; ce sont des attentes, pas des faits VPS.
Contrôler les métadonnées des seuls volumes identifiés :

```bash
: "${DB_VOLUME:?}" "${DOCUMENTS_VOLUME:?}"
docker volume inspect --format '{{.Name}} {{.Driver}} {{.Mountpoint}}' "$DB_VOLUME" "$DOCUMENTS_VOLUME"
```

Si l'installation utilise des binds, ne pas inventer des volumes à leur place.
Pas de `compose up`, `pull`, `restart`, `down`, `prune`, réparation de permissions
ou adoption de stack dans cet inventaire.

### 2.2 Paramètres API sans révéler de secret

Ce diagnostic lit uniquement l'environnement du processus exécuté, pas les defaults
du code ni un éventuel fichier `.env` chargé par l'application. Un champ absent est
**inconnu**, pas implicitement sûr. Compléter par les options HTTP et la révision
exacte de l'image ; ne pas démarrer l'application pour lire sa configuration.

```bash
docker exec -i "$API_CONTAINER" python - <<'PY'
import json, os, re
paths = ('STORAGE_DIR', 'RECOVERY_STATE_PATH', 'LIFECYCLE_DATA_ROOT',
         'LIFECYCLE_BACKUP_LOCK_PATH', 'LIFECYCLE_REGISTRY_PATH',
         'LIFECYCLE_CONFIRMATION_PATH', 'LIFECYCLE_AUTHENTICATED_CONFIRMATION_PATH',
         'LIFECYCLE_AUTHENTICATION_KEY_PATH', 'LIFECYCLE_HOLDS_PATH',
         'LIFECYCLE_ADMISSION_ANCHOR_PATH', 'LIFECYCLE_ADMISSION_KEY_PATH',
         'ERASURE_AUTHORITY_DIR', 'ERASURE_REQUESTS_DIR')
flags = ('AI_ENABLED', 'OWNER_DEMO_ENABLED', 'LEGACY_API_ENABLED',
         'PUBLIC_REGISTRATION_REQUIRES_APPROVAL', 'PUBLIC_REGISTRATION_USE_LIFECYCLE_RECEIPTS',
         'LIFECYCLE_DURABLE_RECEIPTS_REQUIRED', 'LIFECYCLE_SYNTHETIC_MUTATIONS_ENABLED',
         'PUBLIC_LEGAL_READY', 'SMTP_STARTTLS')
numbers = ('PUBLIC_REGISTRATION_LIMIT', 'SMTP_PORT', 'ERASURE_APPLICATION_UID')
enums = {'REGISTRATION_MODE': ('disabled', 'invite', 'public'),
         'APPLICATION_PROFILE': ('standard', 'lite'),
         'EXTRACTION_MODE': ('sandbox', 'development')}
result = {}
for name in paths + flags + numbers + tuple(enums):
    value = os.environ.get(name)
    if value is None:
        result[name] = 'ABSENT: default image a verifier'
    elif name in paths:
        result[name] = value if re.fullmatch(r'/[A-Za-z0-9_./-]+', value) else 'INVALIDE/EXPURGE'
    elif name in flags:
        result[name] = value.lower() if value.lower() in ('true', 'false', '1', '0') else 'INVALIDE/EXPURGE'
    elif name in numbers:
        result[name] = int(value) if re.fullmatch(r'[0-9]{1,10}', value) else 'INVALIDE/EXPURGE'
    else:
        result[name] = value if value in enums[name] else 'INVALIDE/EXPURGE'
for name in ('BFF_SERVICE_KEY', 'SMTP_HOST', 'SMTP_FROM', 'SMTP_USERNAME', 'SMTP_PASSWORD',
             'ERASURE_INSTANCE_ID', 'PUBLIC_OPERATOR_NAME', 'PUBLIC_CONTACT_EMAIL',
             'PUBLIC_LEGAL_NOTICE_URL', 'PUBLIC_PRIVACY_URL', 'PUBLIC_TERMS_URL', 'PUBLIC_TERMS_VERSION'):
    result[name + '_PRESENT'] = bool(os.environ.get(name))
result['process_uids'] = os.getresuid()
print(json.dumps(result, sort_keys=True))
PY
```

Ne pas remplacer cela par `env`, `printenv`, `docker inspect` intégral,
`compose config` intégral ou `config --environment`. Ne jamais afficher
`DATABASE_URL`, mots de passe, clés HMAC/BFF/SMTP/SSH, cookies ou jetons.
Une présence de secret ne prouve pas sa validité. `API_KEYS` ne doit pas être
imprimé : sa vacuité se vérifie dans la revue privée de configuration.

### 2.3 PostgreSQL : schéma, compteur et comptes agrégés

`DB_USER` et `DB_NAME` doivent être confirmés depuis la configuration existante,
pas déduits d'un exemple. Utiliser le socket du conteneur ; aucun mot de passe
en argument ou dans la sortie. Si l'accès est refusé, arrêter le diagnostic,
pas assouplir l'authentification.

```bash
ro_sql() {
  : "${DB_CONTAINER:?}" "${DB_USER:?}" "${DB_NAME:?}"
  docker exec -i \
    --env 'PGOPTIONS=-c default_transaction_read_only=on -c statement_timeout=5000 -c lock_timeout=1000' \
    "$DB_CONTAINER" psql -X -w -v ON_ERROR_STOP=1 -P pager=off -U "$DB_USER" -d "$DB_NAME"
}
ro_sql <<'SQL'
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SHOW server_version;
SHOW transaction_read_only;
SELECT rolsuper AS connected_role_superuser,
       pg_has_role(current_user, 'pg_read_all_stats', 'USAGE') AS can_read_all_stats
 FROM pg_roles WHERE rolname=current_user;
SELECT extname, extversion FROM pg_extension WHERE extname='vector';
SELECT to_regclass('public.alembic_version') AS revision_table,
       to_regclass('public.public_registration_quota') AS quota_table,
       to_regclass('public.users') AS users_table;
SELECT table_name, column_name FROM information_schema.columns
 WHERE table_schema='public' AND table_name IN ('users','public_registration_quota')
 ORDER BY table_name, ordinal_position;
COMMIT;
SQL
```

Si `alembic_version` existe, lire sa révision sous la même protection :

```bash
ro_sql <<'SQL'
BEGIN READ ONLY;
SELECT version_num FROM public.alembic_version;
COMMIT;
SQL
```

**Uniquement si le schéma et les colonnes attendus 0007/0008 sont confirmés** :

```bash
ro_sql <<'SQL'
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SELECT id, issued_count, closed,
       (SELECT count(*) FROM users WHERE registration_kind='public') AS public_present,
       issued_count >= 0 AND issued_count >=
         (SELECT count(*) FROM users WHERE registration_kind='public') AS floor_consistent,
       greatest(0, 10-issued_count) AS capacity_remaining_theoretical
 FROM public_registration_quota WHERE id='public';
SELECT registration_kind, count(*) AS accounts,
       count(*) FILTER (WHERE disabled_at IS NOT NULL) AS disabled
 FROM users GROUP BY registration_kind ORDER BY registration_kind;
SELECT count(*) AS documents FROM documents;
SELECT count(*) AS workspaces FROM workspaces;
SELECT count(*) AS memberships FROM workspace_memberships;
SELECT count(*) AS deletion_requests FROM account_deletion_requests;
SELECT status, count(*) FROM ai_reservations GROUP BY status;
SELECT status, count(*) FROM index_jobs GROUP BY status;
SELECT status, count(*) FROM long_summary_jobs GROUP BY status;
SELECT count(*) AS other_clients FROM pg_stat_activity
 WHERE datname=current_database() AND backend_type='client backend' AND pid<>pg_backend_pid();
SELECT schema_name FROM information_schema.schemata
 WHERE schema_name NOT IN ('public','information_schema') AND schema_name !~ '^pg_';
SELECT matviewname FROM pg_matviews WHERE schemaname='public';
SELECT c.relname, t.tgname FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
 JOIN pg_namespace n ON n.oid=c.relnamespace
 WHERE NOT t.tgisinternal AND n.nspname='public';
COMMIT;
SQL
```

Pour 0008 seulement : compter aussi les publics vérifiés, approuvés et bloqués
par agrégats, sans e-mail ni UUID nominatif dans le rapport :

```bash
ro_sql <<'SQL'
BEGIN READ ONLY;
SELECT count(*) FILTER (WHERE email_verified_at IS NOT NULL) AS verified,
       count(*) FILTER (WHERE approved_at IS NOT NULL) AS approved,
       count(*) FILTER (WHERE disabled_at IS NOT NULL) AS disabled
 FROM users WHERE registration_kind='public';
COMMIT;
SQL
```

Exiger une révision unique et une ligne de quota unique. Version inconnue, quota
absent/négatif, dépendance inconnue ou incohérence : **STOP**, aucune « réparation »
dans le diagnostic. Les lectures sont ponctuelles ; les refaire sous maintenance
avant toute migration. Ne jamais lire `pg_stat_activity.query`, les tokens,
password hashes, e-mails ou textes documentaires pour un inventaire global.
Si le rôle SQL ne voit pas les autres sessions, ne pas interpréter un zéro comme
une preuve de maintenance ; faire qualifier l'accès opérateur existant, sans
octroyer automatiquement de privilèges ni laisser l'API/les producteurs démarrés.

Le plafond est **10 admissions publiques cumulatives**, y compris comptes
désactivés/en attente et admissions déjà effacées. `legacy` et `invite` sont exclus.
`issued_count` peut dépasser les comptes présents sans être erroné ; il ne baisse
jamais. Recouper l'historique administratif indépendant si un rollback ancien
du compteur est suspect. Si dix admissions ont déjà eu lieu, il n'y a pas dix
nouvelles places. Ne pas modifier le compteur ou reclasser les comptes.

### 2.4 Lifecycle, latch et autorités

À partir des chemins et montages réellement observés :

```bash
: "${RECOVERY_CONTROL_FILE:?}"
namei -l -- "$RECOVERY_CONTROL_FILE"
stat -c '%F uid=%u gid=%g mode=%a links=%h %n' -- "$RECOVERY_CONTROL_FILE"
```

Lecture bornée du seul état du latch, sur l'hôte avec les droits de lecture requis :

```bash
STATE_PATH="$RECOVERY_CONTROL_FILE" python3 - <<'PY'
import json, os, stat, sys
def unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError()
        value[key] = item
    return value
try:
    fd = os.open(os.environ['STATE_PATH'], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022 or info.st_nlink != 1:
            raise ValueError()
        raw = stream.read(4097)
    if len(raw) > 4096:
        raise ValueError()
    value = json.loads(raw, object_pairs_hook=unique)
    if (set(value) != {'format', 'state'} or type(value['format']) is not int
            or value['format'] != 1 or value['state'] not in ('ready', 'quarantined')):
        raise ValueError()
    print(value['state'])
except Exception:
    print('invalid')
    sys.exit(1)
PY
```

Répéter `namei`/`stat` uniquement sur les répertoires et fichiers identifiés :
registres SQLite, confirmations, holds, verrou, clé HMAC, éventuels en-têtes
root/demandes et confiance de release. Ne pas ouvrir les clés ni journaliser les
politiques/preuves d'identité. Le latch JSON, s'il correspond au format attendu,
doit être lu par un validateur borné n'émettant que `ready`, `quarantined` ou
`invalid`, jamais par un dump de fichier arbitraire.

Vérifier ownership **et ancêtres**, absence de symlinks/hardlinks inattendus,
séparation des magasins, cohérence des montages host/conteneur et domaine HMAC
existant. L'autorité de confiance de release, l'autorité d'effacement root et les
registres lifecycle sont distincts : l'existence de l'une ne provisionne pas les autres.
Ne lancer aucun `init`, réconciliation, levée de hold ou `verify` d'effacement
dans la phase L : `verify` écrit un résultat durable.

### Fiche de sortie de l'inventaire — actuellement inconnue

À compléter dans un dossier opérateur privé : projet/fichiers Compose ; IDs,
digests et révisions ; version PostgreSQL/vector ; schéma et historique du quota ;
volumes/binds/réseaux ; UID/GID et capacités des processus ; latch et ancêtres ;
chemins/instances lifecycle et root ; espace disponible ; proxy/IP réelle ;
outillage de déploiement déjà adopté ; protection de sauvegarde existante ;
responsables, échéances de conservation et application de repli.
**Aucune de ces valeurs VPS n'est confirmée par ce rapport.**

## 3. Blocage d'intégration opérationnelle à traiter avant déploiement

Le code vérifié établit les faits suivants :

- `tools/release_security.py::BUNDLE_FILES` est une liste fermée attestée ;
  `compose.erasure.yaml` n'y figure pas.
- `ci.yml` copie le Compose de production et les outils retenus dans le bundle,
  pas l'overlay d'effacement.
- `tools/deploy_production.py::Stack.__init__` construit sa commande avec un seul
  `-f <bundle>/compose.production.yaml`, projet `documind-prod`.
- `deploy.yml` exige un bundle exactement reconnu et une approbation indépendante ;
  certains contrôles d'installation vérifient également les labels des fichiers Compose.

**Ne pas ajouter simplement un fichier au bundle attesté, modifier son Compose
après attestation, monter les autorités par un `compose up` parallèle ou modifier
les labels pour satisfaire le contrôleur.** Un déploiement « vert » du bundle
actuel ne suffit pas à installer les montages root nécessaires.

Une décision relue est requise : rendre la configuration d'effacement partie
intégrante du contrat de livraison attesté et du contrôleur utilisé, ou approuver
une procédure opérateur compatible avec ces mêmes protections, prouvée en
préproduction. Ce rapport ne développe pas cette adaptation et n'en invente pas
l'approbation. Tant que ce point n'est pas réglé, **arrêt avant l'installation
root et avant l'ouverture**, même si la CI de branche est verte.

## 4. Prérequis concrets d'installation et de maintenance — M-VPS

### Répertoires, montages et privilèges

Définir explicitement, après inventaire :

| Paramètre | Exigence |
|---|---|
| `ERASURE_AUTHORITY_HOST_DIR` | Répertoire root 0755, ancêtres root sûrs, hors des volumes/restaurations applicatifs |
| `ERASURE_REQUESTS_HOST_DIR` | UID/GID applicatifs réels, mode 0700, persistant |
| `ERASURE_REVIEW_HOST_DIR` | Root 0700 ; politique et preuve privée root 0600, non montées dans l'API |
| `ERASURE_INSTANCE_ID` | UUID décidé et approuvé explicitement ; aucune génération au démarrage |
| `ERASURE_APPLICATION_UID` | UID réel non nul vérifié ; pas une supposition `1000` |
| `RECOVERY_CONTROL_FILE` | Fichier root contrôlé indépendamment, montage API lecture seule |
| Magasins lifecycle | Réutilisation vérifiée des clés/registres privés applicatifs, répertoires séparés |

Une implantation hors `/srv/documind-ai` peut convenir si elle respecte la
séparation et la politique de restauration ; aucun emplacement proposé n'est
un fait acquis ou une autorisation de création.

Exemple de provisionnement de **nouveaux** chemins, uniquement après accord :

```bash
: "${ERASURE_BASE_DIR:?}" "${API_UID:?}" "${API_GID:?}"
# Ancetres root verifies par namei ; API_UID/API_GID releves, jamais inventes.
# Executer ce bloc sous root, apres verification des variables.
test "$(id -u)" -eq 0 || exit 1
test "$API_UID" -gt 0 || exit 1
case "$ERASURE_BASE_DIR" in /*) ;; *) exit 1 ;; esac
if test -e "$ERASURE_BASE_DIR" || test -L "$ERASURE_BASE_DIR"; then
  printf '%s\n' 'STOP: chemins existants a examiner, aucun chmod/chown automatique'
  exit 1
fi
umask 077
mkdir -m 0755 -- "$ERASURE_BASE_DIR" || exit 1
mkdir -m 0755 -- "$ERASURE_BASE_DIR/authority" || exit 1
mkdir -m 0700 -- "$ERASURE_BASE_DIR/requests" "$ERASURE_BASE_DIR/review" || exit 1
chown -- "$API_UID:$API_GID" "$ERASURE_BASE_DIR/requests"
```

Ce bloc ne crée ni clé, ni politique, ni instance. En reprise partielle, examiner
les chemins existants au lieu de supprimer/recréer. Pour une installation existante,
réutiliser seulement après validation ; jamais de `chown -R` ou `chmod -R`.

Le montage API de l'autorité est **read-only**, celui des demandes read-write.
Ne donner à l'API ni root, ni capacité supplémentaire, ni socket Docker.
Le contrôleur ponctuel root n'expose aucun port, a seulement le réseau PostgreSQL
interne et les montages identifiés ; le protocole proposé nécessite `SETUID` et
`DAC_OVERRIDE` après `--cap-drop ALL`, pas `--privileged` ni `SYS_ADMIN`.
Qualifier ces capacités et les UID/montages exacts en préproduction ; rootless
Docker, userns-remap, NFS, ACL ou SELinux peuvent changer les contraintes.
Le provisionnement host est une opération root séparée, pas un privilège de l'API.

La fonction `admin()` et ses montages sont décrits intégralement dans le rapport
d'implémentation. Elle nécessite les variables confirmées, l'image publiée par
digest et le contrat de déploiement résolu ci-dessus ; ne pas la remplir avec
des noms de volumes supposés ou le tag local d'une image de preuve.

### Fermeture, migration et préservation

Configuration fermée à conserver :

```dotenv
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
PUBLIC_LEGAL_READY=false
```

Avant toute migration autorisée : relever les compteurs, vérifier la sauvegarde
opérationnelle existante et son aptitude à restauration, fermer la porte SQL via
la commande existante, passer en maintenance et arrêter tous les producteurs.
Les commandes `backend.*` suivantes s'exécutent dans l'environnement opérateur
approuvé de l'installation, pas sur l'hôte sans configuration ni dans une API root :

```bash
python -m backend.account_admin public-registration status
python -m backend.account_admin public-registration close --execute
```

Pour une installation déjà adoptée par le contrôleur, le futur déclenchement
autorisé serait, depuis un terminal GitHub opérateur :

```bash
: "${MAIN_RELEASE_SHA:?}" "${CI_RUN_ID:?}"
gh workflow run deploy.yml --repo AdelineMeistertzheim403/DocuMind_AI --ref main \
  -f "release_sha=$MAIN_RELEASE_SHA" -f "ci_run_id=$CI_RUN_ID" \
  -f operation=deploy -f initialize=false -f allow_migration=true -f approve_public_beta=false
```

**Ne pas exécuter maintenant.** Il exige une release publiée sur `main`, sa CI
verte, le bundle/digests attestés et l'approbation root indépendante de confiance.
Vérifier la correspondance du projet `/srv/documind-ai` et les prérequis réels
avant de retenir ce chemin. Si l'installation n'est pas adoptée, STOP :
pas de `initialize=true` pour contourner l'inventaire.

La commande de migration sous-jacente est `alembic upgrade head` dans l'image
candidate configurée, sous maintenance ; ne pas l'exécuter manuellement en plus
du workflow. Depuis 0007, 0008 ajoute `users.approved_at`, conserve identités,
documents et relations, ferme le quota et ne l'abaisse pas : il est au moins
le maximum de l'ancien compteur et du nombre de comptes publics présents.
Elle ne récupère pas magiquement un historique perdu avant migration.

Comparer avant/après les agrégats, volumes et empreintes d'un échantillon autorisé,
sans extraire de contenu privé dans Git. Les publics existants ont leur
`approved_at` initialement NULL et demandent revue individuelle ; les comptes
legacy/invite ne sont pas reclassés ni supprimés. Aucune approbation en masse.
Si le schéma est déjà 0008, vérifier plutôt que rejouer une migration inutile.

### Installation root et parcours d'effacement — commandes M-VPS

En fenêtre autorisée : gate fermée, mode disabled, latch root durable en
`quarantined`, web/API et tous les producteurs arrêtés, autres clients SQL fermés,
registre de holds et identité contrôlés. Le bind d'un latch remplacé par rename
peut rester sur l'ancien inode : vérifier la valeur montée et recréer les
conteneurs si nécessaire, sans écrire `ready` par défaut.

Après approbation de l'instance et de la politique réelle seulement :

```bash
# admin() = controleur root ponctuel approuve, pas docker exec API root.
admin init
# Pour un compte deja desactive, reception administrative sans contourner le login :
admin request-account "$USER_UUID"
# Pour toute reference recue persistante :
admin plan "$OPERATION_UUID"
admin status "$OPERATION_UUID"
admin authorize "$OPERATION_UUID" --confirm "$OPERATION_UUID" \
  --policy /run/erasure-review/policy.json \
  --identity-evidence /run/erasure-review/identity-review
admin execute "$OPERATION_UUID" --confirm "$OPERATION_UUID"
admin verify "$OPERATION_UUID"
```

`init` n'est pas une commande de réparation d'une autorité perdue ou d'une autre
instance. Le tester d'abord dans la stack isolée ; ne pas l'exécuter si l'autorité
de production existe déjà sans rapprochement préalable.
`plan`, `authorize`, `execute` **et `verify` écrivent des preuves**.
Une réception 202 n'est pas un effacement ; `execute` reste en attente de vérification.
Exiger `active_erasure_verified=true` après nouvelle invocation de `verify`.
`completed=false` reste correct tant que toutes les copies ne sont pas traitées.

En interruption, conserver quarantaine et référence, résoudre la cause et reprendre
la même opération sans changer le plan. Compteur, source, schéma ou données
incohérents : revue, jamais force SQL ou abandon des protections.
Ne relever la quarantaine qu'après vérification fraîche de toutes les opérations
et validation opérateur. Redémarrage : sessions mémoire perdues, reconnexion requise.

## 5. Conservation, SMTP, DNS, HTTPS et juridique

### Décisions de conservation manquantes

Faire approuver et consigner hors Git : responsable, base juridique, périmètres
effaçables/conservés, échéances et propriétaires de chaque copie ; durée des logs,
des sauvegardes/WAL/snapshots/réplicas/exports, des preuves d'identité et du journal
root ; gels éventuels, preuve d'expiration et procédure de réponse au demandeur.
Aucune durée de test n'est une règle de production.

La politique du moteur exige une décision explicite `owner_accounting=erase`.
Une obligation légale incompatible impose STOP, pas une fausse politique.
Les durées configurées sont enregistrées, pas appliquées par un nouvel ordonnanceur.
L'absence active ne prouve ni l'effacement des blocs MVCC/SSD, ni celui des copies
hors inventaire. Ne pas annoncer une conformité juridique ou un effacement total
à partir du seul résultat SQL/unlink.

Conserver les tombstones hors restaurations applicatives et une copie opérateur
récupérable vérifiée. Toute restauration se fait en quarantaine, sans producteurs,
avec rapprochement des admissions/effacements et nouvelle vérification indépendante.
Un rollback conjoint du journal root et des données ne peut pas être détecté sans
preuve indépendante plus récente : en son absence, NO-GO, pas de réinitialisation.
Ne pas réouvrir une ancienne base ni recycler des admissions après effacement.

### Probes réseau L-VPS — après autorisation seulement

Renseigner `APP_HOST`, `MAIL_DOMAIN`, le sélecteur DKIM et le serveur SMTP depuis
les valeurs approuvées, sans afficher de credential :

```bash
: "${APP_HOST:?}"
dig +short "$APP_HOST" A
dig +short "$APP_HOST" AAAA
curl --silent --show-error --output /dev/null --write-out '%{http_code}\n' "http://$APP_HOST/"
curl --fail --silent --show-error "https://$APP_HOST/bff/health"
curl --fail --silent --show-error "https://$APP_HOST/bff/auth/options"
curl --silent --show-error --output /dev/null --write-out '%{http_code}\n' "https://$APP_HOST/bff/documents"
openssl s_client -connect "$APP_HOST:443" -servername "$APP_HOST" \
  -verify_hostname "$APP_HOST" -verify_return_error </dev/null
```

Attendre HTTPS valide sans `-k`, redirection HTTP sûre, health vert hors maintenance,
options `disabled`, plafond 10, approbation requise et capacité publique false ;
documents sans session refusés 401. En quarantaine, un 503 est attendu, pas une
raison de forcer le latch. Vérifier aussi IP A/AAAA réellement desservies, proxy
Traefik/réseau `web`, Host/origine/CSRF, cookies `__Host-documind`, absence d'API/DB
publiques, confinement et fonctions IA/demo/legacy désactivées.

```bash
: "${MAIL_DOMAIN:?}" "${DKIM_SELECTOR:?}" "${SMTP_HOST:?}"
dig +short "$MAIL_DOMAIN" MX
dig +short "$MAIL_DOMAIN" TXT
dig +short "_dmarc.$MAIL_DOMAIN" TXT
dig +short "$DKIM_SELECTOR._domainkey.$MAIL_DOMAIN" TXT
# Choisir UNE variante conforme au fournisseur, sans AUTH ni mot de passe :
openssl s_client -connect "$SMTP_HOST:465" -servername "$SMTP_HOST" \
  -verify_hostname "$SMTP_HOST" -verify_return_error </dev/null
# Ou STARTTLS obligatoire :
openssl s_client -starttls smtp -connect "$SMTP_HOST:587" -servername "$SMTP_HOST" \
  -verify_hostname "$SMTP_HOST" -verify_return_error </dev/null
```

465 correspond à TLS implicite/`SMTP_STARTTLS=false`, 587 à
`SMTP_STARTTLS=true`. Aucun repli plaintext ou certificat invalide accepté.
Contrôler expéditeur autorisé et alignement SPF/DKIM/DMARC. Un handshake ne prouve
pas l'authentification ni la livraison ; l'envoi/réception effectifs demandent
un test autorisé, d'abord en préproduction avec données fictives.
La file SMTP est mémoire ; vérifier les renvois et la procédure opérateur.
L'approbation administrative n'envoie pas de notification automatique.

Faire approuver avant `PUBLIC_LEGAL_READY=true` l'identité/contact réel de
l'exploitante, mentions légales, confidentialité, conditions de bêta versionnées,
plafond, approbation, règles de conservation et exercice des droits.
Vérifier les trois URLs HTTPS publiées, leur contenu et leur version ; ne pas
remplacer un texte approuvé par un brouillon ou considérer un statut HTTP 200
comme validation juridique.

## 6. Plan d'ouverture à six portes indépendantes

| Porte | Actions, sous autorisation | Critère de passage |
|---|---|---|
| 1 — Release | Publier la branche, CI du SHA exact, revue ; puis accord distinct pour intégration `main` et publication automatique | CI complète verte ; images par digest, bundle attesté et confiance indépendante ; intégration des montages d'effacement résolue |
| 2 — Migration fermée | Diagnostic autorisé, conservation opérationnelle existante vérifiée, mode disabled/gate fermée, migration 0007→0008 approuvée | Données et historique conservés, compteur non abaissé, schéma 0008 et services maîtrisés |
| 3 — Autorité/effacement | Provisionnement approuvé, contrat de déploiement compatible, root séparé, répétition préalable sur Linux/PostgreSQL isolé | UID/montages/capacités, holds, réception, autorisation, interruptions et vérification fraîche prouvés |
| 4 — Fonctionnel/opérationnel | Parcours complet fictif en préproduction ; santé, isolation, SMTP/TLS et procédure d'incident | Inscription → e-mail → approbation → connexion/import/usage → demande → effacement vérifié ; avant approbation refusé |
| 5 — Juridique/conservation | Décisions et responsables réels, textes publiés, sauvegardes/logs/journal et restauration rapprochée | Validation documentée ; aucune obligation ou copie sans traitement décidé |
| 6 — Ouverture | Accord explicite séparé, public préparé avec SQL encore fermé, contrôles puis réouverture SQL | Compteur cohérent <10, approbation obligatoire, health et suivi disponibles |

Ne créer ni dix comptes fictifs ni un compte « recyclable » dans la base de
production pour qualifier la limite : chaque admission publique consomme une
place historique. Les tests de plafond/concurrence et d'effacement restent isolés.
Un éventuel témoin de production requiert une décision séparée et une vraie place.

### Dernière porte uniquement — M-ouverture, interdite à ce stade

Une fois toutes les autres portes validées, préparer `REGISTRATION_MODE=public`
et `PUBLIC_LEGAL_READY=true` avec les textes approuvés, **SQL toujours fermé**.
Le contrôleur actuel exige une approbation publique de préparation :
`approve_public_beta=true`, `initialize=false`, `allow_migration=false` en 0008.
Ne pas utiliser ce mode pour contourner le blocage de montages ou d'attestation.

Après nouvelle décision d'ouverture, dans l'API correctement configurée :

```bash
python -m backend.account_admin public-registration status
python -m backend.account_admin public-registration reopen
# Simulation examinee, puis seulement si l'ouverture est explicitement autorisee :
python -m backend.account_admin public-registration reopen --execute
```

Les commandes sans `--execute` sont des simulations, pas une ouverture.
Vérifier ensuite les options et le quota en lecture seule, sans inscrire un faux
utilisateur. Pour chaque véritable testeur après vérification e-mail :

```bash
python -m backend.account_admin public-account status "$USER_UUID"
python -m backend.account_admin public-account approve "$USER_UUID"
# Revue individuelle validee :
python -m backend.account_admin public-account approve "$USER_UUID" --execute
```

Notification manuelle, suivi des échecs SMTP et des demandes d'effacement.
En incident : fermer SQL, revenir au mode disabled et à la maintenance selon la
procédure approuvée ; ne pas baisser le compteur pour « réparer » l'ouverture.

### Retour arrière

Repli applicatif seulement, schéma 0008 conservé, volumes/lifecycle/journal root
conservés, porte SQL fermée. Il faut une image attestée et approuvée qui conserve
**aussi les protections d'effacement et tombstones** : la compatibilité SQL 0008
seule ne suffit plus. Le parent `a3d2adb` sans ce moteur n'est pas un repli
automatiquement acceptable après activation/effacements.
Si aucun tel repli n'est qualifié, maintenir la maintenance ; pas de downgrade
0007, restauration automatique d'ancienne base, suppression de reçu ou retour Lite.
La restauration de données est une décision distincte, jamais un rollback implicite.

## 7. Checklist finale GO / NO-GO

- [x] Commit du moteur et tests identifiés ; dépendances et assets nécessaires suivis.
- [x] Worktree de livraison initial propre ; aucun nettoyage ou fusion historique.
- [x] CI contient effacement natif PostgreSQL, parcours bêta, frontend/BFF et sécurité.
- [x] Publication de branche/dispatch préparés sans exécution ; pas de publication d'images sur cette branche.
- [x] Métadonnées de reviewers `production` présentes ; ne valent pas une autorisation.
- [x] Procédure de diagnostic expurgée et séparation L/M préparées.
- [ ] Accord de publication de branche et CI distante verte du HEAD exact.
- [ ] Intégration/promotion et publication d'images expressément approuvées.
- [ ] Contrat attesté de déploiement des montages d'effacement résolu et qualifié.
- [ ] Inventaire VPS autorisé, relevé privé complet et installation compatible/adoptée.
- [ ] Historique public réconcilié ; au moins une place disponible si ouverture prévue.
- [ ] Migration fermée et conservation des utilisateurs existants validées.
- [ ] Autorité root réelle, UID/paths/montages/capacités et procédure opérateur qualifiés.
- [ ] Conservation, copies, gels, preuve indépendante du journal et restauration validés.
- [ ] SMTP/DNS/HTTPS, documents juridiques et parcours préproduction approuvés.
- [ ] Repli 0008 avec protections d'effacement approuvé, ou maintien fermé accepté.
- [ ] Autorisations distinctes de déploiement, remise en service et ouverture SQL.

**État final : préparation documentaire et Git locale livrée ;
production non inspectée, non modifiée et ouverture non autorisée.**
