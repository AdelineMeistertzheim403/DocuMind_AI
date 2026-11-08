# Protocole candidat de construction P4 - offline et review-only

**Cette revision est BLOCKED. Aucun Dockerfile executable ni autorisation
de build/create/start. Les etapes futures ne doivent pas etre executees
tant que les preuves et autorisations requises manquent.**

## B0 - transfert et controles sans Docker

Verifier les ancres de `TRANSFER.md` par un canal independant, puis les
manifestes exacts. Sur Debian, utiliser seulement le Python hote approuve
et packaging26.3 deja verifie. Ne rien installer pour contourner une
dependance d'outil manquante. Les43 wheels sont dans la livraison v2 ;
ne pas modifier ni reextraire r3, v1, ni leurs preuves H1.

Definir PY (Python approuve absolu), PAQUET (extraction verifiee),
PAQUET_SUMS_ANCHOR (ancre recue) et E (destination absolue neuve,
parent existant, hors tout repertoire scelle/historique).
Executer ces commandes individuellement, en conservant chaque retour.

```sh
umask 077
mkdir -m 0700 -- "$E"
"$PY" -I -B "$PAQUET/common.py" verify "$PAQUET" --anchor "$PAQUET_SUMS_ANCHOR"
"$PY" -I -B "$PAQUET/record.py" --out "$E/wheel-command" --timeout 120 -- \
  "$PY" -I -B "$PAQUET/wheels.py" \
  --inventory "$PAQUET/materials/DEPENDENCIES_OBSERVED.json" \
  --wheel-dir "$PAQUET/materials/wheels" --out "$E/wheel-recheck.json"
"$PY" -I -B "$PAQUET/record.py" --out "$E/native-command" --timeout 120 -- \
  "$PY" -I -B "$PAQUET/native.py" \
  --inventory "$PAQUET/materials/DEPENDENCIES_OBSERVED.json" \
  --wheels "$PAQUET/materials/wheels" --out "$E/native-recheck.json"
"$PY" -I -B "$PAQUET/record.py" --out "$E/static-command" --timeout 120 -- \
  "$PY" -I -B "$PAQUET/verify_materials.py" --root "$PAQUET" \
  --out "$E/static-reproduction.json"
"$PY" -I -B "$PAQUET/record.py" --out "$E/gate-command" -- \
  "$PY" -I -B "$PAQUET/gate.py" --root "$PAQUET" --out "$E/material-gate.json"
```

Le gate refuse avec **code2**, decision BLOCKED et build_go=false.
Ce code2 est propre a ce nouveau gate ; le refus H1 historique rc1
reste intact. Capturer la commande avec record.py dans une evidence
neuve, sans transformer le refus en PASS build. Ne pas masquer ce retour
par `|| true`, reutiliser E, ni continuer vers build.

Les checksums de la copie d'inventaire doivent rester
`60f0d9f0b668409bba75914b5ef40027036c54ac69de96b05b8e813032813c20`.
La reproduction de la matrice/composants se fait avec
`report_materials.py --root PAQUET --out-dir E/reports-neufs`, ce
repertoire devant exister et etre vide, hors du paquet scelle.
Les comparaisons PyPI utilisent les reponses archivees, pas de nouvelle
connexion reseau Debian. Ne pas executer les commandes curl des receipts.
verify_materials.py retourne0 uniquement pour la reproduction statique
et inclut explicitement la decision BLOCKED ; ce n'est pas un GO build.

## B1 - ARRET AVANT BUILD : entree base et fermeture native

Une collecte ulterieure autorisee peut lire **les metadonnees d'image**
de la base candidate Debian locale et exporter son image sans la lancer.
Enregistrer le daemon/endpoint Unix local approuve, Engine/builder,
IDs complets et commandes/retours. Aucun inspect de conteneur historique
avec ENV/secrets ; aucune commande de P2/P3/D11. Ne pas promettre que
l'image P3 est une base P4 avant controle.

Exiger les preuves suivantes dans une nouvelle livraison scellee :

