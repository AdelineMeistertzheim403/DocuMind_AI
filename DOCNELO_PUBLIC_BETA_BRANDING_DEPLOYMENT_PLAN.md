# Plan de déploiement contrôlé — Docnelo Public Beta

Date : 31 octobre 2026. **Plan conditionnel, aucune commande de ce document n'a été exécutée.** Le workspace courant est NO-GO : build CSS en échec, changements fonctionnels mélangés, provenance des sources Web à confirmer. Lire l'[audit](DOCNELO_PUBLIC_BETA_BRANDING_AUDIT.md) et le [rapport de tests](DOCNELO_PUBLIC_BETA_BRANDING_TEST_REPORT.md).

## Choix de release et limites

Un seul composant à reconstruire : **image Web Public Beta**, incluant de nouveaux fichiers statiques et le BFF **strictement identique** à celui déjà actif. Ne reconstruire ni API, ni PostgreSQL, ni Traefik, ni image de sauvegarde. Aucun Alembic upgrade, changement de table/API/auth/admission/Restic, de domaine, de volume ou de nom technique.

Pour garantir l'absence de changement BFF, l'image finale sera dérivée de l'image Web active figée par digest ou par ID d'image vérifié. Seul /app/dist est remplacé pendant le build. Les sources server, node_modules runtime, USER/CMD/healthcheck et le contrat de sessions proviennent de la base active. Le build frontend passe d'abord sur une sélection de changements graphiques revue, liée à un commit propre et aux empreintes des entrées.

Emails, OpenAPI et prompt backend restent ceux de l'API actuelle. Leur changement de marque serait un second lot API distinct ; aucun backend actuel du workspace ne doit être embarqué. Les anciens noms dans les versions juridiques historiques sont conservés. Ces limites de couverture doivent être acceptées avant go du lot Web.

La release d'exploitation est un **nouveau répertoire de métadonnées** sous /opt/documind-public-beta ; la release applicative actuelle reste /opt/documind-public-beta/public-beta-candidate-20261030T234818Z. Compose continue d'utiliser cette dernière comme project-directory : pas de copie d'env, de changement du latch ou des chemins de volumes. Aucun lien current n'est basculé.

## 1. Conditions de go et sélection des sources

Avant de construire une image livrable :

1. Retrouver les sources exactes ayant produit le dist de l'image Web active. L'export local mélange src provenant de HEAD et dist/server provenant de l'image ; ne pas présumer leur équivalence. Capturer l'ID d'image actif et vérifier l'export de référence.
2. Préparer un commit isolé depuis cette référence. Sélectionner uniquement les changements de marque ; ne pas copier Account.tsx, Layout.tsx, services/api.ts ou les tests actuels en bloc. Exclure Beta Lite ajouté, suppression différée, téléchargement nouveau et changements de cookies/BFF. Les fonctions déjà actives dans la référence doivent rester identiques.
3. Supprimer du **lot isolé** la dépendance nouvelle à /bff/ui-config et UI_ENVIRONMENT_LABEL ; garder le badge Public Beta statique et les avertissements IA correspondant à l'environnement courant, sans changement de config.
4. Corriger l'import des tokens CSS dans ce lot : chemin relatif de compilation vérifié ou module dans src/styles. Ne pas désactiver les CSS ou Tailwind pour faire réussir le build.
5. Conserver les contenus et identifiants juridiques historiques exacts. Exclure documents.ts courant tant que les modifications réécrivent les mêmes versions. Toute nouvelle édition exige un nouvel identifiant séparé, sans modification de la version/URL d'admission de l'API.
6. Refaire tests/build et recette navigateur CSS active sur le commit isolé, puis vérifier mêmes requêtes/contrats que la référence. Le résultat 123/0 de cet audit n'est pas une validation de ce futur commit.
7. Vérifier que le mode d'inscription reste strictement celui de l'instance et que les inscriptions publiques ne deviennent pas disponibles. Ne définir ni PUBLIC_LEGAL_READY=true, ni REGISTRATION_MODE=public, ni paramètre d'ouverture. Ne déployer aucun .env.example.

