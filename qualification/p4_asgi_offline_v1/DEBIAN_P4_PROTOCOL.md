# Protocole Debian differe - P4 uniquement

**EXAMEN UNIQUEMENT. Ne pas executer les phases differees sans autorisations
distinctes. Aucune commande Docker n'a ete executee dans cette preparation.**

Les chemins POSIX ci-dessous concernent exclusivement la future VM Debian.
Ne pas adapter ces commandes au VPS. Ne jamais reutiliser une variable LAB,
un fichier env, un nom de conteneur ou une evidence d'une session historique.
Ne pas relancer P1/P2/P3/D11, ni utiliser Compose. Le P3 arrete reste conserve.

## H0 - transfert, perimetre et outils offline

VM Debian13 isolee physiquement/logiquement de tout reseau applicatif.
Lire `TRANSFER.md`. Verifier les ancres par un canal independant AVANT
d'executer un script transfere. Le Python hote approuve et son venv
restent une dependance operateur, pas une source de paquets pour l'image.

```sh
set -eu
umask 077
set -C
# Valeurs absolues revues, sans symlinks, jamais chemins de production :
P4=/chemin/nouveau/p4-asgi-offline-v1
CANDIDATE=/chemin/candidat-r3-complet-fige
PY=/chemin/venv-hote-approuve/bin/python
# L'ancre P4 vient du canal independant, pas d'un calcul auto-approuve :
"$PY" -I -B "$P4/offline.py" verify "$P4" --anchor "$P4_SUMS_ANCHOR"
"$PY" -I -B "$P4/offline.py" candidate "$CANDIDATE"
```

Le parent de la nouvelle evidence operateur doit deja exister sous une
racine development dediee, hors tout manifeste historique scelle.
Creer une evidence nouvelle par tentative, y compris les refus.
Ne pas journaliser l'environnement hote, secrets, .env ou donnees reelles.

```sh
BASE=/home/adeline/docnelo-lab/development/v5.1-hardening/quarantine-debian-evidence
test -d "$BASE"
PREP_EVIDENCE="$BASE/p4-preparation-$(date -u +%Y%m%dT%H%M%SZ)-$("$PY" -I -B -c 'import uuid; print(uuid.uuid4().hex)')"
mkdir -m 700 -- "$PREP_EVIDENCE"
mkdir -m 700 -- "$PREP_EVIDENCE/docker-home" "$PREP_EVIDENCE/docker-config"
unset DOCKER_HOST DOCKER_CONTEXT DOCKER_TLS_VERIFY DOCKER_CERT_PATH DOCKER_API_VERSION
unset DOCKER_CUSTOM_HEADERS COMPOSE_FILE COMPOSE_PROFILES PYTHONPATH PYTHONHOME
unset PYTEST_ADDOPTS PYTEST_PLUGINS
export HOME="$PREP_EVIDENCE/docker-home" DOCKER_CONFIG="$PREP_EVIDENCE/docker-config"
export PATH=/usr/bin:/bin SHELL=/bin/sh
```

Les commandes Docker futures utilisent toujours le daemon local explicite
`--host unix:///var/run/docker.sock`. Nettoyer DOCKER_HOST/DOCKER_CONTEXT,
COMPOSE_FILE/PROFILES, options Python/pytest et les parametres applicatifs.
Prevoir un DOCKER_CONFIG neuf/vide et un HOME operateur dedie ; ne pas
heriter de credentials ou de plugins Compose. Pas de endpoint TCP/SSH,
pull, login, build reseau, resolution de tags ou socket dans un conteneur.
Les chemins socket alternatifs/rootless ne sont pas approuves ici.

## H1 - ARRET AVANT BUILD

Reproduire l'inventaire dans une **nouvelle sortie**, avec `packaging26.3`
deja disponible et verifie, sans rien installer :

```sh
"$PY" -I -B "$P4/offline.py" inventory \
  --candidate "$CANDIDATE" \
  --historical-transfer "$HISTORICAL_TRANSFER_RO" \
  --pyyaml-wheel "$PYYAML_CP311_WHEEL_RO" \
  --out "$PREP_EVIDENCE/inventory-recheck.json"
"$PY" -I -B "$P4/collect.py" --out "$PREP_EVIDENCE/build-gate-refusal" -- \
  "$PY" -I -B "$P4/offline.py" build-gate \
  --inventory "$P4/DEPENDENCIES_OBSERVED.json" \
  --approval "$P4/BUILD_APPROVAL.pending.json"
```

