# Docnelo Public Beta — Livraison API capacité dix, maintien fermé

31 octobre 2026. **Aucune commande VPS de ce document n’a été exécutée.** GO technique local ne vaut ni autorisation d’intervention ni autorisation d’ouverture publique. Le premier déploiement proposé conserve disabled, closed=true, issued_count=0, limite cinq, flags juridiques et latch existants.

## 1. Transfert privé proposé

Ne transférer que payload, jamais api-active.tar, la copie sans tags, les dumps/clé de labo ou les worktrees. Remplacer uniquement l’hôte SSH inconnu :

```powershell
$ReleaseRoot = 'C:\Users\Adeline\Documents\DocuMind_AI\deliveries\docnelo-lifecycle-10-api'
$Payload = Join-Path $ReleaseRoot 'payload'
$VpsTarget = 'debian@REMPLACER_HOTE_SSH'
$RemoteStage = '/home/debian/docnelo-lifecycle10-8b11d4daf47b'
Get-FileHash -Algorithm SHA256 -LiteralPath "$Payload\SHA256SUMS"
# Conserver cette empreinte independamment du transfert.
$Prepare = @'
set -eu
umask 077
test ! -e /home/debian/docnelo-lifecycle10-8b11d4daf47b
mkdir -m 700 /home/debian/docnelo-lifecycle10-8b11d4daf47b
'@
$Prepare | ssh "$VpsTarget" 'sh -s'
if ($LASTEXITCODE -ne 0) { throw 'Staging non neuf : arret' }
$Items = @(Get-ChildItem -LiteralPath $Payload | ForEach-Object { $_.FullName })
scp -r @Items "${VpsTarget}:${RemoteStage}/"
if ($LASTEXITCODE -ne 0) { throw 'Transfert prive en echec' }
```

Le staging 0700 protège l’archive ; aucune publication ou opération Docker ne fait partie du transfert. Vérifier l’empreinte de SHA256SUMS avant d’utiliser les scripts transférés.

## 2. Précontrôles opérateur en lecture seule

Sur Debian, shell Bash dédié :

```bash
set -euo pipefail
umask 077
D=(docker --host unix:///var/run/docker.sock)
INCOMING=/home/debian/docnelo-lifecycle10-8b11d4daf47b
APP_ROOT=/opt/documind-public-beta/public-beta-candidate-20261030T234818Z
PROOF=/home/debian/docnelo-lifecycle10-8b11d4daf47b.before.json
RUNTIME=/home/debian/docnelo-lifecycle10-8b11d4daf47b.runtime-before.json
BASE_ID=sha256:4aa850b6fb8d16b32fd731d94b232b2f817f461892b3f39a28e7557a25a5eb3d
WEB_ID=sha256:ebdbc7fba1c61c03349088ca093470c78eec9dd91c5e2aa92ab1d8c0db5be362
cd "$INCOMING"
sha256sum SHA256SUMS
# Comparer avec Windows AVANT toute utilisation.
sha256sum --check --strict SHA256SUMS
chmod 600 api-capacity10.tar
"${D[@]}" inspect --format '{{.Name}} {{.Image}} {{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}' \
  documind-public-beta-db-1 documind-public-beta-api-1 documind-public-beta-web-1
test "$("${D[@]}" inspect --format '{{.Image}}' documind-public-beta-api-1)" = "$BASE_ID"
test "$("${D[@]}" inspect --format '{{.Image}}' documind-public-beta-web-1)" = "$WEB_ID"
"${D[@]}" image inspect --format '{{.Id}} {{.Os}}/{{.Architecture}}' "$BASE_ID"
"${D[@]}" exec documind-public-beta-api-1 id
"${D[@]}" exec documind-public-beta-api-1 python -B -m alembic current
test ! -e "$PROOF"
if (set -C; "${D[@]}" exec -i documind-public-beta-api-1 python -B - < probe_status.py > "$PROOF"); then
  echo 'Diagnostic herite conserve ; qualification candidate toujours requise.'
else
  echo 'Diagnostic herite non qualifie : ne pas migrer ; revue et probe compatible obligatoires.'
fi
python3 -B operator_runtime.py capture --proof "$RUNTIME"
"${D[@]}" stats --no-stream documind-public-beta-db-1 documind-public-beta-api-1 documind-public-beta-web-1
df -h /opt/documind-public-beta
cat /opt/documind-public-beta/recovery-state.json
```