### Liste cible précise des chemins statiques à sélectionner

Cette liste de **16 chemins** décrit le lot minimal proposé, pas un patch déjà préparé. Les fichiers mixtes nécessitent une sélection des seuls changements graphiques. Les tests du commit isolé devront également être adaptés/revus ; leur liste exacte sera annexée au manifeste de ce commit, avant go.

```text
frontend/index.html
frontend/public/manifest.webmanifest
frontend/public/brand/docnelo/docnelo-horizontal-dark-transparent.png
frontend/public/brand/docnelo/favicon.ico
frontend/public/brand/docnelo/docnelo-icon-32.png
frontend/public/brand/docnelo/docnelo-icon-64.png
frontend/public/brand/docnelo/docnelo-icon-192.png
frontend/public/brand/docnelo/docnelo-icon-512.png
frontend/public/brand/docnelo/docnelo-tokens.css
frontend/src/components/Brand.tsx
frontend/src/components/Layout.tsx
frontend/src/components/Assistant.tsx
frontend/src/pages/Account.tsx
frontend/src/pages/AISettings.tsx
frontend/src/services/api.ts
frontend/src/styles.css
```

Conserver le Dockerfile et package-lock de référence, les autres sources et contrats, les versions légales, le BFF et sa config. Ne pas livrer les variantes Business ou autres images non utilisées dans le lot minimal. La fermeture exacte du contexte frontend peut inclure les fichiers **inchangés** requis par le build ; ils sont figés et inventoriés, sans reprise du workspace sale.

## 2. Précontrôles VPS, lecture seule sauf création de métadonnées neuves

À exécuter ultérieurement par l'opérateur, sans arrêter les services. Utiliser un identifiant de release unique ; conserver l'ancienne image et la sauvegarde V5 validée, sans relancer Restic.

```bash
set -euo pipefail
umask 077
APP_ROOT=/opt/documind-public-beta/public-beta-candidate-20261030T234818Z
RELEASE_ID=docnelo-web-20261031-r1
RELEASE=/opt/documind-public-beta/branding-$RELEASE_ID
APP_ORIGIN=https://documind.adelinemeistertzheim.fr

# mkdir refuse toute réutilisation de cette release ; pas d'écrasement.
sudo mkdir -m 0700 "$RELEASE"
sudo chown debian:debian "$RELEASE"
export RECOVERY_CONTROL_FILE=/opt/documind-public-beta/recovery-state.json
unset COMPOSE_FILE COMPOSE_PROJECT_NAME
BASE=(docker compose --project-directory "$APP_ROOT" -p documind-public-beta
  --env-file "$APP_ROOT/.env.public-beta"
  --env-file "$APP_ROOT/.env.public-beta.images"
  -f "$APP_ROOT/compose.public-beta.vps.yaml")

python3 - "$RELEASE/before.json" <<'PY'
import json, subprocess, sys
names = ['documind-public-beta-db-1','documind-public-beta-api-1','documind-public-beta-web-1']
containers = json.loads(subprocess.check_output(['docker','inspect',*names], text=True))
report = {}
for c in containers:
    name = c['Name'].lstrip('/')
    labels = c['Config'].get('Labels') or {}
    assert labels.get('com.docker.compose.project') == 'documind-public-beta'
    assert c['State']['Running'] and c['State'].get('Health',{}).get('Status') == 'healthy'
    report[name] = {'id':c['Id'], 'image_id':c['Image'], 'image_ref':c['Config']['Image'],
                    'started_at':c['State']['StartedAt'],
                    'config_files':labels.get('com.docker.compose.project.config_files','')}
with open(sys.argv[1], 'x') as f: json.dump(report, f, indent=2)
print('Public Beta: trois conteneurs healthy ; identités conservées dans before.json')
print('Fichiers Compose du Web:', report[names[-1]]['config_files'])
PY
```

