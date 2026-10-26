# Sprint 14.7.5 — Supply chain et reproductibilité des builds

26 octobre 2026. Branche locale `preparation/sprint-14-5-ux-email-abuse`, HEAD
`8243e0511c5505a9cc70f76ad02392f7a816590d`. Références :
[qualification 14.7.3](SPRINT_14_7_3_RELEASE_RISK_QUALIFICATION_REPORT.md),
[intégrité 14.7.4](SPRINT_14_7_4_DOCUMENT_INTEGRITY_REPORT.md),
[revue RC](SPRINT_14_7_1_RELEASE_CANDIDATE_REVIEW.md),
[runbook](SPRINT_14_7_PUBLIC_BETA_OPENING_RUNBOOK.md).

**RF10-03 réduit, mais non clos.** Quatre distributions transitives sont maintenant
contraintes aux versions déjà observées ; l'inventaire CI devient vérifiable et
bloque les dépendances de la fermeture runtime/test non contraintes ou divergentes.
Deux réinstallations hors ligne par plateforme réussissent sur les mêmes archives
hachées. Ni les trois images de production ni l'environnement PEP 517 ne sont
reconstruits entièrement : les preuves ne permettent pas de certifier la supply chain.
**PR en brouillon envisageable après autorisation ; RC utilisable et public No-Go.**
Aucun risque n'est accepté au nom de l'exploitante.

## 1. État initial et périmètre de confiance

Le lock initial possédait 47 lignes de contraintes exactes, sans hashes, mais
laissait quatre distributions transitives Linux non contraintes et trois Windows.
`setuptools>=75` est résolu dans le build PEP 517 isolé ; le lock runtime ne le
contraint pas automatiquement. Les bases Python/Node/PostgreSQL sont des tags,
APT/APK et le tag source pgvector restent dynamiques. Les digests des images
finales et le bundle attesté assurent l'identité des sorties, pas l'immuabilité
des entrées ni leur origine. Ces constats 14.7.3 restent distincts d'un audit CVE.

Toutes les inspections de cette mission sont locales : caches pip, venvs, sources,
images Docker déjà présentes. Aucun téléchargement, Registry, GitHub, VPS, B2,
SMTP réel ou fournisseur IA contacté. La fermeture de production reste l'état
annoncé par l'opératrice, pas un contrôle distant réalisé ici.

## 2. Dépendances Python et changement appliqué

`requirements.lock` reprend exactement la proposition 14.7.3 :

```text
argon2-cffi-bindings==26.1.0
cffi==2.1.1
pycparser==3.11; sys_platform == "win32"
pycparser==3.12; sys_platform == "linux"
uvloop==0.23.0; sys_platform == "linux"
```

Ce sont les **versions déjà installées**, pas des mises à jour fonctionnelles.
Les 47 lignes antérieures sont conservées textuellement, sans changement de version.
Le fichier est normalisé CRLF vers LF : `git diff` montre donc 52/47 lignes ; un
contrôle binaire `splitlines()` confirme que seules les cinq lignes ci-dessus sont
ajoutées au contenu. Cette normalisation résout les avertissements whitespace de Git.

Couverture de la fermeture des dépendances déclarées runtime **et extra test** :
Windows CPython 3.13.7, 50 distributions ; WSL CPython 3.12.3 et image de preuves
CPython 3.13.17 Linux, 49. Aucune version manquante, non contrainte ou divergente
dans ces fermetures observées. Colorama/tzdata et uvloop expliquent des différences
de plateforme ; pycparser conserve les deux versions effectivement observées.
Les extras desktop, macOS, PyPy et arm64 ne sont pas certifiés par cette campagne.
Le projet reste à la version 0.1.0 ; les futures releases sont identifiées par SHA
Git/digests, pas par ce numéro.

## 3. Archives réelles et SHA-256

