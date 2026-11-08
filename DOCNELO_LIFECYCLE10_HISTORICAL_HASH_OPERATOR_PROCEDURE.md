# Lifecycle 10 — Comparaison historique sécurisée sur VPS

Procédure proposée à l’opératrice uniquement. Aucun accès VPS par Codex. Les seules opérations applicatives sont des lectures de métadonnées et de configurations ; aucun changement d’état de service.

## 1. Identifier les pièces, sans les remplacer

Session Bash privée, sans `set -x`, dans le contexte d’interpolation déjà qualifié par r2 :

```bash
set -euo pipefail
umask 077
APP_ROOT=/opt/documind-public-beta/public-beta-candidate-20261030T234818Z
BASE="$APP_ROOT/compose.public-beta.vps.yaml"
BACKUP="$BASE.bak.20261031-005952"
DIAG=/home/debian/docnelo-lifecycle10-hash-diagnostic-r2
PYTHON=/usr/bin/python3.11
D=(docker --host unix:///var/run/docker.sock)
test -f "$BASE"
test -f "$BACKUP"
test -x "$PYTHON"
test "$(sha256sum "$DIAG/SHA256SUMS" | cut -d' ' -f1)" = \
  a85ddae4ba4fce98bf8f21caa4dd37f08fbb566d697dc559e49346d190dd56a3
(cd "$DIAG" && sha256sum --check --strict SHA256SUMS)
sha256sum "$BASE" "$BACKUP"
wc -l "$BASE" "$BACKUP"
stat --printf='%n size=%s inode=%i mtime=%y ctime=%z birth=%w\n' "$BASE" "$BACKUP"
date -u '+heure actuelle UTC=%Y-%m-%dT%H:%M:%SZ'
date '+fuseau actuel=%Z %z'
"${D[@]}" compose version --short
"${D[@]}" inspect --format '{{.Id}} created={{.Created}} started={{.State.StartedAt}} image={{.Image}} reference={{.Config.Image}}' \
  documind-public-beta-api-1
"${D[@]}" inspect --format '{{.Name}} files={{index .Config.Labels "com.docker.compose.project.config_files"}} working_dir={{index .Config.Labels "com.docker.compose.project.working_dir"}} oneoff={{index .Config.Labels "com.docker.compose.oneoff"}}' \
  documind-public-beta-api-1 documind-public-beta-web-1 documind-public-beta-db-1
```

Exiger la même API connue 4aa850…, Compose 2.35.1, projet/répertoire attendus et création annoncée du 31 octobre à 01:11:06Z. Une différence est un nouveau fait à examiner, pas un identifiant à remplacer dans les contrôles.

Comparer les empreintes : export local 300 lignes `15f42bf1f3332d2052c0f304994d0fab455fe86a84c627e4749195123d3c0fd0`, source locale 362 lignes `f46571b71b7a3174c96b15b2848f2b31cdae60339621116eb14be03393dc4ff2`. Ne déduire aucune identité de fichier de la seule concordance de lignes. Le fuseau actuel ne prouve pas celui utilisé lors du nommage de la sauvegarde.

Ne pas publier `.env`, inspect complet, config complète, clés, témoins ou contenu de journaux privés. Aucun hash Docker n’est édité, aucun fichier n’est déplacé ou restauré.

## 2. Conserver tous les overrides actifs dans leur ordre

```bash
LABELS=$("${D[@]}" inspect --format '{{index .Config.Labels "com.docker.compose.project.config_files"}}' \
  documind-public-beta-api-1 documind-public-beta-web-1 documind-public-beta-db-1)
FILE_TEXT=$(printf '%s\n' "$LABELS" | "$PYTHON" -B -c '
import pathlib,sys
rows=sys.stdin.read().splitlines()
assert len(rows)==3 and all(rows)
ordered=[]
for row in rows:
    for name in row.split(","):
        p=pathlib.Path(name)
        assert p.is_absolute() and p.resolve()==p and p.is_file()
        assert p.is_relative_to("/opt/documind-public-beta")
        if name not in ordered: ordered.append(name)
print("\n".join(ordered))
')
mapfile -t FILES <<< "$FILE_TEXT"
CURRENT_ARGS=()
BACKUP_ARGS=()
REPLACED=0
for file in "${FILES[@]}"; do
  CURRENT_ARGS+=(--compose-file "$file")
  if test "$file" = "$BASE"; then
    BACKUP_ARGS+=(--historical-compose-file "$BACKUP")
    REPLACED=$((REPLACED+1))
  else
    BACKUP_ARGS+=(--historical-compose-file "$file")
  fi
done
test "$REPLACED" -eq 1
printf '%s\n' "${FILES[@]}"
```