Exiger healthy, API toujours 4aa850…, Web toujours R2, app UID/GID approuvés (modèle testé : 1000/1000), migration 0007, quota fermé/zéro, mode disabled/limite cinq, IA/demo/legacy/synthétique désactivés, latch ready sans réécriture et empreintes de modules correspondant à la référence. La cohérence des magasins sera obligatoirement qualifiée par le probe candidate avant migration ; un diagnostic hérité négatif n’est jamais converti artificiellement en succès. Ne jamais envoyer inspect complet/Env, .env, liens de vérification ou clés dans un ticket.

probe_status vérifie aussi la cohérence observée du témoin/ancre ; il n’autorise pas une reprise. **La référence héritée peut refuser le modèle root:app sous ascendance app-owned** : si ce probe refuse pour cette raison, arrêter ce chemin et faire consigner la revue opérateur des propriétaires, modes et consommateurs du volume. Ne pas changer les clés, permissions ou latch pour obtenir un succès, ni falsifier le JSON. Le chemin de diagnostic compatible ci-dessous doit alors être revu explicitement avant de poursuivre ; les autres causes de refus restent des NO-GO.

Les fingerprints ne stockent pas les variables secrètes : seuls leurs hashes avec les autres paramètres effectifs sont conservés. Ils exigent après intervention mêmes paramètres Docker, volumes et réseaux ; DB sans redémarrage, Web même conteneur/image (un stop/start de sauvegarde est permis), API sur l’ID candidat.

## 3. Préserver tous les Compose actifs

Lire les labels des **deux** services : l’override Web R2 doit rester dans la résolution, même s’il n’apparaît pas dans le vieux label API.

```bash
"${D[@]}" inspect --format '{{index .Config.Labels "com.docker.compose.project.config_files"}}' documind-public-beta-api-1
"${D[@]}" inspect --format '{{index .Config.Labels "com.docker.compose.project.config_files"}}' documind-public-beta-web-1
"${D[@]}" inspect --format '{{index .Config.Labels "com.docker.compose.project.working_dir"}}' documind-public-beta-api-1
"${D[@]}" compose version
mapfile -t ACTIVE_FILES < <("${D[@]}" inspect --format '{{index .Config.Labels "com.docker.compose.project.config_files"}}' documind-public-beta-web-1 | python3 -c 'import sys; print("\n".join(sys.stdin.read().strip().split(",")))')
test "${#ACTIVE_FILES[@]}" -gt 0
export RECOVERY_CONTROL_FILE=/opt/documind-public-beta/recovery-state.json
unset COMPOSE_FILE COMPOSE_PROJECT_NAME
BASE=("${D[@]}" compose --project-directory "$APP_ROOT" -p documind-public-beta
  --env-file "$APP_ROOT/.env.public-beta" --env-file "$APP_ROOT/.env.public-beta.images")
CHECK_FILES=()
for file in "${ACTIVE_FILES[@]}"; do
  test -f "$file"
  BASE+=(-f "$file")
  CHECK_FILES+=(--compose-file "$file")
done
```

Revoir l’ordre, les chemins physiques et l’inclusion de tous les fichiers API/Web. Si des overrides API manquent, arrêter et faire revoir la liste complète ; ne pas les supprimer pour faire passer le contrôle. RECOVERY_CONTROL_FILE est une variable du processus de résolution ; aucun fichier de latch n’est modifié.