Le cache HTTP pip contient 87 archives wheel reconnues sous Windows et 51 sous WSL.
Les wheels nécessaires sont copiés **sans modification d'octets** vers des répertoires
neufs sous `var/s14-7-5-wheelhouse-*`. Leur nom local est reconstruit depuis Name,
Version, Build et un tag compatible du WHEEL : c'est un **alias local**, pas une
prétendue preuve du nom téléchargé ou de l'URL d'origine. Les SHA-256 portent sur
l'archive entière et sont revérifiés après copie, jamais déduits des RECORD installés.

Exemples effectivement calculés, sans hash inventé :

| Archive identifiée par métadonnées | Plateforme | SHA-256 des octets en cache |
| --- | --- | --- |
| argon2-cffi-bindings 26.1.0 | Windows abi3 | `2c36ff87b5dfaa477d0bd51e9d7f6abdae7c8955d2983c97419085d842154b3e` |
| argon2-cffi-bindings 26.1.0 | Linux abi3 | `27f1821903e2ceadcb88ec2b45ef190897b7682449c772f4d9b53e42c520cf29` |
| cffi 2.1.1 | Windows CPython 3.13 | `1aa5645c30469b09530c4ebca77ebf8f17618293c58f8549cb1a543a50236e7d` |
| cffi 2.1.1 | Linux CPython 3.12 | `c1453022f490d2459a11819d83ad1d586e9ff65a12ac3e705ffebd46d3685dcf` |
| pycparser 3.11 | py3-none-any | `51d5a8ba2be0bbe440b99d2112604c95bbbc3c2748a64260186c541e1729cd80` |
| pycparser 3.12 | py3-none-any | `a076f3f489b39b43ed13563a1dafe42447445bec2e294154ec5c57fcdda4c85e` |
| uvloop 0.23.0 | Linux CPython 3.12 | `090865d8ce7a03986755a3ce711b7dd0d4b44eb14ab74368b717f3fad1180208` |
| pip 25.2 | py3-none-any | `6d67a2b4e7f14d8b31b8b52648866fa717f45a1eb70e83002f4331d07e953717` |

L'inventaire complet avec tags/hashes est conservé en privé dans les deux wheelhouses.
**Origine indépendante non vérifiée** : un hash calculé sur le cache ne certifie pas
l'éditeur ni l'absence de compromission initiale. Les rapports portent donc
`origin_verified=false`. Ne pas promouvoir ces fichiers privés en lock officiel
de production sans revue de provenance et acquisition contrôlée.

Les fichiers `dependencies.hashed.txt` ne sont générés que si **toute** la fermeture
sélectionnée est disponible. Les 50/49 dépendances tierces sont réinstallées avec
`--no-index --only-binary=:all: --require-hashes` dans deux venvs neufs par plateforme.
Le projet `.` n'est pas installé par cette commande : son build est une preuve
distincte manquante. Aucun `--require-hashes` n'est ajouté au pipeline incomplet.
Un wheel pycparser fictivement altéré est refusé par pip avec code 1, motif de hash
incorrect et aucun paquet installé : contrôle négatif réussi, pas échec applicatif.

### Matériaux à récupérer pour la cible Docker CPython 3.13 Linux amd64

Le cache Linux disponible est surtout CPython 3.12 ; les tags réels de l'image 3.13
ont été comparés, sans considérer un wheel CPython 3.12 comme compatible par défaut.
Onze archives natives manquent pour réinstaller entièrement cette cible :

```text
cffi==2.1.1                 greenlet==3.5.6
httptools==0.9.0            jiter==0.17.0
MarkupSafe==3.0.4           psycopg-binary==3.3.6
pydantic_core==2.50.1       PyYAML==6.0.3
SQLAlchemy==2.0.55          uvloop==0.23.0
websockets==17.2
```

Leur version est connue, **leurs hashes d'archives Linux 3.13 ne le sont pas** dans
ce lot. Les dépendances abi3/pure Python compatibles sont réellement distinguées
par les tags, pas supposées nécessiter toutes un nouveau wheel.

## 4. pip, setuptools, wheel et PEP 517