Comparer la liste config_files avec BASE. **Si la release active utilise un override, notamment registration-gate, ajouter le même fichier existant à BASE avant toute suite** ; ne pas le retirer ou reconstruire ses labels. En cas d'autre chemin/projet, arrêter et vérifier le déploiement réel. Les commandes restantes réutilisent le tableau BASE ainsi validé, y compris pour rollback.

Ne pas afficher/sauver le résultat brut de docker compose config ou de docker inspect contenant Env. Les seuls champs sauvegardés ci-dessus sont les identités des conteneurs/images et les chemins Compose ; pas de secrets.

Observer les options d'inscription, sans créer de compte :

```bash
curl --fail --silent --show-error --proto '=https' \
  "$APP_ORIGIN/bff/auth/options" | python3 -c '
import json,sys
d=json.load(sys.stdin)
keys=("registration_mode","application_profile","public_capacity_configured","public_registration_availability",
      "terms_version","terms_url","privacy_url","legal_notice_url")
v={k:d.get(k) for k in keys}
if v["registration_mode"] not in ("disabled","invite","public"):
    raise SystemExit("STOP: mode inscription inconnu")
if v["registration_mode"] == "public" and v["public_registration_availability"] not in ("closed","full"):
    raise SystemExit("STOP: disponibilite publique inattendue ; aucune modification automatique")
print(json.dumps(v))' > "$RELEASE/registration-before.json"
cat "$RELEASE/registration-before.json"
```

Conserver le mode existant ; une configuration publique déjà fermée ne doit pas être ouverte. Cette observation ne remplace pas le contrôle des restrictions d'invitation/Lite dans l'environnement réel. Ne pas poster de demande d'inscription, ne pas toucher aux quotas et ne pas modifier PUBLIC_LEGAL_READY. Ne pas lire ou exporter les secrets Restic pour ce déploiement.

Lire l'architecture de l'image active pour fixer la plateforme du build ; ne pas supposer l'architecture du poste Windows :

```bash
OLD_ID=$(docker inspect --format '{{.Image}}' documind-public-beta-web-1)
docker image inspect --format '{{.Os}}/{{.Architecture}}' "$OLD_ID"
ROLLBACK_REF=documind-public-beta-web:rollback-$RELEASE_ID
docker tag "$OLD_ID" "$ROLLBACK_REF"
test "$(docker image inspect --format '{{.Id}}' "$ROLLBACK_REF")" = "$OLD_ID"
printf '%s\n' "$OLD_ID" > "$RELEASE/old-image-id.txt"
printf '%s\n' "$ROLLBACK_REF" > "$RELEASE/old-image-ref.txt"
```

Le tag de rollback est nouveau et ne modifie pas les octets de l'image active. Si la base dispose d'un RepoDigest, l'utiliser de préférence. Sinon exporter cette image avec docker save, transférer l'archive protégée au builder et contrôler SHA-256 + image ID après docker load ; ne pas reconstruire une approximation de cette base à partir du dépôt.

## 3. Build sur poste/CI, jamais sur la production

Commandes Bash proposées pour un environnement de build contrôlé. SOURCE_BASE_COMMIT doit identifier la source Web de référence vérifiée et REVIEWED_COMMIT le nouveau commit de marque propre ; ne pas remplacer ces valeurs par le HEAD sale actuel.

```bash
SOURCE_BASE_COMMIT=REMPLACER_PAR_SHA_SOURCE_WEB_VERIFIE
REVIEWED_COMMIT=REMPLACER_PAR_SHA_BRANDING_ISOLE
STAGE=/CHEMIN/NEUF/build-docnelo-web-20261031-r1
git worktree add --detach "$STAGE" "$REVIEWED_COMMIT"
git diff --name-only "$SOURCE_BASE_COMMIT" "$REVIEWED_COMMIT"
# Revue obligatoire de chaque chemin/changement ; aucun backend, migrations,
# tools de backup, Compose, env, authentification ou contrat BFF nouveau.
cd "$STAGE/frontend"
npm ci --no-audit --no-fund
npm test
npm run build
```

