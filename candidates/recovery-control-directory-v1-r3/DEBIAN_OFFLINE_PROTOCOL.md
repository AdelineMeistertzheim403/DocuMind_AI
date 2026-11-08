# Protocole differe - Debian 13 isole, sans reseau applicatif

## Revision r3 - proposition pour examen, pas de GO P3

Les candidats v1/r2 figes, leurs preuves et les namespaces P2 restent inchanges.
Cette copie r3 n'est pas leur remplacement. Le premier constat fourni par
l'operateur est Docker Compose **2.26.1-4**, YAML source explicitement
`create_host_path: false`, rendu `bind: {}` avec et sans `--no-normalize`,
refus par la garde v1, aucun conteneur P3 cree. Ce constat n'est pas
presente comme une reproduction native executee sur Windows.

Le preflight r2 execute sur Debian a ensuite refuse le rendu natif
`mem_limit: "134217728"` : il ne normalisait que le nombre entier.
Ce nouveau constat est fourni par l'operateur, pas reproduit ici par Docker.
R3 accepte uniquement ces trois couples type/valeur pour le rendu :
chaine `"128m"`, entier JSON `134217728`, chaine `"134217728"`.
Le float `134217728.0`, les nombres exponentiels, booleens, valeurs
voisines et variantes d'unites/espaces/zeros initiaux sont refuses.
Le YAML source garde `128m` ; ne pas le modifier ni reecrire le JSON
Compose natif pour contourner un refus. Le rendu brut reste la preuve.

Ne pas corriger le YAML en supprimant false ou en mettant true.
`--no-normalize` n'est pas une solution demontree. Ne pas assouplir
globalement `validate_compose()` pour accepter un dictionnaire vide.
La nouvelle validation est obligatoire **ensemble** : source + rendu
lie aux parametres + etat hote/P2, puis inspections Engine distinctes.
Elle est limitee au lecteur minimal P3 ; les gardes operationnelles
restent strictes et bloquees.

Pour la reprise r3, conserver les LAB et preuves P2/r2 existants. Ne
relancer ni provisioning, publication, chmod ou mutation des sections
P2 ci-dessous. Le nouveau preflight est exclusivement en lecture sur
ces sources et ecrit uniquement une nouvelle evidence.

**A executer uniquement apres autorisation laboratoire. Rien de cette
campagne Docker n'a ete execute pendant la preparation Windows.**
Ni VPS, ni base, ni SMTP, ni IA, ni Uvicorn, ni Dockerfile build/pull.
Ne jamais lancer les quatre Compose applicatifs complets.

## P0 - entree en laboratoire, pas en exploitation

1. Verifier l'inventaire du nouveau transfert et `INPUTS.json`. Extraire
   dans un nouveau repertoire development, jamais dans une release ou
   une preuve existante. Les manifestes SHA ne sont pas des signatures :
   confirmer leurs empreintes par un canal de confiance independant.
2. VM Debian 13 isolee ; CPython 3.11.18/x86_64 et venv dedie pour
   l'ASGI. Engine/Compose deja installes, daemon **local** uniquement,
   contexte et socket Unix controles. Refuser DOCKER_HOST/DOCKER_CONTEXT
   distants, endpoint TCP, builds, pulls et resolutions de tags.
   L'acces operateur au daemon local n'est jamais monte dans un conteneur.
3. Images deja chargees et revues par **image ID sha256**, avec runtime
   Python approuve. Pour le profil ASGI : Debian 13, CPython 3.11.18 et
   venv complet dans l'image. Le Python 3.13 des Dockerfiles operationnels
   n'est pas qualifie par substitution d'une image labo 3.11.
4. Dependances offline : les locks source runtime/test et package-lock
   sont inventories, mais **ne sont pas un wheelhouse CP311 complet**.
   La precedente livraison FastAPI possede 42 wheels CP311 Linux :
   verifier ses manifestes en lecture seule, sans la modifier.
   PyYAML 6.0.3 est necessaire en plus pour cette campagne statique.
   Fournir son wheel CP311 Linux compatible et son SHA approuve, puis
   une nouvelle fermeture verrouillee et hashee. Ne pas utiliser le hash
   d'un wheel CP313 pour CP311. Aucune collecte de dependances ni nouvelle
   image n'est realisee ici ; absence de ces prerequis = arret explicite.
   Installer seulement depuis des sources locales revues, avec
   `--no-index --only-binary=:all: --require-hashes`, puis `pip check`.
   Inventorier versions, fichiers wheel et SHA avant/apres. Le lanceur
   conserve aussi versions/empreintes RECORD, sans pretendre verifier
   cryptographiquement tous les binaires installes.