| Environnement | Observation |
| --- | --- |
| Venv Windows initial | pip 25.2 ; setuptools et wheel absents |
| Venv WSL initial | pip, setuptools et wheel absents ; son Python est réutilisable |
| Image de preuves Linux | pip 26.2.2 ; setuptools et wheel absents du runtime |
| Installation Windows neuve | Pilotée par pip 25.2 externe via `--python`, dans un venv sans pip |
| Installation Linux neuve | pip 25.2 exécuté depuis son wheel haché, sans l'installer implicitement dans le venv |

Aucun wheel setuptools ou wheel n'est disponible dans les caches examinés. Leur
version réellement résolue lors d'un futur build PEP 517 reste inconnue. **Aucun
`requirements.build.lock` fictif n'est créé**, aucune version supposée épinglée.
`pyproject.toml`, la politique de build et les Dockerfiles restent inchangés.

Étape autorisée future à préparer : choisir et revoir des versions exactes de
pip/setuptools/wheel et leurs transitifs ; récupérer les archives, vérifier les
SHA-256 et l'origine ; créer un lock build distinct, complet et haché. Dans un
builder propre sans réseau, construire une wheel du projet revu avec ces seuls outils,
puis hacher cette wheel et l'installer avec la fermeture tierce hachée.
`--no-build-isolation` ne serait acceptable que dans **ce builder dédié entièrement
verrouillé**, jamais comme contournement sur un venv applicatif existant. Une autre
voie garde PEP 517 isolé et utilise les contraintes de build d'un pip dont le support
est vérifié ; ne pas ajouter une option récente à pip 25.2 sans vérifier sa disponibilité.
Ces deux voies sont des propositions, pas des builds réalisés ici.

## 5. Images de base et paquets système

| Entrée | Preuve locale / limite |
| --- | --- |
| python:3.13-slim | Tag déclaré, base originale absente comme image autonome ; aucun RepoDigest vérifié, aucune valeur inventée. |
| node:22-alpine | Tag déclaré deux fois dans le Dockerfile frontend ; base originale absente, aucun digest vérifié. Node 20 présent n'est pas un remplacement admissible. |
| postgres:17-alpine | Image locale Linux/amd64, RepoDigest `postgres@sha256:b0f9560a2de083e2cc7382e75f808c7381a32852a7ec49117deedb300e552b24`. Identité lue dans le moteur local, pas une revalidation d'origine Registry. |
| Bases applicatives dérivées | Image IDs locaux sans RepoDigest : ne pas les présenter comme des digests de manifeste à mettre dans FROM ou release.json. |
| API native | Deux overlays : mêmes 87 versions DPKG et mêmes SHA-256 de 18 fichiers natifs de distributions. libseccomp2 observé 2.6.0-2. |
| PostgreSQL natif | PostgreSQL 17.11, Alpine 3.24.2 ; inventaire APK conservé localement. Toolchain de compilation supprimée du runtime, versions exactes non prouvées par cet inventaire. |

Pin candidat connu pour revue :
`postgres:17-alpine@sha256:b0f9560a2de083e2cc7382e75f808c7381a32852a7ec49117deedb300e552b24`,
avec plateforme explicite linux/amd64. Il n'est **pas appliqué** : les trois builds
de production complets ne sont pas réalisables hors ligne avec les matériaux actuels.
Les bases Python/Node doivent être récupérées et leurs références vérifiées avant
de compléter un verrou cohérent des trois images.

APT `apt-get update` et `libseccomp2` sans version, APK `build-base git` et leurs
transitifs restent dynamiques. Un digest de base ne fige pas un futur apt/apk update.
Prévoir dépôt/snapshot vérifié, versions exactes, paquets et hashes disponibles,
politique de mise à jour de sécurité et preuve de rebuild. Geler éternellement une
ancienne base n'est pas une politique de sécurité. Aucun paquet système mis à jour ici.

## 6. pgvector : version, source et compilation

Source **déclarée dans Dockerfile.db** :
`https://github.com/pgvector/pgvector.git`, clone shallow du tag `v0.8.7`, build
`make with_llvm=no` avec `build-base` et Git APK, puis suppression du source et de
la toolchain. La version du paquet Python est **pgvector 0.5.1**, distincte de
l'extension serveur 0.8.7 ; aucune mise à jour des deux.

