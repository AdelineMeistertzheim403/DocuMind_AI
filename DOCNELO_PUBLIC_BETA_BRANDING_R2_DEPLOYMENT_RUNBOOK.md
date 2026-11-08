# Docnelo Public Beta Web Branding R2 — Livraison et rollback

**GO local uniquement. Aucune commande VPS ci-dessous n'a été exécutée.** Une décision opérateur distincte reste nécessaire après les précontrôles. Ne pas reprendre les images ou overrides R1 : cette livraison est exclusivement qualifiée contre 930171… .

## 1. Transfert privé proposé, sans publication

Les archives Docker et extractions sont privées : pas de git add, registre, dépôt d'artefacts public ou lien de partage public. Ne transférer que payload à l'opérateur VPS autorisé. L'archive d'entrée web-active.tar, sa copie sans tags, les extractions brutes et les caches ne sont pas à transférer.

PowerShell sur le poste source ; remplacer uniquement l'hôte SSH inconnu :

```powershell
$R2 = 'C:\Users\Adeline\Documents\DocuMind_AI\deliveries\docnelo-web-branding-r2'
$Payload = Join-Path $R2 'payload'
$VpsTarget = 'debian@REMPLACER_PAR_HOTE_VPS'
$RemoteStage = '/home/debian/docnelo-web-branding-r2-b046e5d8256d'
Get-FileHash -Algorithm SHA256 -LiteralPath "$Payload\SHA256SUMS"
# Conserver cette empreinte independamment du transfert.
$PrepareStage = @'
set -eu
umask 077
test ! -e /home/debian/docnelo-web-branding-r2-b046e5d8256d
mkdir -m 700 /home/debian/docnelo-web-branding-r2-b046e5d8256d
'@
$PrepareStage | ssh "$VpsTarget" 'sh -s'
if ($LASTEXITCODE -ne 0) { throw 'Staging non neuf : arret, aucune fusion' }
$Files = @(Get-ChildItem -LiteralPath $Payload -File | ForEach-Object { $_.FullName })
scp @Files "${VpsTarget}:${RemoteStage}/"
if ($LASTEXITCODE -ne 0) { throw 'Transfert prive R2 en echec' }
```

Le staging 0700 protège l'archive dès réception. Aucun conteneur n'est chargé ou démarré par cette phase. La vérification SHA ci-dessous doit précéder toute utilisation des scripts ou de l'image reçus.

## 2. Intégrité et précontrôles VPS en lecture seule

Sur Debian, dans un shell Bash dédié :

```bash
set -euo pipefail
umask 077
INCOMING=/home/debian/docnelo-web-branding-r2-b046e5d8256d
PROOF=/home/debian/docnelo-web-branding-r2-b046e5d8256d.operator-proof.json
APP_ROOT=/opt/documind-public-beta/public-beta-candidate-20261030T234818Z
D=(docker --host unix:///var/run/docker.sock)
cd "$INCOMING"
sha256sum SHA256SUMS
# Comparer avec l'empreinte conservee sur Windows AVANT de poursuivre.
sha256sum --check --strict SHA256SUMS
chmod 600 "$INCOMING/web-r2.tar"
python3 -B collect_preflight.py --output "$PROOF"
```

collect_preflight inspecte le Docker local et GET HTTPS /bff/auth/options, sans lancer de commande applicative dans les conteneurs. Il ne fait aucun up/start/stop et ne modifie aucune configuration. Seul un nouveau fichier privé de preuve est créé, sans écraser une preuve antérieure.

Exiger :

- trois conteneurs documind-public-beta-db-1/api-1/web-1 healthy et projet documind-public-beta ;
- Web toujours sur **sha256:9301710690ea35cd3b81db3acf48deb38638c6e7fa3c29dac77756d60025f487**, plateforme linux/amd64 ;
- fichiers Compose actifs appartenant à la release attendue, registration-gate inclus s'il est actif ;
- mode d'inscription connu et aucune inscription publique disponible ; versions/URLs juridiques conservées pour comparaison ;
- empreinte des paramètres effectifs de chaque conteneur : HostConfig, paramètres Config, variables Env hachées sans sortie de leurs valeurs, labels projet/service, montages et réseaux.