L’opératrice valide l’ordre, l’override Web R2 et tout override API. Si BASE n’apparaît pas exactement une fois, arrêter : il faut d’abord identifier la vraie chaîne. Le remplacement ci-dessus est **uniquement un argument de lecture** ; aucun fichier Compose n’est réécrit.

## 3. Comparaison bornée avec le contexte courant constant

Cette première expérience compare C et « sauvegarde + overrides actifs + contexte courant ». **Ce n’est pas encore la configuration historique.** Les noms d’options `--historical-*` du diagnostic ne constituent pas une attestation.

Conserver le même contexte shell d’interpolation que la recette r2 précédente. Ne pas modifier des variables pour chercher un résultat égal. Si les preuves précédentes utilisaient une autre chaîne d’options ou un autre contexte, arrêter et documenter cette différence.

```bash
OUT=$(mktemp -d /home/debian/docnelo-history-evidence.XXXXXXXX)
if (set -C; "$PYTHON" -B "$DIAG/diagnose_replay.py" \
  "${CURRENT_ARGS[@]}" \
  --env-file "$APP_ROOT/.env.public-beta" \
  --env-file "$APP_ROOT/.env.public-beta.images" \
  "${BACKUP_ARGS[@]}" \
  --historical-env-file "$APP_ROOT/.env.public-beta" \
  --historical-env-file "$APP_ROOT/.env.public-beta.images" \
  > "$OUT/controlled-comparison.json"); then
  RC=0
else
  RC=$?
fi
printf 'Code diagnostic : %s\n' "$RC"
"$PYTHON" -B - "$OUT/controlled-comparison.json" <<'PY'
import json,sys
p=json.load(open(sys.argv[1]))
assert p.get('diagnostic_complete') is True, 'Collecte incomplète : arrêter'
assert p['active_override_sequences_preserved'] is True
assert all(p['known_active_images'].values()) and all(p['container_identity_and_health'].values())
for section in (p['current'],p['historical_inputs']['replay']):
    q=section['modes']['defer_paths']
    assert q['complete'] and all(q['matches'].values()), 'Rejeu non fidèle : arrêter'
print(json.dumps(p,indent=2)) # Rapport r2 sans valeurs d’environnement.
assert p['status']=='NO-GO' and p['opening_authorized'] is False
PY
```

Le retour **2 reste normal** pour ce diagnostic, qui n’autorise rien. Les hashes directs des fichiers sont calculés nativement ; le rejeu fidèle est vérifié séparément avec `defer_paths`. Les mêmes chemins env_file, leur ordre et leur interpolation sont conservés.

Examiner `historical_inputs.declaration_changed_paths`, les hashes API/DB/Web et les comparaisons aux labels D. Si les modèles réels correspondent aux sources locales analysées, les différences API doivent se limiter aux cinq variables lifecycle. Toute autre différence réelle devient une piste étayée, à documenter sans en afficher la valeur.

## 4. Vérifier les cinq valeurs effectives sans les afficher

Cette lecture supplémentaire compare les deux chaînes entièrement rendues, overrides compris, à l’environnement API. Elle évite de confondre une valeur du fichier de base avec la valeur réellement gagnante après fusion.