L'image locale contient `default_version='0.8.7'` dans vector.control, PostgreSQL
17.11 et le binaire vector.so dont le SHA-256 est :
`a261f42e7ea60b22aa852d06e960fdb82782fc1d34cd66cca0781f968cfa47f3`.
Ce hash **n'est pas** celui de l'archive source, ni une preuve du commit Git exact.
Le répertoire Git a été supprimé ; aucun commit ou tarball source n'est disponible
localement dans les matériaux examinés. Ne pas inventer le commit du tag.

Dans une étape réseau autorisée, lire le tag et sa cible sur l'origine officielle,
vérifier le commit complet et le contenu/version, puis récupérer ce commit exact,
archiver les sources avec une méthode documentée et calculer leur SHA-256.
Le Dockerfile pourra alors vérifier commit/archive avant compilation, sans se
contenter du nom de tag. Vérifier sur PostgreSQL 17 les migrations, `CREATE EXTENSION`,
dimensions et tests vectoriels avant adoption. Le fonctionnement du binaire local
ne certifie pas la reproductibilité de cette future compilation.

## 7. CI, provenance et mécanismes de livraison

Deux étapes d'inventaire sont ajoutées aux jobs Python Linux/Windows, après
installation. `tools/build_materials.py --require-pins` vérifie chaque dépendance
et ses extras, les marqueurs et toutes les contraintes entrantes ; version absente,
non contrainte ou incompatible donne un échec. Le code de retour est conservé sous
PowerShell avant écriture UTF-8. Les inventaires sont archivés séparément avec
l'action upload-artifact déjà épinglée et le SHA du run dans leur nom.

Le JSON `documind-materials-v1` contient versions, empreintes des contraintes,
pyproject, Dockerfiles/workflows disponibles, état connu des outils de build,
hash du lock npm et, en option, les vrais hashes de wheels. Pas d'env, URL privée,
chemin hôte, auteur ou secret. Une erreur de lecture/métadonnée est expurgée.
**Ce n'est ni un SBOM SPDX/CycloneDX certifié, ni une attestation d'origine, ni un
scan de vulnérabilités.** Les inventaires de runners ne sont pas présentés comme
l'inventaire des images finales ; `pep517_environment_verified=false` reste explicite.

Les huit références d'actions uniques restent des SHA de 40 caractères. Leur
existence/origine et l'adéquation des commentaires de version ne sont pas revérifiées
à distance. Python `3.13`, Node `22`, runners et composants internes Buildx demeurent
évolutifs. `npm ci` reste utilisé ; lock v3 : **368 paquets**, HTTPS registry.npmjs.org,
SRI SHA-512 syntaxiquement valides, deux paquets avec scripts d'installation.
Les octets de tous les tarballs npm n'ont pas été revérifiés dans ce lot.

`publish` exige toujours `python`, `windows`, `frontend` réussis ; réservé à main
hors PR ; trois builds/push séquentiels **linux/amd64**. Pas de continue-on-error
ajouté. L'archivage always des diagnostics n'efface pas l'échec d'une étape.
Les jobs de déploiement, approbations, digests/labels, schéma 0007, profil
`public-beta-2026-10-v1`, registre root et guards des scripts ops sont préservés.
Le bundle reste exactement **neuf fichiers**, lié aux trois digests : aucun inventaire
machine, wheelhouse ou nouvel outil n'y est ajouté implicitement.

SBOM futur : choisir et verrouiller le générateur et ses matériaux avant activation.
Activer aveuglément un générateur SBOM téléchargé ajouterait une nouvelle entrée
non vérifiée. Examiner aussi la provenance BuildKit effectivement émise : elle
peut être générée par les defaults actuels ; elle n'est ni supposée absente ni
certifiée simplement parce que build-push-action est utilisé. Lier ensuite les
matériaux aux digests exacts, au code/workflow/SHA/run/attempt par une politique revue.

RF10-04 inchangé : publication partielle => arrêt, conservation du run, digests et
diagnostics ; aucune suppression, retagging, réexécution ou approbation automatique.
Des inventaires séparés n'autorisent pas une release dont le bundle final manque.