La derniere commande refuse et son code doit rester non nul. Avec `set -e`,
le shell s'arrete ; ne pas contourner en poursuivant le protocole.
Ce refus est un blocage de preparation, **pas un PASS P4**.
Le gate est volontairement non deverrouillable dans cette revision.

Lire `DEPENDENCIES.md` : obtenir archive de base et image ID verifies,
CPython3.11.18 binaire/stdlib et provenance, fermeture ELF systeme, wheels
et bootstrap approuves, recette offline revue. Pas de Dockerfile utilisable
dans ce paquet. Aucun pip/apt reseau ou paquet non verifie n'est autorise.
Une revision de construction approuvee est necessaire avant le build.

**Les sections suivantes sont reservees a une autorisation future** et
supposent cette revision/image et leurs preuves deja approuvees. Ne pas
les interpreter comme une permission de franchir H1.

## H2 - ouverture d'un cas P4 neuf

Un namespace par profil ET par cas de `TEST_MATRIX.md` (36 au total).
Renseigner explicitement `CASE`, `PROFILE`, `TEST_UID`, `PRIMARY_GID`,
`READER_GID` et `IMAGE_ID` apres revue ; pas de valeur implicite.
Choisir UID test, GID primaire et GID lecteur distincts, non nuls,
non privilegies, sans reutilisation d'une identite de service reel.
Verifier absence de remap/userns/rootless ; ne pas supposer que UID
conteneur egale UID hote. Si mapping non identite : arret, revue distincte.

L'operateur privilegie n'utilise que les scripts verifies et le Python
approuve. Les ecritures privilegiees sont limitees au nouveau prefixe P4 :

```sh
P4LAB="/var/tmp/docnelo-p4-$("$PY" -I -B -c 'import uuid; print(uuid.uuid4().hex)')"
# Refuser toute valeur preexistante, historique ou non canonique.
test ! -e "$P4LAB"
"$PY" -I -B "$P4/p4_control.py" --candidate "$CANDIDATE" --root "$P4LAB" \
  --authorize-new-p4-synthetic-only provision \
  --uid "$TEST_UID" --primary-gid "$PRIMARY_GID" --reader-gid "$READER_GID" \
  > "$PREP_EVIDENCE/provision-$CASE-$PROFILE.json"
OP="$P4LAB/operator"
```

`$P4LAB/control` = root:lecteur0750, enfant root:lecteur0440 neuf
quarantined. `$P4LAB/evidence` = UID:GID0700, vide. `$OP` = root0700.
Root hote garde naturellement ses privileges d'administration ; le
0700 exclut tous les autres UID non privilegies. Ne jamais rendre
l'evidence accessible au seul groupe lecteur.
Une erreur de provisioning laisse le namespace en place : abandonner la
tentative, conserver les traces, ne pas reparer/reutiliser automatiquement.

Pour les cas initialement ready **seulement**, avant creation :

```sh
"$PY" -I -B "$P4/collect.py" --out "$OP/initial-state" -- \
  "$PY" -I -B "$P4/p4_control.py" --candidate "$CANDIDATE" --root "$P4LAB" \
  --authorize-new-p4-synthetic-only publish --kind ready
```

Pour D05 et les D09 initialement fermes, ne pas publier ready avant startup.
Le publisher de quarantaine de r3 est utilise pour la fermeture normale ;
ready et fautes sont reserves a ce nouveau marqueur synthetique.

## H3 - ARRET AVANT CREATE

Preparer un **nouveau** `$OP/plan.json` a partir du formulaire pending.
Renseigner `case`, `profile`, nom `docnelo-p4-<uuid>-<profil>-<cas>`,
`root`, `candidate`, UID/GID, image ID `sha256:<64hex>`, preuve SHA de
revue image, environnement exact de l'image, initial_ready et probes
ordonnes de la matrice. Jamais de tag image ni de secret. Le chemin
venv impose est `/opt/p4-venv/bin/python`.

L'image future doit contenir seulement ses outils P4 sous `/opt/p4-tools`
et l'inventaire approuve sous `/opt/p4-materials`, pas une app lancee.
Son ENV peut seulement contenir PATH/LANG/LC_ALL/TZ/PYTHON_VERSION/
PYTHON_SHA256 explicitement revus. Pas de VOLUME, ONBUILD, port expose,
entrypoint metier ou fichier .env. Image P3 interdite comme substitut.

Capturer via `collect.py`, dans des sorties nouvelles :
`docker --host ... version`, `docker --host ... info --format '{{json .}}'`,
`docker --host ... image inspect "$IMAGE_ID"`.
Pour cette derniere capture, utiliser le nom impose par la collecte :