5. Pour D20, Node et fermeture npm de `source/frontend/package-lock.json`
   deja presents offline. Si restauration necessaire :
   `npm ci --offline --ignore-scripts --no-audit --no-fund`.
   Ne pas lancer `npm test` : certains tests historiques ouvrent des sockets.
6. Choisir/verifier UID API non-root, GID primaire et GID de lecture
   dedie ; enregistrer image inspect, identites effectives, userns/remap,
   groupes et droits. Rootless/remap ne sont pas presumes compatibles.
   L'identite native du conteneur ne prouve pas seule le mapping hote.

Creer un **nouveau** repertoire d'evidence avec `mkdir` sans `-p` pour
la derniere composante :

```sh
BASE=/home/adeline/docnelo-lab/development/v5.1-hardening/quarantine-debian-evidence
CASE="recovery-directory-$(date -u +%Y%m%dT%H%M%SZ)-$(python3 -c 'import uuid; print(uuid.uuid4().hex)')"
E="$BASE/$CASE"
mkdir -m 700 -- "$E"
```

Le parent BASE doit deja exister. Capturer commandes, exit codes, stdout,
stderr, identites, inventaires et JUnit **sous E**, sans ecraser un fichier.
Ne pas journaliser l'environnement hote ni inspecter des services reels.
Un echec laisse les traces et interdit la suite ; aucun resume automatique
ne transforme un cas non execute en succes.

## P1 - campagne host sans Docker

Dans une fermeture offline deja verifiee, variables pytest externes
absentes, plugin autoload desactive :

```sh
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
/chemin/venv/bin/python -I -B "$CANDIDATE/run_local.py" \
  --evidence "$E/host-unit-asgi" --scratch "$E/host-scratch"
```

Les deux dernieres sorties doivent etre neuves. Ce profil refuse toute
tentative de sous-processus, socket, SQL, SMTP, IA ou thread reel.
Il execute les trois fichiers P1/r2 inchanges (119 + 51 cas) et les
nouveaux tests de normalisation memoire r3 : il ne teste
ni un bind Docker, ni le vrai latch restaure, ni une base.

## P2 - nouveau controle synthetique, privilege local explicite

Le provisioning est une operation root **locale de laboratoire** autorisee,
pas une commande a appliquer a un serveur existant. Ne pas executer ces
commandes sur le dossier de preuves. Choisir GID lecteur apres P0.

```sh
LAB="/var/tmp/docnelo-rcd-$(python3 -c 'import uuid; print(uuid.uuid4().hex)')"
# PY et CANDIDATE sont des chemins absolus verifies ; READER_GID est explicite.
"$PY" -I -B "$CANDIDATE/lab/control.py" --root "$LAB" provision --reader-gid "$READER_GID"
```

`LAB` doit etre absent. Le script refuse tout autre namespace que
`/var/tmp/docnelo-rcd-<32 hex>`, tout symlink/ancetre non fiable, et tout
repertoire existant au provisioning. Il cree marqueur root 0600, verrou
stable externe 0600, repertoire root:lecteur 0750, latch neuf quarantined
0440. Le couple device/inode du repertoire est inscrit dans le marqueur.
Toutes les autres operations verifient ce marqueur et cette identite.

Publisher normal, **fermeture seulement** :

```sh
"$PY" -I -B "$CANDIDATE/lab/control.py" --root "$LAB" publish
```

Les essais suivants sont des fautes/controles positifs explicitement
synthetiques. `--authorize-synthetic-only` n'autorise aucun latch reel :

```sh
"$PY" -I -B "$CANDIDATE/lab/control.py" --root "$LAB" publish --kind ready --authorize-synthetic-only
"$PY" -I -B "$CANDIDATE/lab/control.py" --root "$LAB" remove --authorize-synthetic-only
"$PY" -I -B "$CANDIDATE/lab/control.py" --root "$LAB" publish --kind invalid-json --authorize-synthetic-only
```