## 8. Expériences de reproductibilité

| Niveau | Résultat réel |
| --- | --- |
| Matériaux Python Windows | Deux venvs neufs, mêmes 50 wheels, hashes contrôlés, mêmes versions ; aucune résolution réseau. |
| Matériaux Python WSL | Deux venvs neufs, mêmes 49 wheels et versions ; bootstrap pip haché séparé. |
| Overlays Docker Linux | Deux builds sans cache d'étapes et sans réseau, même parent local déjà construit ; mêmes 49 versions, 18 hashes natifs et 87 versions système. |
| Frontend Windows | Deux TypeScript/Vite builds, mêmes dépendances déjà installées ; cinq fichiers dist, mêmes SHA-256. Node 22.12.0/npm 10.9.0. |
| Trois Dockerfiles production | **Non reconstruits deux fois** : bases et matériaux réseau incomplets ; les overlays COPY ne recompilent ni pip/APT/APK ni pgvector, et ne reconstruisent pas l'image frontend. |
| Bit à bit | Aucune garantie générale : les deux images finales ont des IDs différents malgré des inventaires égaux. L'égalité des cinq fichiers frontend ne certifie pas une image OCI bit-identique. |

Comparaison complémentaire : configuration runtime des deux images identique,
horodatages de création différents et digests de couches rootfs différents.
Les 151 fichiers sources examinés ont néanmoins des contenus, modes et mtimes
identiques ; les métadonnées des sous-répertoires comparés sont aussi identiques.
Cela ne constitue pas un manifeste exhaustif des headers tar de chaque couche :
la cause exacte de tous les écarts de couches n'est pas établie. Ne pas annoncer
que normaliser les timestamps suffirait à obtenir une image bit-identique.

Parent de preuve commun : `documind-s14-7-4-proofs:local`, Image ID
`sha256:ef681ff0101655e241fabd3f8d8edffc8655a7ce7aae46e2ae388d85b3b40362`.
Overlays finaux, après normalisation du lock en LF :

```text
documind-s14-7-5-proofs-a-final:local
sha256:5aae93c88e0bc7fc98664168ac81e83640c0b1daa18cc95a557dbd21205a31c8
documind-s14-7-5-proofs-b-final:local
sha256:0631781d00b957ed3bcf1b2b8a541c458c68f2b99c91451aaf15bb5637a4e084
```

Ce sont des **Image IDs locaux**, pas des références Registry ni des candidats
autorisés au déploiement. Les deux premiers overlays précédant la normalisation
sont conservés séparément ; ils ne sont pas confondus avec ces sorties finales.
Les expériences prouvent une répétabilité limitée des matériaux sélectionnés,
pas une supply chain entièrement reproductible ou authentifiée.

Un retour 1 du pilote PowerShell de la paire finale a été constaté, alors que les
deux journaux Docker montrent leurs exports terminés. Les deux sorties ont ensuite
été relues par Image ID avec succès, inventoriées et testées ; aucun test défaillant
n'est converti en succès. La cause de ce retour du pilote n'est pas attribuée à
Docker sans preuve. Ce harnais privé n'est pas intégré à la CI et ne constitue pas
la preuve d'un workflow de double build prêt à publier.

## 9. Tests et commandes

| Campagne de ce lot | Réussis | Ignorés | Échecs |
| --- | --- | --- | --- |
| Tests initiaux du nouvel outil, Windows puis WSL | 13 chacun | 0 | 0 |
| Outil final + déploiement/registre/autorisation, Windows | 199 | 5 | 0, 22,39 s |
| Windows neuf haché, intégrité/public/email/IA off/guards/backup | 232 | 6 | 0, 254,74 s |
| WSL neuf haché, même sélection + Linux natif/protocole | 306 | 4 | 0, 340,65 s |
| Docker final Python 3.13, outil/intégrité/confinement | 108 | 1 | 0, 36,65 s |
| PostgreSQL 17.11/pgvector 0.8.7 neuf, intégrité/concurrence/guards | 124 | 2 | 0, 122,71 s |
| Docker root, registre/approbation/guard ops | 2 | 0 | 0, 0,81 s |
| Deux installations Windows et deux Linux hors réseau | 4 installations | — | 0 |
| Wheel volontairement altéré | 1 rejet attendu | — | Aucun paquet installé |
| Deux builds frontend | 2 builds | — | 0, cinq fichiers identiques |