Après succès et recette, utiliser un Dockerfile de livraison dédié, hors des fichiers applicatifs actuels. Exemple de contenu `Dockerfile.branding` dans ce contexte frontend propre :

```dockerfile
ARG WEB_BASE_REF
FROM node:22-alpine@sha256:025b8e975a61d94e33abeafaad1255ef44e4898cf1a1b6446860009c72e6d284 AS assets
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY index.html tsconfig.json vite.config.ts ./
COPY public ./public
COPY src ./src
RUN npm run build

FROM ${WEB_BASE_REF}
USER root
# Suppression limitée au filesystem de la NOUVELLE image en construction.
# Aucun volume ni conteneur actif n'est monté dans ce build.
RUN rm -rf /app/dist
COPY --from=assets --chown=node:node /app/dist /app/dist
USER node
```

Précondition vérifiée : la base active correspond bien au runtime décrit par frontend/Dockerfile (USER node, /app, CMD server/index.mjs, healthcheck présent). Si l'image réelle diffère, arrêter et adapter le Dockerfile après revue, sans supposer ses UID ni son chemin. Le contexte de build est le seul frontend du commit isolé ; aucun secret ou .env n'y entre. Le cache/build Docker ne doit pas avoir accès aux volumes applicatifs.

```bash
PLATFORM=REMPLACER_PAR_LINUX_ARCHITECTURE_VERIFIEE
WEB_BASE_REF=REMPLACER_PAR_REFERENCE_IMAGE_ACTIVE_FIGEE
EXPECTED_BASE_ID=sha256:REMPLACER_PAR_ID_IMAGE_ACTIVE
NEW_TAG=documind-public-beta-web:docnelo-20261031-r1
test "$(docker image inspect --format '{{.Id}}' "$WEB_BASE_REF")" = "$EXPECTED_BASE_ID"
docker build --platform "$PLATFORM" --pull=false -f Dockerfile.branding \
  --build-arg WEB_BASE_REF="$WEB_BASE_REF" --tag "$NEW_TAG" .
test "$(docker image inspect --format '{{.Id}}' "$WEB_BASE_REF")" = "$EXPECTED_BASE_ID"
docker image inspect --format '{{.Id}}' "$NEW_TAG" > new-image-id.txt
docker save --output web-image.tar "$NEW_TAG"
sha256sum web-image.tar > WEB_IMAGE_SHA256SUMS
```

Un tag seul n'est pas une garantie d'immuabilité. Conserver le SHA complet du commit, la plateforme, la base ID/digest, la nouvelle image ID et les SHA-256 des entrées/dist/archive/Dockerfile dans un RELEASE.json, plus un SHA256SUMS couvrant les métadonnées. Utiliser un nom neuf, ne jamais réutiliser le tag. Le plan privilégie le digest de registre si disponible ; le mode archive ci-dessus reste contrôlé par l'ID exact de l'image avant et après déploiement, avec pull interdit.

Avant livraison, comparer sur le builder, depuis des conteneurs **créés sans démarrage ni volumes**, les arbres /app/server, dépendances runtime et la configuration d'image à la base figée. Leurs empreintes doivent être identiques ; seule /app/dist et les métadonnées de création de l'image sont autorisées à changer. Ne pas conclure à cette identité à partir du seul nom du tag. Effectuer la recette sur environnement jetable, puis transférer manuellement web-image.tar, les empreintes et métadonnées de release dans le nouveau répertoire VPS (SCP), sans env ni secrets.

## 4. Vérification d'image et de configuration avant bascule

Les étapes 4 à 6 restent bloquées tant que les conditions de go ne sont pas remplies. Aucune commande de ces étapes n'a été exécutée pour cet audit.

