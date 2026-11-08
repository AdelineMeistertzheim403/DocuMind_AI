# Lifecycle 10 — Procédure opérateur du diagnostic r2

Commandes proposées seulement. Aucun accès VPS par Codex, aucune installation automatique, aucun redémarrage ou changement applicatif.

## 1. Transfert distinct et contrôle

Depuis PowerShell local, avec l’hôte Public Beta vérifié :

```powershell
$VpsHost = Read-Host 'Hôte SSH Public Beta validé'
$Bundle = (Resolve-Path '.\deliveries\docnelo-lifecycle10-hash-diagnostic-r2').Path
(Get-FileHash (Join-Path $Bundle 'SHA256SUMS') -Algorithm SHA256).Hash.ToLowerInvariant()
ssh "debian@$VpsHost" 'test ! -e /home/debian/docnelo-lifecycle10-hash-diagnostic-r2'
if ($LASTEXITCODE -ne 0) { throw 'Destination présente ou SSH indisponible' }
scp -r "$Bundle" "debian@${VpsHost}:/home/debian/"
if ($LASTEXITCODE -ne 0) { throw 'Transfert incomplet' }
```

Noter l’empreinte du manifeste via un canal de confiance. Ne transférer ni binaire Compose, `.env`, archive Docker, clé ou relevé réel. R2 n’a besoin d’aucun script parent ou r1 pour fonctionner.

Sur le VPS, dans une session Bash opératrice dédiée :

```bash
set -euo pipefail
umask 077
DIAG=/home/debian/docnelo-lifecycle10-hash-diagnostic-r2
APP_ROOT=/opt/documind-public-beta/public-beta-candidate-20261030T234818Z
PREVIOUS=/home/debian/docnelo-hash-evidence.evPkFKul/diagnostic.json
PYTHON=/usr/bin/python3.11
D=(docker --host unix:///var/run/docker.sock)
cd "$DIAG"
sha256sum SHA256SUMS
# Comparer avec l'empreinte locale notée avant de poursuivre.
sha256sum --check --strict SHA256SUMS
test -x "$PYTHON"
"$PYTHON" --version
"$PYTHON" -B "$DIAG/diagnose_replay.py" --help
test -f "$PREVIOUS"
"${D[@]}" compose version --short
```

Exiger Compose 2.35.1. Si l’interpréteur validé est ailleurs, renseigner son chemin physique ; n’installer aucune dépendance pour ce diagnostic. Ne pas modifier une release existante, même si un fichier de livraison semble devoir être corrigé.

## 2. Conserver la chaîne courante d’entrée

Le relevé doit utiliser le même contexte d’interpolation que le diagnostic précédent. Les variables shell pouvant servir d’entrée ne doivent pas être effacées ou remplacées pour obtenir une égalité. Les deux fichiers d’interpolation restent les fichiers existants et inchangés. Ne pas afficher `env`, `printenv`, inspect complet ou config complet ; pas de `set -x`.

```bash
# Valeur de session déjà utilisée par les procédures Public Beta ; aucun fichier édité.
export RECOVERY_CONTROL_FILE=/opt/documind-public-beta/recovery-state.json
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
ARGS=()
for file in "${FILES[@]}"; do ARGS+=(--compose-file "$file"); done
printf '%s\n' "${FILES[@]}"
```

L’opératrice vérifie l’ordre complet et la présence de l’override Web R2. L’union des chemins de labels n’atteste pas que leur contenu est resté identique depuis création. Si l’ordre diffère de celui du précédent diagnostic, conserver cette différence comme inconnue : ne pas omettre un override pour faire correspondre les hashes. Un ordre contradictoire entre services impose une revue ; r2 le signale.

## 3. Nouvelle preuve expurgée, sans toucher aux précédentes