```bash
"$PYTHON" -B - "$DIAG" "$OUT/controlled-comparison.json" <<'PY'
import json,pathlib,sys
sys.path.insert(0,sys.argv[1])
import diagnose_replay as d
try:
    p=json.load(open(sys.argv[2]))
    d.require(p.get('diagnostic_complete') is True,'incomplete')
    for name,expected in p['input_fingerprints'].items():
        d.require(d.file_sha(pathlib.Path(name))==expected,'input_changed')
    c=d.Compose(list(map(pathlib.Path,p['input_file_order'])),list(map(pathlib.Path,p['interpolation_env_file_order'])))
    h=p['historical_inputs']
    b=d.Compose(list(map(pathlib.Path,h['compose_file_order'])),list(map(pathlib.Path,h['interpolation_env_file_order'])))
    d.require(c.execute('version')=='2.35.1','version')
    before=d.Docker().read('containers',[d.PROJECT+'-api-1'])
    active=d.env(before[0]['Config']['Env'])
    keys=('LIFECYCLE_REGISTRY_PATH','LIFECYCLE_CONFIRMATION_PATH',
          'LIFECYCLE_AUTHENTICATED_CONFIRMATION_PATH','LIFECYCLE_HOLDS_PATH','LIFECYCLE_ADMISSION_ANCHOR_PATH')
    checks={}
    for label,engine in (('current_chain',c),('backup_with_current_overrides',b)):
        values=d.resolved_environment(engine.render()['services']['api'])
        checks[label]={key:key in values and key in active and values[key]==active[key] for key in keys}
    d.require(c.hashes()==p['current']['direct_hashes'] and b.hashes()==h['direct_hashes'],'context_changed')
    d.require(d.stable_rows(before)==d.stable_rows(d.Docker().read('containers',[d.PROJECT+'-api-1'])),'container_changed')
    for name,expected in p['input_fingerprints'].items():
        d.require(d.file_sha(pathlib.Path(name))==expected,'input_changed')
    print(json.dumps({'status':'NO-GO','matches':checks,'counts':{name:sum(values.values()) for name,values in checks.items()},'opening_authorized':False},indent=2))
except Exception:
    print('{"status":"NO-GO","reason":"five_paths_comparison_unconfirmed","opening_authorized":false}')
    raise SystemExit(2)
PY
```

Si la chaîne sauvegarde+overrides correspond désormais à 5/5, les overrides expliquent pourquoi un fichier de base à 0/5 peut participer à une chaîne différente ; leur provenance devient essentielle. Si elle reste à 0/5, ne pas la considérer comme une création ordinaire compatible avec l’API active, même si son hash rejoint D. Documenter la contradiction sans réécrire de valeurs.

## 5. Simulation bornée issue de l’export 280 lignes

Cette expérience facultative teste une différence **observée dans une source locale conservée**, pas une recherche de valeurs : les sept déclarations lifecycle explicites sont omises dans une copie en mémoire du modèle courant. Aucun fichier n’est écrit ni proposé comme déploiement. Les valeurs éventuellement fournies par env_file sont comparées à l’API sans être affichées.

```bash
"$PYTHON" -B - "$DIAG" "$OUT/controlled-comparison.json" <<'PY'
import copy,json,pathlib,sys
sys.path.insert(0,sys.argv[1])
import diagnose_replay as d
try:
    p=json.load(open(sys.argv[2]))
    d.require(p.get('diagnostic_complete') is True,'incomplete')
    for name,expected in p['input_fingerprints'].items():
        d.require(d.file_sha(pathlib.Path(name))==expected,'input_changed')
    engine=d.Compose(list(map(pathlib.Path,p['input_file_order'])),list(map(pathlib.Path,p['interpolation_env_file_order'])))
    d.require(engine.execute('version')=='2.35.1','version')
    direct=engine.hashes()
    d.require(direct==p['current']['direct_hashes'],'context_changed')
    model=engine.render(mode='defer_paths')
    d.require(engine.hashes(full=model)==direct,'replay_not_faithful')
    before=d.Docker().read('containers',[d.PROJECT+'-api-1'])
    active=d.env(before[0]['Config']['Env'])
    keys=('LIFECYCLE_REGISTRY_PATH','LIFECYCLE_CONFIRMATION_PATH',
          'LIFECYCLE_AUTHENTICATED_CONFIRMATION_PATH','LIFECYCLE_HOLDS_PATH','LIFECYCLE_ADMISSION_ANCHOR_PATH',
          'LIFECYCLE_AUTHENTICATION_KEY_PATH','LIFECYCLE_ADMISSION_KEY_PATH')
    probe=copy.deepcopy(model)
    for key in keys:
        d.require(key in probe['services']['api']['environment'],'declaration_missing')
        probe['services']['api']['environment'].pop(key)
    values=d.resolved_environment(engine.render(full=probe)['services']['api'])
    matches={key:key in values and key in active and values[key]==active[key] for key in keys}
    hashes=engine.hashes(full=probe)
    unchanged={s:hashes[s]==direct[s] for s in ('db','web')}
    d.require(all(unchanged.values()),'non_api_hash_changed')
    d.require(engine.hashes()==direct,'context_changed')
    d.require(d.stable_rows(before)==d.stable_rows(d.Docker().read('containers',[d.PROJECT+'-api-1'])),'container_changed')
    for name,expected in p['input_fingerprints'].items():
        d.require(d.file_sha(pathlib.Path(name))==expected,'input_changed')
    print(json.dumps({'status':'NO-GO','hypothesis':'seven_declarations_omitted_as_in_local_280_export',
        'changed_paths':d.diff(model,probe),'env_file_values_match_active':matches,
        'matching_count':sum(matches.values()),'api_hash_matches_D':hashes['api']==p['deployed_label_hashes']['api'],
        'db_web_unchanged':unchanged,'historical_provenance_established':False,'opening_authorized':False},indent=2))
except Exception:
    print('{"status":"NO-GO","reason":"bounded_280_hypothesis_unconfirmed","opening_authorized":false}')
    raise SystemExit(2)
PY
```