Les sélections se recouvrent. L'outil final a **15 tests** ; ses deux tests
complémentaires de SRI et de contraintes multi-parents sont inclus dans les suites
finales, pas attribués rétroactivement aux premiers passages de 13.
Les skips concernent surtout PostgreSQL/root/Unix dans les environnements inadéquats.
Le skip Docker final est le verrou PG : il n'est pas transformé en preuve passée.
Les 22 cas d'intégrité sont tous exécutés dans la sélection PG, ainsi que les neuf
entrelacements d'inscription PostgreSQL. Les deux skips PG sont les preuves root,
exécutées séparément dans un conteneur sans réseau et avec son seul tmpfs.
Les suites complètes Windows/WSL 775/817 du rapport 14.7.4 restent **historiques**,
pas relancées dans ce lot sans changement de logique applicative. React/BFF, E2E
HTTPS/SMTP et restauration B2 réelle ne sont pas annoncés comme rejoués.

Exemples des commandes réellement utilisées :

```text
python tools/build_materials.py --require-pins --npm-lock frontend/package-lock.json
python -m pip --python <venv-Windows-neuf>/Scripts/python.exe install --disable-pip-version-check --no-index --only-binary=:all: --find-links <wheelhouse-revue> --require-hashes -r <fermeture-complete.hashed.txt>
docker --host npipe:////./pipe/dockerDesktopLinuxEngine build --no-cache --pull=false --network none --build-arg PROOFS_BASE=documind-s14-7-4-proofs:local -f ops/testing/Dockerfile.beta-recipe --target proofs -t documind-s14-7-5-proofs-a-final:local .
npm.cmd run build
git diff --check
```

Les vrais chemins et logs sont sous `var/s14-7-5-*`, ignorés. Chaque venv, basetemp,
conteneur et base est neuf. Docker readonly/non-root, cap-drop ALL,
no-new-privileges, limites CPU/mémoire/PID conservées ; confinement sans réseau ni
volumes. Le PostgreSQL de test utilise uniquement un réseau interne et tmpfs propres,
aucun port/bind/volume existant. Aucun assouplissement Landlock/seccomp.

## 10. Fichiers modifiés et préservation

```text
requirements.lock                         cinq contraintes, normalisation LF
.github/workflows/ci.yml                   deux inventaires et leur archivage séparé
tools/build_materials.py                   nouveau
tests/test_build_materials.py              nouveau
docs/SPRINT_14_7_5_SUPPLY_CHAIN_REPORT.md    nouveau
```

Les 74 candidats préexistants ont été relevés avant intervention : **73/74 restent
identiques octet par octet**. Le seul différent est ci.yml. En retirant en mémoire
les quatre blocs ajoutés (deux inventaires/deux archivages), son SHA-256 redevient
exactement celui du relevé initial : toutes les modifications CI antérieures sont
préservées. Aucun fichier applicatif,
Dockerfile, Compose, migration, quota, secret, rollback/backup/registre ou ancien
rapport modifié dans ce lot. Les archives, inventaires générés, logs, venvs et dist
ne sont pas candidats Git. Le futur commit doit inclure simultanément le script,
le lock et le workflow, jamais seulement une référence CI vers un fichier absent.

État final : **35 suivis modifiés + 43 non suivis = 78 candidats** ; index vide,
branche et HEAD inchangés. Les cinq fichiers du lot passent le contrôle des blancs,
les deux Python passent l'analyse AST et le workflow se parse en YAML. Les trois
gates de publication et les trois cibles amd64 sont également contrôlés séparément.
`git diff --check` réussit après normalisation LF du seul lock. Les conteneurs et le
réseau PG de mission sont supprimés après contrôle des labels et de l'absence de
montages persistants ; aucun volume n'est supprimé et aucune ressource préexistante
n'est modifiée. Images, caches de preuve, wheelhouses et venvs de test restent locaux.