Les variantes invalid-utf8/duplicate/boolean/unknown/extra/oversized sont
preparees. `mode --object latch --mode 000`, `mode --object directory
--mode 0700`, `symlink`, `fifo` exigent la meme autorisation synthetique.
Le changement de mode du repertoire sert uniquement a D09, sans changer
son inode ; retablir 0750 explicitement avant publication.
Un mode fichier incorrect doit etre remplace par la voie synthetique
autorisee avant de reutiliser le publisher normal : sa garde ne doit
jamais etre affaiblie pour reparer le test.

`publish --interrupt <point> --authorize-synthetic-only` interrompt le
publisher **reel ajoute** avec exit 91 : after-metadata, after-file-fsync,
before-replace, after-replace, after-directory-fsync. Un namespace neuf
par point, barriere maintenue, controles d'etat/inode/hash apres sortie.
Les temporaires interrompus sont conserves comme traces et doivent
provoquer le refus de la garde. Ne pas les nettoyer automatiquement.
Cela ne simule pas une panne physique de disque ou un power-cut.

## P3 - lecteur minimal Docker, jamais une API reseau

`lab/compose.static.yaml` contient **un seul lecteur Python**, sans DB,
port, reseau, secrets, capabilities, socket Docker ou volume RW.
Il n'est jamais fusionne avec un Compose applicatif.

Dans un fichier d'environnement **fictif neuf** sous E, renseigner seulement :

```dotenv
LAB_IMAGE=sha256:<image-ID-local-revu>
LAB_PYTHON=/chemin/python-dans-image
LAB_READER_UID=<UID-non-root-verifie>
LAB_READER_PRIMARY_GID=<GID-primaire-verifie>
RECOVERY_READER_GID=<GID-lecteur-verifie>
RECOVERY_CONTROL_DIR=/var/tmp/docnelo-rcd-<32hex>/recovery-control
LAB_PROBE=/chemin/candidat/lab/docker_reader.py
```

Utiliser un projet unique `docnelo-rcd-...`,
`--project-directory "$CANDIDATE/lab"`, `--env-file "$E/static.env"`
et **un seul** `-f "$CANDIDATE/lab/compose.static.yaml"` explicite.
Suivre la sequence P3-r3 ci-dessous avant toute demande de creation.
L'ancienne consigne de passer le JSON seul a `validate_compose()` ne
convient pas au rendu omitempty observe ; cette garde reste volontairement
stricte, pour les anciens tests et les autres appelants.

Uniquement apres validation P3-r3 complete et autorisation laboratoire
ulterieure, `create --no-build api`, inspection
**avant start** : NetworkMode none, aucun port, USER attendu, groupe
lecteur, rootfs RO, ALL drop, no-new-privileges et deux binds RO exacts.
Inspecter aussi les autres conteneurs locaux : aucun alias vers LAB,
aucun sous-montage et aucune propagation partagee. Ne pas accepter les
seuls labels comme preuve. Puis `start api` de ce lecteur minimal.

Les opens frais, dans le **meme conteneur deja demarre**, sont faits par :

```sh
docker exec "$STATIC_ID" "$LAB_PYTHON" -I -B /probe.py
docker exec "$STATIC_ID" "$LAB_PYTHON" -I -B /probe.py --writes
```

Conserver l'ID exact du conteneur, inspect, identites, inode repertoire,
metadonnees enfant et hash avant/apres. Le lecteur ne valide pas
l'authenticite du JSON : sa valeur `state` n'est que telemetrie.
Le middleware reel et le parseur strict font l'essai applicatif.

Pour D01 uniquement, creer un **autre lecteur temoin negatif** par
`docker create` avec les memes protections mais le bind direct de
`LAB/recovery-control/recovery-state.json` sur le chemin du fichier.
Ne jamais l'ajouter a un candidat Compose ; sa configuration est
justement refusee par la garde. Le temoin ne donne aucun GO.

Pour D11 absent, faire echouer `create --no-build api` du lecteur
minimal en fournissant une source neuve inexistante ; ne jamais employer
la syntaxe `-v` qui pourrait creer le repertoire. Capturer le refus et
verifier que le daemon n'a rien cree. Aucun autre service n'existe dans
cette recette. Les quatre Compose applicatifs restent **config-only**.

### P3-r3 : source + rendu + hote, sans creation automatique

1. Verifier le transfert r3, son INPUTS.json et SHA256SUMS par un canal
   de confiance. Lire dans l'inventaire approuve les SHA de
   `lab/compose.static.yaml` et `lab/docker_reader.py` ; les fournir
   comme SOURCE_SHA et PROBE_SHA. Ne pas fabriquer une nouvelle valeur
   attendue a partir d'un fichier non verifie.