## 4. Installer une nouvelle release après décision d’intervention

```bash
RELEASE=/opt/documind-public-beta/lifecycle10-8b11d4daf47b
NEW_TAG=documind-public-beta-backend:capacity10-8b11d4daf47b
NEW_ID=sha256:32a1516206d9e648e3741b54dc0543c0b455f22cdf676e7d69d9a971e1f4213d
sudo mkdir -m 0700 "$RELEASE"
sudo chown debian:debian "$RELEASE"
cp -a "$INCOMING"/. "$RELEASE"/
cd "$RELEASE"
sha256sum --check --strict SHA256SUMS
if PRESENT=$("${D[@]}" image inspect "$NEW_TAG" --format '{{.Id}}' 2>/dev/null); then
  test "$PRESENT" = "$NEW_ID"
else
  "${D[@]}" load --input "$RELEASE/api-capacity10.tar"
fi
test "$("${D[@]}" image inspect "$NEW_TAG" --format '{{.Id}}')" = "$NEW_ID"
test "$("${D[@]}" image inspect "$NEW_TAG" --format '{{.Os}}/{{.Architecture}}')" = linux/amd64
```

mkdir refuse une release existante ; le tag ne peut pas écraser une image différente. Le garde ci-dessous exige l’état initial fermé/zéro, toutes les références/overrides et les hashes Compose actuels, et n’autorise que l’image API/pull_policy et le namespace explicite approuvé. En cas de dérive, arrêter, sans modification opportuniste des paramètres attendus. Aucun lien current, fichier .env ou domaine n’est changé.

L’override candidate.closed contient l’image API, pull_policy=never et **LIFECYCLE_AUTHENTICATED_NAMESPACE=documind-public-beta**, namespace du provisionnement publié. Ce dernier remplace la constante locale du lecteur hérité ; il ne réécrit pas l’en-tête signé. Aucun REGISTRATION_MODE, PUBLIC_LEGAL_READY, PUBLIC_REGISTRATION_LIMIT ou latch n’est défini par cet override ; la nouvelle garde opérationnelle reste false par défaut.

### Diagnostic candidate obligatoire, sans démarrage applicatif

Après contrôle indépendant des propriétaires/modes et chargement de l’image vérifiée, la candidate effectue le **probe en lecture seule** dans un conteneur one-off, sans démarrer l’API et sans exécuter la migration. Conserver le relevé initial, ne pas l’écraser. Le producteur de ce nouveau relevé est explicitement la candidate sur les magasins existants, tandis que l’API active reste sur 4aa850… :

```bash
PROOF_COMPAT=/home/debian/docnelo-lifecycle10-8b11d4daf47b.candidate-readonly.json
test ! -e "$PROOF_COMPAT"
(set -C; "${BASE[@]}" -f "$RELEASE/api.candidate.closed.override.yaml" run --rm --no-deps -T --interactive \
  --entrypoint python api -B - < "$RELEASE/probe_status.py" > "$PROOF_COMPAT")
python3 -B "$RELEASE/check_closed_compose.py" --proof "$PROOF_COMPAT" --release "$RELEASE" "${CHECK_FILES[@]}"
PROOF="$PROOF_COMPAT"
```

Ce probe n’importe pas backend.main, ne lance ni worker ni SMTP, effectue la transaction SQL en READ ONLY et ne fait que lire les preuves HMAC, via la barrière partagée déjà existante. Il ne provisionne pas de clé ou magasin. Exiger le quota zéro/fermé, disabled/cinq, flags sûrs, version 0007, clés distinctes dans le répertoire approuvé et cohérence HMAC avec le namespace explicite documind-public-beta. Si le namespace authentifié réel diffère, arrêter pour revue d’une variante qualifiée ; jamais de réécriture d’en-tête ou d’adoption automatique de la valeur trouvée en base. Les empreintes des modules de ce relevé doivent correspondre à la candidate, et non être présentées comme celles de l’ancien processus.

