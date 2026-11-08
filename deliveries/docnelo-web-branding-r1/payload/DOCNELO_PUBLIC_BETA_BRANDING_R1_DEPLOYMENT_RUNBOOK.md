# Docnelo Public Beta Web Branding R1 — Runbook opérateur

**Aucune commande VPS de ce document n'a été exécutée. Verdict actuel : NO-GO de déploiement.** La préparation locale est terminée ; commencer uniquement par les contrôles en lecture seule. La bascule n'est proposée qu'après revue de la preuve obtenue et décision GO explicite de l'opérateur. Si une condition échoue, arrêter ; ne pas changer les paramètres pour contourner la garde.

## 1. Fichiers à transférer et preuve d'intégrité

Sur Windows, PowerShell. Remplacer uniquement le nom d'hôte SSH inconnu ; aucun ID d'image n'est à inventer. Le répertoire distant doit être neuf.

```powershell
$R1 = 'C:\Users\Adeline\Documents\DocuMind_AI\deliveries\docnelo-web-branding-r1'
$Payload = Join-Path $R1 'payload'
$VpsTarget = 'debian@REMPLACER_PAR_HOTE_VPS'
$RemoteStage = '/home/debian/docnelo-web-branding-r1'
Get-FileHash -Algorithm SHA256 -LiteralPath "$Payload\SHA256SUMS"
# Conserver cette empreinte independamment du transfert.
ssh "$VpsTarget" "test ! -e /home/debian/docnelo-web-branding-r1"
if ($LASTEXITCODE -ne 0) { throw 'Staging distant deja present : arret, aucune fusion' }
scp -r "$Payload" "${VpsTarget}:${RemoteStage}"
if ($LASTEXITCODE -ne 0) { throw 'Transfert R1 en echec' }
```

Le payload contient l'archive Web, des métadonnées, le patch et des contrôles en lecture seule ; pas de .env, DB ou données utilisateur. Ne pas transférer le worktree complet, node_modules, npm-cache, baseline-dist ou les anciens exports.

Sur Debian, sans chargement ni démarrage d'image :

```bash
set -euo pipefail
umask 077
INCOMING=/home/debian/docnelo-web-branding-r1
PROOF=/home/debian/docnelo-web-branding-r1.operator-proof.json
cd "$INCOMING"
sha256sum SHA256SUMS
# Comparer avec l'empreinte conservee sur Windows AVANT de poursuivre.
sha256sum --check --strict SHA256SUMS
python3 -B collect_preflight.py --output "$PROOF"
```

Ce collecteur contacte seulement le Docker local via unix:///var/run/docker.sock et GET HTTPS /bff/auth/options sur le domaine actuel. Il n'exécute aucun up/start/stop, ne lance aucun processus applicatif dans les conteneurs et n'écrit que le nouveau fichier de preuve. Il vérifie :

- trois conteneurs Public Beta healthy, noms et projet attendus ;
- Web actif exactement sur f15855942fb4… et plateforme linux/amd64 ;
- fichiers Compose actifs sous la release applicative actuelle, en conservant le registration-gate s'il est présent ;
- mode d'inscription connu et aucune disponibilité publique ouverte ;
- versions/URLs juridiques et indicateurs existants, sans modification de PUBLIC_LEGAL_READY ni d'aucune autre valeur.

Le fichier de preuve est créé sans écrasement ; conserver les éventuelles preuves précédentes et employer un nouveau chemin si nécessaire. Les valeurs Env complètes ne sont jamais sorties. Le collecteur n'assimile pas un échec réseau/HTTP à une inscription fermée.

Pour transmettre la preuve à la revue depuis Windows, sans l'ajouter au payload scellé :

```powershell
scp "${VpsTarget}:/home/debian/docnelo-web-branding-r1.operator-proof.json" "$R1\operator-proof-vps.json"
if ($LASTEXITCODE -ne 0) { throw 'Collecte de preuve en echec' }
```

### Si la provenance ne correspond pas

Arrêt : le candidat n'est pas autorisé sur cette autre base. Voici les observations manuelles en lecture seule, sans secret ni hypothèse sur l'ID actif :