2. Creer une evidence r3 **neuve** sous BASE (meme regle CASE unique que
   P0). Ne pas ecrire dans l'evidence de l'echec P3 ou dans le LAB.
   Ne pas placer les sorties sous un repertoire deja scelle par
   SHA256SUMS/INPUTS.json ; sceller la nouvelle evidence seulement a la fin.
   Capturer version du plugin, daemon local approuve et son DockerRootDir.
   Le preflight ne contacte pas le daemon : ce dernier chemin est fourni
   explicitement et doit correspondre a la preuve `docker info` locale.
   Refuser tout endpoint distant, pull, build et resolution de tags.
3. Ecrire sous la nouvelle evidence un `parameters.json` avec exactement
   les sept chaines du fichier static.env :

```json
{
  "LAB_IMAGE": "sha256:<64 hex de l'image locale approuvee>",
  "LAB_PYTHON": "/chemin/python-dans-image",
  "LAB_READER_UID": "<UID explicite non nul>",
  "LAB_READER_PRIMARY_GID": "<GID primaire explicite non nul>",
  "RECOVERY_READER_GID": "<GID lecteur explicite non nul>",
  "RECOVERY_CONTROL_DIR": "/var/tmp/docnelo-rcd-<32hex>/recovery-control",
  "LAB_PROBE": "/chemin/r3/lab/docker_reader.py"
}
```

   Aucun autre champ ni secret. Les deux fichiers doivent exprimer les
   memes valeurs approuvees. Ne pas heriter des variables COMPOSE_FILE,
   COMPOSE_PROFILES, DOCKER_HOST/CONTEXT ou des sept parametres du shell.
   Pour le rendu, utiliser un environnement epure et un Docker config
   vide dedie dans la nouvelle evidence, avec endpoint Unix **local**
   explicitement approuve. Aucun env_file implicite ou override.
4. Capturer `docker compose ... config --format json` dans un fichier
   neuf avec noclobber, sans `--resolve-image-digests`. Le fichier
   source utilise est le YAML original valide, pas une reconstitution
   du JSON. Conserver aussi stderr et exit code. Le rendu peut contenir
   `bind: {}` ; cela n'atteste rien seul. Un second rendu
   `--no-normalize` peut etre conserve pour diagnostic, sans lui attribuer
   une garantie supplementaire.
5. Executer avec le Python offline approuve disposant de PyYAML :

```sh
"$PY" -I -B "$CANDIDATE/preflight_p3.py" \
  --source "$CANDIDATE/lab/compose.static.yaml" \
  --source-sha256 "$SOURCE_SHA" \
  --probe-sha256 "$PROBE_SHA" \
  --rendered "$E/rendered.json" \
  --parameters "$E/parameters.json" \
  --p2-record "$LAB/.candidate-lab.json" \
  --docker-root "$DOCKER_ROOT_VERIFIE" \
  --project "$PROJET_P3_UNIQUE" \
  --evidence "$E/source-render-host-neuf"
```

   La lecture du marqueur P2 root:0600 exige les droits locaux approuves ;
   ne pas changer son mode/proprietaire pour ce controle. Les privileges,
   l'interpreteur et les sources hashes doivent etre revus avant elevation.
   Le wrapper verifie l'inventaire r3 avant import du validateur. Le
   preflight ne cree aucune source ni verrou, ne lance aucune commande,
   ne fait aucun publish/ready et ne touche pas aux fichiers P2.

   Niveau source : YAML unique sans merge/cle dupliquee, deux binds longs
   RO avec false booleen **explicitement present**, profil lecteur complet
   sans heritage, substitutions restreintes aux sept parametres.

   Niveau rendu : projet/service exacts, image ID, USER UID:GID non-root,
   groupe lecteur, environnement et chemins exacts, network none, aucun
   port, rootfs RO, capabilities/securites/limites conservees, cibles
   et sources liees aux declarations. Seuls `bind: {}` et le false explicite
   sont admissibles a ce niveau apres preuve source. Bind absent/null,
   true, option supplementaire, masque, alias et changement RW refusent.
   Les dictionnaires vides sont reconstitues uniquement dans une copie
   interne pour repasser les gardes strictes ; le rendu brut reste intact.
   Pour mem_limit, seuls les trois couples type/valeur listes en tete
   sont normalises dans cette copie. L'absence de limite est un refus ;
   aucune conversion int(), float(), trim, changement de casse ou unite.
   Une autre difference du profil interdit de poursuivre.

   Niveau hote obligatoire : repertoire **deja existant**, metadonnees
   root:groupe/0750 et enfant0440, ancetres, aucun fichier parasite,
   exclusion DockerRootDir, identite device/inode du marqueur P2.
   Le probe doit aussi exister, etre regulier single-link et avoir le
   SHA approuve. Un repertoire source absent fait echouer, sans mkdir.

   La sortie preserve source brute, rendu brut, parametres, record P2,
   hashes et resultat dans une evidence neuve. Exit 0 signifie seulement
   `REVIEW_ONLY_SOURCE_RENDER_HOST_PREFLIGHT`, **p3_go=false**. Echec :
   exit non nul, aucune creation ; conserver sa sortie dans des logs neufs.
   Verifier `revision: v1-r3` dans preflight.json. Conserver la chaine
   mem_limit native et le bind vide, leurs types et SHA dans rendered.json.