## 5. Sauvegarde avant migration et migration explicite

Uniquement pendant une fenêtre autorisée, utiliser l’orchestrateur V5.1 déjà approuvé avec son interpréteur Python 3.11 existant, le bucket/préfixe vérifiés et la release applicative physique APP_ROOT. Le chemin de cette release d’outillage et les valeurs B2 ne sont pas inventés ici ; les relever dans le dossier opérateur validé.

Commande disponible, à renseigner depuis ces références vérifiées :

```text
PYTHON3_11_VALIDE -B RELEASE_OUTILLAGE_V51/tools/public_beta_backup.py --root /opt/documind-public-beta/public-beta-candidate-20261030T234818Z --expected-bucket BUCKET_PUBLIC_BETA_VALIDE --expected-prefix PREFIXE_PUBLIC_BETA_VALIDE
```

Exiger le répertoire produit par cette capture, V5 complet avec les deux clés, validation hors ligne, snapshot Restic distant confirmé et restauration en laboratoire. Aucun ls -dt, réenregistrement d’ID dépôt, forget/prune ou suppression de capture. L’orchestrateur laisse API/Web arrêtés ; ne pas les redémarrer automatiquement en cas d’échec. PostgreSQL doit rester disponible et healthy. Les copies de configuration peuvent être privées ; aucun affichage de secrets.

Après sauvegarde qualifiée, alors que les inscriptions et services applicatifs sont toujours fermés :

```bash
# Conteneur one-off de la candidate, utilisateur app, mêmes volumes/configurations.
# --no-deps ne lance ni lifecycle-init ni migration Alembic.
"${BASE[@]}" -f "$RELEASE/api.candidate.closed.override.yaml" run --rm --no-deps --entrypoint python api \
  -B -m backend.lifecycle_capacity
# Revoir le dry-run : compteur 0, closed true, état settled ; autorisation d'ouverture false.
"${BASE[@]}" -f "$RELEASE/api.candidate.closed.override.yaml" run --rm --no-deps --entrypoint python api \
  -B -m backend.lifecycle_capacity --execute --confirm MIGRATE-PUBLIC-BETA-CAPACITY-10
```

La première commande n’écrit pas les magasins. La seconde est la migration volontaire future des deux fichiers existants ; elle ne touche ni compteur SQL, clés, anciens témoins, données utilisateur ou latch. Ne jamais lancer lifecycle-init pour simuler une migration. Un schéma/journal/état pending inattendu exige revue ; ne pas convertir WAL ou supprimer des témoins dans cette fenêtre.

## 6. Bascule API seule et contrôles

```bash
"${BASE[@]}" -f "$RELEASE/api.candidate.closed.override.yaml" up -d --no-deps --no-build --pull never api
test "$("${D[@]}" inspect --format '{{.Image}}' documind-public-beta-api-1)" = "$NEW_ID"
# Redemarrer explicitement le conteneur Web existant arrete par la sauvegarde.
"${D[@]}" start documind-public-beta-web-1
test "$("${D[@]}" inspect --format '{{.Image}}' documind-public-beta-web-1)" = "$WEB_ID"
```

Attendre healthy avec une limite opérateur de deux minutes ; un retour up -d ne suffit pas. Les sessions API en mémoire peuvent nécessiter une reconnexion après recréation, sans perte des comptes, consentements ou compteurs persistants. Aucun redémarrage DB, aucune reconstruction Web/API en ligne, aucune migration Alembic ou modification Traefik. En cas d’échec, arrêter la procédure, maintenir les inscriptions fermées et décider manuellement de la récupération.

```bash
python3 -B "$RELEASE/operator_runtime.py" verify --proof "$RUNTIME" --expected-api-image "$NEW_ID"
"${D[@]}" exec -i documind-public-beta-api-1 python -B - < "$RELEASE/probe_status.py"
"${D[@]}" exec documind-public-beta-api-1 python -B -m backend.lifecycle_capacity
```