| Preuve | Controle requis |
|---|---|
| Archive Docker/OCI + SHA | Origine, fichier exact, ID config, manifest digest distinct, couches et diff IDs verifies |
| OS/platforme | /etc/os-release Debian13, linux/amd64 ; le tag n'est pas une preuve |
| CPython | 3.11.18 exact, binaire/libpython/stdlib, configuration et origine du build |
| Natif | PT_INTERP reel, chargeur/symlinks, glibc et versions fournies, chaque DT_NEEDED recursive et son SHA |
| Extensions | Tous les ELF des wheels et lib-dynload, ISA CPU, RPATH/RUNPATH/ld cache, relocations et imports |
| Provenance | Paquets et versions, origines/signatures/attestations verifiees ou limites explicitement acceptees |
| Builder | Version/driver/frontend preinstalle offline, aucune image builder/pull implicite |
| Revue | Decisions signees/attestees selon politique operateur, sans remplacer la provenance par un SHA |

Pas de lecture/embarquement de donnees restaurees, de venv hote, de .env,
de socket, de namespace, de cle ou de preuve historique dans l'image.
Toute extraction/reconstitution rootfs future doit etre hors des sources
figees, avec traitement revu des whiteouts, hardlinks/symlinks, modes et
contenus de couches. Le catalogue v2 **ne realise pas cette extraction**
et ne qualifie pas les diff IDs des images rejetees.

Une base absente, CP313 au lieu deCP311, une bibliotheque inconnue ou
un symbole manquant impose NO-GO. Pas de fallback system-libpq, pip,
wheel, sdist, compilation ou paquet apt pour faire passer le controle.
Les10 noms systeme du rapport natif ne sont pas une liste apt complete :
la stdlib et les modules charges tardivement doivent etre fermes aussi.

## B2 - algorithme d'assemblage a figer dans une revision suivante

Ceci est une specification de recette, **pas un Dockerfile utilisable**.
L'image de base, le builder et les commandes dependent de preuves encore
absentes. Aucun FROM/tag/digest n'est fourni par supposition.

1. Contexte neuf avec liste exacte : base approuvee locale,43 wheels
   bytes-identiques, locks a hashes, outils de verification, fichiers
   P4 v1 strictement verifies necessaires aux probes futures. Aucun
   backend copie dans l'image : le candidat complet sera monte RO.
2. Le frontend Docker doit deja etre local : pas de directive syntax
   distante ni de creation automatique d'un builder qui pull son image.
   Une pin de digest ou `--pull=false` n'est pas, seule, une garantie
   d'absence de resolution registry. `--network=none` ne couvre que le
   reseau des etapes de build, pas toutes les resolutions du frontend.
   Le labo reste sans egress ; toute tentative de collecte interdit build.
3. Lier la reference FROM locale a l'ID approuve immediatement avant
   build, avec le comportement du driver reel qualifie hors ligne.
   Une balise locale seule n'est pas une identite immuable. Le choix
   entre image ID/reference CAS/import local attend cette qualification.
4. Creer `/opt/p4-venv` avec le CPython3.11.18 verifie,
   `venv --without-pip`, sans system-site-packages. Ne pas reutiliser
   de venv ni les wheels non inventories d'ensurepip.
5. Bootstrap uniquement depuis le fichier pip25.2 hashe. L'import zip
   du probe v2 demontre cette mecanique sur la machine de preparation,
   pas sur la cible. La future recette doit verifier `pip.__file__`
   dans ce wheel, puis le pip installe dans le venv exact.
6. Fournir explicitement les43 fichiers wheel, chacun avec son SHA.
   Aucun extra implicite, aucun telechargement ou resolution de deps.
   Protections conjointes : pip isole/config externe neutralisee,
   `--no-index --no-deps --only-binary=:all: --require-hashes
   --no-compile --no-cache-dir --disable-pip-version-check`.
   Des chemins locaux explicites sont preferables ; si find-links
   est retenu, prouver le repertoire exact43 et l'unicite fichier/pin.