```bash
OUT=$(mktemp -d /home/debian/docnelo-replay-r2-evidence.XXXXXXXX)
if (set -C; "$PYTHON" -B "$DIAG/diagnose_replay.py" \
  "${ARGS[@]}" \
  --env-file "$APP_ROOT/.env.public-beta" \
  --env-file "$APP_ROOT/.env.public-beta.images" \
  --previous-diagnostic "$PREVIOUS" > "$OUT/diagnostic.json"); then
  RC=0
else
  RC=$?
fi
printf 'Code de retour du diagnostic : %s\n' "$RC"
"$PYTHON" -B - "$OUT/diagnostic.json" <<'PY'
import json,sys
p=json.load(open(sys.argv[1]))
assert p.get('diagnostic_complete') is True, 'Collecte incomplète : arrêter'
print(json.dumps(p,indent=2)) # Aucun environnement brut ou valeur sensible dans ce rapport.
assert p['previous_hash_triplets_match'] is True, 'Autres hashes/contexte : arrêter la comparaison temporelle'
assert p['active_override_sequences_preserved'] is True
assert all(p['container_identity_and_health'].values())
assert all(p['known_active_images'].values())
assert p['status']=='NO-GO' and p['opening_authorized'] is False
PY
```

Le retour **2 est systématique**, même pour une collecte complète : cet outil n’autorise rien. Une exception produit `diagnostic_complete=false`. Ne jamais traiter ce retour comme un feu vert de migration.

`previous_hash_triplets_match` compare seulement les trois groupes de hashes C/H1/labels du relevé précédent. Ce n’est pas une preuve que tous les paramètres des conteneurs sont identiques au relevé ancien. Les contrôles de stabilité internes concernent la collecte r2 ; les fingerprints runtime et preuves lifecycle historiques restent nécessaires pour toute future intervention.

## 4. Localiser exactement le rejeu infidèle

Lire séparément :

* `current.modes` pour C ;
* `H1_r1_hypothesis.modes` pour le gel précédent ;
* les trois entrées API/DB/Web de `matches` dans chaque mode.

Pour chaque échec r1, examiner `resolved_changed_paths` lorsqu’il est disponible, et `input_paths_changed_from_r1` dans les modes différés. Les listes donnent des JSON Pointers, jamais leurs valeurs.

Interprétation :

1. r1 échoue et `defer_paths` correspond : l’effet de la résolution préalable des chemins est démontré **pour ce modèle et ce service**. Les chemins modifiés doivent expliquer la différence, par exemple env_file ou source bind.
2. Seul `defer_paths_and_normalization` correspond : examiner aussi les champs transformés par normalisation ; ne pas attribuer le problème aux seuls chemins.
3. Aucun mode ne correspond : cause encore inconnue ; ne pas exploiter un modèle aplati comme historique. Conserver les preuves pour une investigation supplémentaire.
4. Un rendu résolu indisponible ne signifie pas que son hash est indisponible : consulter `complete`, `resolved_comparison_complete` et les motifs séparés.
5. `declarative_view_available=false` signifie que les indicateurs de présence ne sont pas disponibles ; les `null` ne sont pas des absences démontrées.

Si le hash du rejeu r1 est lui-même indisponible, R2 n’attribue pas une cause au seul motif qu’un autre mode fonctionne : `r1_replay_unavailable_not_attributed` exige une revue supplémentaire.

Même un rejeu fidèle de H1 ne signifie pas H1 égal à D : H1 reste une hypothèse qui ajoute deux déclarations. La preuve recherchée est la fidélité du rejeu **et**, séparément, la configuration historique authentifiée reproduisant D.

## 5. Retrouver la configuration réellement exécutée à la création

Faire rassembler dans un dossier privé de preuve, sans modifier les originaux :

* Relevé de création ou journal d’intervention liant conteneur API, image, date, commande et fichiers.
* Contenu exact et ordre des Compose/overrides à cette date ; source/commit et empreintes, si conservés.
* Référence textuelle exacte de l’image, même si plusieurs références désignent l’ID 4aa850….
* Déclarations env_file, ordre, chemins et format ; contexte original des variables shell et fichiers d’interpolation.
* Options explicites ou héritées, plateforme et éventuelle compatibilité Compose.

Les commits identifiés dans l’analyse sont des pistes à vérifier, pas des références de production adoptées. Les labels config_files ne contiennent pas les anciens octets. Une image applicative ne restitue pas les paramètres de sa commande Compose.

Ne pas restaurer une sauvegarde dans un volume actif pour effectuer cette recherche. Toute extraction de configuration doit rester une opération isolée et autorisée, hors de cette procédure. Ne pas scanner ni publier les clés ou données. Un fichier historique d’environnement éventuellement conservé reste privé 0600 dans un dossier 0700, hors Git et hors bundle.

