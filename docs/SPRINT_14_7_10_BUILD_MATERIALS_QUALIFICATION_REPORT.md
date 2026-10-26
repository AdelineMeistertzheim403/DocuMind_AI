# Sprint 14.7.10 — Acquisition et qualification des matériaux de build

26 octobre 2026. Code étudié : PR Draft nº 6, source
`f3c92eb8ba2bb69b83a9798ebc3df8a70f48fbb2`, branche locale
`preparation/sprint-14-review`. Références lues :
[14.7.9](SPRINT_14_7_9_PREMERGE_RISK_REVIEW.md),
[14.7.5](SPRINT_14_7_5_SUPPLY_CHAIN_REPORT.md),
[14.7.4](SPRINT_14_7_4_DOCUMENT_INTEGRITY_REPORT.md),
[runbook](SPRINT_14_7_PUBLIC_BETA_OPENING_RUNBOOK.md).

**RF10-03 réduit, non clos.** Les onze wheels manquants sont acquis à leur version
exacte, les 49 distributions runtime/test Linux sont disponibles avec hashes
vérifiés, et le build Python isolé du projet est répétable octet pour octet sur
deux essais. Bases officielles et source pgvector sont maintenant identifiées.
Les trois images de production ne sont pas reconstruites ni certifiées : matériaux
npm/système, vérification cryptographique des provenances et adoption contrôlée
des entrées restent ouverts. Aucune acceptation de risque ou publication autorisée.

## 1. Périmètre et conservation des preuves

Les accès réseau réalisés concernent uniquement :

- `pypi.org` : métadonnées de versions et documents de provenance ;
- `files.pythonhosted.org` : octets des wheels annoncés par ces métadonnées ;
- registre officiel Docker Hub, `registry-1.docker.io`, authentification anonyme
  `auth.docker.io`, via le client Docker pour les manifestes/provenances et la base
  Python par digest ;
- `api.github.com/repos/pgvector/pgvector` et `codeload.github.com/pgvector/pgvector` :
  tag, commit, arbre Git et archive du dépôt officiel ;
- `deb.debian.org` et `dl-cdn.alpinelinux.org` : métadonnées officielles de paquets.

Pas d'accès Registry privée, VPS, B2, SMTP, fournisseur IA ou nouvelles Actions.
Les URLs présentes dans les provenances ne sont pas automatiquement suivies.
En particulier, **registry.npmjs.org n'est pas dans la liste d'origines autorisées
de cette mission et n'a pas été contacté**. Aucun périmètre réseau élargi.

Répertoire privé ignoré : `var/s14-7-10-materials/` ; contexte Docker explicitement
sélectionné sous `var/s14-7-10-clean-context/` ; pilotes de qualification
sous `var/s14_7_10_*.py`. Les wheels, JSON, index système, archive pgvector,
locks expérimentaux, export Git et sorties restent sous var. La base Python
est aussi acquise dans le cache du moteur Docker local, par digest, sans retaguer
une image existante ou créer de tag de future release. Pas de conteneur ou volume
préexistant arrêté, modifié ou supprimé ; conteneurs d'essai lancés avec `--rm`.

Les premiers refus d'accès au daemon Docker/WSL dans le bac à sable local sont
distincts de la disponibilité réelle : lecture autorisée hors de ce bac à sable,
Docker Desktop **29.8.2** et WSL disponibles. Aucun réglage système modifié.
Le client HTTPS Python a rencontré `SSLCertVerificationError` pour Docker ;
le client Docker existant a réussi avec sa confiance TLS normale. Aucun
`verify=false`, `--insecure`, changement de certificats ou règle réseau appliqué.

## 2. Onze wheels Linux CPython 3.13

Acquisition initiale : **13:44:09–13:44:12 UTC**. Pour chaque fichier exact de
14.7.9 : réponse officielle PyPI, fichier unique, `yanked=false`, taille et
SHA-256 calculés conformes aux métadonnées ; nom/version METADATA conformes,
tags WHEEL égaux aux tags du nom et Requires-Python compatible avec 3.13.17.
Aucune substitution de version ou sdist.

