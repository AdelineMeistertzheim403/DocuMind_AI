# Lifecycle 10 — Procédure opérateur de preuve H / empreinte déployée

Commandes proposées, jamais exécutées sur le VPS par Codex. Aucun service n’est démarré, arrêté ou recréé. Aucun `.env`, label ou fichier scellé n’est modifié.

## Livraison et vérification

PowerShell local, après renseignement de l’hôte validé :

```powershell
$VpsHost = Read-Host 'Hôte SSH Public Beta validé'
$Bundle = (Resolve-Path '.\deliveries\docnelo-lifecycle10-hash-diagnostic-r1').Path
(Get-FileHash (Join-Path $Bundle 'SHA256SUMS') -Algorithm SHA256).Hash.ToLowerInvariant()
ssh "debian@$VpsHost" 'test ! -e /home/debian/docnelo-lifecycle10-hash-diagnostic-r1'
if ($LASTEXITCODE -ne 0) { throw 'Destination présente ou SSH indisponible' }
scp -r "$Bundle" "debian@${VpsHost}:/home/debian/"
if ($LASTEXITCODE -ne 0) { throw 'Transfert incomplet' }
```

Noter l’empreinte du manifeste localement, puis la comparer sur le VPS par un canal opérateur de confiance. Ne pas transférer le binaire de qualification local, l’ensemble du dépôt ou un relevé contenant des secrets.

```bash
set -euo pipefail
umask 077
DIAG=/home/debian/docnelo-lifecycle10-hash-diagnostic-r1
R1=/opt/documind-public-beta/docnelo-lifecycle10-compose-guard-r1
PARENT=/opt/documind-public-beta/lifecycle10-8b11d4daf47b
AUDIT=/opt/documind-public-beta/compose-review-r1-20261031T183619Z/audit.json
cd "$DIAG"
sha256sum SHA256SUMS
# Comparer avec l'empreinte relevée sur le poste local avant de poursuivre.
sha256sum --check --strict SHA256SUMS
test "$(sha256sum "$R1/SHA256SUMS" | cut -d' ' -f1)" = \
  56c448a98858cc54e226c298bde042d159451c12b2380a5535ac3a7d45dc1431
(cd "$R1" && sha256sum --check --strict SHA256SUMS)
test -f "$AUDIT"
python3 --version
python3 -B "$DIAG/diagnose_hash.py" --help
```

Si l’audit réel a un autre nom de fichier, renseigner son chemin physique après vérification ; ne jamais recréer un audit à partir des seuls résultats collés dans un message. Vérifier aussi l’emplacement physique du parent si différent du nom prévu ci-dessus. Python 3.11 convient ; aucune dépendance pip supplémentaire n’est nécessaire.

## Diagnostic sans mutation

Utiliser la même session d’interpolation que l’audit initial, les mêmes deux fichiers d’environnement et le même ordre d’overrides. Ne pas activer `set -x` et ne pas afficher l’environnement. Le contrôleur fixe le socket Docker local, le projet et le répertoire physique de l’application.

```bash
export RECOVERY_CONTROL_FILE=/opt/documind-public-beta/recovery-state.json
FILE_TEXT=$(python3 -B - "$AUDIT" <<'PY'
import json,pathlib,sys
p=json.load(open(sys.argv[1]))
files=p['selected_compose_files']
assert files and len(files)==len(set(files))
for name in files:
    f=pathlib.Path(name)
    assert f.is_absolute() and f.resolve()==f and f.is_file()
    assert f.is_relative_to('/opt/documind-public-beta')
print('\n'.join(files))
PY
)
mapfile -t FILES <<< "$FILE_TEXT"
ARGS=()
for file in "${FILES[@]}"; do ARGS+=(--compose-file "$file"); done
# Relire la liste et son ordre : l'override Web R2 doit être conservé.
printf '%s\n' "${FILES[@]}"
OUT=$(mktemp -d /home/debian/docnelo-hash-evidence.XXXXXXXX)
if (set -C; python3 -B "$DIAG/diagnose_hash.py" \
  --r1 "$R1" --parent "$PARENT" --audit "$AUDIT" "${ARGS[@]}" \
  > "$OUT/diagnostic.json"); then
  RC=0
else
  RC=$?
fi
printf 'Code diagnostic : %s\n' "$RC"
python3 -B - "$OUT/diagnostic.json" <<'PY'
import json,sys
p=json.load(open(sys.argv[1]))
assert p.get('diagnostic_complete') is True, 'Collecte incomplète : arrêter'
print(json.dumps(p,indent=2)) # Valeurs d'environnement absentes du rapport.
assert p['audit_snapshot_matches'] is True, 'Audit ancien ou contexte différent : arrêter'
assert p['r1_exact_two_field_injection'] is True, 'Injection r1 non reproduite : arrêter'
assert p['rendered_H_roundtrip_hashes_match'] is True, 'Rejeu non fidèle : ne pas exploiter les hypothèses'
assert p['status']=='NO-GO' and p['opening_authorized'] is False
PY
```

