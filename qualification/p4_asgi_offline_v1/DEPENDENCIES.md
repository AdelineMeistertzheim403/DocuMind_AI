# Inventaire et fermeture des composants

## Selection proposee, pas approuvee

`DEPENDENCIES_OBSERVED.json` est l'inventaire exhaustif et lisible machine :
43 distributions, nom exact du wheel, version, SHA256 des octets, taille,
tags ABI/plateforme, Requires-Python/Requires-Dist, provenance observee.
Chaque fichier ELF embarque a aussi son SHA, sa taille, architecture et
DT_NEEDED. Les 32 ELF incluent les extensions de tests livrees par greenlet.
Les noms de fichiers/SONAME ne prouvent pas la version des bibliotheques
embarquees ; leur provenance reste celle du wheel parent, a revoir.

`requirements.p4.proposed.lock` est une **selection candidate** a un wheel
par pin. Il ne donne aucune autorisation d'installation ou de build.

| Groupe | Distributions directement utiles |
|---|---|
| Lanceur et harness | pytest9.1.1, HTTPX0.28.1, SQLAlchemy2.0.55, psycopg3.3.6 + binary, OpenAI2.54.0, Alembic1.20.0 |
| App et routeurs reels | FastAPI0.146.0, Starlette1.9.0, pydantic2.14.1 + core2.50.1, pydantic-settings2.16.0, argon2-cffi25.1.0, psutil7.2.2, pgvector0.5.1, python-multipart0.0.32 |
| Verification statique | PyYAML6.0.3 ; non requis par le seul test monte, inclus pour la campagne et l'inventaire |
| Bootstrap propose | pip25.2 historique ; non importe par le test, different du builder r3 |
| Transitifs | Tous les autres pins de l'inventaire ; derives de METADATA et markers cibles, pas du venv hote |

Le profil applicatif `standard` ne signifie **pas** `fastapi[standard]`.
Aucun extra FastAPI/Starlette/OpenAI, CLI HTTPX ou Uvicorn n'est selectionne.
Seul `psycopg[binary]` active un extra.

`psutil` est importe par `backend/services/worker.py` meme si aucun worker
reel ne demarre. `argon2` est importe par `backend/auth.py`.
`pgvector.sqlalchemy` est importe par les modeles RAG. SQLAlchemy/Mako/
MarkupSafe/greenlet, pydantic-core, jiter, cffi, argon2 bindings et
psycopg-binary ne peuvent donc pas etre remplaces par des stubs.

Cryptography50.0.2 (autorite Lite), PyMuPDF1.28.2 (extraction), Uvicorn,
uvloop, httptools, watchfiles, websockets et leurs extras ne sont pas
appeles dans ce chemin isole. Les imports cryptography du candidat
sont differes dans les fonctions d'autorite, laquelle est fail-on-access.
Les exclure est un **choix de perimetre a approuver**, pas une preuve
que ces dependances sont disponibles pour l'application complete.
Toute extension du chemin d'import invalide cette selection.
Les metadonnees du wheel pgvector fourni ne declarent pas numpy ;
ne pas deduire des besoins d'une autre distribution/version pgvector.

## Ecarts avec les locks r3

| Lock r3 | Limite pour P4 |
|---|---|
| `requirements.lock` | Versions, marqueurs Linux/Windows ; pas de hashes de fermeture |
| `requirements.runtime.lock` | CP313/Linux ; hashes ABI cffi, greenlet, jiter, MarkupSafe, psycopg-binary, pydantic-core, SQLAlchemy, PyYAML differents des wheels CP311 observes |
| `requirements.test.lock` | Cinq wheels purs disponibles dans l'archive CP311, ne suffit pas a lui seul |
| `requirements.build.lock` | packaging26.3, pip26.2.1, setuptools84.2.1, wheel0.48.0 ; le transfert observe fournit packaging26.3/pip25.2 seulement |

P4 n'installe pas `documind-ai` en editable ni via PEP517. Le candidat
source complet est monte RO ; les imports sont ceux du lanceur fige.
Une methode wheel-only sans compilation n'a pas besoin de setuptools/
wheel du builder applicatif. Cela exige de revoir le bootstrap pip25.2,
ou de fournir et inventorier un autre bootstrap explicitement approuve.
Ne pas copier un venv hote, recycler l'image P3 ou utiliser ensurepip
sans inventorier ses wheels embarques.

## Provenance observee

Les 42 wheels proviennent de l'archive du transfert
`deliveries/docnelo-v51-restored-latch-fastapi-20261102`.
L'archive, son manifeste interne, son lock et le manifeste externe sont
verifies en lecture seule. La qualification historique n'est pas une
approbation P4 ; confirmer les ancres via un canal independant.