```bash
D=(docker --host unix:///var/run/docker.sock)
"${D[@]}" inspect --format '{{.Name}} {{.Image}} {{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}' \
  documind-public-beta-db-1 documind-public-beta-api-1 documind-public-beta-web-1
ACTIVE_WEB_ID=$("${D[@]}" inspect --format '{{.Image}}' documind-public-beta-web-1)
"${D[@]}" image inspect --format '{{.Id}} {{.Os}}/{{.Architecture}} {{json .RepoDigests}}' "$ACTIVE_WEB_ID"
"${D[@]}" image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$ACTIVE_WEB_ID"
"${D[@]}" inspect --format '{{index .Config.Labels "com.docker.compose.project.config_files"}}' documind-public-beta-web-1
```

Il faut alors fournir cette identité, la provenance CI/commit de cette image, son package-lock et les empreintes des fichiers server/dist réellement servis. Ne pas modifier le collecteur pour accepter un nouvel ID sans reproduire cette autre référence et requalifier R1. Ne pas envoyer de dump brut d'Env, .env, clé ou document utilisateur.

## 2. Installation dans une nouvelle release — après preuve et GO opérateur

Les étapes suivantes ne sont pas à lancer tant que le NO-GO n'est pas levé sur la preuve réelle. Elles ne modifient ni .env, ni lien current, ni release applicative.

```bash
APP_ROOT=/opt/documind-public-beta/public-beta-candidate-20261030T234818Z
RELEASE=/opt/documind-public-beta/branding-docnelo-web-r1-22b6428-v2
BASE_ID=sha256:f15855942fb4382375648841bbcdc486fd39d252e80e8fdf8eb42999d6590019
NEW_ID=sha256:b8dcd1edd1c0e366f0bc605914424585a96d261b49b82e952458dfab1a911a1a
NEW_TAG=documind-public-beta-web:docnelo-r1-22b6428-v2
ROLLBACK_TAG=documind-public-beta-web:r1-rollback-f15855942fb4
D=(docker --host unix:///var/run/docker.sock)

sudo mkdir -m 0700 "$RELEASE"
sudo chown debian:debian "$RELEASE"
cp -a "$INCOMING"/. "$RELEASE"/
cd "$RELEASE"
sha256sum --check --strict SHA256SUMS

# Ne pas ecraser un tag qui identifierait deja une autre image.
if PRESENT_ID=$("${D[@]}" image inspect "$NEW_TAG" --format '{{.Id}}' 2>/dev/null); then
  test "$PRESENT_ID" = "$NEW_ID"
else
  "${D[@]}" load --input "$RELEASE/web-image.tar"
fi
test "$("${D[@]}" image inspect "$NEW_TAG" --format '{{.Id}}')" = "$NEW_ID"
test "$("${D[@]}" image inspect "$NEW_TAG" --format '{{.Os}}/{{.Architecture}}')" = linux/amd64
test "$("${D[@]}" inspect --format '{{.Image}}' documind-public-beta-web-1)" = "$BASE_ID"

if ROLLBACK_ID=$("${D[@]}" image inspect "$ROLLBACK_TAG" --format '{{.Id}}' 2>/dev/null); then
  test "$ROLLBACK_ID" = "$BASE_ID"
else
  "${D[@]}" tag "$BASE_ID" "$ROLLBACK_TAG"
fi
test "$("${D[@]}" image inspect "$ROLLBACK_TAG" --format '{{.Id}}')" = "$BASE_ID"
```

Les tags sont neufs et contrôlés par ID ; conserver les deux images et l'archive. Pas de pull global, build sur VPS, prune ou suppression de volume. Seule l'image Web est chargée ; aucune image API/PostgreSQL n'est reconstruite ni remplacée.

## 3. Contrôle du Compose et maintien de la configuration

Ne pas recopier le Compose du dépôt ou un fichier .env.example. Utiliser les fichiers de la release active enregistrés par le collecteur, dans le même ordre. Les scripts ci-dessous ne sourcent aucun fichier secret et ne sortent jamais un config rendu contenant des secrets.

```bash
export RECOVERY_CONTROL_FILE=/opt/documind-public-beta/recovery-state.json
unset COMPOSE_FILE COMPOSE_PROJECT_NAME
python3 -B "$RELEASE/check-compose.py" --proof "$PROOF" --release "$RELEASE"

mapfile -t ACTIVE_FILES < <(python3 -c 'import json,sys; print("\n".join(json.load(open(sys.argv[1]))["compose_files"]))' "$PROOF")
test "${#ACTIVE_FILES[@]}" -gt 0
BASE=("${D[@]}" compose --project-directory "$APP_ROOT" -p documind-public-beta
  --env-file "$APP_ROOT/.env.public-beta"
  --env-file "$APP_ROOT/.env.public-beta.images")
for file in "${ACTIVE_FILES[@]}"; do BASE+=(-f "$file"); done
```