7. Interdire sdists, PEP517, scripts setup/editable et les deps build
   setuptools/wheel du backend. Le pip vendored n'autorise aucun build.
   La selection n'installe pas documind-ai ; imports source par run_local
   avec candidat RO, conforme au contrat r3/v1.
8. Copier les outils qualifies vers `/opt/p4-tools` et les inventaires
   vers `/opt/p4-materials`. Pour les probes P4 v1, conserver les octets
   exacts de son runtime_probe.py/offline.py, pas une substitution v2.
   Fixer ENV minimal approuve, USER non-root, aucun VOLUME/ONBUILD/port/
   healthcheck/app-entrypoint. Chaque lancement override explicitement
   l'entrypoint Python ; jamais l'entrypoint Docnelo normal.
9. Fixer versions des outils, contexte, ordre, modes/UID/GID, mtimes et
   SOURCE_DATE_EPOCH revu ; capturer logs/retours, image inspect,
   config/layers/diff IDs, archive finale et SHA. Rejouer le build
   autorise dans un contexte neuf pour comparer les resultats.
   Ne pas affirmer l'egalite bit-a-bit des exports sans la demontrer.

La construction ulterieure exige une autorisation specifique apres
revue de cette nouvelle recette et des materiaux complets. Le gate v1
reste inchange et ferme ; v2 ne contourne pas cette protection.

## B3 - verifications apres construction autorisee

Dans les preuves de build puis dans l'image finale autorisee :
CPython3.11.18, Debian13, amd64, chemin venv,43 distributions exactes,
pip25.2, `pip check` code0, aucun paquet manquant/parasite, chaque
RECORD et fichier installe conforme, pas de pycache genere.

Verifier imports fastapi/starlette/httpx/pytest/sqlalchemy/psycopg avec
implementation **binary**, openai/alembic/argon2/psutil/pgvector.sqlalchemy/
pydantic_settings/python_multipart/yaml et stdlib ssl/sqlite3/ctypes/zlib/
bz2/lzma. Sans importer l'entrypoint normal ni connecter de services.
Observer les bibliotheques mappees, SHA, versions effectives et ABI.
Un pip check reussi ne remplace ni ces imports ni la fermeture native.

Lire image inspect sur l'ID immuable, export SHA et inventaires. Distinguer
ID de config image, manifest digest registry/OCI et hash de l'archive :
ils ne sont pas interchangeables. Capturer les trois s'ils existent.
L'image finale doit etre revue avant tout create ; un build reussi seul
ne donne aucun GO P4 ni une approbation de provenance.

## B4 - ARRET AVANT CREATE et ARRET AVANT START

Les campagnes ASGI conservent le protocole et les scripts P4 v1
**inchanges**, avec autorisations separees. Nouveau namespace P4 seulement.
Ne pas reprendre H1/P1/P2/P3/D11, chmod un controle historique ou promouvoir
une ancienne evidence pour satisfaire les nouvelles preuves.

Create distinct de start : image ID exacte, pull never, reseau none,
aucun port, USER/GID numeriques non-root, groupe lecteur explicite,
cap-dropALL, no-new-privileges, rootfsRO, limitesCPU/RAM/swap/processus,
aucun socket, candidatRO sur /candidate, controle synthetiqueRO sur
/run/documind-control, nouvelle evidence0700 RW sur /evidence, tmpfs/tmp.

Inspect obligatoire du conteneur created jamais demarre, sources/cibles/
RO/RW/propagation/groupes/limites/entrypoint/environment exacts, absence
d'alias et gel des sources. Tout ecart interdit start. Autorisation start
ulterieure obligatoire, puis dialogue RCD_EVENT, commits atomiques
post-startup et probes closed/sentinel, arret JSON controle et collecte
complete selon v1. Les403 Lite restent distincts des503 de quarantaine.

Une validation image necessitant un processus dans le conteneur suit
elle aussi create -> inspect -> autorisation start ; pas de `docker run`
de diagnostic qui court-circuite les points d'arret.