Les paramètres Env complets, tokens, corps de réponse et exceptions Docker ne sont pas affichés. PUBLIC_LEGAL_READY peut être constaté dans la preuve mais n'est jamais défini ou modifié. Une erreur HTTP/réseau n'est pas interprétée comme « inscriptions fermées ».

Si le précontrôle échoue, arrêter. Diagnostics autorisés en lecture seule :

```bash
"${D[@]}" inspect --format '{{.Name}} {{.Image}} {{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}' \
  documind-public-beta-db-1 documind-public-beta-api-1 documind-public-beta-web-1
ACTIVE_ID=$("${D[@]}" inspect --format '{{.Image}}' documind-public-beta-web-1)
"${D[@]}" image inspect --format '{{.Id}} {{.Os}}/{{.Architecture}} {{json .RepoDigests}}' "$ACTIVE_ID"
"${D[@]}" inspect --format '{{index .Config.Labels "com.docker.compose.project.config_files"}}' documind-public-beta-web-1
"${D[@]}" inspect --format '{{index .Config.Labels "com.docker.compose.version"}}' documind-public-beta-web-1
"${D[@]}" compose version
```

Si l'image n'est plus 930171…, refaire une qualification depuis cette autre référence, sans modifier opportunément l'ID attendu du collecteur. Si les chemins/overrides diffèrent, les faire revoir ; ne pas en retirer pour faire passer le contrôle. Ne jamais envoyer un inspect complet contenant Env ou les fichiers .env.

La preuve peut être récupérée pour revue privée, hors du payload scellé :

```powershell
scp "${VpsTarget}:/home/debian/docnelo-web-branding-r2-b046e5d8256d.operator-proof.json" "$R2\operator-proof-vps.json"
if ($LASTEXITCODE -ne 0) { throw 'Collecte de preuve en echec' }
```

## 3. Nouvelle release d'outillage/métadonnées, après décision opérateur

Ne copier aucun fichier applicatif sur la release actuelle. Le nouveau dossier conserve uniquement la livraison et ses preuves ; APP_ROOT et les .env restent inchangés, aucun lien current n'est basculé.

```bash
RELEASE=/opt/documind-public-beta/branding-docnelo-web-r2-b046e5d8256d
BASE_ID=sha256:9301710690ea35cd3b81db3acf48deb38638c6e7fa3c29dac77756d60025f487
NEW_ID=sha256:ebdbc7fba1c61c03349088ca093470c78eec9dd91c5e2aa92ab1d8c0db5be362
NEW_TAG=documind-public-beta-frontend:docnelo-r2-b046e5d8256d
ROLLBACK_TAG=documind-public-beta-frontend:r2-rollback-9301710690ea

sudo mkdir -m 0700 "$RELEASE"
sudo chown debian:debian "$RELEASE"
cp -a "$INCOMING"/. "$RELEASE"/
cd "$RELEASE"
sha256sum --check --strict SHA256SUMS
chmod 600 "$RELEASE/web-r2.tar"

if PRESENT_ID=$("${D[@]}" image inspect "$NEW_TAG" --format '{{.Id}}' 2>/dev/null); then
  test "$PRESENT_ID" = "$NEW_ID"
else
  "${D[@]}" load --input "$RELEASE/web-r2.tar"
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

mkdir refuse une release existante ; les contrôles de tag refusent un écrasement d'une image différente. Le tag d'origine frontend:2026-10-31 reste intact. Aucun pull global ou registre n'est utilisé. L'ancienne image doit être conservée pour rollback ; aucun prune ou nettoyage n'est inclus.

## 4. Configuration inchangée et overrides actifs

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

check-compose vérifie que seule image/pull_policy Web diffère, que tous les autres paramètres et services restent identiques, que l'environnement résolu corresponde à l'actif, que le fingerprint n'ait pas dérivé depuis la collecte et que le hash Compose Web corresponde au label de déploiement courant. Les changements de labels/ressources/réseaux/configurations ne doivent pas être réconciliés pendant ce lot.

Si le hash ne correspond pas, arrêter : vérifier les fichiers et la version de Compose, sans éditer de secret ni contourner la garde. Diagnostics sans rendu brut de configuration :

```bash
"${BASE[@]}" config --hash web
"${D[@]}" inspect --format '{{index .Config.Labels "com.docker.compose.config-hash"}}' documind-public-beta-web-1
```

Les anciennes preuves R1 ne sont pas acceptables : elles concernent une autre image et ne contiennent pas les fingerprints R2. RECOVERY_CONTROL_FILE est seulement transmis au processus de résolution Compose ; le latch existant n'est ni écrit ni changé d'état. Ne pas recopier un .env.example et ne pas définir PUBLIC_LEGAL_READY=true ou REGISTRATION_MODE=public.

## 5. Bascule Web seule proposée

Uniquement après revue du dossier réel et choix explicite de la fenêtre opérateur :

```bash
python3 -B "$RELEASE/check-compose.py" --proof "$PROOF" --release "$RELEASE"
"${BASE[@]}" -f "$RELEASE/web.r2.override.yaml" up -d --no-deps --no-build --pull never web
test "$("${D[@]}" inspect --format '{{.Image}}' documind-public-beta-web-1)" = "$NEW_ID"
"${D[@]}" inspect --format '{{.Name}} {{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}' \
  documind-public-beta-db-1 documind-public-beta-api-1 documind-public-beta-web-1
