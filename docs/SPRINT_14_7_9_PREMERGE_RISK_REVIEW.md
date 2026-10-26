# Sprint 14.7.9 — Revue pré-fusion et qualification préalable RF10-03

26 octobre 2026. Relevé GitHub en lecture seule à **13:30:58 UTC**.
Références lues : [audit CI 14.7.8](SPRINT_14_7_8_GITHUB_CI_REVIEW_REPORT.md),
[supply chain 14.7.5](SPRINT_14_7_5_SUPPLY_CHAIN_REPORT.md),
[préparation PR 14.7.6](SPRINT_14_7_6_PR_PREPARATION_REPORT.md).

**La CI de PR est verte et les inventaires des runners sont cohérents. RF10-03
reste partiellement ouvert : ces preuves ne qualifient pas les images finales.
Go pour poursuivre la revue en Draft ; No-Go pour fusion, RC utilisable,
déploiement ou ouverture à ce stade.** Aucune acceptation de risque n'est décidée
au nom de l'exploitante.

## 1. Périmètre et preuves récupérées

- [PR nº 6](https://github.com/AdelineMeistertzheim403/DocuMind_AI/pull/6).
- [Run 40326201923, nº 15, tentative 1](https://github.com/AdelineMeistertzheim403/DocuMind_AI/actions/runs/40326201923),
  événement `pull_request`, terminé avec `success`.
- Deux artefacts téléchargés via l'API GitHub ; seul leur fichier JSON attendu a
  été lu, sans extraction arbitraire du ZIP et avec limites de taille.
- Empreintes SHA-256 calculées sur les octets ZIP et JSON réellement reçus.
  Les deux hashes ZIP correspondent au champ `digest` fourni par GitHub.
  Cela établit l'intégrité du transfert par rapport à cette métadonnée GitHub,
  **pas** une signature indépendante du fournisseur de chaque dépendance.
- Téléchargements limités aux inventaires CI existants ; aucun wheel, sdist,
  tarball npm, image ou paquet système acquis. Aucun accès Registry/VPS.
- Copies privées sous `var/s14-7-9-evidence/`, ignorées par Git. Jeton en mémoire,
  non écrit ni affiché ; redirections HTTPS suivies sans transmettre le jeton
  GitHub au stockage d'artefacts. Pas de lien signé conservé dans le rapport.

| Inventaire | Artefact GitHub | SHA-256 ZIP, identique au digest API |
| --- | --- | --- |
| Linux | [12652930295](https://github.com/AdelineMeistertzheim403/DocuMind_AI/actions/runs/40326201923/artifacts/12652930295) | `9e805a21fb4a485061d50f2c91e2ecf291bdd535809176a9e1f2608590ca1046` |
| Windows | [12654625580](https://github.com/AdelineMeistertzheim403/DocuMind_AI/actions/runs/40326201923/artifacts/12654625580) | `02aed09bf07406757145af8142dddb1977946bc5d20d76ed5a05a08caf35578d` |

Noms : `documind-runner-materials-{linux,windows}-502b1e07ceb4ddd98d53b46a17cfb4e48afbe205`.
Non expirés au relevé. SHA-256 des membres JSON :

- Linux : `24d138449f534a6977753c7f651d447829a6a64d60b6990a7a1c3c0b1d813d42` ;
- Windows : `338c984aac363cdfaa664c907516884f782f64c1d9efe81edadb770679a5ed4f`.

### Identité du code et du checkout

Source de PR : `f3c92eb8ba2bb69b83a9798ebc3df8a70f48fbb2`.
Base/main : `8243e0511c5505a9cc70f76ad02392f7a816590d`.
Les logs checkout des trois jobs, relus dans 14.7.8, établissent le SHA réellement
testé : **`502b1e07ceb4ddd98d53b46a17cfb4e48afbe205`**, merge synthétique de PR,
pas une fusion sur main. Les noms d'artefacts utilisent ce SHA ; le run est rattaché
au SHA source. Les JSON ne contiennent pas eux-mêmes de champ Git SHA signé :
leur rattachement repose sur le run, les noms, le workflow et les logs checkout.

Les huit empreintes de sources renseignées par chaque inventaire ont été comparées
aux blobs Git du commit source : requirements.lock, pyproject.toml, les trois
Dockerfiles, les deux workflows et package-lock.json. **8/8 Linux identiques
octet pour octet ; 8/8 Windows identiques après conversion LF vers CRLF des blobs.**
Les différences de hashes ne démontrent donc aucune dérive textuelle de ces fichiers.
Les hashes originaux ne sont pas remplacés par une empreinte normalisée.
Cette comparaison ne couvre pas tous les fichiers applicatifs ni les couches OCI.

## 2. Versions et couverture des contraintes

| Propriété | Linux | Windows |
| --- | --- | --- |
| Format | documind-materials-v1 | documind-materials-v1 |
| Python | 3.13.16 | 3.13.17 |
| Plateforme/machine | linux / x86_64 | win32 / AMD64 |
| Fermeture runtime + extra test | 49 distributions | 50 distributions |
| constraint_coverage_complete | true | true |
| issues | liste vide | liste vide |
| pip installé | 26.2.1 | 26.2.2 |
| setuptools / wheel installés dans le runner à l'inventaire | absents / absents | absents / absents |
| PEP 517 déclaré | setuptools>=75 | setuptools>=75 |
| pep517_environment_verified | false | false |

Vérification indépendante des lignes et marqueurs du lock, sans installation :
**49/49 versions Linux et 50/50 Windows correspondent au pin applicable**.
Les 48 noms communs n'ont qu'une divergence de version : pycparser 3.12 Linux,
3.11 Windows, explicitement conditionnée dans le lock. uvloop 0.23.0 n'est présent
que sous Linux ; colorama 0.4.6 et tzdata 2026.5 seulement sous Windows.
Ces différences sont attendues ; Python et pip diffèrent aussi, puisque leur
sélection CI reste flottante à l'intérieur d'une série.

Nuance de couverture : le lock possède 51 noms actifs sous Linux, dont colorama
et tzdata non présents dans la fermeture Linux observée ; Windows en a 50, tous
présents. Une contrainte ne force pas l'installation. `--require-pins` valide la
fermeture runtime/test parcourue, **pas tous les paquets possibles, extras desktop,
outils PEP 517, paquets système ou autres architectures**. Le projet lui-même et
les distributions éventuellement préinstallées hors fermeture ne constituent pas
une liste exhaustive des paquets de la machine dans cet outil.

Les deux inventaires confirment pour le lock npm : 368 paquets, deux avec scripts
d'installation, `downloaded_bytes_verified=false`. Le hash Linux du lock est
`7ce52768894aeaccbd4f632b6c18261348cf6858a6f5787fc5ad86d52e051804` ; Windows
`2c5dacf78084273575b85daab15161f3f8ea1c7355d4c4fc69de697df32a2014`, différence
LF/CRLF démontrée. Il s'agit de l'examen du lock par le script Python, pas d'un
inventaire npm installé dans le job frontend ou dans son image finale.

### Limite d'origine et d'intégrité

Aucun champ `wheel_archives` n'est présent : le workflow n'a pas passé `--artifacts`.
Les noms/versions installés et hashes des fichiers du dépôt ne donnent ni les
hashes des wheels téléchargés, ni leurs URLs d'origine, ni des attestations PyPI.
Les JSON ne donnent pas de tags de wheels, de SBOM d'image ou de source pgvector.
Les hashes RECORD installés ne remplaceraient pas ceux des archives.

L'absence de setuptools/wheel dans le runner ne signifie pas qu'ils n'ont pas
servi au build : PEP 517 peut les installer dans un environnement isolé temporaire.
Les versions effectives et la fermeture de cet environnement ne sont pas établies
par ces artefacts. pip connu dans le runner n'est ni verrouillé pour les futurs
runs ni nécessairement le pip des Dockerfiles.

## 3. Onze archives Linux Python 3.13 : acquis documentaire et manque réel

Les logs existants du job Python mentionnent les onze noms ci-dessous. Ils donnent
maintenant des **noms d'archives observés**, plus précis que la liste de versions
de 14.7.5. Aucun octet de ces wheels n'a été téléchargé par cette mission : ils
restent manquants dans le wheelhouse local qualifié. Une installation CI réussie
ne fournit pas leur provenance vérifiée ni leur hash d'archive.

Cible : CPython standard 3.13, ABI cp313, Linux x86_64/glibc (backend slim),
pas Windows, musllinux/Alpine, arm64 ou CPython free-threaded cp313t. Les tags
multiples figurent textuellement dans les noms ; une compatibilité avec le
conteneur exact devra être vérifiée avec ses tags supportés, pas déduite du
seul nom Linux. PostgreSQL Alpine est un autre ensemble de matériaux.

| Distribution et origine officielle ? consulter | Archive observ?e ? acqu?rir |
| --- | --- |
| [cffi 2.1.1](https://pypi.org/project/cffi/2.1.1/) | `cffi-2.1.1-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.whl` |
| [greenlet 3.5.6](https://pypi.org/project/greenlet/3.5.6/) | `greenlet-3.5.6-cp313-cp313-manylinux_2_24_x86_64.manylinux_2_28_x86_64.whl` |
| [httptools 0.9.0](https://pypi.org/project/httptools/0.9.0/) | `httptools-0.9.0-cp313-cp313-manylinux1_x86_64.manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl` |
| [jiter 0.17.0](https://pypi.org/project/jiter/0.17.0/) | `jiter-0.17.0-cp313-cp313-manylinux_2_17_x86_64.manylinux2014_x86_64.whl` |
| [MarkupSafe 3.0.4](https://pypi.org/project/MarkupSafe/3.0.4/) | `markupsafe-3.0.4-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl` |
| [psycopg-binary 3.3.6](https://pypi.org/project/psycopg-binary/3.3.6/) | `psycopg_binary-3.3.6-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.whl` |
| [pydantic_core 2.50.1](https://pypi.org/project/pydantic_core/2.50.1/) | `pydantic_core-2.50.1-cp313-cp313-manylinux_2_17_x86_64.manylinux2014_x86_64.whl` |
| [PyYAML 6.0.3](https://pypi.org/project/PyYAML/6.0.3/) | `pyyaml-6.0.3-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl` |
| [SQLAlchemy 2.0.55](https://pypi.org/project/SQLAlchemy/2.0.55/) | `sqlalchemy-2.0.55-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl` |
| [uvloop 0.23.0](https://pypi.org/project/uvloop/0.23.0/) | `uvloop-0.23.0-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl` |
| [websockets 17.2](https://pypi.org/project/websockets/17.2/) | `websockets-17.2-cp313-cp313-manylinux1_x86_64.manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl` |

Origines proposées pour acquisition future : pages de versions PyPI officielles
liées dans le tableau, puis fichiers HTTPS exposés par leurs métadonnées officielles
(notamment files.pythonhosted.org). **Pages et métadonnées non consultées dans ce
lot** : présence actuelle de chaque fichier, hash publié, statut yanked et
attestations restent à vérifier. Les noms viennent des logs, pas d'une réponse PyPI
actuelle. Ne pas inventer une URL CDN ni un SHA-256 pour combler ce manque.

## 4. État détaillé RF10-03 : autres matériaux

| Entrée | Preuve disponible | Preuve manquante avant qualification |
| --- | --- | --- |
| pip | 26.2.1 Linux runner ; 26.2.2 Windows runner | Choix exact approuvé, archives et hashes d'origine, pip des builders/images ; le pip 25.2 local historique n'est pas celui du run. |
| setuptools / wheel | Absents des inventaires runners ; setuptools>=75 déclaré | Versions et transitifs réellement utilisés en PEP 517, archives authentifiées et lock build distinct ; ne pas conclure à une version de wheel nécessaire sans examiner le backend choisi. |
| Wheel du projet | Installation CI réussie, sources identifiées | Wheel construite du SHA revu, outils/entrées identifiés, hash et provenance de cette sortie. |
| python:3.13-slim | Tag dans Dockerfile ; preuve du runtime d'isolation réussie | Digest index/manifeste amd64 de la base réellement résolue, identité/origine et inventaire final ; Python runner 3.13.16 ne fixe pas Python du conteneur. |
| node:22-alpine | Tag des deux stages frontend ; Node runner 22.23.3/npm 10.9.9 observés en 14.7.8 | Digests exacts et plateforme des deux stages, Node/npm et fermeture npm réellement présents dans les images ; pas de déduction depuis le runner. |
| postgres:17-alpine | Tag Dockerfile.db ; image CI de test construite et suite PG réussie | Base réellement résolue par ce build, paquets et sortie OCI ; le RepoDigest local historique de 14.7.5 n'est pas une validation du build de ce run. |
| APT | apt-get update et libseccomp2 sans version exacte | Snapshot/dépôt, signatures, versions/hashes des deb et transitifs ; distinguer hôte CI et image backend. |
| APK | build-base/git et transitifs installés, puis supprimés du runtime DB | Versions/hashes des entrées de compilation et dépôts vérifiés ; un inventaire runtime seul perd la toolchain. |
| pgvector serveur | Clone shallow du tag v0.8.7 depuis github.com/pgvector/pgvector ; make with_llvm=no | Commit complet du tag, archive source hachée, lien source/toolchain/binaire ; ni la version Python pgvector 0.5.1 ni le hash historique de vector.so ne donnent ce commit. |
| Actions / Buildx / BuildKit | Références d'actions épinglées par SHA ; build-push-action utilisé dans publish | Origine des actions, versions effectives BuildKit/buildx/frontends, matériaux et politique de provenance liée au digest réel. Ne pas supposer les defaults immuables. |
| Provenance/SBOM | JSON internes de runners, hashes Git/artefacts ; publish skipped | Provenance réellement émise par un build final, mode/couverture, sujets et matériaux, inventaires des trois images ; aucun SBOM certifié SPDX/CycloneDX ni audit CVE actualisé revendiqué. |

Les digests de sorties et le statement de sécurité du bundle attestent des liens
d'identité contrôlés par le projet ; ils ne verrouillent pas rétroactivement les
entrées dynamiques. Ne pas assimiler ce statement à une provenance BuildKit
exhaustive ou à une approbation root indépendante déjà accordée.

## 5. Trois fiches de risque indépendantes

### R14-SQL-01 — HTTP 503 historique inexpliqué

- **Faits vérifiés :** le rapport 14.7.2 conserve un GET 503 dans
  test_worker_interruption_resume_and_owner_isolation lors de la suite WSL 14.7.1
  (795 réussis, 27 ignorés, un échec). Événement system.database.unavailable ;
  famille SQLAlchemyError connue, classe DBAPI/requête fautive inconnues.
  Répétitions ultérieures et CI actuelle passent. Ce n'est pas le timeout des six
  anciens échecs Windows, ni une preuve de contention SQLite.
- **Incertitudes :** cause, fréquence, dépendance au pool/worker et portée PG
  non établies. Un arrêt borné de thread ne prouve pas sa terminaison universelle.
- **Impact potentiel :** indisponibilité de suivi/reprise ; aucune perte de donnée
  ou violation de propriétaire démontrée par cet incident, sans garantie générale.
- **Mesures existantes :** sessions distinctes, autorisations et checkpoints,
  journalisation expurgée SEC10-04, jeux SQLite/PG et workers testés ; aucune
  augmentation de timeout ou retry SQL aveugle.
- **Bloquants :** réapparition spontanée reproductible, état durable incohérent,
  autorisation erronée ou échec PG inexpliqué imposent diagnostic/correction avant
  livraison. Une CI verte ne vaut pas clôture de l'incident.
- **Acceptation humaine envisageable :** poursuite de revue/qualification privée,
  sans public et avec seuil d'arrêt écrit ; toute acceptation pour livraison
  fermée doit préciser sa durée, version, surveillance et voie de récupération.
  Aucune telle acceptation n'est donnée ici.

### R14-SQL-03 — Admission commitée, réponse en erreur et notification absente

- **Faits vérifiés :** backend/public_registration.py:admit incrémente le quota
  SQL et crée compte/workspace/token dans la transaction ; session.commit précède
  mail_queue.put_nowait. Une faute synthétique après commit effectif peut produire
  une erreur sans mail ; une file pleine est également traitée sans annuler un
  compte déjà commité. La place est cumulative ; rollback après commit ne
  rembourse pas cette admission. La démonstration antérieure n'est pas une panne
  naturelle de production constatée pendant ce lot.
- **Incertitudes :** fréquence réelle, livraison SMTP et récupération opératrice
  sur environnement réel non mesurées. File RAM non durable ; aucune garantie
  transactionnelle d'envoi SMTP depuis les tests fictifs.
- **Impact potentiel :** une des cinq places consommée avec compte non vérifié,
  réponse trompeuse pour l'utilisateur, courrier absent ; pas de dépassement du
  quota ou de double compte démontré dans les tests de ce risque.
- **Mesures existantes :** admission atomique cumulative, refus d'accès avant
  vérification email, réponse générique, renvoi protégé avec preuve de mot de
  passe, anti-abus/révocation, compteurs et logs ; aucun reset automatique du quota.
- **Bloquants :** avant public, procédure réelle de renvoi et rapprochement
  compte/quota/email, critères d'alerte et décision explicite sur ce risque.
  Une correction durable future peut étudier une outbox transactionnelle et la
  réconciliation des commits incertains, sans prétendre qu'elle est implémentée.
- **Acceptation humaine envisageable :** cinq admissions cumulatives au maximum,
  version/période précises, intervention identifiée, fermeture immédiate disponible,
  pas de promesse de zéro admission sur 503 ni de remboursement implicite.
  Déploiement fermé sans nouvelle inscription et ouverture publique restent des
  périmètres différents à décider, pas une acceptation globale.

### RF10-03 — Provenance et reproductibilité partielles

- **Faits vérifiés :** versions de la fermeture runtime/test contraintes et
  cohérentes, intégrité des deux inventaires reçus vérifiée, divergences de
  plateforme expliquées. Entrées Docker/PEP 517/système encore dynamiques,
  onze wheels sans hashes/provenance qualifiés, aucun inventaire d'image finale.
- **Incertitudes :** origine indépendante des archives, outils isolés et matériaux
  exacts de futures images ; reproductibilité complète et équivalence des sorties.
  Aucune probabilité de compromission ou CVE particulière déduite de ces lacunes.
- **Impact potentiel :** build futur différent malgré même Git SHA, composants
  compromis ou non revus, impossibilité de reconstruire une sortie de confiance.
  Un sandbox runtime ne certifie pas son propre build ni celui du BFF/DB.
- **Mesures existantes :** contraintes et inventaire bloquant, actions par SHA,
  npm ci/lock, trois gates CI, amd64 seul, tags SHA protégés contre écrasement,
  digests/statement/registre root et guards de livraison. Les protections runtime
  restent inchangées.
- **Bloquants :** entrées non qualifiées sans décision écrite compatible avec la
  publication automatique ; matériaux/digests divergents, preuve d'origine
  obligatoire absente ou bundle incomplet interdisent une RC utilisable.
- **Acceptation humaine envisageable :** si décidée, une unique tentative privée
  identifiée par SHA/run/attempt, durée et limites explicites ; aucun rerun,
  déploiement ou public inclus par défaut. Les anciennes acceptations Sprint 10
  ne couvrent pas automatiquement ce Sprint 14. L'alternative est de qualifier
  les matériaux avant fusion. Aucun des deux choix n'est fait ici.

**R14-SQL-02 demeure distinct :** correctif d'intégrité documentaire présent dans
la branche et testé sous fautes définies ; ni réparation d'une incohérence ancienne
ni correction de SQL-01/03. **RF10-04 demeure distinct :** si publication partielle,
arrêt de livraison, preuves conservées, aucune suppression/retagging/relance
automatique ; nouvelle décision nécessaire.

## 6. PR et protection effective avant fusion

PR **open, Draft=true**, une seule entrée de commit, source et base inchangées,
merged=false, auto_merge=null. Aucun nouveau commit depuis 14.7.8.
main réel lu à l'API pointe aussi sur 8243e0511c5505a9cc70f76ad02392f7a816590d.

| Protection de main observée | Valeur |
| --- | --- |
| Pull Request obligatoire | required_pull_request_reviews présent |
| Contrôles obligatoires | python, windows, frontend, chacun app_id=15368 (GitHub Actions) |
| Branche à jour | strict=true |
| Administrateurs inclus | enforce_admins.enabled=true |
| Conversations résolues | required_conversation_resolution.enabled=true |
| Force push / suppression | false / false |
| Approbations minimales | 0 ; aucune approbation indépendante imposée techniquement |
| Rejet des anciennes approbations | dismiss_stale_reviews=true |
| Code owner / approbation du dernier push | false / false |
| Signatures / historique linéaire requis | false / false |
| publish obligatoire | Non |

L'API renvoie aussi contexts en lecture, en plus de checks ; cela ne modifie pas
les trois liens app_id. Aucune règle n'a été écrite. Zéro review formelle retournée
par l'API de cette PR ; la revue humaine demandée ne doit pas être supposée faite
parce que required_approving_review_count vaut zéro. Résolution effective de chaque
conversation et décision de risque restent à vérifier avant une future fusion.

| Job de la tentative 1 | Résultat | Preuves de tests de 14.7.8 |
| --- | --- | --- |
| [python](https://github.com/AdelineMeistertzheim403/DocuMind_AI/actions/runs/40326201923/job/121583422638) | success | 72 natifs + 72 Docker ; SQLite 832/28 ignorés ; PG 844/16 ignorés ; zéro échec |
| [windows](https://github.com/AdelineMeistertzheim403/DocuMind_AI/actions/runs/40326201923/job/121583423054) | success | 790 réussis, 30 ignorés, zéro échec |
| [frontend](https://github.com/AdelineMeistertzheim403/DocuMind_AI/actions/runs/40326201923/job/121583422920) | success | 52 React, 50 BFF, TypeScript/build réussis |
| [publish](https://github.com/AdelineMeistertzheim403/DocuMind_AI/actions/runs/40326201923/job/121594346179) | skipped | Aucune publication sur cette PR |

Ces campagnes se recouvrent ; ne pas sommer en tests uniques. Aucun test réexécuté
dans 14.7.9. Les avertissements de dépréciation et tests opt-in non exécutés restent
ceux documentés dans 14.7.8 ; aucune nouvelle campagne n'est nécessaire pour lire
ces preuves.

**Effet d'une fusion :** ci.yml se déclenche sur push main ; après succès des
trois jobs, publish peut automatiquement construire/pousser backend, frontend et
postgres, séquentiellement en linux/amd64. La condition exclut les PR, pas une
fusion sur main. Aucun déploiement n'est automatique : deploy.yml est manuel avec
ses gates distincts. Ne pas fusionner seulement pour obtenir des matériaux de
build sans autoriser explicitement cet effet de publication et traiter RF10-04.

## 7. Plan futur d'acquisition et de vérification — non exécuté

1. Autorisation distincte, origines approuvées et stockage privé de preuves.
   Fixer la cible Linux amd64/CPython 3.13/glibc et l'image cible, sans toucher à
   l'environnement applicatif existant ni modifier implicitement les versions.
2. Lire les métadonnées officielles des onze versions ; relever nom exact, tags,
   URL HTTPS sans credentials, taille, SHA-256 publié, statut yanked et attestations
   disponibles. Refuser fichier absent, nom ambigu, tag incompatible ou substitution
   sdist. Si les fichiers observés ne sont plus disponibles, arrêter et présenter
   l'écart plutôt que résoudre automatiquement une autre version.
3. Télécharger seulement après autorisation les archives sélectionnées ; calculer
   leurs SHA-256 et confronter aux métadonnées de l'origine. Consigner la chaîne
   de provenance et ses limites : hash et index ne prouvent pas seuls l'identité
   de l'éditeur. Requalifier aussi les wheels déjà en cache, origin_verified=false.
4. Compléter la fermeture runtime/test et, séparément, runtime de production.
   Produire un manifeste complet d'archives et un lock haché seulement quand toutes
   les entrées sont disponibles. Réinstaller hors ligne dans un environnement neuf
   avec vérification des hashes ; les seuls onze ajouts ne certifient pas le reste.
5. Choisir et qualifier pip/setuptools/wheel et transitifs effectivement nécessaires
   au backend PEP 517. Lock build distinct, environnement isolé reproductible,
   aucune option --no-build-isolation sur un venv arbitraire. Construire/hacher la
   wheel projet du Git SHA approuvé et conserver les preuves d'entrée/sortie.
6. Vérifier bases officielles Python/Node/PostgreSQL, digests d'index et manifestes
   amd64 ; ne pas utiliser un Image ID local comme digest de FROM. Qualifier les
   dépôts, signatures, versions et hashes APT/APK et toolchain ; prévoir mises à
   jour de sécurité, pas un gel définitif des composants.
7. Résoudre le tag pgvector v0.8.7 sur son dépôt officiel en commit complet,
   récupérer/vérifier l'archive exacte et compiler avec toolchain identifiée.
   Distinguer source, extension serveur, paquet Python et vector.so. Tout changement
   de verrouillage/code nécessite une nouvelle revue/CI du nouveau SHA.
8. Qualifier les trois builds complets dans des builders jetables à entrées connues,
   avec comparaison des matériaux/sorties. Réutiliser les tests existants affectés
   par les entrées modifiées ; pas de campagne supplémentaire aveugle. Distinguer
   répétabilité des versions, équivalence fonctionnelle et reproduction bit à bit.
9. Examiner les matériaux/provenances réellement émis par BuildKit, version/mode,
   sujets/digests, code/workflow/run/attempt, sources et base layers. Un éventuel
   générateur SBOM doit lui-même être qualifié. Prévoir séparément un audit CVE
   actualisé autorisé ; aucun scan ou certificat de sécurité actualisé ici.

## 8. Images définitives après publication future autorisée

La publication n'est pas demandée par ce rapport. Après autorisation seulement :

1. Vérifier merge SHA réel et run main/attempt, gates et absence de changement
   non revu ; lire les trois sorties Registry par digest et plateforme amd64.
   Ne pas confondre attestations OCI et architectures exécutables supplémentaires.
2. Contrôler labels de révision/profil public-beta-2026-10-v1, neuf fichiers du
   bundle, release.json, hashes du statement et schéma 0007 ; comparer aux artefacts
   du run approuvé. Un inventaire runner n'entre pas implicitement dans le bundle.
3. Lire inventaires/provenances des images exactes et les rapprocher des matériaux
   qualifiés, sans déduire l'inventaire runtime du seul pip freeze du runner.
4. Recetter ces digests dans une stack jetable à données fictives : confinement
   Linux strict, propriétaires/sessions/uploads, intégrité SQL-02, quota et email
   fictif, IA off, sauvegarde/restauration et guards/rollback. Réutiliser la recette
   existante avec ces nouvelles sorties ; une preuve sur un overlay antérieur ne
   valide pas les images publiées. Aucun fournisseur réel sans autorisation.
5. RF10-04 : toute sortie manquante, partielle, incohérente ou bundle absent arrête
   la livraison ; conserver run, digests et diagnostics. Aucune suppression,
   retagging, réexécution ou adoption automatique d'une image isolée.
6. Examiner ensuite seulement approbation root indépendante, bootstrap des guards,
   sauvegardes, secours corrigé/correction en avant et autorisation de livraison
   fermée. Aucune intervention VPS ni ouverture n'est incluse dans la publication.

## 9. Décisions humaines, gates et verdicts

Décisions encore requises : traitement explicite des trois fiches de risque,
qualification RF10-03 ou périmètre d'acceptation privé limité, revue humaine du
code, autorisation distincte de fusion couvrant la publication main et RF10-04.
Ne pas réutiliser une ancienne acceptation hors de sa version ou de son délai.

Avant fusion : source/base/checks/protections revérifiés à l'instant de décision,
conversations résolues, aucun nouveau commit non revu, aucun secret ou invariant
de sécurité altéré, risques statués et publication automatique explicitement
autorisée. Un refus de ces conditions est un No-Go, même si GitHub affiche des
checks verts. Aucun bouton ou réglage GitHub n'a été modifié dans cette mission.

| Étape | Verdict |
| --- | --- |
| CI de PR | Validée pour f3c92eb8 et son checkout synthétique 502b1e07 ; ignorés et limites conservés. |
| PR en Draft / revue | Go pour poursuivre la revue humaine ; statut inchangé. |
| Fusion et publication automatique | No-Go en l'absence des décisions/preuves et de l'autorisation ci-dessus. |
| RC utilisable | No-Go : matériaux/provenance/images définitives/bundle et recette non qualifiés par ces inventaires. |
| Déploiement fermé | No-Go : approbation, images recettées, bootstrap/backup/secours et autorisation distincte manquants. |
| Ouverture publique | No-Go : risques d'inscription/email, exigences du runbook et validations opérationnelles réelles non levés ; cinq admissions maximum à autoriser séparément, IA toujours off. |

## 10. Contrôles locaux et clôture

Lecture des rapports, du code d'inventaire, des Dockerfiles/workflows et du chemin
d'admission. Vérifications hors ligne des pins/marqueurs, hashes d'archives et des
huit sources par plateforme ; aucun install/build ni test applicatif relancé.
Seul ce rapport Markdown est ajouté aux fichiers non suivis ; les deux rapports
14.7.7 et 14.7.8 préexistants restent intacts. Scripts de lecture et JSON sous var
restent privés et ignorés. Aucun fichier applicatif, lock, workflow, migration,
secret ou configuration de production modifié ; index vide.

`git diff --check` et contrôle UTF-8/blancs du nouveau rapport exécutés à la clôture.
Aucun commit, push, PR, merge, rerun, publication, déploiement, accès VPS,
activation d'inscription ou IA. **Arrêt après le rapport, dans l'attente des
décisions humaines ; aucune acceptation ou publication implicite.**

## Annexe — Versions installées effectivement inventoriées

La liste suivante est transcrite des deux artefacts ; tiret = absent de la fermeture
parcourue, pas preuve d'absence absolue sur la machine. Tous les pins applicables
de ces lignes sont égaux aux versions indiquées.

| Distribution | Linux | Windows |
| --- | --- | --- |
| alembic | 1.20.0 | 1.20.0 |
| annotated-doc | 0.0.5 | 0.0.5 |
| annotated-types | 0.8.0 | 0.8.0 |
| anyio | 4.15.1 | 4.15.1 |
| argon2-cffi | 25.1.0 | 25.1.0 |
| argon2-cffi-bindings | 26.1.0 | 26.1.0 |
| certifi | 2026.10.18 | 2026.10.18 |
| cffi | 2.1.1 | 2.1.1 |
| click | 8.5.0 | 8.5.0 |
| colorama | - | 0.4.6 |
| distro | 1.9.0 | 1.9.0 |
| fastapi | 0.146.0 | 0.146.0 |
| greenlet | 3.5.6 | 3.5.6 |
| h11 | 0.16.0 | 0.16.0 |
| httpcore | 1.0.9 | 1.0.9 |
| httptools | 0.9.0 | 0.9.0 |
| httpx | 0.28.1 | 0.28.1 |
| idna | 3.20 | 3.20 |
| iniconfig | 2.3.1 | 2.3.1 |
| jiter | 0.17.0 | 0.17.0 |
| mako | 1.4.3 | 1.4.3 |
| markupsafe | 3.0.4 | 3.0.4 |
| openai | 2.54.0 | 2.54.0 |
| opentelemetry-api | 1.45.1 | 1.45.1 |
| packaging | 26.3 | 26.3 |
| pgvector | 0.5.1 | 0.5.1 |
| pluggy | 1.7.0 | 1.7.0 |
| psutil | 7.2.2 | 7.2.2 |
| psycopg | 3.3.6 | 3.3.6 |
| psycopg-binary | 3.3.6 | 3.3.6 |
| pycparser | 3.12 | 3.11 |
| pydantic | 2.14.1 | 2.14.1 |
| pydantic-core | 2.50.1 | 2.50.1 |
| pydantic-settings | 2.16.0 | 2.16.0 |
| pygments | 2.21.0 | 2.21.0 |
| pymupdf | 1.28.2 | 1.28.2 |
| pytest | 9.1.1 | 9.1.1 |
| python-dotenv | 1.2.4 | 1.2.4 |
| python-multipart | 0.0.32 | 0.0.32 |
| pyyaml | 6.0.3 | 6.0.3 |
| sniffio | 1.3.1 | 1.3.1 |
| sqlalchemy | 2.0.55 | 2.0.55 |
| starlette | 1.9.0 | 1.9.0 |
| tqdm | 4.70.1 | 4.70.1 |
| typing-extensions | 4.16.0 | 4.16.0 |
| typing-inspection | 0.4.4 | 0.4.4 |
| tzdata | - | 2026.5 |
| uvicorn | 0.54.0 | 0.54.0 |
| uvloop | 0.23.0 | - |
| watchfiles | 1.3.0 | 1.3.0 |
| websockets | 17.2 | 17.2 |