6. **Ne pas creer/demarrer de conteneur au titre de cette revision.**
   Apres examen et autorisation ulterieure distincte seulement :
   reverifier hashes et identite hote immediatement avant creation,
   bloquer les autres writers/renames et utiliser exactement YAML,
   parametres, projet et endpoint controles. Ne pas recharger le rendu
   `bind: {}` comme un nouveau fichier Compose.
7. Meme apres autorisation future de `create` du lecteur seul, inspecter
   **avant tout start** : image ID reel, USER et GroupAdd attendus,
   sources/cibles exactes des deux binds, RW=false, rootfs RO,
   NetworkMode none, aucun port, ALL drop, no-new-privileges, limites
   attendues. Relever aussi l'absence d'alias RW/inherited/config/secrets
   dans les autres conteneurs locaux, de sous-montage et de propagation
   non revue ; revalider identite/modes hote apres create. Toute divergence
   interdit start. Les UID/GID effectifs et les lectures restent des
   preuves distinctes a obtenir dans une campagne autorisee.

La concordance de documents n'est pas une preuve d'execution Engine.
La verification hote est ponctuelle : un rename/suppression entre le
preflight et create reste un risque TOCTOU. Il faut gel operateur,
revalidation avant/apres et le test D11 natif dans un **nouveau**
namespace negatif explicitement autorise. Le comportement effectif de
Compose face a une source absente n'est pas qualifie par `bind: {}`.
Aucune experimentation D11, creation ou mise en service n'est faite ici.

## P4 - ASGI reel dans un conteneur sans reseau

Prerequis plus forts que P3 : image ASGI locale revue avec Debian13,
venv CP311.18 et fermeture des dependances. Ne pas utiliser l'entrypoint
Docnelo de l'image. Le candidat entier est monte RO sur `/candidate`,
le controle synthetique RO sur `/run/documind-control`, un nouveau
repertoire de preuves distinct sur `/evidence` RW et uniquement `/tmp`
en tmpfs ; **aucun parent du controle en RW**.

Creation directe avec `--pull=never`, `--network none`, aucun `-p`,
`--user UID:GID`, `--group-add GID_lecteur`, `--cap-drop ALL`,
`--security-opt no-new-privileges`, `--read-only`, limites explicites,
`--entrypoint /chemin/venv/bin/python`. Le repertoire hote d'evidence
est preprovisionne pour ce seul UID ; le controle demeure root:lecteur.
Les binds utilisent `--mount`, jamais une creation implicite de source.
Capturer/revoir inspect avant start, sans donner le socket au conteneur.

Arguments du processus Python :

```text
-I -B /candidate/run_local.py
--mounted-profile standard
--reader-gid <GID_lecteur>
--evidence /evidence/run-neuf
--scratch /tmp/case-neuf
```

Ajouter seulement `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` a l'environnement
synthetique ; ne transmettre aucun secret ni dotenv. stdin doit rester
ouvert (`docker create -i` puis attach interactif controle) jusqu'au stop.
Le lanceur interdit lui-meme sockets, sous-processus et dependances reelles.

Attendre `RCD_EVENT {"event":"startup",...}`. Dans un second terminal
operateur autorise, publier le nouvel enfant atomiquement, fsync compris,
enregistrer hash/temps de commit ; **puis seulement** envoyer :

```json
{"action":"probe","expect":"closed"}
{"action":"stop"}
```