## 11. Vulnérabilités et limites

Aucune CVE précise nouvelle identifiée ou auditée ici. Aucun scan distant, base
d'advisories actualisée, authenticité éditeur, signature d'action/base ou réputation
de package n'est certifié. Les lacunes de verrouillage/provenance sont des risques
confirmés dans le code, pas la preuve d'une exploitation ou d'un package compromis.

Restent dynamiques : outils PEP 517, runtimes/runners, deux bases inconnues, APT/APK,
commit source pgvector, entrées exactes du projet wheel, provenance des archives,
scripts npm et build tools internes des actions. Les wheels CPython 3.13 Linux
manquants empêchent la validation d'une réinstallation neuve complète de la cible
API ; le runtime déjà installé et ses tests ne remplacent pas cette preuve.

## 12. État RF10-03 et PR en brouillon

**Corrigé localement :** dérive possible des quatre transitifs observés, absence
d'inventaire contrôlant la fermeture runtime/test dans la CI.
**Vérifié localement :** octets/hashes en cache, répétition d'installations fermées,
versions et matériaux natifs égaux, invariants testés sur données fictives.
**Documenté seulement :** plan de locks build, bases, source pgvector, provenance
et vérifications encore nécessaires. **RF10-03 reste ouvert**, sans acceptation
automatique ni extension de l'ancienne exception privée.

Go technique pour une **PR en brouillon de revue**, après autorisation explicite
de commit/push/PR et inventaire Git actualisé. Ne pas la présenter comme une RC
livrable, fusionner automatiquement ou supprimer les réserves. SQL-02 reste corrigé ;
SQL-01 reste inexpliqué, SQL-03 et les preuves d'exploitation restent distincts.

## 13. Conditions d'une RC privée et d'un déploiement fermé

Avant RC utilisable : récupérer les 11 wheels Linux 3.13 manquants et les matériaux
build choisis dans un environnement réseau explicitement autorisé ; vérifier origine,
tags, SHA-256 et fermeture ; figer les outils de build séparément ; obtenir les
bases Python/Node et vérifier les trois références amd64 ; fixer commit/archive
pgvector et paquets système. Refaire les trois builds complets deux fois, comparer
matériaux et résultats, tester les images réellement construites.
Une nouvelle décision de risque bornée peut être proposée pour un écart explicitement
identifié ; elle n'est ni prise ici ni une permission implicite d'ouverture.

La CI réelle doit réussir python/windows/frontend sur le SHA exact. Lire inventaires,
provenance effectivement émise, trois digests, neuf fichiers et attestation ; traiter
RF10-04 en cas d'échec. Aucun workflow distant n'est exécuté dans ce lot.

Déploiement fermé : autorisation séparée, images exactes recettées, registre root
approuvé indépendamment, scripts ops compatibles installés, sauvegarde/restauration
qualifiées, fermeture conservée, secours corrigé ou correction en avant approuvée.
Ne pas approuver comme secours un ancien candidat réintroduisant SQL-02 ; ne jamais
éditer un marqueur de maintenance ou fabriquer current pour débloquer une reprise.

## 14. Ouverture publique et verdict final

**Ouverture publique No-Go.** Elle exige en plus les décisions SQL-01/SQL-03/RF10-03,
recette des digests réels sur Linux/ABI accepté, SMTP/textes/alertes/B2 et restauration
indépendante réels, quota cumulatif connu, fermeture d'urgence prête et autorisation
opératrice distincte. IA toujours fermée ; aucune inscription ouverte dans ce lot.

**Verdict factuel : contraintes transitives et traçabilité améliorées, répétabilité
partielle démontrée, builds de production complets non certifiés. RF10-03 non clos ;
pas de RC utilisable publiée ni de déploiement autorisé.** Les prochaines preuves
nécessitent une étape d'acquisition/build CI réelle explicitement autorisée.
Aucun commit, push, merge, publication Registry, accès VPS, changement d'env de
production, migration, quota, inscription, IA ou suppression de sauvegarde.