```bash
cd "$RELEASE"
# Comparer d'abord cette empreinte avec celle conservee par le builder.
sha256sum SHA256SUMS
sha256sum --check --strict SHA256SUMS
sha256sum --check --strict WEB_IMAGE_SHA256SUMS
# SHA256SUMS couvre aussi RELEASE.json, new-image-id.txt et le manifeste archive.
docker load --input web-image.tar
NEW_WEB_REF=documind-public-beta-web:docnelo-20261031-r1
EXPECTED_NEW_ID=$(cat new-image-id.txt)
test "$(docker image inspect --format '{{.Id}}' "$NEW_WEB_REF")" = "$EXPECTED_NEW_ID"
printf 'services:\n  web:\n    image: "%s"\n    pull_policy: never\n' \
  "$NEW_WEB_REF" > "$RELEASE/web.override.yaml"
printf 'services:\n  web:\n    image: "%s"\n    pull_policy: never\n' \
  "$ROLLBACK_REF" > "$RELEASE/web.rollback.yaml"
```

Ne transmettre que des références d'image revues, sans texte libre ni sauts de ligne. Les deux overrides font partie du dossier de release, privé ; aucune édition de .env.public-beta.images existant.

Comparer en mémoire les deux configurations Compose sans sortir de secrets :

```bash
python3 - "$RELEASE/web.override.yaml" "${BASE[@]}" <<'PY'
import json, subprocess, sys
override, base = sys.argv[1], sys.argv[2:]
a = json.loads(subprocess.check_output(base+['config','--format','json'], text=True))
b = json.loads(subprocess.check_output(base+['-f',override,'config','--format','json'], text=True))
assert a.get('name') == b.get('name') == 'documind-public-beta'
old = a['services']['web'].copy()
new = b['services']['web'].copy()
old.pop('image', None); new.pop('image', None)
old.pop('pull_policy', None); new.pop('pull_policy', None)
assert old == new, 'STOP: Web modifie au-dela de image/pull_policy'
aa = {**a, 'services':{k:v for k,v in a['services'].items() if k != 'web'}}
bb = {**b, 'services':{k:v for k,v in b['services'].items() if k != 'web'}}
assert aa == bb, 'STOP: autre service/reseau/volume/config modifie'
containers=json.loads(subprocess.check_output(['docker','inspect','documind-public-beta-web-1'],text=True))
c=containers[0]
active=(c['Config'].get('Labels') or {}).get('com.docker.compose.project.config_files','').split(',')
supplied=[base[i+1] for i,x in enumerate(base[:-1]) if x in ('-f','--file')]
assert active == supplied, 'STOP: fichiers/overrides Compose differents de la reference active'
runtime=dict(v.split('=',1) for v in c['Config'].get('Env',[]) if '=' in v)
assert all(runtime.get(k) == str(v) for k,v in a['services']['web'].get('environment',{}).items()), 'STOP: derive environnement Web deja presente'
print('Configuration verifiee : seule image Web/pull_policy change ; environnement et overrides conserves')
PY
```

Si le Compose sur disque diffère des conteneurs actifs, ou si un override est absent, arrêter et résoudre cette provenance avec l'opérateur : ne pas prendre ce déploiement comme occasion de réconcilier des configurations fonctionnelles. Le fichier Compose courant du workspace n'est pas la configuration à recopier.

## 5. Bascule Web seule, après validation opérateur du dossier concret

```bash
test "$(docker image inspect --format '{{.Id}}' "$NEW_WEB_REF")" = "$EXPECTED_NEW_ID"
"${BASE[@]}" -f "$RELEASE/web.override.yaml" up -d --no-deps --no-build --pull never web
test "$(docker inspect --format '{{.Image}}' documind-public-beta-web-1)" = "$EXPECTED_NEW_ID"
docker inspect --format '{{.Name}} {{.State.Status}} {{.State.Health.Status}}' \
  documind-public-beta-db-1 documind-public-beta-api-1 documind-public-beta-web-1
```

Seul Web peut être recréé ; ne lancer ni up global, ni pull global, ni stop/start API/DB/lifecycle-init. Une brève interruption Web est attendue sur cette topologie à une seule instance ; aucune promesse de bascule sans interruption. Conserver les cookies/headers/documind et contrôler qu'une session existante reste utilisable ; une requête CSRF en vol peut nécessiter un réessai lors du redémarrage Web.