```sh
"$PY" -I -B "$P4/collect.py" --out "$OP/image-inspect" -- \
  docker --host unix:///var/run/docker.sock image inspect "$IMAGE_ID"
```

Verifier Engine26.1.5+dfsg1, le daemon local et les securites/cgroups,
Debian13, identite rootful sans remap. La version Compose est un contexte
historique seulement ; Compose n'est jamais invoque ici.
Copier la revue image approuvee sous `$OP/image-review.json`, sans la
modifier : son SHA doit etre `image_review_sha256` du plan ; champs
`approved:true`, `image_id`, `native_closure_approved:true`,
`inventory_sha256` de l'inventaire exact inclus dans l'image.
Ce n'est pas le formulaire pending ni une approbation auto-generee.

Verifier acces non-root au candidat sans chmod de r3 ; si inaccessible,
arreter et faire revoir le transfert, pas les permissions du candidat fige.
Enregistrer le mountinfo hote, les modes/identites des sources, l'absence
de sous-montages, propagation partagee et alias. Ne pas lire les donnees
des montages historiques. Geler toute mutation des sources pendant ce cas.

```sh
"$PY" -I -B "$P4/collect.py" --out "$OP/host-before-create" -- \
  "$PY" -I -B "$P4/p4_control.py" --candidate "$CANDIDATE" --root "$P4LAB" \
  --authorize-new-p4-synthetic-only check
"$PY" -I -B "$P4/check_create.py" --plan "$OP/plan.json" --out "$OP/create-argv.json"
```

Revoir l'argv, les sources **deja existantes**, l'evidence vide, et les
hashes. Un resultat argv n'est jamais un create GO.

Autorisation create distincte seulement : executer **exactement** l'argv
genere au travers du collecteur. L'operateur peut le charger sans shell
intermediaire avec ce dispatcher explicite (pas de start) :

```sh
"$PY" -I -B -c '
import json, subprocess, sys
v = json.load(open(sys.argv[1]))["argv"]
raise SystemExit(subprocess.call([sys.executable, "-I", "-B", sys.argv[2],
    "--out", sys.argv[3], "--", *v]))
' "$OP/create-argv.json" "$P4/collect.py" "$OP/create"
```

Cette commande contient uniquement `docker create`, avec pull never,
network none, USER/GID, group-add lecteur, cap-drop ALL, no-new-privileges,
rootfs RO, 512MiB RAM et swap total512MiB (donc pas de swap supplementaire),
0.5CPU, 64processus, IPC none, cgroupns prive, pas d'auto-remove/restart,
stdin ouvert non-TTY, healthcheck desactive et logs locaux conserves.
Trois binds longs rprivate exacts : candidatRO, controleRO, evidenceRW.
Un seul tmpfs `/tmp` 64MiB, noexec/nosuid/nodev.
Les `/proc`, `/dev`, `/sys` internes geres par Docker ne sont pas des
binds utilisateurs additionnels ; les revoir dans mountinfo au runtime.

Si create refuse : conserver le code numerique et stdout/stderr,
verifier en lecture seule l'absence de nouveau conteneur/source creee,
classer la tentative FAIL/INCOMPLETE, **ne pas la transformer en D11**.
Ne pas changer l'argv pour contourner le refus. Ne jamais utiliser `-v`.

## H4 - ARRET AVANT START : inspection obligatoire

`$CID` doit etre l'ID complet retourne par **ce** create reussi et
confirme par le nom/label attendus. Ne jamais prendre un ID historique.

```sh
"$PY" -I -B "$P4/collect.py" --out "$OP/created-inspect" -- \
  docker --host unix:///var/run/docker.sock container inspect "$CID"
cp --no-clobber "$OP/created-inspect/stdout" "$OP/created-inspect.json"
cp --no-clobber "$OP/image-inspect/stdout" "$OP/image-inspect.json"
```

La capture `image-inspect` doit avoir ete creee en H3. Verifier son code0.
Capturer `docker ... container ls -aq --no-trunc` avant/apres cette phase.
Pour chaque autre ID, y compris P3 arrete, capturer **seulement** :

```text
docker --host unix:///var/run/docker.sock container inspect \
  --format '{"Id":{{json .Id}},"Mounts":{{json .Mounts}}}' <IDs-explicites-autres>
```

Ne pas collecter ENV/config/secrets de conteneurs historiques/reels.
Assembler ces seules lignes JSON dans `$OP/others.json`, tableau exact ;
si aucun autre conteneur, tableau `[]` documente par la liste complete.
Recouper les IDs avec la liste du daemon, pas seulement les labels.
L'inspecteur interdit tout alias de la racine P4/controle/evidence,
meme RO, et tout alias RW du candidat. Un probe P3 historique RO sur
un fichier du candidat est permis et doit rester intact.