PyYAML provient du fichier local
`deliveries/docnelo-v51-pyyaml-wheel-cp311/pyyaml-6.0.3-cp311-cp311-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl`.
SHA observe : `b8bb0864c5a28024fac8a632c443c87c5aa6f215c0b126c449ae1a150412f31d`.
Aucune preuve de collecte authentifiee/approbation independante n'est
fournie. Son hash n'est pas le hash CP313 du lock runtime.

## Composants d'image manquants

| Composant | Version cible / empreinte / provenance |
|---|---|
| Base OS + archive Docker/OCI | Debian13 amd64 ; ID, hash archive et origine **MANQUANTS** |
| Interpreteur et libpython | CPython3.11.18 x86_64 ; archive binaire, build flags, SHA et origine **MANQUANTS** |
| Stdlib et modules dynamiques | ssl, sqlite3, ctypes, zlib, bz2, lzma, asyncio, etc. ; SHA/origine **MANQUANTS** |
| Chargeur et glibc | Profil tags propose glibc2.41 ; relever la version reelle Debian et symboles, SHA **MANQUANTS** |
| Bibliotheques systeme | libc/libm/libdl/libpthread/librt/libresolv, libgcc_s, libstdc++, libz ; versions/hashes **MANQUANTS** |
| Libs stdlib supplementaires | OpenSSL, libffi, sqlite, bz2, lzma et toute DT_NEEDED recursive ; **A ETABLIR** |
| Configuration image | ENV, USER, absence VOLUME/ONBUILD/entrypoint metier, identite venv ; **NON FOURNIE** |

`IMAGE_COMPONENTS.pending.json` inventorie aussi ces absences et les
DT_NEEDED systeme non satisfaites par les ELF embarques observes.
Les valeurs null sont des blocages, jamais des empreintes a completer
automatiquement depuis une image inconnue.

Les bibliotheques psycopg embarquees (libpq, OpenSSL, Kerberos, LDAP,
SASL, SELinux, etc.) ont des noms prives et hashes dans l'inventaire.
Il faut encore fermer leurs besoins systeme recursifs et auditer les
versions reelles/provenances. DT_NEEDED ne couvre pas dlopen tardif.
Ne jamais executer `ldd` sur un binaire non approuve ; utiliser un
analyseur ELF offline revu, puis des observations mappees apres approbation.

## Methode reproductible attendue apres levee des blocages

1. Constituer sur une machine de collecte autorisee distincte (pas cette
   preparation, pas le labo isole) les archives binaires deja verifiees :
   base Debian13, CPython3.11.18 cible, wheels exacts, bootstrap, outils.
   Conserver URL/origine, horodatage, signatures/attestations disponibles,
   auteur de revue, version, SHA et plateforme de chaque composant.
2. Verifier hors ligne les signatures/ancres approuvees. Controler les
   fichiers ELF et la fermeture recursive et les modules stdlib requis.
   Faire un inventaire de la base (dpkg metadata ET SHA des fichiers)
   et du build CPython. Tout composant inconnu bloque.
3. Verrouiller le contexte exact, la recette revue et ses outils par SHA.
   Base locale par image ID immuable ; aucune balise a resoudre. Aucune
   instruction FROM distante, apt, curl, sdist, compilation implicite,
   PEP517 ou dependance resolue pendant l'assemblage.
4. Venv neuf au chemin stable `/opt/p4-venv`, sans paquets systeme et sans
   ensurepip non inventorie. Bootstrap depuis le wheel pip approuve.
   Installation de tous les wheels explicites avec les protections
   **conjointes** `--no-index --no-deps --only-binary=:all:
   --require-hashes --no-compile --no-cache-dir`, configuration pip
   externe neutralisee. Pas de resolution meme locale implicite.
5. Assembly Docker futur avec pull interdit et reseau build none,
   uniquement composants locaux approuves. Inclure les outils P4 sous
   `/opt/p4-tools`, l'inventaire sous `/opt/p4-materials`. Ne pas inclure
   l'app, .env, cles, namespaces, preuves ou socket Docker dans l'image.
   Default entrypoint inoffensif, jamais l'entrypoint normal Docnelo.
6. Executer pip check **offline** dans cette fermeture, verifier la liste
   exacte des distributions, chaque RECORD/fichier, imports et binaires.
   Le probe a runtime sous restrictions confirme l'ABI, pas la provenance.
7. Conserver logs/codes du build, versions builder, SOURCE_DATE_EPOCH,
   ordre/mtime/modes du contexte, options de compression, image inspect,
   ID/config/layers, archive exportee + SHA et inventaires avant/apres.
   Refaire l'assemblage depuis les memes entrees et comparer les sorties.
   Ne pas promettre une egalite bit-a-bit des archives Docker sans la
   demontrer ; distinguer reproductibilite des entrees et du resultat.

Cette methode **n'est pas une recette de construction executable**.
Le build-gate de ce paquet reste ferme jusqu'a une nouvelle revision
revue qui fournisse les composants et la recette manquants.