Exiger API candidate, Web R2 inchangé, DB sans redémarrage, fingerprints identiques hormis l’ajout contrôlé du namespace (sa valeur exacte est vérifiée séparément), version 0007, migration already_migrated=true en dry-run, compteur zéro/closed=true, limite cinq, disabled, nouvelle garde false, flags juridiques/versions et latch identiques au relevé préalable. Comparer aussi les empreintes/identités/modes des clés avant/après dans le dossier privé, sans lire leurs octets dans le terminal.

Le nouvel outillage tooling-v5.2 doit être utilisé pour les captures suivantes : V5.1 ne comprend pas les nouvelles tables. Conserver les anciennes releases et toutes les sauvegardes. La future recette réelle n’utilise que des comptes existants autorisés, sans E2E de création/suppression contre le VPS. Aucune sonde d’inscription ou d’email réel n’est exécutée par ce dossier.

## 7. Réouverture : commande disponible, hors de cette phase

La commande de dry-run est public-registration reopen ; l’exécution requiert --execute --confirm REOPEN-PUBLIC-BETA-10. Elle refuse les flags actuels disabled/limite cinq. Sa future utilisation exige une nouvelle décision humaine, CGU/notice/confidentialité approuvées sous de nouveaux identifiants, SMTP validé, capacité dix et garde opérationnelle explicitement approuvée, durabilité active et synthétique/IA/demo/legacy désactivés.

Ce runbook ne définit aucune commande changeant ces variables vers un état public. Il ne retire aucun libellé brouillon et ne considère pas PUBLIC_LEGAL_READY comme une approbation juridique automatique.

## 8. Fermeture d’urgence et retour arrière compatible dix

Si des admissions ont été ultérieurement autorisées, la commande suivante reste disponible dans le profil standard attesté :

```bash
"${D[@]}" exec documind-public-beta-api-1 python -B -m backend.account_admin public-registration close --execute
"${D[@]}" exec documind-public-beta-api-1 python -B -m backend.account_admin public-registration status
```

Vérifier compteur inchangé et accès des comptes éligibles maintenu. Pour revenir à un service fermé avec la **même image compatible dix**, après décision opérateur :

```bash
"${BASE[@]}" -f "$RELEASE/api.candidate.closed.override.yaml" -f "$RELEASE/api.emergency.closed.override.yaml" \
  up -d --no-deps --no-build --pull never api
```

L’override d’urgence définit uniquement disabled et garde opérationnelle false ; il conserve le plafond déjà configuré, les données, schémas, clés et versions juridiques. Dans un nouveau shell, reconstruire BASE et les constantes depuis les preuves revue ; ne pas perdre l’override Web R2. Les contrôles « état initial zéro/cinq » ne sont pas à réutiliser après de vraies admissions : examiner alors l’état monotone courant, sans changer les attentes pour masquer une incohérence.

**Aucun rollback automatique vers 4aa850… après migration**, et explicitement jamais après la sixième admission. Ne pas faire de downgrade SQLite ni restaurer une base d’avant ouverture pour effacer les comptes. Si la candidate elle-même ne peut servir, conserver fermé et traiter l’incident avec une image de fermeture compatible dix qualifiée ; aucune remise à zéro ou réparation de témoin n’est autorisée par cette procédure. Les cas pending/commit incertain nécessitent une réconciliation indépendante revue, pas un settle manuel improvisé.

Avant migration seulement, si les schémas restent prouvés 1/2 et aucune donnée n’a changé, l’ancienne image peut rester la référence fermée. Après migration, conserver les ajouts et privilégier la fermeture compatible ci-dessus. Aucun outil ou configuration Production n’entre dans ces opérations.

**GO technique local pour préparer une livraison fermée. Précontrôles et décisions opérateur restent obligatoires ; aucune ouverture ou intervention VPS effectuée.**