```

Une brève interruption Web est possible sur cette instance unique. Attendre healthy, avec limite opérateur de deux minutes, sans restart supplémentaire. Le retour de up -d ne suffit pas. Aucune commande API/DB/lifecycle-init, migration, Traefik, Restic ou volume n'est prévue.

Après stabilisation :

```bash
python3 -B "$RELEASE/verify-state.py" --proof "$PROOF" --expected-web-id "$NEW_ID"
```

Le contrôle exige même ID/image/StartedAt DB/API, paramètres Docker effectifs, montages et réseaux stables, services healthy, bon ID Web, modes/versions/URLs juridiques inchangés et absence d'ouverture publique. Les adresses/identités d'endpoints automatiquement allouées et la référence d'image Web peuvent changer ; pas les paramètres utilisateur.

Recette opérateur : HTTPS au domaine actuel, logo/favicon/couleurs, session de test existante, navigation, lecture d'un document de test déjà présent et liens/version des pages juridiques. Aucun E2E de création/suppression contre le VPS, aucun email ou nouvel appel IA comme sonde. Le téléchargement BFF reste 404 comme sur la référence : ne pas ouvrir une route ou supprimer les liens pendant cette recette.

Conserver l'override R2 dans le registre opérateur pour les prochains up web. Un up utilisant seulement le Compose de base pourrait remettre l'ancienne image puisque les .env sont volontairement inchangés. Les cookies de session gardent leur nom ; un CSRF en vol peut nécessiter un réessai au redémarrage Web.

## 6. Rollback proposé vers 930171…

Si la recette échoue, ne pas tenter de « réparer » l'API, les données, les inscriptions ou le latch dans ce lot. Décider du retour de l'image Web :

```bash
test "$("${D[@]}" image inspect "$ROLLBACK_TAG" --format '{{.Id}}')" = "$BASE_ID"
"${BASE[@]}" -f "$RELEASE/web.rollback.yaml" up -d --no-deps --no-build --pull never web
test "$("${D[@]}" inspect --format '{{.Image}}' documind-public-beta-web-1)" = "$BASE_ID"
# Attendre healthy, sans redemarrer API/DB.
python3 -B "$RELEASE/verify-state.py" --proof "$PROOF" --expected-web-id "$BASE_ID"
```

Dans un nouveau shell, relire les variables et reconstruire BASE depuis la même preuve. check-compose est réservé à l'avant-bascule sur la référence 930171… ; verify-state sert à l'après-bascule ou au rollback. Si des paramètres ont dérivé sur disque ou par une action externe, arrêter et diagnostiquer ; ne pas employer cette livraison pour les réinitialiser automatiquement.

Il n'y a aucun rollback de base ou restauration de sauvegarde : les données, .env, migrations et Restic ne sont pas modifiés. Conserver toutes les images, releases et preuves. **Ne jamais revenir à l'image historique R1 f1585594… pour ce rollback.**

## Verdict

**GO local pour R2.** Il ne vaut pas autorisation de déploiement : précontrôles VPS, décision opérateur et vérifications après bascule restent obligatoires. Aucune commande de livraison, bascule ou rollback n'a été exécutée par l'agent sur le VPS.
