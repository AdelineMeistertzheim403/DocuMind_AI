# Docnelo V5.1 - P4 Build Materials v2

**Decision de preparation : BLOCKED. Review-only. Build GO=false ;
create/start GO=false ; aucun GO production.**

Livraison independante de r3 et de P4 offline v1. Aucun de ces arbres
ni des preuves P1/P2/P3/D11/H1 n'est modifie. Aucun build, pull, load,
create, start, exec ou stop Docker n'a ete effectue. Aucun acces aux
donnees restaurees reelles. D11 n'a pas ete relance.

## Resultats de cette preparation

| Sujet | Constat verifie | Decision |
|---|---|---|
| Ancre inventaire Debian/v1 | `60f0d9f0b668409bba75914b5ef40027036c54ac69de96b05b8e813032813c20`, identique localement | Entree figee, pas une approbation |
| Wheels | 43 copies byte-identiques, SHA/taille, RECORD exhaustif et tags internes verifies | Integrite statique PASS, ABI cible non executee |
| Base locale | Requete npipe locale refusee, code1 conserve ; 9 archives Docker-save examinees, 6 IDs de config distincts | Aucune base Debian13/CPython3.11.18 verifiee |
| Images Python archivees | Hint ENV Python3.13.17, pas3.11.18 ; archives web sans runtime Python cible | Rejetees comme base P4, sans demarrage |
| ELF des wheels | 32 ELF64 x86_64 ; 120 liens DT_NEEDED ; 31 liens locaux directs coherents noms/versions, 89 non resolus sans base | Fermeture binaire non approuvee |
| PyYAML6.0.3 | Wheel exact publie sur PyPI, hash et taille identiques | Provenance de contenu corroboree, pas de signature/revue independante |
| pip25.2 | Meme concordance PyPI ; execution `--version` depuis le wheel zip, sans installation | Probe Windows/CP313 seulement, bootstrap CP311 non qualifie |
| Recette Docker | Base, fermeture systeme et builder offline non qualifies | Aucun Dockerfile executable delivre |

Les resultats Debian transmis par l'operateur (transfert v1, r3,
transfert historique5/5, metadonnees43/0 erreur et H1 refuse avec rc1)
sont conserves comme contexte fourni, pas reexecutes ou reconstruits.
H1 reste un refus correct de garde, **pas un PASS build/P4**.

## Base : recherche et limites

`LOCAL_IMAGE_ARCHIVES.json` inventorie chaque archive par taille, SHA,
image ID calcule sur les octets de configuration et layer/diff IDs
declares. Aucun layer applicatif n'a ete extrait ni execute. Les
diff IDs n'ont pas ete recalcules ; un ID de configuration observe
ne prouve pas l'authenticite de l'image ou ses fichiers systeme.
Les ENV complets, commandes d'historique et donnees metier ne sont pas
publies : seul le hint public PYTHON_VERSION est releve.

La consultation du daemon sur l'endpoint Windows local
`npipe:////./pipe/docker_engine` est indisponible (receipt complet,
retour1 dans `local-image-list`). Elle n'etablit pas l'absence d'une
image sur un autre endpoint ni sur la VM Debian. Aucun daemon/Desktop
n'a ete demarre pour contourner ce refus.

Les IDs des images Python **non cibles** observes sont notamment :
`sha256:4aa850b6fb8d16b32fd731d94b232b2f817f461892b3f39a28e7557a25a5eb3d`,
`sha256:525c859f0d162d0ff47ae1f7a04d630a14702d8815b1cf6862833b662f523ca4`,
`sha256:32a1516206d9e648e3741b54dc0543c0b455f22cdf676e7d69d9a971e1f4213d`.
Ils ne sont pas des propositions de remplacement. L'image P3 presente
sur Debian n'est pas livree ici ; son identite/provenance ne sont pas
deduites de son usage historique ni du Python du venv hote.

`P4_IMAGE_COMPONENTS.json` garde donc image_id, hash d'archive de base,
CPython, glibc, chargeur et provenance a **null/non approuve**.