## 6. Rejouer des entrées historiques authentifiées, sans gel

Cette étape est optionnelle tant que les entrées manquent. Les chemins ci-dessous sont volontairement des **emplacements à renseigner**, pas des identifiants inventés :

```bash
HISTORICAL_BASE=/CHEMIN/PRIVE/DU/COMPOSE_HISTORIQUE.yaml
HISTORICAL_OVERRIDE=/CHEMIN/PRIVE/DE/OVERRIDE_HISTORIQUE.yaml
HISTORICAL_ENV=/CHEMIN/PRIVE/DU/CONTEXTE_INTERPOLATION_HISTORIQUE
HISTORICAL_IMAGES_ENV=/CHEMIN/PRIVE/DU/CONTEXTE_IMAGES_HISTORIQUE
PROVENANCE=/CHEMIN/PRIVE/DU/DOSSIER_DE_PREUVE_DOCUMENTE.txt
test -f "$HISTORICAL_BASE"
test -f "$HISTORICAL_OVERRIDE"
test -f "$HISTORICAL_ENV"
test -f "$HISTORICAL_IMAGES_ENV"
test -f "$PROVENANCE"
if (set -C; "$PYTHON" -B "$DIAG/diagnose_replay.py" \
  "${ARGS[@]}" \
  --env-file "$APP_ROOT/.env.public-beta" \
  --env-file "$APP_ROOT/.env.public-beta.images" \
  --previous-diagnostic "$PREVIOUS" \
  --historical-compose-file "$HISTORICAL_BASE" \
  --historical-compose-file "$HISTORICAL_OVERRIDE" \
  --historical-env-file "$HISTORICAL_ENV" \
  --historical-env-file "$HISTORICAL_IMAGES_ENV" \
  --provenance-evidence "$PROVENANCE" > "$OUT/with-history.json"); then
  HISTORY_RC=0
else
  HISTORY_RC=$?
fi
printf 'Code du diagnostic historique : %s\n' "$HISTORY_RC"
```

Adapter le **nombre et l’ordre** des options historiques à la chaîne attestée. Ne pas fabriquer un override s’il n’existait pas. Le répertoire de projet reste celui de l’application physique. Les contextes shell C et historique sont ceux de la même session figée ; si l’ancien contexte shell différait, cette comparaison n’est pas encore qualifiée. Ne pas changer des variables au hasard pour rechercher un hash égal.

Le déplacement de copies peut modifier les chemins relatifs d’include/extends ou d’autres ressources : le contexte et la disposition de fichiers doivent être justifiés. R2 n’est pas un exporteur universel garantissant la fidélité de tous les Compose ; la matrice reste obligatoire.

Exiger : collecte complète, hashes directs historiques égaux aux labels existants, rejeu historique fidèle pour chaque service, et revue des `declaration_changed_paths`. La preuve de provenance doit relier ces entrées à la création réelle ; le programme n’en juge pas l’authenticité. La simple présence du fichier PROVENANCE ne valide rien : seule son empreinte est conservée, pas son contenu.

## 7. Conservation effective et décision suivante

`preservation` liste les différences de valeurs effectives et l’empreinte de l’environnement API actif. Ce relevé ne remplace pas une conservation privée approuvée, et n’autorise pas l’adoption des valeurs actuelles du `.env`. Aucune valeur ancienne ou nouvelle n’est affichée, aucun fichier n’est généré par le diagnostic. Toute future méthode de déploiement devra préserver les valeurs approuvées sans prétendre que leur représentation explicite est l’historique déclaratif.

Le diagnostic r2 ne remplace ni les contrôles d’images, volumes, réseaux, cookies/API, ni les preuves du quota, namespace, HMAC et latch. Il n’appelle pas le probe applicatif et ne contourne aucun garde scellé. Tant que la cause réelle du rejeu et la configuration historique API ne sont pas démontrées, conserver le **NO-GO**.

Aucune commande de migration ou bascule n’est incluse. Le retour arrière consiste à cesser le diagnostic et conserver les dossiers de preuves ; aucun service, fichier `.env`, label, clé ou témoin n’a à être restauré. Ne rien supprimer et ne modifier aucun ancien artefact.