| Wheel (version exacte) | SHA-256 publie = calcule | Provenance PyPI |
| --- | --- | --- |
| [cffi 2.1.1](https://pypi.org/pypi/cffi/2.1.1/json) | `a931079504ecc49efed7744c476a5c343a92fabf66dec2db95edb1b2fdc770e2` | HTTP 404 |
| [greenlet 3.5.6](https://pypi.org/pypi/greenlet/3.5.6/json) | `f98e8215e172f567ce80eeaed9107fb4d32b6c44f26983d9b8334658136a205a` | HTTP 404 |
| [httptools 0.9.0](https://pypi.org/pypi/httptools/0.9.0/json) | `088de1738e1af624466a01c35d652dbe6fb825be887c76d68aa850621d81db88` | Document disponible, signature non verifiee |
| [jiter 0.17.0](https://pypi.org/pypi/jiter/0.17.0/json) | `58df29268a95e910f17db7ec9178eb7f15aa8619aaca3575275c4e6b3f4fe4c5` | Document disponible, signature non verifiee |
| [MarkupSafe 3.0.4](https://pypi.org/pypi/MarkupSafe/3.0.4/json) | `434139499bb20b502ed3baa1f169e618f924a97e7a777fea1a49446d80106cf6` | Document disponible, signature non verifiee |
| [psycopg-binary 3.3.6](https://pypi.org/pypi/psycopg-binary/3.3.6/json) | `cec5ea900390897d0b46130f60bc2883bf19c314f9044235217c8be88b0ef269` | HTTP 404 |
| [pydantic_core 2.50.1](https://pypi.org/pypi/pydantic_core/2.50.1/json) | `17e722e156d0444ecaefbe640bdb60928752bf2013e2b7a11cdb099aaae19bec` | HTTP 404 |
| [PyYAML 6.0.3](https://pypi.org/pypi/PyYAML/6.0.3/json) | `0f29edc409a6392443abf94b9cf89ce99889a1dd5376d94316ae5145dfedd5d6` | HTTP 404 |
| [SQLAlchemy 2.0.55](https://pypi.org/pypi/SQLAlchemy/2.0.55/json) | `998f729f57381f8fdee8e402d2081da76c17a2501fa92c9046c24fdff581c729` | HTTP 404 |
| [uvloop 0.23.0](https://pypi.org/pypi/uvloop/0.23.0/json) | `e2cba180d6451822763eda8364f342435a873bcfb3849cbd82fdeca248ca65eb` | Document disponible, signature non verifiee |
| [websockets 17.2](https://pypi.org/pypi/websockets/17.2/json) | `d87091c4347daadbcc0833b65812ff38d7350c67339625d4e4a512cf38e3e8ef` | Document disponible, signature non verifiee |

Les noms complets d'archives, URLs HTTPS stables de fichiers, tailles, tags et
hashes publiés/calculés sont conservés dans `acquisition-report.json` ; noms et
hashes de toutes les archives figurent aussi en annexe. Les tags exacts de ces
onze fichiers sont ceux listés dans 14.7.9, maintenant confirmés dans leurs WHEEL.
Ce sont des wheels cp313/cp313 manylinux x86_64 : cible glibc, pas musl/Alpine,
arm64, Windows ou cp313t. Le seuil glibc varie selon les tags de chaque fichier.

### Provenances PyPI réellement disponibles

L'endpoint officiel `/integrity/<projet>/<version>/<fichier>/provenance` répond :

- documents disponibles pour **httptools, jiter, MarkupSafe, uvloop, websockets** ;
- HTTP 404 pour **cffi, greenlet, psycopg-binary, pydantic_core, PyYAML, SQLAlchemy**.

Les cinq statements décodés portent le predicate
`https://docs.pypi.org/attestations/publish/v1` et le nom/hash du fichier reçu.
Identités de publication déclarées dans ces documents : MagicStack/httptools
(`release.yml`), pydantic/jiter (`ci.yml`), pallets/markupsafe (`publish.yaml`),
MagicStack/uvloop et python-websockets/websockets (`release.yml`). Ces dépôts
supplémentaires n'ont pas été contactés ; il s'agit de données reçues de PyPI.

**Non réalisé :** validation cryptographique indépendante des signatures,
certificats, racines et preuves de transparence, ou audit du workflow éditeur.
Document disponible et sujet cohérent ne valent pas identité cryptographiquement
certifiée. Un 404 ne signifie ni paquet compromis ni preuve universelle qu'aucune
autre attestation n'existe. L'intégrité HTTPS/hash est établie par rapport à PyPI,
pas une garantie absolue contre une compromission de l'éditeur ou de l'index.

## 3. Fermeture Python et inventaire PEP 517 distinct

Les 49 distributions de l'inventaire Linux CI de 14.7.9 ont été acquises auprès
de PyPI à leur version exacte ; fichier binaire compatible sélectionné, metadata
Name/Version et SHA-256 contrôlés. Les onze fichiers précédents sont réutilisés
à l'identique. Avec trois ajouts de tooling, cela fait **52 wheels uniques**,
**53160927 octets** au total :
packaging 26.3 fait déjà partie des 49 distributions.

Deux locks locaux **uniquement expérimentaux** sont générés sous var :

- `qualification-runtime-test.lock` : les 49 distributions et leurs vrais hashes ;
- `qualification-build.lock` : quatre distributions nécessaires à l'environnement
  de qualification retenu, avec tous leurs hashes et dépendances externes actives.

Le second ne prétend pas reproduire le tooling historique PEP 517 de GitHub CI.
Choix pour l'expérience : pip 26.2.1 (version observée sur le runner Linux),
setuptools 84.2.1 (version courante interrogée et compatible avec `setuptools>=75`),
wheel 0.48.0 et son besoin packaging>=24.0, satisfait par packaging 26.3 du lock.
Ce choix relève du builder isolé autorisé, **pas d'une mise à jour adoptée par
l'application ou ses Dockerfiles**. pip 26.2.2 Windows est examiné par métadonnées,
sans remplacer le pip choisi pour l'expérience Linux.

| Outil du builder candidat | Version | SHA-256 du wheel |
| --- | --- | --- |
| packaging | 26.3 | `d7193f7c8e4e93f444fde0262bf90af30e16fa0ad0ad44cb553c87339b23cd1c` |
| pip | 26.2.1 | `71138adf1f4ca900cdb7d289c21b7494329f2332b6d85f0e1c42108c0384ed3e` |
| setuptools | 84.2.1 | `ca140b45d5325a9478f880e351484f62fef15f336462e449ca0c03c873d589c2` |
| wheel | 0.48.0 | `3217dcc807155e45db462d7ef2431f5ddda0d7273b700d05a67b271ceb1287ab` |

Pour ces quatre distributions, les Requires-Dist actifs sans extras ont été
parcourus : aucun besoin externe non couvert par ce lock ; extras de tests/docs
de setuptools non activés. `get_requires_for_build_wheel()` retourne **[]** dans
les deux builders. La fermeture requise par ce backend choisi est donc disponible.
Le paquet wheel externe est conservé pour qualifier explicitement cet outil ;
son installation ne démontre pas que le backend l'a chargé plutôt qu'une copie
vendoriée. Le seul besoin initial du pyproject est setuptools>=75.

Setuptools embarque aussi des copies vendoriées : autocommand 2.2.2,
backports.tarfile 1.2.0, importlib_metadata 8.7.1, jaraco.text 4.0.0,
jaraco.context 6.1.0, jaraco.functools 4.4.0, more_itertools 10.8.0,
packaging 26.3, platformdirs 4.4.0, tomli 2.4.0, wheel 0.46.3, zipp 3.23.0.
Leurs octets sont figés par le hash du wheel setuptools ; cela ne constitue pas
une acquisition indépendante de chacune de leurs sources. L'inventaire externe
seul ne doit pas masquer ces composants.

Le manifeste embarqué `pip/_vendor/vendor.txt` de pip 26.2.1 déclare aussi :
CacheControl 0.14.4, distlib 0.4.2, distro 1.9.0, msgpack 1.1.2, packaging 26.2,
platformdirs 4.10.0, pyproject-hooks 1.2.0, requests 2.34.2, certifi 2026.6.17,
idna 3.18, urllib3 2.7.0, rich 14.2.0, pygments 2.20.0, resolvelib 1.2.1,
setuptools 70.3.0, tomli 2.4.1, tomli-w 1.2.0, truststore 0.10.4. Cette liste
provient du manifeste de l'archive reçue, sans acquisition indépendante de ces
projets ; leurs octets sont liés au hash du wheel pip. Ne pas confondre ces copies
avec les versions distribuées séparément dans le venv. Le lock complet de cette
expérience couvre les distributions externes actives, pas un audit de chaque
source ou patch vendorié.

Incident du pilote local, conservé : sa première inspection exigeait un seul
METADATA dans toute l'archive setuptools et refusait les métadonnées vendoriées.
Le pilote privé a été corrigé pour identifier exclusivement le METADATA principal
au premier niveau dist-info. Aucun contrôle de hash/version n'est retiré, aucun
fichier applicatif ou outil suivi du dépôt n'est modifié. La première inspection
reste sous `closure-first-inspection.json` ; l'acquisition finale a zéro erreur.

## 4. Build Python hors réseau depuis le Git exact

Source exportée par `git archive` depuis f3c92eb8, **289 fichiers suivis**, avec
empreinte de l'archive et manifeste par fichier sous var. Aucun fichier non suivi,
`.env` privé ou répertoire var n'entre dans cette source. Le versionnement du
projet reste 0.1.0 ; la traçabilité de cette wheel expérimentale dépend du manifeste
Git et des preuves, pas de son seul nom de version.

Deux copies neuves sous `/tmp/source-a` et `/tmp/source-b`, deux venvs sans pip
initial. Bootstrap depuis le wheel pip haché, installation du lock build avec
`--no-index --only-binary=:all: --require-hashes`, puis appel du backend PEP 517
préinstallé dans cet environnement dédié. Pas de résolution implicite réseau et
pas d'option --no-build-isolation appliquée au venv applicatif existant.

Confinement de l'expérience : base officielle Python par digest amd64, UID 1000,
`--network none`, racine read-only, `--cap-drop ALL`, `no-new-privileges`, 1536 Mo,
2 CPU, 64 PID, tmpfs borné à 768 Mo. Source/matériaux bind montés en lecture seule,
sortie privée sous var en écriture. Aucun socket Docker monté ni secret applicatif.
Il s'agit de l'environnement de build/test, pas d'un nouveau profil du parseur.

`SOURCE_DATE_EPOCH=1793019084`, date du commit source, dans les deux constructions.
Sans cette expérience, une promesse générale de build déterministe serait abusive.

| Sortie | Taille | SHA-256 |
| --- | --- | --- |
| documind_ai-0.1.0-py3-none-any.whl, essai a | 124216 octets | ff56d72215fff006c514354d34bd8b6cab46d8cff50e758a9e51e56b54cc359f |
| Même wheel, essai b | 124216 octets | ff56d72215fff006c514354d34bd8b6cab46d8cff50e758a9e51e56b54cc359f |

**Octets identiques.** Les deux environnements installent ensuite les 49 wheels
runtime/test hors réseau avec hashes, puis la wheel projet sans résolution de
dépendances. `pip check` réussit deux fois. Les inventaires installés sont conservés.
Cette répétabilité concerne une wheel Python pure du projet, pas les archives
natives tierces recompilées, ni une image OCI complète bit-identique.

### Validation complémentaire et limites

Validation exécutée ensuite dans une image locale dédiée, dépendances dans une
couche immuable, avec les mêmes restrictions d'exécution et `/tmp` explicitement
noexec :

- Python **3.13.17**, glibc **2.41**, UID **1000**, aucune capacité ajoutée ;
- imports des **onze paquets** réussis, psycopg importé avant psycopg_binary
  conformément au contrat de ce dernier ;
- les **53 wheels** présents (52 acquis + wheel projet) possèdent un tag supporté
  par le runtime réel ;
- les **12 dépendances runtime** du METADATA projet correspondent au pyproject
  du Git source ;
- `tests/test_build_materials.py` : **15 réussis, 0 ignoré, 0 échoué**, 0,48 s ;
- `pip check` réussi ; un avertissement Starlette/httpx TestClient, non masqué.

Ce sont des tests ciblés de matériaux et d'inventaire, pas une nouvelle suite
complète Windows/Linux/PostgreSQL ni la recette de l'application finale.

La première validation native a échoué avec `failed to map segment from shared
object` pour _cffi_backend dans le venv sous `/tmp`. Le tmpfs Docker est noexec.
L'essai suivant a placé le venv dans la sortie dédiée sous var ; l'installation
sur le bind mount Windows a dépassé la borne de 180 s. Cette limite n'a pas été
augmentée. Le contexte Docker initial englobait ce venv Linux partiel et son lien
lib64 illisible sous Windows : transfert du contexte refusé, avant build.
Un contexte neuf a donc été créé avec seulement les fichiers explicitement utiles,
sans supprimer le venv ou toucher à des fichiers préexistants.

La première image a été construite avec succès ; son test refusait l'import direct
de psycopg_binary sans import préalable de psycopg. Le harnais privé a corrigé cet
ordre, sans modifier un paquet, puis les deux constructions finales utilisent le
même contexte corrigé. Tous ces refus sont conservés séparément sous var :
`offline-validation-first.log`, `offline-validation-bind-timeout.log`,
`qualification-image-first-context-error.log`,
`qualification-image-import-order-error.log`. Aucun n'est présenté comme un test
applicatif réussi. Les options du tmpfs, les capabilities, le réseau et seccomp
ne sont pas assouplis ; le venv final est dans la couche d'image en lecture seule.
Ces diagnostics de harnais ne concernent pas le sandbox applicatif de production.

## 5. Bases officielles Docker : identité et versions

Manifestes lus via `docker buildx imagetools inspect` ; hash de chaque index raw
comparé au digest annoncé par le client, hash des trois manifestes enfants raw
comparé au descripteur amd64. Plateforme de chaque config : linux/amd64.

| Base officielle | Digest index | Digest manifeste linux/amd64 | Digest de configuration |
| --- | --- | --- | --- |
| python:3.13-slim | `sha256:d98cc29d3266e535dd9da1099688d9cb3ca4753813571e071763d17725460962` | `sha256:d879ed88565a7a3c614b980b369d4a5025a9d057b71f93d09fc6d0b2ca823a18` | `sha256:72036a705a7cff38924efd674e60654666cb283faf7b3fad160b34007f7395bd` |
| node:22-alpine | `sha256:fe4f6d74e20370acb04ad889077d14d0f64a9c8ea6a42bc60cddf1e844699914` | `sha256:025b8e975a61d94e33abeafaad1255ef44e4898cf1a1b6446860009c72e6d284` | `sha256:ae59e9992c6b3e963dd9dac9c476287048177ad8f90ac646669afb738705f56d` |
| postgres:17-alpine | `sha256:266d3c257594e195b309ae9d1805e54c788f1d7b375f56bf6c367aac6c917e7b` | `sha256:e4cb93687b062cd25a0e8f672d85a7708235009d70d31f8a7698d9370092a9c4` | `sha256:ab20e934b27ba3ff927c1b4c9ff8cf6c32f315f743efe68dd3441182a87fb085` |

Les digests sont ceux observés **pendant cette mission**, pas un verrou appliqué.
Le tag node:22-alpine résout Node **22.23.4**, alors que le runner frontend de
14.7.8 utilisait **22.23.3** : c'est une divergence de matériaux à traiter avant
adoption, pas une défaillance prouvée ni une mise à jour implicite de l'application.
Python **3.13.17** est effectivement exécuté dans l'expérience ; versions Node
22.23.4 et PostgreSQL 17.11 sont lues dans leurs configurations/provenances,
pas confirmées par exécution de ces deux bases pendant ce lot.

L'Image ID Python local vaut le digest de configuration
`sha256:72036a705a7cff38924efd674e60654666cb283faf7b3fad160b34007f7395bd`.
Ne pas le substituer au digest de manifeste dans FROM/release.json. Pour Node et
PostgreSQL, les digests de config sont identifiés dans les manifestes, sans
prétendre avoir acquis leurs couches ou inspecté une Image ID locale de ces bases.

### Provenances des bases consultées

Les index contiennent des descripteurs d'attestation liés aux enfants amd64.
Consultation de `.Provenance` sur **l'index** : objet SLSA non vide pour les trois
bases, buildType `https://mobyproject.org/buildkit@v1`, builder déclaré
`https://github.com/docker-library`, cinq entrées materials par base et indicateurs
completeness=true déclarés par le producteur. Les sources/révisions déclarées :

- Python : docker-library/python, e316b6c5b88b7c8e4806aa7626060c9bd8227e66 ;
- Node : nodejs/docker-node, 80f02a542da739e6a662451d1db66456a0dea253 ;
- PostgreSQL : docker-library/postgres, 2603e26e245e558218728ee14e0a42dcb020dc7f.

Ces dépôts ne sont pas clonés : lecture de la provenance stockée dans le registre
officiel seulement. L'appel sur le manifeste enfant seul retournait `{}` ; une
valeur JSON non nulle n'est pas assimilée à une attestation complète. La lecture
de l'index a permis d'examiner les véritables objets SLSA.

Ces données augmentent la traçabilité, mais leurs indicateurs de complétude sont
des déclarations du producteur. Pas de vérification indépendante des signatures
ni de reproduction du build upstream, ni de preuve que toutes les archives APT/APK
et sources téléchargées sont individuellement couvertes par les cinq matériaux.
Elles ne constituent pas la provenance future des trois images DocuMind.

## 6. Dépendances APT/APK encore dynamiques

Dockerfile backend : apt-get update, libseccomp2 sans version/snapshot.
Dockerfile.db : apk add build-base/git et transitifs sans versions, source clonée
par tag puis source/toolchain supprimés. Une base épinglée ne fige pas ces accès.

Métadonnées officielles consultées, sans installation de paquets :

- [Debian trixie InRelease](https://deb.debian.org/debian/dists/trixie/InRelease) et
  [Packages amd64](https://deb.debian.org/debian/dists/trixie/main/binary-amd64/Packages.xz).
  SHA-256 Packages.xz `7778d3e3f303b7ddb8ce0fe7c8d57473a076c6bf2e8f241f75421d2396352498`,
  conforme à la section SHA256 reçue dans InRelease. libseccomp2 **2.6.0-2 amd64**,
  dépendance libc6>=2.14, hash deb publié
  `89d5138e05fb6a86b9afd8b54dc0fb4b14f4c27c05e6c5f767c2132bdf808531`.
  Le deb lui-même n'est pas téléchargé ni vérifié ; signature InRelease non validée
  avec un trousseau indépendant dans ce lot.
- [Alpine v3.24 main x86_64 APKINDEX](https://dl-cdn.alpinelinux.org/alpine/v3.24/main/x86_64/APKINDEX.tar.gz) :
  hash de l'archive reçue `c169fa06972f9d2639ad1ea0effa26bf7223a72101a41c5cf2c12813d885cab5`.
  Entrée RSA présente, pas de validation de signature. Versions observées :
  build-base **0.5-r4**, git **2.54.0-r0**, gcc **15.2.0-r5**, make **4.4.1-r4**,
  musl-dev **1.2.6-r3**. Transitifs et checksums d'index conservés, sans prétendre
  qu'ils sont les hashes SHA-256 des archives APK téléchargées.

Fermeture système complète, dépôts supplémentaires éventuels, signatures, octets
deb/APK et politique de snapshot/mises à jour restent à qualifier. Les versions
de l'index courant ne prouvent pas celles utilisées lors d'un ancien build CI.

## 7. pgvector v0.8.7

Origine : [dépôt officiel](https://github.com/pgvector/pgvector).
Tag résolu par API GitHub en commit
**`f37c13f68b57d2c3472b2214fbcff699d6d34876`**.
[Archive exacte](https://codeload.github.com/pgvector/pgvector/tar.gz/f37c13f68b57d2c3472b2214fbcff699d6d34876) :
**133206 octets**, SHA-256
`83d673c3b287cddbf3879f86215f043f2c2b56c69d37b2a77504910db1ed6e56`.
Hash calculé sur les octets reçus, pas comparé à un checksum de release signé.

Comparaison complémentaire de chaque contenu au Git tree officiel : calcul des
Git blob SHA-1 (`blob <taille>\0<contenu>`) : **158/158 identiques**, aucun chemin
manquant ni divergent, arbre non tronqué. Cela relie l'archive au contenu Git du
commit servi par la même origine ; ce n'est pas une signature indépendante.
L'API indique commit **non signé**, reason=unsigned.

vector.control porte default_version=0.8.7. Le README déclare PostgreSQL 13+ et
documente PostgreSQL 17+ ; il recommande 17.3+ pour un problème de liaison de
17.0–17.2. La base identifiée 17.11 satisfait ce seuil. Cela justifie une
compatibilité déclarée à tester, pas une compilation/intégration nouvelle réussie.

**Non réalisé dans ce lot :** compilation avec toolchain verrouillée, nouvelle
extension vector.so hachée, CREATE EXTENSION et tests PG sur cette compilation.
La suite PG CI antérieure a réussi, mais ne relie pas son binaire à cette archive
qualifiée ni à un toolchain intégralement fixé. Le pgvector Python 0.5.1 reste
distinct de l'extension serveur 0.8.7 ; aucune mise à jour effectuée.

## 8. Reconstructions locales : ce qui est démontré et ce qui manque

| Niveau | Résultat de cette mission |
| --- | --- |
| Acquisition wheels officiels | 52 archives uniques contrôlées, dont les onze exactes manquantes ; aucune substitution. |
| Lock expérimental build | Quatre distributions et dépendances externes actives couvertes, copies vendoriées inventoriées ; non adopté. |
| Deux environnements build neufs hors réseau | Réussis ; aucun appel implicite PyPI. |
| Deux wheels projet | Octets/hashes identiques, même code Git et SOURCE_DATE_EPOCH. |
| Deux installations runtime/test | Hors réseau avec hashes ; pip check réussi deux fois. |
| Compatibilité native et outil d'inventaire | Résultats détaillés en section 4 et dans les sorties privées. |
| Deux images locales de qualification Python | Constructions sans cache d'étapes et sans réseau réussies ; contextes identiques, base et matériaux fixés. Ce ne sont pas les trois images de production. |
| Trois Dockerfiles de production complets deux fois | **Non exécutés** ; matériaux qualifiés incomplets et entrées encore dynamiques. |
| Couches/bit-reproductibilité des trois images finales | **Non établie** ; égalité d'une wheel Python ne vaut pas égalité de couches OCI. |
| Landlock/seccomp, auth, quota, intégrité documentaire sur nouvelles images finales | **Non réexécutés ici**, aucune image finale qualifiée produite ; preuves CI de la PR conservées, pas étendues à ces sorties futures. |

Images de qualification finales, non publiées :

- `documind-s14-7-10-python-qualification-a-v2:local` : Image ID
  `sha256:2fdad259241454fd91efbc99ced69e54e98568220b0ef9532458c2f70cd236be` ;
- `documind-s14-7-10-python-qualification-b-v2:local` : Image ID
  `sha256:b3bdd74543d1ccbdd223fdf275755b6052437209f4d4952d33230e2e0b8ac95c`.

Les deux IDs et leurs listes de couches rootfs sont différents. Comparaison des
versions installées : égales ; hashes de **24 fichiers .so** et **3857 fichiers
.py** du site-packages : égaux. Cela ne couvre pas tous les contenus, notamment
bytecode, métadonnées d'installation et headers/couches ; aucune cause unique de
tous les écarts n'est démontrée. Les dates de création diffèrent aussi. Ne pas
annoncer que la normalisation d'horodatages suffirait à rendre l'OCI identique.
L'image initiale à ordre d'import erroné reste distincte, sans suppression/retagging
d'une image de production. Le Dockerfile de qualification n'ajoute pas libseccomp2
et ne remplace pas Dockerfile/Dockerfile.db/frontend/Dockerfile du projet.

Raisons précises de non-construction complète :

1. Frontend npm : pas de fermeture des 368 tarballs d'origine qualifiée ; accès
   réseau npm hors liste autorisée. Le lock/SRI et un node_modules/cache historique
   ne suffisent pas à prétendre avoir acquis ces matériaux de manière vérifiée.
2. Backend/DB : bases désormais identifiées mais Dockerfiles non adoptés par digest,
   APT/APK et dépendances de compilation non verrouillés/validés intégralement.
   Un build dynamique pourrait réussir, sans remplir l'objectif de mêmes entrées.
3. Builder : version/provenance d'un builder dédié à figer avant expérience de
   production complète. Ne pas télécharger implicitement une image BuildKit ou
   des frontends tiers hors origines approuvées. Les essais Python utilisent un
   conteneur jetable avec le backend PEP 517 explicitement qualifié ; les deux
   images complémentaires utilisent le driver Docker/BuildKit local existant,
   sans télécharger d'image de builder supplémentaire. Ses propres matériaux
   ne sont pas déclarés intégralement qualifiés par cet usage.
4. Provenance : lecture des documents acquise, politique cryptographique de
   vérification/trust et preuves upstream encore incomplètes.

Aucun réseau Docker déverrouillé, mécanisme d'isolation désactivé ou tag de release
utilisé pour faire aboutir artificiellement ces builds.

## 9. Risques et modifications futures proposées — non appliquées

| Risque | État après acquisition |
| --- | --- |
| RF10-03 | Réduction vérifiable : archives Python, tooling candidat, répétabilité wheel, bases et commit pgvector identifiés. **Reste ouvert** pour qualification cryptographique, fermeture npm/système, trois builds complets et provenance des images DocuMind. |
| R14-SQL-01 | HTTP 503 historique inexpliqué ; aucune cause identifiée par ces builds. |
| R14-SQL-03 | Admission commitée malgré erreur/mail absent ; récupération et acceptation opératrice distinctes, aucun remboursement/reset de quota. |
| RF10-04 | Publication séquentielle partielle toujours possible : arrêt/protection des preuves, aucun rerun/retagging/suppression automatique. |

R14-SQL-02 reste corrigé dans le code examiné avec ses preuves antérieures ; pas
de réparation automatique de pertes historiques ni de correction implicite SQL-03.
Aucun nouvel audit CVE actualisé, acceptation de risque ou garantie d'absence de
composant compromis n'est déduit d'un hash ou d'un test réussi.

Propositions futures, soumises à revue et autorisation :

- qualifier/adopter un lock build distinct et une fermeture runtime hachée complète,
  incluant politique des composants vendoriés, sans recopier aveuglément le lock
  expérimental dans le dépôt ;
- proposer des FROM par digest amd64, commit/archive pgvector contrôlés et
  entrées APT/APK reproductibles avec politique de mises à jour ;
- demander séparément, si nécessaire, l'accès à l'origine npm officielle et aux
  matériaux de confiance des vérificateurs de provenance ; aucune extension tacite ;
- choisir un vérificateur et ses racines/matériaux avant de valider signatures et
  preuves de transparence ; définir les cas sans attestation et leur traitement ;
- produire les trois images complètes en double build à entrées identifiées,
  expliquer différences de couches/temps et tester les invariants sur ces images ;
- relier leur inventaire/provenance au vrai Git SHA, run/attempt et digests,
  puis au bundle neuf fichiers et à l'approbation root indépendante.

## 10. Go / No-Go pour une future publication privée

**Go pour poursuivre la qualification et la revue en Draft**, avec ces preuves.
**No-Go pour déclarer une RC utilisable, fusionner/publier, déployer ou ouvrir**
sur la seule base de ce lot. Cette mission ne relit ni ne modifie la PR distante.

Avant de préparer une publication privée autorisée : décider humainement le
traitement de RF10-03/SQL-01/SQL-03, compléter ou traiter explicitement les écarts,
revoir les changements d'entrées proposés et leurs effets, refaire la CI sur le
nouveau SHA si des fichiers suivis changent, et autoriser distinctement l'effet
automatique de publication d'une fusion main. L'ancienne exception Sprint 10
ne couvre pas automatiquement cette version. Aucun risque accepté ici.

Après publication autorisée seulement : vérifier trois digests amd64, provenance
et inventaires réels, neuf fichiers/statement, schéma 0007 et profil
public-beta-2026-10-v1 ; appliquer RF10-04 en cas de sortie partielle ; recetter
les digests réels. Le déploiement fermé exige ensuite son autorisation, ses guards,
sa sauvegarde et sa stratégie de secours. Ouverture publique et IA restent interdites.

## 11. Clôture et contrôles Git

Seul ce rapport rejoint les nouveaux fichiers documentaires non suivis. Aucun
changement de source applicative, dépendance suivie, workflow, migration, secret,
quota, schéma ou .env.production. Les trois rapports 14.7.7–14.7.9 restent conservés.
Locks/harness, export Git, venv de validation et matériaux sont ignorés sous var.
Index vide ; même branche/HEAD. `git diff --check` et contrôles du nouveau Markdown
exécutés à la clôture. Aucun commit, push, PR, merge, workflow lancé ou publication.
Pas d'intervention sur les autres projets Docker, services ou volumes existants.

## Annexe A — Inventaire complet des wheels acquis

Toutes les lignes ci-dessous : version exacte, fichier PyPI non yanked, hash
calculé égal au hash publié. Cet inventaire est celui des matériaux acquis pour
qualification Linux, pas un inventaire des images finales. Les URLs et tailles
figurent dans `closure-acquisition.json`, les reçus originaux sous var.

| Archive acquise | SHA-256 |
| --- | --- |
| `alembic-1.20.0-py3-none-any.whl` | `77eb101048d95f982c0353e9233404889dcd7a6fc244c107836c0e2fc9cf7d9d` |
| `annotated_doc-0.0.5-py3-none-any.whl` | `117bac03a25ede5df5440e855b32d556049ca169ead221505badf432fed4b101` |
| `annotated_types-0.8.0-py3-none-any.whl` | `f072f4d804ea359e4eaf198b1af7a8b0943881a87f31bb764f8bf219bb9419e0` |
| `anyio-4.15.1-py3-none-any.whl` | `6152fdbbf9a77fdec97731721bebf7c4c44f7c29b424b0065826173efc7ed101` |
| `argon2_cffi-25.1.0-py3-none-any.whl` | `fdc8b074db390fccb6eb4a3604ae7231f219aa669a2652e0f20e16ba513d5741` |
| `argon2_cffi_bindings-26.1.0-cp310-abi3-manylinux_2_26_x86_64.manylinux_2_28_x86_64.whl` | `27f1821903e2ceadcb88ec2b45ef190897b7682449c772f4d9b53e42c520cf29` |
| `certifi-2026.10.18-py3-none-any.whl` | `73191c47aaa79da394e8fee2dbc2ec827432cab56311122c9e47abf79e390f62` |
| `cffi-2.1.1-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.whl` | `a931079504ecc49efed7744c476a5c343a92fabf66dec2db95edb1b2fdc770e2` |
| `click-8.5.0-py3-none-any.whl` | `255bc9599cf7748b4b1a446ccc735421bd08a2ae529a8b88597d3de5664ee360` |
| `distro-1.9.0-py3-none-any.whl` | `7bffd925d65168f85027d8da9af6bddab658135b840670a223589bc0c8ef02b2` |
| `fastapi-0.146.0-py3-none-any.whl` | `0eb9985a7d5bb11ce9a962d4b65e0cf1a2e13d6aca2e14da57bc526370e26748` |
| `greenlet-3.5.6-cp313-cp313-manylinux_2_24_x86_64.manylinux_2_28_x86_64.whl` | `f98e8215e172f567ce80eeaed9107fb4d32b6c44f26983d9b8334658136a205a` |
| `h11-0.16.0-py3-none-any.whl` | `63cf8bbe7522de3bf65932fda1d9c2772064ffb3dae62d55932da54b31cb6c86` |
| `httpcore-1.0.9-py3-none-any.whl` | `2d400746a40668fc9dec9810239072b40b4484b640a8c38fd654a024c7a1bf55` |
| `httptools-0.9.0-cp313-cp313-manylinux1_x86_64.manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl` | `088de1738e1af624466a01c35d652dbe6fb825be887c76d68aa850621d81db88` |
| `httpx-0.28.1-py3-none-any.whl` | `d909fcccc110f8c7faf814ca82a9a4d816bc5a6dbfea25d6591d6985b8ba59ad` |
| `idna-3.20-py3-none-any.whl` | `ab7ae7122974553370f0bdb919e1a960b2cd1bc1ef0276416d896db81c14582c` |
| `iniconfig-2.3.1-py3-none-any.whl` | `9121e2c1fdb355232495be3194c8dfe87ccc2d5dee45947b78e68f499790d7a7` |
| `jiter-0.17.0-cp313-cp313-manylinux_2_17_x86_64.manylinux2014_x86_64.whl` | `58df29268a95e910f17db7ec9178eb7f15aa8619aaca3575275c4e6b3f4fe4c5` |
| `mako-1.4.3-py3-none-any.whl` | `723296007c870bfd6b3f0c3230dba7198096e5269297ebf5e4eff9e7ffa39d4f` |
| `markupsafe-3.0.4-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl` | `434139499bb20b502ed3baa1f169e618f924a97e7a777fea1a49446d80106cf6` |
| `openai-2.54.0-py3-none-any.whl` | `89089789197ccdb87f173a03145ed1598d00795220c93e96cf712b1cbf5e5f2b` |
| `opentelemetry_api-1.45.1-py3-none-any.whl` | `b31553efa588ae44bc306f863c785c5333a9ecc091248c6ee68b4b6c87fdedfb` |
| `packaging-26.3-py3-none-any.whl` | `d7193f7c8e4e93f444fde0262bf90af30e16fa0ad0ad44cb553c87339b23cd1c` |
| `pgvector-0.5.1-py3-none-any.whl` | `ec5bcd5ffaefe6ecb2dcc9564ca921d284564b969183bc837a144604773af8ea` |
| `pip-26.2.1-py3-none-any.whl` | `71138adf1f4ca900cdb7d289c21b7494329f2332b6d85f0e1c42108c0384ed3e` |
| `pluggy-1.7.0-py3-none-any.whl` | `7dd7b0d8832ba3cb632c306926ded123429211b83641b35dc5c41ad2d34f9bec` |
| `psutil-7.2.2-cp36-abi3-manylinux2010_x86_64.manylinux_2_12_x86_64.manylinux_2_28_x86_64.whl` | `076a2d2f923fd4821644f5ba89f059523da90dc9014e85f8e45a5774ca5bc6f9` |
| `psycopg-3.3.6-py3-none-any.whl` | `a1db9f7148b06a28606767efaca51fa6f9398c5c0a3810519be69d7000bdb631` |
| `psycopg_binary-3.3.6-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.whl` | `cec5ea900390897d0b46130f60bc2883bf19c314f9044235217c8be88b0ef269` |
| `pycparser-3.12-py3-none-any.whl` | `a076f3f489b39b43ed13563a1dafe42447445bec2e294154ec5c57fcdda4c85e` |
| `pydantic-2.14.1-py3-none-any.whl` | `9195d967ec791692a04438115466764fb8b9a27b31f14a760437694f40d6b454` |
| `pydantic_core-2.50.1-cp313-cp313-manylinux_2_17_x86_64.manylinux2014_x86_64.whl` | `17e722e156d0444ecaefbe640bdb60928752bf2013e2b7a11cdb099aaae19bec` |
| `pydantic_settings-2.16.0-py3-none-any.whl` | `7e73acf7f61936a15e5a3b6eedaea29f133357faf7272f2607ba479b049dd7f2` |
| `pygments-2.21.0-py3-none-any.whl` | `2363c69b61c4a97c838da3b130dcd6468f4848992b21a82f2a63ec34377137d9` |
| `pymupdf-1.28.2-cp310-abi3-manylinux_2_28_x86_64.whl` | `397d6715c1f0df7548a92d0afd8ce370fc48fa47aeefac16be2bc04a16a8227f` |
| `pytest-9.1.1-py3-none-any.whl` | `37a86b45efb9a47a61a36449063e8e18d0cab3161329fc099eb21783169c4f0c` |
| `python_dotenv-1.2.4-py3-none-any.whl` | `42269a8a5b3fd54ffa6f3d84b18abed50064717576b4ecf03dc4a55d8aa04fdc` |
| `python_multipart-0.0.32-py3-none-any.whl` | `ff6d3f776f16878c894e52e107296ffc890e913c611b1a4ec6c44e2821fe2e23` |
| `pyyaml-6.0.3-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl` | `0f29edc409a6392443abf94b9cf89ce99889a1dd5376d94316ae5145dfedd5d6` |
| `setuptools-84.2.1-py3-none-any.whl` | `ca140b45d5325a9478f880e351484f62fef15f336462e449ca0c03c873d589c2` |
| `sniffio-1.3.1-py3-none-any.whl` | `2f6da418d1f1e0fddd844478f41680e794e6051915791a034ff65e5f100525a2` |
| `sqlalchemy-2.0.55-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl` | `998f729f57381f8fdee8e402d2081da76c17a2501fa92c9046c24fdff581c729` |
| `starlette-1.9.0-py3-none-any.whl` | `fd3f159936e882d06c1108f84688f7cda2cf85fc6a592a50edbd175e882c2ddc` |
| `tqdm-4.70.1-py3-none-any.whl` | `c293e525e6fef9c20e8728fd4612df02a0aa31bb5fe91ecd93e123b1b7bffa73` |
| `typing_extensions-4.16.0-py3-none-any.whl` | `481caa481374e813c1b176ada14e97f1f67a4539ce9cfeb3f350d78d6370c2e8` |
| `typing_inspection-0.4.4-py3-none-any.whl` | `65b8397ba37ccbce054456aaccddfc91e6e3083c92824df348d96ca832f3f147` |
| `uvicorn-0.54.0-py3-none-any.whl` | `505bdb0f318731d45f1f712071fc781a8981f6847a31c902c9f5e652d4f67faf` |
| `uvloop-0.23.0-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl` | `e2cba180d6451822763eda8364f342435a873bcfb3849cbd82fdeca248ca65eb` |
| `watchfiles-1.3.0-cp310-abi3-manylinux_2_17_x86_64.manylinux2014_x86_64.whl` | `b5768b49e426fd5b550b012c866db347cdf15c398ef98dc557b6e6b72fa74cd1` |
| `websockets-17.2-cp313-cp313-manylinux1_x86_64.manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl` | `d87091c4347daadbcc0833b65812ff38d7350c67339625d4e4a512cf38e3e8ef` |
| `wheel-0.48.0-py3-none-any.whl` | `3217dcc807155e45db462d7ef2431f5ddda0d7273b700d05a67b271ceb1287ab` |