check-compose exige que seul image/pull_policy de Web change, que tous les autres services/réseaux/volumes et paramètres Web restent identiques, que l'environnement Web résolu corresponde à l'actif et que les overrides n'aient pas changé depuis la preuve. Une dérive préexistante sur disque impose l'arrêt, pas une réconciliation pendant le rebranding. Aucun PUBLIC_LEGAL_READY=true ou mode public n'est défini ; RECOVERY_CONTROL_FILE ne sert qu'à résoudre le chemin canonique existant sans le réécrire.

## 4. Bascule Web seule proposée

Après revue finale du dossier concret et fenêtre opérateur :

```bash
python3 -B "$RELEASE/check-compose.py" --proof "$PROOF" --release "$RELEASE"
"${BASE[@]}" -f "$RELEASE/web.r1.override.yaml" up -d --no-deps --no-build --pull never web
test "$("${D[@]}" inspect --format '{{.Image}}' documind-public-beta-web-1)" = "$NEW_ID"
"${D[@]}" inspect --format '{{.Name}} {{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}' \
  documind-public-beta-db-1 documind-public-beta-api-1 documind-public-beta-web-1
```

Une brève interruption Web est attendue avec une seule instance. Attendre healthy, au maximum deux minutes, par observations sans restart supplémentaire. Le retour de up -d n'est pas une preuve de santé. Aucun up global, redémarrage API/DB/lifecycle-init ou Alembic n'est prévu.

Après stabilisation :

```bash
python3 -B "$RELEASE/verify-state.py" --proof "$PROOF" --expected-web-id "$NEW_ID"
```

Ce contrôle exige DB/API de même ID, image et StartedAt, volumes identiques, Web sur le bon ID, services healthy, mode/profil/versions/URLs juridiques conservés et aucune ouverture publique. Il ne crée pas de compte pour tester l'inscription.

Recette manuelle minimale : HTTPS sur le domaine actuel, logo/favicon/titre, compte de test **existant**, navigation et lecture d'un document de test déjà présent, CSS desktop/mobile et liens juridiques historiques. Ne pas lancer les E2E du dépôt qui créent/suppriment des données sur ce VPS. Ne pas envoyer d'email, supprimer un compte/document ou ouvrir les inscriptions comme sonde. Le cookie de session reste historique ; un CSRF en vol peut nécessiter un réessai au redémarrage Web.

Conserver ce chemin d'override dans le registre opérateur des déploiements : un futur up web doit l'inclure. Les .env restent inchangés ; un up avec seulement le Compose de base pourrait remettre l'ancienne image. Les opérations start/stop de sauvegarde ne sont pas modifiées par cette livraison.

## 5. Rollback Web proposé

Si une vérification échoue, ne pas tenter de corriger l'API, la DB, les quotas ou le latch. Revenir seulement à l'image Web conservée :

```bash
test "$("${D[@]}" image inspect "$ROLLBACK_TAG" --format '{{.Id}}')" = "$BASE_ID"
"${BASE[@]}" -f "$RELEASE/web.rollback.yaml" up -d --no-deps --no-build --pull never web
test "$("${D[@]}" inspect --format '{{.Image}}' documind-public-beta-web-1)" = "$BASE_ID"
# Attendre healthy, sans redemarrage des autres services.
python3 -B "$RELEASE/verify-state.py" --proof "$PROOF" --expected-web-id "$BASE_ID"
```

Dans un nouveau shell, relire les variables de l'étape 2 et reconstruire BASE depuis la même preuve selon l'étape 3 ; ne pas appeler check-compose après bascule, car sa fonction est précisément de vérifier la référence **avant** remplacement. verify-state est le contrôle après bascule ou rollback.

Aucun rollback de données, restauration Restic ou changement de migration n'est nécessaire : rien de cela n'a été modifié. Garder l'ancienne release applicative, les deux images et les preuves, sans nettoyage automatique. Si la santé DB/API est affectée par un événement externe, arrêter et diagnostiquer séparément au lieu de les redémarrer dans cette procédure.

## Décision finale de cette préparation

**NO-GO de déploiement à cette date : image active et fermeture publique non encore observées sur le VPS.** Les contrôles locaux sont réussis et l'image est concrète. Les commandes de collecte ci-dessus permettent de lever ce dernier manque sans modifier l'environnement. Une autre image active exige une nouvelle qualification, jamais une modification opportuniste de l'ID attendu.
