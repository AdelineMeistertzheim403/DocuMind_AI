# Lifecycle 10 — Runbook actualisé avant migration fermée

Toutes les commandes ci-dessous sont proposées à l’opératrice. Aucune n’a été exécutée sur le VPS par Codex. Ce runbook traite le NO-GO Compose ; il n’autorise ni migration ni bascule. Ne pas relancer les anciennes étapes de déploiement tant que les critères de sortie ne sont pas satisfaits.

## 1. Transférer uniquement la nouvelle release d’outillage

PowerShell local ; renseigner le véritable hôte sans l’inventer :

```powershell
$VpsHost = Read-Host 'Hôte SSH Public Beta validé'
$Bundle = (Resolve-Path '.\deliveries\docnelo-lifecycle10-compose-guard-r1').Path
(Get-FileHash (Join-Path $Bundle 'SHA256SUMS') -Algorithm SHA256).Hash.ToLowerInvariant()
# Noter cette empreinte par un canal opérateur de confiance.
ssh "debian@$VpsHost" 'test ! -e /home/debian/docnelo-lifecycle10-compose-guard-r1'
if ($LASTEXITCODE -ne 0) { throw 'Destination déjà présente ou SSH indisponible' }
scp -r "$Bundle" "debian@${VpsHost}:/home/debian/"
if ($LASTEXITCODE -ne 0) { throw 'Transfert incomplet' }
```

Ne transférer ni worktree complet, `.env`, Docker archive, clé, données ni images supplémentaires. La candidate déjà chargée et le bundle parent déjà scellé restent en place.

## 2. Installer dans un nouveau répertoire, sans écrasement

Sur le VPS, session opératrice dédiée, shell Bash. `PARENT` doit correspondre au véritable répertoire contenant le bundle parent scellé ; le nom ci-dessous est celui prévu par son runbook. S’il diffère, faire vérifier son emplacement physique et son manifeste, sans recopier les artefacts pour fabriquer une nouvelle référence.

```bash
set -euo pipefail
umask 077
INCOMING=/home/debian/docnelo-lifecycle10-compose-guard-r1
FIX=/opt/documind-public-beta/docnelo-lifecycle10-compose-guard-r1
PARENT=/opt/documind-public-beta/lifecycle10-8b11d4daf47b
APP_ROOT=/opt/documind-public-beta/public-beta-candidate-20261030T234818Z
D=(docker --host unix:///var/run/docker.sock)
test -d "$PARENT"
test ! -e "$FIX"
cd "$INCOMING"
sha256sum SHA256SUMS
# Comparer manuellement avec l'empreinte notée localement avant de poursuivre.
sha256sum --check --strict SHA256SUMS
test "$(sha256sum "$PARENT/SHA256SUMS" | cut -d' ' -f1)" = \
  9d077ca43a8995429e6a471f30e9cd12d7724292a56dd6a74332c4f0954497c5
(cd "$PARENT" && sha256sum --check --strict SHA256SUMS)
sudo mkdir -m 0700 "$FIX"
sudo chown debian:debian "$FIX"
cp -a "$INCOMING"/. "$FIX"/
(cd "$FIX" && sha256sum --check --strict SHA256SUMS)
python3 --version
# Exiger l'interpréteur opérateur Python 3.11 validé ; préciser son chemin si nécessaire.
python3 -B "$FIX/check_closed_compose.py" --help
```

Ce correctif n’a pas de dépendance pip supplémentaire. Il n’installe pas Python, ne charge aucune image et ne modifie aucun outil existant. Ne pas utiliser `cp` sur une release déjà présente. Le dossier d’arrivée et FIX doivent être distincts des releases existantes et de Production.

## 3. Précontrôles en lecture seule