Pour un processus initialement ready, le controle positif autorise
synthetique est `{"action":"probe","expect":"sentinel"}` : HTTP 500
intentionnel de la sentinelle aval, jamais un traitement metier.
La sentinelle est placee devant le vrai routeur, pas a sa place.
Un stop sans probe, EOF, mauvaise reponse, skip ou xfail font echouer.

Repeter avec `--mounted-profile beta_lite` dans une nouvelle evidence ;
les 403 Lite precedant la quarantaine sont comptes separement des 503.
Les autorites Lite sont des sentinelles fail-on-access, pas une
qualification de la chaine signee Lite ou de son writer 0644.

## Matrice D01-D20 et etat de preparation

Toutes les lignes Docker/POSIX ci-dessous sont **NON EXECUTEES**.
Les tests Windows donnent seulement les sous-preuves indiquees.

| ID | Operation preparee / oracle | Sous-preuve locale et limite |
|---|---|---|
| D01 | P3 temoin bind fichier, ready puis close ; ancien inode/ready attendu comme echec du modele | experience Debian fournie par l'utilisateur, non reproduite ici |
| D02 | P3 repertoire stable, meme sequence ; nouvel inode enfant/hash q apres commit, inode parent stable | replaces natifs Windows seulement ; lab/control.py + lecteur prepares |
| D03 | P4 initial ready, close puis probe closed sur tous les couples route/methode enregistres | vraie app ASGI Windows executee, sans bind Docker |
| D04 | P4 meme processus ready, q puis ready autorise, probe sentinel | reouverture synthetique Windows demontree ; aucune autorisation runtime ajoutee |
| D05 | P4 initial q, ready autorise, probe closed ; aucun worker ne demarre | preuve ASGI Windows executee |
| D06 | P4 nouveau processus autorise ready, probe sentinel et spies positifs | nouveau lifespan Windows execute ; nouveau processus/container a faire |
| D07 | P4 initial ready, remove, probe closed ; ENOENT, parent non recree | ASGI Windows execute |
| D08 | P4 remplacer chacune des 7 variantes invalides, probe closed, body non consomme | variantes executees en ASGI Windows |
| D09 | modes latch 000 et parent0700 sous UID API reel ; nouveaux opens refuses ; refaire initial ferme puis retablir | metadonnees simulees seulement ; P4 + mode prepares, droits Linux a faire |
| D10 | P3 --writes non-root : read autorise, write/truncate/unlink/rename/create tous refuses ; alias absents | modeles de gardes executes ; RO/DAC reels non testes |
| D11 | P3 source absente create refuse ; enfant absent dans source presente -> P4 closed | absence enfant ASGI executee ; create_host_path natif a verifier |
| D12 | symlink parent/enfant, FIFO/device : garde host refuse ; P4 symlink uniquement | modeles executes ; **ne jamais envoyer une requete sur FIFO**, open actuel peut bloquer |
| D13 | P3 `--hold` : FD ouvert avant commit, envoyer COMMIT_PUBLISHED apres replace ; ancien FD peut garder ready, fresh doit voir q | script prepare ; aucune promesse d'annulation des requetes/FD deja admis |
| D14 | deux lecteurs P3 et deux processus P4 existants, puis lecteur capture one-off none ; memes hashes frais apres commit | plusieurs consommateurs Docker non executes |
| D15 | republier plusieurs fois, relever UID/GID0440 avant/apres ; mode0600/0664 et mauvais owner/groupe doivent faire refuser la garde | ordre fchown/fchmod et controles modelises executes ; systeme reel a faire |
| D16 | rendu natif des 4 Compose config-only ; anciens overrides/masques/alias injectes doivent echouer ; inspect puis recreation du lecteur | rendu synthetique et mutations de configuration executes ; Compose/Engine non executes |
| D17 | sous barriere, renommer volontairement source synthetique et recreer son nom ; observer ancien repertoire monte ; garde identity doit refuser | changement d'inode simule execute ; operation Docker reservee a un nouveau namespace negatif |
| D18 | un LAB neuf par --interrupt ; exit91 attendu, hash/etat ancien ou nouveau complet selon commit ; garde refuse temporaires ; aucune reouverture | interruptions modelisees executees ; script Linux prepare, pas de power-cut prouve |
| D19 | nouvelle mini archive synthetique ready conservee + hash ; extraction dans **nouveau** artefact 0600 ; provisioning P2 force q dans autre dir ; comparer hashes origine/runtime | protocole prepare, aucune restauration/base/archives historiques executee ou modifiee |
| D20 | `node lab/frontend_inmemory.mjs` avec dependances npm offline ; upstream injecte503 -> health503, config200, Host/origin403 ; pas de serveur/socket | script prepare et syntaxe verifiee seulement ; cas non execute |