## Analyse native

`P4_NATIVE_CLOSURE.json` contient pour chacun des32 fichiers ELF :
wheel parent, version de distribution, chemin virtuel d'installation,
SHA, architecture, PT_INTERP, DT_NEEDED, RPATH/RUNPATH/SONAME,
versions requises et definitions exportees de versions.
L'analyse est statique, sans ldd ni appel de chargeur.

Les 10 noms systeme non resolus sont `ld-linux-x86-64.so.2`,
`libc.so.6`, `libdl.so.2`, `libgcc_s.so.1`, `libm.so.6`,
`libpthread.so.0`, `libresolv.so.2`, `librt.so.1`,
`libstdc++.so.6`, `libz.so.1`. Les31 correspondances locales concernent
des bibliotheques privees de psycopg-binary et leurs versions de symboles.
Elles ne prouvent ni les relocations individuelles ni la recherche
recursive complete du chargeur.

Les versions requises observees incluent GLIBC jusqu'a2.25,
GLIBCXX jusqu'a3.4.21 et CXXABI jusqu'a1.3.9. Cela est compatible
**statiquement en principe** avec les familles annoncees ; ce n'est pas
une preuve qu'une glibc2.41 reelle ou les bons fournisseurs existent
dans une base P4. Les tags manylinux ne qualifient ni glibc seule,
ni les autres libs, ni l'ISA CPU, ni les imports reels.

Sans base, restent inconnus : PT_INTERP du Python, chargeur et symlinks,
libpython/stdlib/lib-dynload, bibliotheques systeme et cache ld,
symboles/versions effectivement fournis, provenance des paquets et
chargements tardifs dlopen. Les32 ELF incluent les extensions tests
greenlet livrees dans le wheel ; elles ne sont pas supprimees pour
faire disparaitre leur besoin libstdc++.

## PyYAML : verification nouvelle, sans approbation inventee

Sur la machine Windows de preparation, **hors VM Debian**, deux GET
HTTPS explicites ont archive les metadonnees publiques PyPI pour
PyYAML6.0.3 et pip25.2. Aucun wheel n'a ete telecharge, aucun paquet
installe. Les scripts de controle livres sont offline ; ne pas relancer
ces acquisitions reseau dans le labo.

Le fichier PyYAML CP311/manylinux x86_64 local (806638 octets) correspond
exactement au fichier de la release PyPI :
`b8bb0864c5a28024fac8a632c443c87c5aa6f215c0b126c449ae1a150412f31d`.
Publication indiquee par PyPI : `2025-09-25T21:32:04.553491Z`.
Le JSON, les en-tetes HTTP, stdout/stderr, commande, retour numerique,
horodatages et hashes sont conserves dans `pyyaml-upstream`.
`P4_UPSTREAM_COMPARISONS.json` donne l'URL exacte du fichier publie.

Sources publiques comparees :
https://pypi.org/pypi/PyYAML/6.0.3/json et
https://pypi.org/pypi/pip/25.2/json.
Les en-tetes HTTP, TLS et checksums ne sont pas des signatures de
l'artefact. Aucune signature/attestation n'a ete verifiee, aucune chaine
complete du telechargement initial local n'est disponible et aucune
approbation independante n'est accordee par cette comparaison.

## Selection minimale et bootstrap

`P4_WHEEL_APPROVAL_MATRIX.md` justifie chaque distribution. Les41
distributions de fermeture du chemin monte, plus PyYAML (outil statique)
et pip (bootstrap), conservent les43 pins figes de v1. Le graphe de
Requires-Dist est reverifie pour CPython3.11.18/Linux/x86_64 ; seules
les dependances de l'extra psycopg[binary] sont activees.
Standard est un profil applicatif, **pas** fastapi[standard].

Les imports reels imposent aussi psutil (worker importe), argon2
(auth), pgvector (modeles), Alembic (harness), OpenAI et psycopg
(gardes du lanceur). Ils ne sont pas remplaces par des stubs.
Cryptography, PyMuPDF, Uvicorn/uvloop/httptools/watchfiles/websockets,
les extras de CLI et les services reels restent exclus du chemin P4
controle. Les autorites Lite restent fail-on-access. Un elargissement
du harness invaliderait cette selection, sans droit de modifier r3.