Un calcul terminé sans erreur ne vaut pas un PASS. Si les sept valeurs correspondent et que le hash API rejoint D, une représentation déclarative compatible est identifiée ; il faut encore prouver que cette famille et ce contexte ont servi à créer le conteneur. Si le hash ne rejoint pas D, l’hypothèse simple est insuffisante : conserver le résultat et rechercher seulement d’autres différences documentées. Ne pas élargir en essais combinatoires de variables ou d’options.

Des overrides ou champs API propres au VPS peuvent différer des sources locales ; cette simulation conserve ces autres entrées courantes. Elle n’affirme donc pas que le modèle complet est une copie authentifiée de l’export 280.

## 6. Déductions autorisées et recherche de provenance

* Si seules les cinq variables API diffèrent et que l’API active a déjà leurs valeurs courantes, le grand diff init ne constitue pas une explication de D. Rechercher une autre déclaration ou un autre contexte attesté, sans construire une famille de valeurs au hasard.
* Si l’API de la sauvegarde rejoint D mais reste incompatible avec les valeurs effectives, le résultat n’est pas une solution de déploiement : la chaîne de création réelle n’est pas établie.
* Si un override documenté transforme les cinq chemins et change aussi d’autres champs, comparer ces champs identifiés. Aucune modification ne devient autorisée parce qu’elle explique un hash.
* Si les sources VPS diffèrent des empreintes locales, ne pas appliquer directement les conclusions d’identité des modèles locaux. Utiliser les différences du relevé réel.
* La famille 280 n’avait pas les sept déclarations explicites : elle peut être compatible avec les mêmes valeurs effectives via env_file. Son identité et son usage historique restent à établir, même si la simulation bornée rejoint D.

Rassembler la preuve liant l’ID API à l’action de création de 01:11:06Z : journal d’intervention, script exact et sa version, commande et cwd, fichiers ordonnés avec leurs octets/empreintes, référence image, paramètres et contexte d’interpolation. Ne pas afficher une histoire shell brute ; elle peut contenir des secrets et ne garantit pas des dates fiables.

Option facultative de corroboration, sans config ni valeurs :

```bash
API_CONTAINER_ID=$("${D[@]}" inspect --format '{{.Id}}' documind-public-beta-api-1)
"${D[@]}" events \
  --since 2026-10-31T01:05:00Z --until 2026-10-31T01:15:00Z \
  --filter type=container --filter "container=$API_CONTAINER_ID" \
  --format '{{.Time}} {{.Action}} {{.Actor.ID}}'
```

L’historique Docker est limité et volatil. L’absence d’événement ne prouve pas l’absence de création. Un événement confirme une action/identité, sans attester les octets Compose. Aucun journal ne doit être supprimé ou modifié.

## 7. Historique authentifié et décision

Si la chaîne réellement utilisée est retrouvée, la comparer avec r2 selon sa procédure scellée, en remplaçant les **arguments historiques** par les seules pièces authentifiées, sans modifier les originaux. Préserver chemins, env_file, ordre d’overrides et contexte ; vérifier tous les rejeux et les hashes natifs. Ne pas utiliser un contexte actuel inconnu comme substitut implicite du contexte historique.

Une empreinte égale est une preuve de reproductibilité dans le contexte testé, pas une preuve d’utilisation historique. Il faut aussi expliquer les cinq valeurs effectives et authentifier la chaîne de création. Les contrôles lifecycle et le garde Compose existant restent obligatoires ; ils ne sont ni modifiés ni remplacés.

**NO-GO maintenu** jusqu’à ces preuves. Aucun `up`, `run`, `exec`, lifecycle-init, changement de Compose/`.env`/label, redémarrage, migration ou ouverture dans cette procédure. Aucun retour arrière de service n’est nécessaire : seuls de nouveaux relevés privés peuvent avoir été écrits par l’opératrice.