```sh
"$PY" -I -B "$P4/check_create.py" --plan "$OP/plan.json" \
  --inspect "$OP/created-inspect.json" --image-inspect "$OP/image-inspect.json" \
  --others "$OP/others.json" --out "$OP/created-inspection.json"
"$PY" -I -B "$P4/collect.py" --out "$OP/host-after-create" -- \
  "$PY" -I -B "$P4/p4_control.py" --candidate "$CANDIDATE" --root "$P4LAB" \
  --authorize-new-p4-synthetic-only check
```

Revoir tous les champs verifies par `inspect_created`, les limites
reelles et les sources/cibles, l'image ID, entrypoint Python explicite,
`-I -B /candidate/run_local.py --mounted-profile ...`, le groupe lecteur.
Conteneur `created`, StartedAt nul, jamais demarre.
Reverifier gel, hashes et inode/device du controle avant tout start.
Tout ecart interdit le start. Ne pas utiliser `docker update`, commit,
exec preparatoire, recreation ou correction silencieuse.

`PASS_CREATED_INSPECTION_ONLY` indique toujours `start_go=false` :
l'operateur doit donner et enregistrer une autorisation start distincte.
Le gate ne peut pas empecher un administrateur de contourner la procedure ;
aucun start automatise n'est fourni.

## H5 - startup et dialogue controle, deux terminaux

Seulement apres H4 accepte et autorisation start. Terminal A, dans un
shell epure, lancer la capture interactive bornee (900s, pas de detach).
Verrouiller les droits des logs synthetiques ; ne pas saisir de secret.
`script` doit deja etre disponible/verifie sur Debian, pas installe ici.

```sh
"$PY" -I -B "$P4/collect.py" --out "$OP/start-session" --timeout 900 -- \
  script --return --flush \
  --log-in "$OP/stdin.log" --log-out "$OP/terminal.log" --log-timing "$OP/timing.log" \
  --command "docker --host unix:///var/run/docker.sock start -ai $CID"
```

La sortie du collecteur est dans `$OP/start-session/stdout`. Terminal B
peut l'observer avec `tail -f` ; interrompre seulement ce tail apres
`RCD_EVENT startup`, pas la capture ni le conteneur.
Le stdin du conteneur reste ouvert via le terminal A. Pas de pipeline
`echo`/here-document qui fermerait stdin, ni `docker start -d`.

Attendre l'evenement startup et verifier `ready_at_start`, routes>0,
chemin exact et compteurs workers (voir matrice). L'horloge daemon/hote
doit etre la meme, stable sans correction NTP pendant le cas.
En absence de startup, timeout ou erreur : INCOMPLETE/FAIL et conservation,
pas de publication de reparation ni d'envoi de probe a l'aveugle.

Avant le premier changement, produire les observations d'identite et ABI
dans **ce nouveau conteneur**, processus externe non-root, sans backend :

```sh
"$PY" -I -B "$P4/collect.py" --out "$OP/runtime" -- \
  docker --host unix:///var/run/docker.sock exec "$CID" \
  /opt/p4-venv/bin/python -I -B /opt/p4-tools/runtime_probe.py \
  --inventory /opt/p4-materials/DEPENDENCIES_OBSERVED.json \
  --out /evidence/runtime-probe.json
```

Verifier code0, UID/GID/groupes, maps, CapEff/CapBnd=0, NoNewPrivs=1,
Seccomp attendu, uid de PID1, mountinfo RO/RW exact et aucun socket Docker.
Relever cgroup CPU/memory/pids avec les fichiers du cgroup effectif ;
les valeurs doivent correspondre a 500000000 NanoCPU, 536870912 octets,
swap max0 et pids64 (probe cgroups v2 dans runtime-probe).
Une observation invalide interdit de continuer ; pas de correction in situ.
Le probe est distinct du lancement ASGI et ne remplace pas le test monte.

## H6 - publication apres startup, puis probe

Terminal B : action **exacte** de la matrice, sous collecteur exclusif :

```sh
"$PY" -I -B "$P4/collect.py" --out "$OP/action-01" -- \
  "$PY" -I -B "$P4/p4_control.py" --candidate "$CANDIDATE" --root "$P4LAB" \
  --authorize-new-p4-synthetic-only publish --kind quarantined
```