Le code retour **2 est attendu même lorsque la collecte est complète** : cet outil n’est pas un garde d’autorisation. `diagnostic_complete=false` indique au contraire un relevé inexploitable. Il ne faut pas convertir son retour en succès de déploiement.

Le rapport vérifie que les hashes C/H/labels sont toujours ceux du premier audit. Une différence invalide la comparaison temporelle : conserver les deux relevés et reconstituer le contexte exact, sans éditer les résultats précédents.

## Lecture de la preuve

1. `public_fields_explicit_in_hash_C` indique si les deux champs existaient dans les déclarations explicites de C. Deux `false`, associés à `api_has_env_file_in_hash_view=true` et à l’apparition de ces deux chemins dans `hash_view_C_to_H_changed_paths`, établissent que r1 ajoute des déclarations au modèle haché.
2. `hashes.C.api != hashes.D_deployed_labels.api` reste une question distincte. Identifier une explication initiale avant toute adaptation du garde.
3. `observational_hypotheses` n’est exploitable que si le rejeu de C et H est fidèle. Chaque entrée précise sa `baseline` C ou H. Une entrée `api_matches_deployed=true` et `web_db_hashes_preserved=true` fournit une différence déclarative suffisante pour reproduire D depuis cette base. Examiner ses chemins et retrouver son origine historique. Elle n’est pas approuvée automatiquement.
4. Aucun match signifie seulement que les hypothèses limitées n’expliquent pas le hash. L’outil ne recherche pas des valeurs secrètes ni toutes les combinaisons de champs.

## Retrouver une préimage historique

Rechercher dans les preuves déjà conservées : commande initiale, ordre des overrides, source exacte du Compose et son commit, éventuel rendu non interpolé privé, contexte de plateforme/compatibilité et fichiers d’environnement historiques. Ne pas scanner ni restaurer automatiquement les sauvegardes dans le volume actif. Faire extraire les archives de configuration par une procédure séparée, isolée et autorisée si nécessaire.

Un rendu ordinaire `compose config --format json` mélange les valeurs d’`env_file` aux variables explicites et ne suffit pas. La référence attendue par `--historical-model` est un **modèle d’entrée Compose JSON** conservant les déclarations `env_file`, les chemins corrects et les expressions/échappements compatibles avec le contexte de rejeu. Un modèle obtenu par `config --no-interpolate --no-env-resolution --format json` convient comme entrée à qualifier, sans être réputé historique par son seul format. Les chemins d’origine doivent rester résolus par le même `--project-directory` ; un déplacement de copie ne doit pas devenir un changement de chemin haché.

Conserver cette référence hors bundle/Git dans un dossier privé 0700, fichier 0600. Elle peut contenir des secrets ; ne pas l’afficher, la joindre ou en copier les valeurs dans un ticket. Le contexte d’interpolation actuel doit être justifié pour ce rejeu ; si des valeurs historiques d’interpolation manquent, le résultat reste non démontré.

Avec un fichier privé déjà vérifié et identifié par l’opératrice :

```bash
HISTORICAL_MODEL=/CHEMIN/PRIVE/DE/LA/REFERENCE_HISTORIQUE_VERIFIEE.json
test -f "$HISTORICAL_MODEL"
if (set -C; python3 -B "$DIAG/diagnose_hash.py" \
  --r1 "$R1" --parent "$PARENT" --audit "$AUDIT" "${ARGS[@]}" \
  --historical-model "$HISTORICAL_MODEL" > "$OUT/with-historical-reference.json"); then
  REF_RC=0
else
  REF_RC=$?
fi
printf 'Code diagnostic avec référence : %s\n' "$REF_RC"
```

Exiger collecte complète, snapshot identique, rejeu fidèle, `historical_reference.all_hashes_match_deployed=true`, provenance vérifiée et revue des `changed_paths_from_H`. Le moteur Compose calcule les hashes : aucun calcul Python approximatif ni remplacement du label Docker n’est admis. Les chemins JSON de cette comparaison pointent vers les différences d’entrée ; leurs effets après interpolation restent à revoir dans le contexte historique.

## Suite et retour arrière

Rester en NO-GO jusqu’à explication complète de C/D et H/D. Si les deux champs n’étaient historiquement que dans `env_file`, un futur correctif devra séparer la preuve du modèle historique et la conservation runtime approuvée ; il ne devra plus exiger naïvement que leur ajout explicite soit identique au modèle historique. Cette nouvelle conception demandera une release distincte, des tests et une revue. Aucun patch de r1 n’est fourni ou appliqué par cette procédure.

Conserver tous les dossiers de preuves. Puisque rien n’a été déployé ou migré, le retour arrière consiste à arrêter le diagnostic : aucun service à restaurer, aucune modification de `.env`, quota, label, clé ou volume à annuler. Aucun nettoyage destructif n’est proposé. Les empreintes et garde-fous existants restent obligatoires.