Pour D16, l'interpolation synthetique Python n'est **pas** l'algorithme
Compose. Produire dans E quatre rendus natifs avec environnements
fictifs complets distincts et fichiers env_file fictifs s'ils sont requis.
Ne pas utiliser les .env reels ni demander resolve-image-digests.
Verifier les gardes avec ces JSON et l'absence des anciennes cibles dans
`Mounts` reels. Restart n'est pas recreation ; changement du parent
apres creation invalide la qualification.

Pour D17, les seules commandes rename/mkdir sont a rediger/revoir avec
les chemins litteraux du **nouveau** LAB : aucun script generique ne
remplace le repertoire. `lab/control.py` refuse ensuite l'inode inconnu.
Conserver le temoin, ne pas tenter de le faire passer par un reset du marqueur.

Pour D19, ne pas appeler validate_restore avec une base. Une mini archive
de fichiers exclusivement synthetiques suffit a cette sous-preuve :
ne jamais reutiliser une archive existante ; aucune extraction vers le
controle vivant, aucun copy/chmod du latch restaure conserve comme preuve.
La qualification Backup/Restore complete demeure hors perimetre.

## Migration preparee - non executable par le candidat

1. Etablir et prouver une **barriere de trafic independante** du latch
   (lab : absence de ports et network none). En exploitation, une
   maintenance reverse-proxy exigerait une autorisation separee ;
   elle n'est pas effectuee ici.
2. Geler anciens writers, timers, captures et deployments ; identifier
   toutes les generations. Obtenir/conserver le verrou operateur
   historique au meme inode. Desactiver les anciens points d'entree
   pour eviter un backup de l'ancien chemin en parallele.
3. Arreter/drainer les anciens lecteurs et activites. La quarantaine
   HTTP ne stoppe ni les workers deja demarres ni les requetes admises.
   Un vieux bind fichier ready n'est pas une barriere de maintenance.
4. Provisionner un **nouveau** repertoire stable hors releases, donnees,
   backups et preuves ; publier uniquement q avec UID/GID/mode avant
   replace. Verifier hash, parser strict, traverse et lecture par UID API.
   Ne pas changer les permissions du fichier restaure original 0600.
5. Rendre un seul Compose complet par environnement, aucune fusion avec
   ancien fichier ; inspecter toutes les sources, cibles et aliases.
   Refaire les inventaires et attestations incluant le helper ; aucune
   signature ou confiance d'une ancienne release ne couvre ce candidat.
6. Recreer de facon controlee tous les consommateurs, y compris one-offs,
   avec le nouveau bind. Ne pas remplacer le repertoire apres creation.
   Verifier identites effectives, RO, meme inode enfant neuf et etat q.
   Un simple restart du vieux conteneur est insuffisant.
7. Demarrage q : health503 attendu, donc `depends_on: service_healthy`
   peut empecher le BFF de demarrer. Ne pas contourner cette securite
   pour obtenir une fausse preuve frontend ; D20 utilise une injection
   in-memory independante. Tester q et absence d'effets avant tout aval.
8. Toute erreur maintient barriere et fermeture ; aucun rollback vers
   un bind fichier ready. Si retour de code necessaire, seuls code et
   configuration compatibles avec le repertoire restent envisageables.
   Passage ready soumis a une decision operateur distincte et a de
   nouvelles preuves, jamais automatique. Un processus demarre ferme
   doit etre recree apres autorisation ; un processus initialement ready
   peut relire ready sans recreation (D04), ce qui est un risque a gerer.

Fin de campagne : arreter uniquement les IDs exacts des lecteurs crees
par ce CASE ; conserver inspect et preuves, sans `down -v`, purge,
prune ou suppression recursive. Hash de chaque fichier de preuve,
JUnit sans skip/xfail, versions Engine/Compose/image/dependances et
manifestes sources avant/apres. Produire le verdict seulement pour
les cas effectivement executes. Aucune ouverture automatique a ready.

**Aucun GO Docker operationnel, S2, Lifecycle 10, Public Beta ou production.**