```bash
"${D[@]}" inspect --format '{{.Name}} image={{.Image}} user={{.Config.User}} health={{.State.Health.Status}} started={{.State.StartedAt}}' \
  documind-public-beta-db-1 documind-public-beta-api-1 documind-public-beta-web-1
"${D[@]}" image inspect documind-public-beta-backend:capacity10-8b11d4daf47b \
  --format '{{.Id}} {{.Os}}/{{.Architecture}}'
"${D[@]}" compose version
"${D[@]}" inspect --format '{{.Name}} compose={{index .Config.Labels "com.docker.compose.version"}} hash={{index .Config.Labels "com.docker.compose.config-hash"}} files={{index .Config.Labels "com.docker.compose.project.config_files"}}' \
  documind-public-beta-db-1 documind-public-beta-api-1 documind-public-beta-web-1
"${D[@]}" inspect --format '{{.Created}}' documind-public-beta-api-1
stat --format='%y %n' "$APP_ROOT/.env.public-beta"
```

Exiger les IDs API 4aa850…, candidate 32a151…, Web ebdbc7…, linux/amd64, services healthy, 0007/quota zéro fermé/limite cinq/disabled/latch ready selon le relevé candidat déjà obtenu. Si une version Compose diffère de celle des labels, arrêter pour revue ; ne pas modifier les labels ou installer une version au hasard.

Ne jamais afficher `docker inspect` complet, `compose config` complet, `printenv`, `cat .env` ou les clés. Pas de `set -x`. Les valeurs des champs publics sont traitées comme privées dans cette procédure.

## 4. Sélectionner tous les fichiers Compose actifs

```bash
export RECOVERY_CONTROL_FILE=/opt/documind-public-beta/recovery-state.json
unset COMPOSE_FILE COMPOSE_PROJECT_NAME COMPOSE_PROFILES
ACTIVE_LABELS=$("${D[@]}" inspect --format '{{index .Config.Labels "com.docker.compose.project.config_files"}}' \
  documind-public-beta-api-1 documind-public-beta-web-1 documind-public-beta-db-1)
ORDERED_FILES=$(printf '%s\n' "$ACTIVE_LABELS" | python3 -c '
import sys
rows=sys.stdin.read().splitlines()
assert len(rows)==3 and all(rows)
seen=[]
for row in rows:
    for value in row.split(","):
        assert value.startswith("/opt/documind-public-beta/")
        if value not in seen: seen.append(value)
print("\n".join(seen))
')
mapfile -t ACTIVE_FILES <<< "$ORDERED_FILES"
BASE=("${D[@]}" compose --project-directory "$APP_ROOT" -p documind-public-beta
  --env-file "$APP_ROOT/.env.public-beta" --env-file "$APP_ROOT/.env.public-beta.images")
CHECK_FILES=()
for file in "${ACTIVE_FILES[@]}"; do
  test -f "$file"
  BASE+=(-f "$file")
  CHECK_FILES+=(--compose-file "$file")
done
printf '%s\n' "${ACTIVE_FILES[@]}"
```

L’opératrice revoit l’ordre et l’union obtenue, notamment l’override Web R2. Le garde vérifie que chaque séquence active est incluse dans cet ordre. Ne retirer aucun override pour obtenir un PASS. Une ambiguïté d’ordre ou une modification de structure reste un NO-GO.

## 5. Nouveau dossier privé et diagnostic exhaustif

```bash
STATE=/opt/documind-public-beta/compose-review-r1-$(date -u +%Y%m%dT%H%M%SZ)
sudo mkdir -m 0700 "$STATE"
sudo chown debian:debian "$STATE"
# À remplacer par le chemin physique du relevé candidat réellement obtenu.
PROOF_SOURCE=/CHEMIN/ABSOLU/DU/RELEVE_CANDIDATE_EXISTANT.json
test -f "$PROOF_SOURCE"
test ! -e "$STATE/proof.json"
install -m 0600 "$PROOF_SOURCE" "$STATE/proof.json"
if python3 -B "$FIX/check_closed_compose.py" audit \
  --release "$PARENT" "${CHECK_FILES[@]}" --proof "$STATE/proof.json" \
  --state-dir "$STATE" --report "$STATE/audit.json" \
  --private-review "$STATE/public-identity-review.json"; then
  AUDIT_RC=0
else
  AUDIT_RC=$?
fi
printf 'Code diagnostic : %s\n' "$AUDIT_RC"
python3 -B - "$STATE/audit.json" <<'PY'
import json,sys
p=json.load(open(sys.argv[1]))
print(json.dumps(p,indent=2)) # Rapport conçu sans valeurs d'environnement.
assert p['status'] in ('ALIGNED','REVIEW_REQUIRED'), 'NO-GO: arrêter avant préparation'
assert all(g['status']=='passed' for g in p['gates'])
assert all(p['historical_hash_matches_deployed'].values())
assert p['opening_authorized'] is False
PY
```