Contrôler manuellement, sans inscription ni création de données :

- Santé des trois conteneurs, ID et StartedAt de DB/API **inchangés** par rapport à before.json ; Web sain sur l'ID attendu.
- Accès HTTPS au domaine courant, login d'un compte existant, navigation et lecture d'un document de test déjà présent. Aucun envoi d'email ni suppression de compte/document pour cette vérification.
- Logo, favicon, titre et pages servies par le nouvel index, sans erreur CSS/JS ; routes juridiques historiques conservées.
- Nouvelle observation GET /bff/auth/options identique sur mode/profil/versions et sans disponibilité publique nouvelle. Ne pas utiliser une requête register comme sonde.
- Identités/volumes/latch inchangés ; aucun appel à Alembic, aucun changement Restic.

Vérification automatisable de non-redémarrage DB/API :

```bash
python3 - "$RELEASE/before.json" <<'PY'
import json, subprocess, sys
before=json.load(open(sys.argv[1]))
names=['documind-public-beta-db-1','documind-public-beta-api-1']
for c in json.loads(subprocess.check_output(['docker','inspect',*names],text=True)):
    old=before[c['Name'].lstrip('/')]
    assert (c['Id'],c['Image'],c['State']['StartedAt']) == (old['id'],old['image_id'],old['started_at'])
    assert c['State']['Running'] and c['State'].get('Health',{}).get('Status') == 'healthy'
print('DB/API inchanges et healthy')
PY
```

Si Web n'est pas healthy ou si un contrôle de marque/contrat/inscription échoue, décider du rollback Web ; aucune tentative automatique de redémarrer API/DB ou de migrer quoi que ce soit.

L'état Web peut d'abord être starting. Attendre sa stabilisation, avec une limite opérateur de deux minutes ; ne pas déclarer le succès sur le seul retour de up -d. Une absence de healthy dans ce délai déclenche la décision de retour arrière.

## 6. Rollback simple et sans données

Dans le même shell contrôlé, ou après relecture du RELEASE.json et reconstruction identique de BASE (avec les overrides actifs) :

```bash
OLD_ID=$(cat "$RELEASE/old-image-id.txt")
ROLLBACK_REF=$(cat "$RELEASE/old-image-ref.txt")
test "$(docker image inspect --format '{{.Id}}' "$ROLLBACK_REF")" = "$OLD_ID"
"${BASE[@]}" -f "$RELEASE/web.rollback.yaml" up -d --no-deps --no-build --pull never web
test "$(docker inspect --format '{{.Image}}' documind-public-beta-web-1)" = "$OLD_ID"
docker inspect --format '{{.Name}} {{.State.Status}} {{.State.Health.Status}}' \
  documind-public-beta-db-1 documind-public-beta-api-1 documind-public-beta-web-1
```

Réexécuter le contrôle DB/API précédent et les lectures de santé/options. Les fichiers .env, la release applicative d'origine, les quotas, le latch, les volumes et le dépôt Restic n'ont pas été modifiés par cette bascule : aucun rollback de données ni restauration de sauvegarde n'est nécessaire. Conserver les images/dossiers de release et les preuves ; aucune commande de nettoyage de volumes ou de prune d'images/dépôt n'est incluse.

## Méthodes précédentes à ne pas reprendre pour ce lot

Les documents docs/docnelo/DOCNELO_PUBLIC_BETA_DEPLOYMENT.md et DOCNELO_BRANDING_INTEGRATION.md sont antérieurs à cet audit : ils évoquent construction API+Web, ajout de UI_ENVIRONMENT_LABEL, up global et un volet production. Ils ne sont pas le plan autorisé ici. L'exporteur existant peut également omettre le rebranding non commité ou exporter des sources différentes du dist. Ne pas les exécuter comme procédure de cette release.

La préparation s'arrête au dossier revu et testable. Ce document ne vaut ni approbation du commit futur, ni autorisation de déploiement automatique, ni validation juridique ou ouverture d'inscriptions.