Verifier code0 et receipt complet. Pour publish, inode enfant nouveau,
parent device/inode stable, UID0/GIDlecteur0440 et SHA attendu ; fsync
fichier puis replace puis fsync repertoire sont termines avant retour.
Conserver stdout (avant/apres, modes, tailles, timestamps ns et hashes).
Le retour `commit_return_ns` borne apres commit durable, pas l'instant
physique exact du disque. Un refus ou une interruption n'atteste pas un commit.

Apres confirmation du commit **seulement**, terminal A, une ligne :

```json
{"action":"probe","expect":"closed"}
```

Attendre l'evenement probe. Ne pas envoyer l'action suivante avant cet
evenement. Pour `sentinel`, envoyer exactement l'attente de la matrice :

```json
{"action":"probe","expect":"sentinel"}
```

D04 a deux actions/probes, D09 en a trois : utiliser `action-02`, etc.
Les autres actions sont `remove`, `symlink`, ou
`mode --object latch --mode 000` / `mode --object directory --mode 0700`,
puis restauration explicite0440/0750 sur **ce P4 seulement**.
Publier ready/invalides via `publish --kind <variante>`.
Ne jamais envoyer de requete contre FIFO/device : risque de blocage.
Le symlink prepare est uniquement dangling dans le controle P4, sans cible reelle.

Apres tous les probes attendus, terminal A :

```json
{"action":"stop"}
```

Attendre la fin normale du lanceur ET de la capture. Stop est la commande
JSON, pas un SIGTERM Docker. Ne pas fermer SSH/stdin avant le retour.
EOF, Ctrl-C, timeout, kill, stop sans probe, ou code perdu = pas de PASS.

Si un conteneur P4 reste actif apres interruption, une autorisation de
stop de secours peut viser **uniquement cet ID P4 confirme** (`docker ...
stop --time 15 "$CID"`), capturee separement. Cela laisse le cas INCOMPLETE
ou FAIL, jamais PASS. Ne pas utiliser prune/rm/down ni toucher P3.

## H7 - collecte finale et verdict

Capturer en sorties neuves avec `collect.py` :

```text
logs:          docker --host ... logs --timestamps <CID>
wait:          docker --host ... wait <CID>
final-inspect: docker --host ... container inspect <CID>
host-final:    python -I -B p4_control.py ... snapshot
```

Un `docker wait` a deux retours : retour du CLI **et** entier stdout du
conteneur ; tous deux doivent etre0. Ne pas prendre `$?` apres `echo`,
tee, cp ou une autre commande pour le retour du test.

Copier sans ecraser `$P4LAB/evidence/run` vers `$OP/container-run`,
et `$P4LAB/evidence/runtime-probe.json` vers `$OP/runtime-probe.json`.
Ne jamais modifier ces fichiers ni leur SHA256SUMS interne. Conserver
les originaux dans le namespace, le conteneur arrete et tous les logs.
L'evidence interne ne suffit pas a prouver les options Engine.

Faire une revue independante et creer `$OP/operator-review.json` :
`plan_sha256` + dictionnaire `checks` contenant exactement les booleens
vrais ci-dessous, **seulement avec preuves associees conservees sous OP** :

```json
{
  "plan_sha256": "<SHA approuve du plan>",
  "checks": {
    "transfer_anchors": true,
    "image_approval": true,
    "daemon_local_rootful_no_remap": true,
    "all_container_ids_accounted": true,
    "no_submounts_or_shared_propagation": true,
    "host_identity_before_after_create": true,
    "startup_before_each_action": true,
    "commit_before_each_probe": true,
    "explicit_stop_sent": true,
    "no_session_interruption": true,
    "runtime_probe_identity_limits": true,
    "candidate_unchanged": true
  }
}
```

Ce JSON n'est pas une signature ; archiver nom de revue, autorisations et
references de preuves sans donnees personnelles inutiles. Ne pas le
pre-remplir pour faire passer l'evaluateur.

```sh
"$PY" -I -B "$P4/evaluate.py" --evidence "$OP" --out "$OP/verdict.json"
"$PY" -I -B "$P4/offline.py" seal "$OP"
```

Si echec/interruption, produire aussi un statut et sceller les traces
partielles hors de tout manifeste deja scelle. Une sortie verdict
manquante est INCOMPLETE, pas implicitement PASS.

Verifier de nouveau r3 et les historiques inventories, puis sceller
l'evidence de campagne globale liant les 36 verdicts, IDs et manifestes.
Ne pas ajouter des fichiers dans OP apres scellement : annexes nouvelles
dans une nouvelle evidence avec references de hashes.
PASS d'un cas ne vaut pas PASS de la matrice ; PASS de la matrice n'est
pas un GO production. Toute couverture D14/D01-D20 non executee doit
rester explicitement exclue ou INCOMPLETE dans la decision finale.