`REVIEW_REQUIRED` reste un refus de poursuivre automatiquement, même avec zéro contrôle technique en échec. Examiner `legacy_first_failure` pour la première exception **réelle** du garde scellé, puis toutes les lignes de `gates` et les trois jeux d’empreintes. `effective_environment_drift` est attendu d’après les constats, mais ne doit pas être inventé dans le dossier opérateur. Une première erreur antérieure prévaut.

Si H/API n’est pas égal au label déployé, conserver le rapport et arrêter : les deux variables ne suffisent pas à expliquer la dérive. Rechercher alors fichiers/ordre/valeurs/version Compose et paramètres effectifs sans changer les attentes. Aucune édition de label, référence, `.env`, clé ou magasin n’est autorisée.

## 6. Revue et approbation explicite

Examiner les anciennes/nouvelles valeurs dans `public-identity-review.json` depuis un éditeur privé. Ne pas les envoyer dans un ticket ou un journal. Justifier pourquoi l’identité actuellement servie doit être conservée pour cette intervention fermée. Si les nouvelles coordonnées doivent être adoptées maintenant, arrêter ce lot et préparer un changement distinct.

En présence d’une différence :

```bash
test ! -e "$STATE/approval.json"
cp --no-clobber "$STATE/approval.template.json" "$STATE/approval.json"
# Intervention humaine : remplir operator/reason et approved=true seulement après revue.
# Ne pas modifier binding, variables ou decision=preserve_active.
nano "$STATE/approval.json"
```

Il n’existe aucune commande d’approbation automatique dans le bundle. Une différence n’est jamais autorisée parce que son nom figure dans une allowlist. En l’absence de différence, l’approbation de ces deux champs n’est pas requise ; les contrôles techniques restent tous obligatoires.

## 7. Préparer le freeze, puis requalifier

```bash
APPROVAL_ARGS=()
if test -f "$STATE/approval.json"; then APPROVAL_ARGS=(--approval "$STATE/approval.json"); fi
FREEZE="$STATE/api.historical-env.override.json"
python3 -B "$FIX/check_closed_compose.py" prepare \
  --release "$PARENT" "${CHECK_FILES[@]}" --proof "$STATE/proof.json" \
  --state-dir "$STATE" --report "$STATE/prepare.json" \
  "${APPROVAL_ARGS[@]}" --freeze "$FREEZE"
python3 -B "$FIX/check_closed_compose.py" check \
  --release "$PARENT" "${CHECK_FILES[@]}" --proof "$STATE/proof.json" \
  --state-dir "$STATE" --report "$STATE/final-check.json" \
  "${APPROVAL_ARGS[@]}" --freeze "$FREEZE"
python3 -B - "$STATE/final-check.json" <<'PY'
import json,sys
p=json.load(open(sys.argv[1]))
assert p['status']=='passed' and p['live_proof_revalidated'] is True
assert p['opening_authorized'] is False
assert all(g['status']=='passed' for g in p['gates'])
print('Précontrôle fermé qualifié ; intervention et ouverture non autorisées par ce résultat.')
PY
test ! -e "$STATE/runtime-before.json"
python3 -B "$PARENT/operator_runtime.py" capture --proof "$STATE/runtime-before.json"
BASE_H=("${BASE[@]}" -f "$FREEZE")
```