Le wheel pip25.2 pur Python (1752557 octets) correspond a PyPI :
`6d67a2b4e7f14d8b31b8b52648866fa717f45a1eb70e83002f4331d07e953717`,
publication `2025-07-30T21:50:13.323040Z`.
`P4_PIP_BOOTSTRAP.json` inventorie aussi son vendor.txt ; les composants
vendored sont couverts par le hash du wheel, **pas approuves chacun**.
Le setuptools vendored n'est pas une autorisation de build PEP517.

Le probe importe pip depuis le zip exact, pas le pip installe. Seul
`--version` est execute, avec sockets/processus/config pip externes
interdits ; aucune installation. La premiere tentative reste conservee :
le probe traitait incorrectement SystemExit(None), qui signifie succes
en Python. Le probe corrige distingue cette semantique d'un code CLI
perdu ; la capture externe finale conserve bien un retour numerique0.
Ce succes Windows/CPython3.13.7 ne qualifie ni l'installation dans un
venv cible CP311 neuf ni pip check cible. Tous deux restent bloques.

## Conditions pour lever le NO-GO

1. Fournir une base locale Debian13/amd64 CPython3.11.18, son archive
   exacte et SHA, image inspect/ID/config/layers, provenance/attestations
   disponibles et decision independante. Pas de tag invente ou de P3
   automatiquement promu.
2. Fournir l'inventaire rootfs/paquets/fichiers de cette base, les
   versions/build flags CPython, le chargeur et la fermeture recursive
   ELF/versions/symlinks/cache, y compris les modules stdlib requis.
3. Executer et capturer sur cette base le bootstrap wheel-only, puis
   pip check, imports, ABI/ISA et hashes, dans un laboratoire de
   composants autorise distinct. Une probe conteneur exige elle aussi
   create/inspect/start autorises, jamais un docker run implicite.
   Refaire ces controles dans l'image finale apres build autorise.
4. Revoir la provenance et accepter explicitement les43 wheels,
   PyYAML/pip et leurs composants embarques ; le contenu corrobore
   par PyPI ne vaut toujours pas acceptation.
5. Qualifier le builder offline : frontend deja local, aucun bootstrap
   implicite d'un builder conteneurise, politique de resolution de base
   et absence de trafic. Publier alors une recette scellee et revue.
6. Obtenir une autorisation **build distincte**, puis conserver les gates
   **create** et **start** de P4 v1. Aucun GO production n'en resulte.

`P4_PREPARATION_DECISION.json` reste BLOCKED. Un materiau absent,
une erreur, un retour perdu ou un controle non execute ne devient jamais
PASS. La conservation des927 fichiers historiques scopes est controlee
avant/apres ; elle ne pretend pas inspecter les namespaces Debian distants.

## Semantique des resultats

PASS_STATIQUE signifie seulement que les octets et observations
declarees ont ete reproduits : hashes/RECORD/tags/graphe/coherence des
rapports. Un rc0 de ces outils ne valide ni une base ni P4.
FAIL couvre contradiction, hash/taille modifie, metadata/tag incompatible
ou fournisseur natif errone. INCOMPLETE couvre materiau/preuve absent,
capture interrompue, retour non numerique/perdu et controle non execute.
FAIL et INCOMPLETE maintiennent tous deux la decision BLOCKED.

READY_FOR_INDEPENDENT_REVIEW ne serait possible qu'avec les materiaux,
fermetures et decisions de revue documentes, jamais par simple changement
de booleens. Meme cet etat ne donnerait aucune autorisation d'execution.
Les 15 tests locaux des nouveaux outils, leur reproduction statique et
les controles sources sont scopes Windows/CPython3.13 ; voir receipts et
LOCAL_CHECKS.json. Aucune campagne Debian P4 n'a ete executee ici.