`check` crée un conteneur one-off de la candidate chargée, sans dépendances, sans pull, avec uniquement le probe scellé passé à Python par stdin. Le probe n’importe pas `backend.main`, n’exécute ni serveur, worker, SMTP ou migration ; SQL est en READ ONLY et les témoins sont authentifiés par les lecteurs existants. Les services actifs restent healthy. Si ce probe échoue ou diffère du relevé approuvé, arrêter. Ne pas corriger le JSON pour obtenir un succès.

La capture runtime parent conserve les deux valeurs publiques dans les fingerprints. Elle reste obligatoire pour toute future intervention. Maintenir une fenêtre exclusive après contrôle ; aucune garantie de verrouillage global Docker n’est fournie. Une modification après approbation impose un nouvel audit et une nouvelle approbation dans un dossier distinct. Aucun fichier de cette procédure ne doit être écrasé pour rejouer un échec.

## 8. Critères de sortie et raccord au déploiement existant

Pour préparer une fenêtre de migration fermée, conserver ensemble : diagnostic réel et sa première erreur, tous les gates passés, H identique aux trois labels déployés, revue humaine justifiée des différences, approbation liée au relevé, freeze exact, contrôle final avec preuve fraîche, fingerprint initial et sauvegarde/restauration indépendante approuvées.

**Ce document s’arrête avant la sauvegarde, la migration et la bascule.** Le succès du garde ne les lance jamais. Une nouvelle décision opérateur reste nécessaire pour les étapes correspondantes du runbook parent `DOCNELO_PUBLIC_BETA_10_USERS_API_DEPLOYMENT_RUNBOOK.md` déjà scellé.

Lors de cette future fenêtre, toutes les commandes parent `compose run`, `compose up`, dry-run de capacité et fermeture d’urgence doivent utiliser `BASE_H` au lieu de `BASE`, puis l’override candidat scellé. Cela vaut aussi pour tout outillage qui résout Compose : vérifier son mécanisme d’overrides avant utilisation ; s’il ne conserve pas H et Web R2, arrêter plutôt que modifier ses scripts dans ce lot. Ne pas lancer les anciennes commandes parent sans cette adaptation revue. Aucun lien `current`, fichier `.env`, domaine, nom technique, volume, API active ou Web R2 ne change pendant la présente préparation.

Le contrôle initial zéro/cinq/0007 ne se réutilise pas après migration : ses attentes ne doivent pas être modifiées pour masquer l’évolution des magasins. Le contrôle après une future intervention reste `operator_runtime.py verify` parent, probe candidat et dry-run de capacité selon son runbook. Ne jamais ignorer un fingerprint en échec.

## 9. Retour arrière du correctif et limites

Avant toute migration/bascule : arrêter l’utilisation de FIX et conserver tous les dossiers de preuve. L’API est toujours 4aa850…, Web R2 et DB sont inchangés ; aucun rollback de service, `.env`, clé ou magasin n’est nécessaire. Le garde parent reste disponible et garde son NO-GO d’origine ; ce refus ne doit pas être contourné. Ne pas supprimer FIX, STATE ou le parent.

Après une future utilisation du freeze par Compose : conserver son chemin et son contenu privé ; il sera référencé par les labels du nouveau conteneur. Toute procédure ultérieure doit conserver son inclusion et son ordre.

Après une future migration lifecycle : **aucun retour automatique vers 4aa850…**. Appliquer la stratégie de fermeture compatible dix du runbook parent avec l’image candidate et tous les overrides approuvés. Aucun downgrade SQLite, reset de quota, réécriture de témoin, chmod/chown de clé, nettoyage Docker/Restic ou restauration effaçant les admissions n’est autorisé par ce correctif.

**Verdict : GO pour préparer/livrer le correctif qualifié localement. NO-GO pour migrer ou basculer le VPS sans tous les contrôles opérateur ci-dessus et une décision d’intervention distincte. Aucune ouverture publique autorisée.**
