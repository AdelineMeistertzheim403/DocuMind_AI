# Sprint 14.7.11 — Qualification npm, APT/APK et images

26 octobre 2026. Travail local, code source de PR nº 6 :
`f3c92eb8ba2bb69b83a9798ebc3df8a70f48fbb2`.
Rapports lus : [14.7.10](SPRINT_14_7_10_BUILD_MATERIALS_QUALIFICATION_REPORT.md),
[14.7.9](SPRINT_14_7_9_PREMERGE_RISK_REVIEW.md),
[14.7.5](SPRINT_14_7_5_SUPPLY_CHAIN_REPORT.md),
[runbook](SPRINT_14_7_PUBLIC_BETA_OPENING_RUNBOOK.md).

**Six constructions hors réseau réussies : deux variantes de qualification par
image backend, frontend et PostgreSQL/pgvector.** Dépendances, configurations et
composants comparés sont identiques entre chaque paire ; les couches OCI et Image
IDs diffèrent. Recette interne et tests ciblés réussis sur les sorties construites.

**RF10-03 reste ouvert.** Ce sont des variantes temporaires contrôlées, pas une
certification des Dockerfiles dynamiques actuellement suivis ou de futures images
CI. Les écarts de construction, signatures npm historiques et limites de
provenance nécessitent une décision humaine. Préparation de cette décision
possible ; fusion/publication, RC utilisable, déploiement et ouverture non autorisés.

## 1. Périmètre et preuves conservées

Seules origines consultées/acquises dans ce lot : `registry.npmjs.org`, dépôt
officiel Debian `deb.debian.org`, et dépôt officiel Alpine
`dl-cdn.alpinelinux.org`. Bases officielles Node/PostgreSQL tirées de Docker Hub
par les digests précédemment vérifiés, via le client Docker et sa validation TLS
normale. Python et matériaux Python/pgvector sont réutilisés depuis 14.7.10,
avec recontrôle des hashes. Aucune origine npm secondaire ou URL de dépôt éditeur
n'est automatiquement suivie. Aucun accès Registry privée, VPS, B2, SMTP réel
ou fournisseur IA ; aucune opération GitHub.

Les 289 fichiers de l'export Git de 14.7.10 sont recopiés sous
`var/s14-7-11/context/source/` et recontrôlés par leur manifeste SHA-256 : tous
identiques. Le dépôt applicatif et ses Dockerfiles/workflows/locks restent intacts.

Preuves ignorées sous `var/s14-7-11/` : inventaires npm, archives, signatures,
reçus APK/deb, copies de qualification, logs, configurations fictives,
comparaisons d'images et snapshot/restauration fictifs. La copie originale du
générateur de recette reste également sous var. Aucun certificat privé, cookie,
mot de passe, token ou contenu de courrier ne doit être joint au futur commit.
Ce rapport ne reproduit aucun de ces éléments ; les identités utilisées sont fictives.

## 2. npm : archives, plateformes, scripts et provenance

### Acquisition exacte

- **368 entrées** du lock, **368 archives uniques** reçues depuis leurs URLs
  `https://registry.npmjs.org/...` ; **215028240 octets** au total.
- Pour chaque entrée : identité/version du JSON officiel et du package.json dans
  l'archive, URL exacte, SRI SHA-512 du lock et octets calculés vérifiés ; intégrité
  et shasum SHA-1 officiels confrontés lorsqu'ils sont présents. Aucun remplacement
  de version ni résolution d'une autre version.
- Hash du lock utilisé et de l'export Git identique :
  `7ce52768894aeaccbd4f632b6c18261348cf6858a6f5787fc5ad86d52e051804`.
- Cache npm préparé **sans réseau** : vérification native de **368 contenus et
  368 entrées**. Aucun `--ignore-scripts` dans les `npm ci` de construction.

Inventaire exhaustif : `npm/acquisition.json`, un reçu par chemin du lock,
avec URLs, version, SRI, SHA-256/SHA-512 calculés, taille, metadata de plateforme,
engines, scripts et provenance disponible. Les archives sont nommées par SHA-512
sous `npm/tarballs/`. Ces matériaux ne sont pas ajoutés à Git.

Première inspection : 30 archives @types utilisaient une racine différente de
`package/`. Le pilote privé exigeait initialement ce préfixe et les refusait.
Correction du seul lecteur de qualification : package.json principal unique au
premier niveau, sans extraction de chemins non sûrs, en conservant nom/version
et SRI. Le premier relevé est conservé ; acquisition finale **368/368, zéro erreur**.

### Ce que npm ci installe réellement

Dans la base officielle **Node 22.23.4 / npm 10.9.9, Linux amd64 musl** :

| Étape | Paquets du lock installés | Divergences de version |
| --- | --- | --- |
| Stage de build, npm ci | 300 | 0 |
| Runtime, npm ci --omit=dev | 118 | 0 |

Les 368 archives sont conservées pour couvrir le lock, y compris les options
d'autres plateformes ; cela ne signifie pas que 368 paquets entrent dans l'image.
La simulation des métadonnées OS/CPU/libc en rendait 296 admissibles. npm 10.9.9
installe néanmoins aussi quatre variantes optionnelles déclarées glibc sous musl :
`@napi-rs/lzma-linux-x64-gnu`, `@rollup/rollup-linux-x64-gnu`,
`@tailwindcss/oxide-linux-x64-gnu`, `lightningcss-linux-x64-gnu`.
Cette différence est observée dans les fichiers installés ; la sélection effective
par npm, le build et les tests priment sur une simple approximation des marqueurs.
Elle n'est pas masquée comme une substitution de version. Aucune des entrées
admissibles n'a un engine Node incompatible avec 22.23.4 selon semver.

Deux entrées du lock déclarent `hasInstallScript` :

- esbuild **0.25.12**, `postinstall: node install.js`, avec binaires optionnels
  par plateforme, tous présents dans les matériaux acquis ; postinstall exécuté
  normalement dans le build sans réseau ;
- fsevents **2.3.3**, optionnel Darwin, exclu sous Linux. Son package déclare des
  scripts build/prepublish et une intégration native ; ne pas annoncer qu'un
  postinstall explicite a été exécuté sous Linux.

whatwg-encoding **3.1.1** est déclaré deprecated. Ce signal n'est pas un audit CVE
ni une preuve de vulnérabilité. Aucun npm audit réseau ou changement de version.

### Signatures et limites de confiance

Clés publiques acquises sur l'origine autorisée :
`https://registry.npmjs.org/-/npm/v1/keys`. Vérification hors réseau avec
`node:crypto`, sur le message officiel `nom@version:dist.integrity` :

- **437 signatures cryptographiquement valides**, zéro signature invalide,
  zéro keyid inconnu ; toutes les 368 entrées ont une signature ;
- **122 paquets** n'ont qu'une signature liée à une clé expirée le
  **29 janvier 2025** ; **60 de ces paquets** sont dans les 118 entrées runtime ;
- les autres **246 paquets** disposent d'au moins une signature d'une clé sans
  expiration indiquée dans la réponse actuelle du registre.

La validité mathématique ne prouve pas la validité historique de la clé lors de
la publication. Aucun horodatage de confiance n'est établi ici pour les 122 cas,
aucune date de vérification n'est antidatée et aucune clé expirée n'est déclarée
acceptée pour une release. Les hashes et la provenance HTTPS de ces matériaux
restent vérifiés pour l'expérience confinée ; la politique de promotion est ouverte.
Les clés sont reçues du même registre HTTPS, pas d'une ancre indépendante épinglée.

**125 documents de provenance** annoncés par les métadonnées ont été récupérés
depuis le même registre. Ils sont disponibles pour revue, sans validation complète
Sigstore/transparence, identité éditeur ou chaîne de confiance indépendante.
Une signature de registre ne vaut pas attestation de sécurité du code de l'éditeur.

## 3. Debian/APT

La base Python par digest contient déjà **libseccomp2 2.6.0-2** et
**libc6 2.41-12+deb13u4**. Le besoin runtime supplémentaire du Dockerfile backend
est donc satisfait dans cette base précise ; aucun nouveau deb à installer pour
ce besoin. Cela ne généralise pas à une future résolution du tag flottant.

Vérifications supplémentaires par rapport à 14.7.10 :

1. Signature du InRelease trixie conservé validée **hors réseau par sqv**, avec
   le trousseau Debian de la base officielle épinglée, sans ajout de clé ou
   assouplissement de politique/date. Trois certificats valides sont retournés.
2. Hash SHA-256 de Packages.xz identique à celui fourni par ce InRelease :
   `7778d3e3f303b7ddb8ce0fe7c8d57473a076c6bf2e8f241f75421d2396352498`.
3. Archive officielle libseccomp2_2.6.0-2_amd64.deb acquise et vérifiée contre
   l'entrée de cet index :
   `89d5138e05fb6a86b9afd8b54dc0fb4b14f4c27c05e6c5f767c2132bdf808531`.
4. Extraction dans un répertoire temporaire, sans installation : hash de la
   bibliothèque identique à celui de la base Python :
   `c851a2378b4ef3a42ada5f8ff1604ad38f6bbcafa2aeea3f6680160d628c2f27`.

Les trousseaux héritent de la confiance dans la base officielle ; ils ne sont pas
une nouvelle validation indépendante de toutes les couches upstream.
Le Dockerfile suivi conserve apt-get update/install sans version ni snapshot.
La copie de qualification remplace cette étape par une assertion de version déjà
présente, pas par un téléchargement APT dynamique supposé reproductible.

## 4. Alpine/APK et pgvector

### Fermeture et signatures

Index main v3.24 x86_64 conservé, SHA-256
`c169fa06972f9d2639ad1ea0effa26bf7223a72101a41c5cf2c12813d885cab5`.
Vérification native de sa signature avec **apk-tools 3.0.8-r0** et les clés de la
base officielle PostgreSQL : réussie, sans allow-untrusted ni TLS désactivé.

Résolution build-base/git par cet index, acquisition de **38 APK exacts** depuis
`https://dl-cdn.alpinelinux.org/alpine/v3.24/main/x86_64/`, SHA-256 calculés et
conservés. `apk verify` : **38/38 signatures OK**. Une seconde lecture native
du dépôt local valide les paquets par rapport à l'index et sa fermeture.

Versions de compilation : build-base **0.5-r4**, git **2.54.0-r0**,
gcc/g++ **15.2.0-r5**, binutils **2.45.1-r1**, make **4.4.1-r4**,
musl-dev **1.2.6-r3**. Les autres bibliothèques et hashes sont recensés dans
`system/alpine-package-receipts.json`. Les métadonnées C: de l'index APK ne sont
pas présentées comme un hash SHA-256 de l'archive complète.

Les premiers essais de résolution ont été refusés : syntaxe booléenne apk 3,
chemin local attendu avec sous-répertoire x86_64, fins de ligne LF et destination
d'écriture. Les erreurs et sorties sont conservées. Le pilote exige absence
d'ERROR en plus du code retour ; aucun résultat partiel n'est présenté comme
une validation. Les signatures finales et la fermeture finale sont bien validées.

La toolchain est un besoin de build, installée dans le groupe virtuel .vector-build
et supprimée après compilation. Le manifeste installé final est comparé entre
les deux sorties ; les dépendances runtime sont conservées. Pas de compilateur
ajouté intentionnellement à l'image de production finale.

### Source et compilation

Source réutilisée, archive et contenus recontrôlés : tag v0.8.7, commit
**f37c13f68b57d2c3472b2214fbcff699d6d34876**, SHA-256 de l'archive
`83d673c3b287cddbf3879f86215f043f2c2b56c69d37b2a77504910db1ed6e56`.
Les 158 blobs Git avaient été vérifiés en 14.7.10 ; aucun changement de version.
Le commit est non signé selon GitHub ; le hash lie l'archive au contenu reçu,
sans lui ajouter une signature indépendante.

Deux compilations hors réseau avec PostgreSQL **17.11**, `make with_llvm=no`,
même chemin /tmp/pgvector et mêmes entrées : même vector.so installé :
**`a261f42e7ea60b22aa852d06e960fdb82782fc1d34cd66cca0781f968cfa47f3`**.
vector.control :
`9f7d0fcada5e68aa41adf9d5b3ab3fd43c83f2edd462c391a0f715d72a9941ec`.
La chaîne source → compilation → binaire de ces deux expériences est maintenant
documentée. Cela ne reconstitue pas la provenance d'un ancien build historique.

Sur l'image a : **CREATE EXTENSION vector**, version **0.8.7**, calcul de distance
vectorielle donnant **1**, création d'un index **HNSW** et insertion/requête réussis.
Le paquet Python pgvector 0.5.1 est distinct ; aucune mise à jour des deux composants.

## 5. Builder et bases effectivement utilisés

- Docker Desktop **29.8.2** ; Buildx **0.37.2**, commit
  `2d379c0c3f22da0d2759d132a0ec81ca949098f0` ; BuildKit **0.33.1**.
- Driver **docker**, worker local desktop-linux déjà installé. Pas de nouveau
  daemon, changement de configuration, privilège insecure, image BuildKit ou
  frontend tiers téléchargé. Les espaces de construction/contextes et conteneurs
  d'essai sont jetables ; le builder partagé n'est pas réinstallé en environnement
  neuf ni sa chaîne binaire entièrement authentifiée par ce lot.
- Commandes de construction : `docker build --no-cache --network none ...` pour
  les six sorties ; cache npm prérempli séparément depuis les 368 reçus vérifiés.
- Hashes raw des manifestes officiels et Image IDs locaux de base/configs
  recontrôlés, **3/3 conformes** aux métadonnées 14.7.10.

| Base | Manifeste exécutable linux/amd64 |
| --- | --- |
| Python 3.13.17 slim | sha256:d879ed88565a7a3c614b980b369d4a5025a9d057b71f93d09fc6d0b2ca823a18 |
| Node 22.23.4 Alpine | sha256:025b8e975a61d94e33abeafaad1255ef44e4898cf1a1b6446860009c72e6d284 |
| PostgreSQL 17.11 Alpine | sha256:e4cb93687b062cd25a0e8f672d85a7708235009d70d31f8a7698d9370092a9c4 |

Digests d'index et de configuration restent distincts, détaillés en 14.7.10.
Les provenances SLSA des bases restent consultées sans validation cryptographique
indépendante exhaustive. Aucun audit CVE actualisé de ces images ou du builder.

## 6. Copies de qualification et différences avec le code suivi

**Aucun Dockerfile suivi modifié.** Trois fichiers temporaires sous var explicitent
les entrées pour l'expérience ; ils ne sont pas automatiquement adoptables en CI :

| Copie | Changement contrôlé |
| --- | --- |
| BackendDockerfile | FROM par digest ; assertion libseccomp déjà présent ; 44 dépendances runtime sans extra test installées avec hashes, plus wheel projet identifiée en 14.7.10 ; staging de dépendances puis copie vers /usr/local ; sources f3c92eb8, USER app et commande uvicorn conservés. |
| FrontendDockerfile | Deux FROM officiels par digest ; cache npm identifié ; npm ci complet et --omit=dev hors réseau avec scripts normaux ; stages de dépendances séparés pour ne pas garder les tarballs/cache dans l'image finale ; même server/dist, USER node et healthcheck. |
| PostgresDockerfile | FROM par digest ; dépôt APK local signé, deux besoins directs de compilation exacts ; source pgvector par archive/commit au lieu du clone de tag ; make/install et suppression de la toolchain ; aucun changement de version PG/pgvector. |

Les matériaux Python runtime/test étaient 49 ; la fermeture de production extraite
des métadonnées Linux est **44**, sans problème de contraintes. Le runtime final
contient ces 44 distributions, DocuMind et le pip de la base : **46 distributions**.
L'overlay de tests ajoute les extras nécessaires, sans les ajouter au backend final.

Les Dockerfiles suivis restent dynamiques sur tags, pip/build isolé, apt/apk et
clone pgvector. **Un succès de ces copies hors ligne ne prouve donc pas que le
workflow actuel reconstruira exactement ces entrées.** Adoption des copies ou d'une
autre stratégie de verrouillage exige revue et nouveaux contrôles de CI autorisés.

## 7. Comparaison des deux constructions

Les six builds sont réussis. Tous les tags ci-dessous sont uniquement locaux,
préfixés documind-s14-7-11, sans SHA/tag de future release.

| Image de qualification | Image ID a | Image ID b |
| --- | --- | --- |
| `documind-s14-7-11-backend-{a,b}:local` | `sha256:7a58bec355ea8cb8b94096de77921dd6e283b3c37f3906ece317da6e30a4a5af` | `sha256:ae9b43d9da0544facca45754c56c55655c5c0aa7aeabfc36d7fec19bb48e4b0e` |
| `documind-s14-7-11-frontend-{a,b}:local` | `sha256:f536afa68c4cd2e247051a13ae155e73ff5d6f3d766f853ddd6136ade7dd6363` | `sha256:7f52ad11af6a684c1a0db7a8a49a5e5e2a58ed9804cb9f52917a478a16268883` |
| `documind-s14-7-11-postgres-{a,b}:local` | `sha256:81845febfc0f925c359c63cd961e3f72c6bfa1d5552c103b9bd29ccf1aa92299` | `sha256:039f7223be0c2942c91393a9cd9b792d1159aa58c6a63631ac869a6cb84d2575` |

Pour chacune des trois paires : **Config Docker identique**, inventaire comparé
identique, mais **Image ID et liste de couches rootfs différents**.

- Backend : mêmes versions, mêmes hashes de **24 fichiers natifs .so** et
  **84 fichiers source Python** sous /app.
- Frontend : même Node/npm, même inventaire de packages et hashes/liens des
  **11426 fichiers/liens** recensés sous /app, dist et server compris.
- PostgreSQL : même vector.so/vector.control et même base de paquets installés.

Ce n'est pas un manifeste exhaustif de toutes les métadonnées, bytecodes, headers
tar et fichiers de l'OCI. La cause de chaque différence de couche n'est pas établie.
Ne pas garantir qu'un réglage de dates suffirait. L'égalité bit à bit de la wheel
projet démontrée en 14.7.10 ne se généralise pas à ces images.

## 8. Tests sur les sorties réellement construites

### Laboratoire Compose

Projet **documind-s14-7-11-c3df5fa8**, réseau interne neuf, aucun port publié,
base/données/documents/certificat/comptes entièrement fictifs. Les services db,
api et web utilisent les trois images a ci-dessus et sont **healthy** avant puis
après la sauvegarde. Pas de montée de privilèges, rootfs API/BFF read-only,
capabilities supprimées, no-new-privileges et tmpfs noexec ; RAM/CPU/PID bornés.
Les services et données de la production ne sont jamais montés.

L'interdiction de migration est respectée : **aucune commande Alembic exécutée**.
Les deux bases de laboratoire sont initialisées par ORM create_all, extension
vector et données initiales fictives ; aucune révision Alembic inventée.
Cela valide les chemins applicatifs sur ce schéma, **pas les migrations/rollback
de schéma 0007**. Les tests qui invoquent explicitement une migration sont exclus.

### Résultats

| Validation | Résultat réel |
| --- | --- |
| Tests Python ciblés, PostgreSQL et sandbox strict | **163 réussis, 11 désélectionnés, 0 ignoré, 0 échec**, 116,89 s |
| React sur le stage Node construit | **52 réussis**, 10 fichiers ; 0 échec |
| BFF Node sur le stage construit et même code serveur | **50 réussis**, 0 ignoré/annulé/échec |
| Build TypeScript/Vite | Réussi dans chacune des deux constructions frontend |
| Recette HTTPS interne | **13 contrôles réussis**, détaillés ci-dessous |
| pgvector compilé | Extension 0.8.7, distance 1 et HNSW réussis |
| Backup/restauration fictifs | **23 tables** identiques, compteur quota certifié, **4 documents** restaurés et hashes/tailles conformes |

Campagne Python : tests existants extraction Linux/protocole, gateway security,
document integrity, public beta et AI disabled enforcement. Les fonctions testées
restent celles de la PR. **Adaptation privée et déclarée de conftest** : initialiser
et retirer seulement le schéma ORM de la base de test dédiée, à la place des
upgrades/downgrades ; semer quota initial et budget fictifs ; forcer le sandbox
au lieu du mode development de la fixture portable. Le fichier suivi est inchangé.
Les snapshots de construction ne contiennent pas cette fixture dans le backend final.

Les 11 désélections, non présentées comme des succès : deux tests de migration,
cinq paramètres d'arrêt brutal explicitement development, deux paramètres de
validation enabled et deux paramètres de désactivation entre étapes nécessitant
une activation explicite du test. La suite complète et les crash tests historiques
ne sont pas prétendus relancés. Les scénarios défensifs sélectionnés utilisent des
fournisseurs simulés et interdisent les vrais SDK externes ; aucun traitement IA
réel n'est activé. Avertissement Starlette/httpx TestClient conservé.

Les tests frontend utilisent un stage de build/dev dérivé du même Dockerfile
temporaire ; tests serveur montés depuis le Git exact. Ils ne sont pas des paquets
de test ajoutés au runtime final. Les assertions HTTPS, elles, s'exécutent dans
l'image frontend finale avec son code BFF réel et contre l'API finale construite.

### Recette HTTPS fictive

Réutilisation du proxy HTTPS de tests existant, adapté uniquement dans une copie
privée pour les chemins de l'image et deux adresses client synthétiques. Certificat
fictif contrôlé, validation TLS conservée ; proxy et client sur loopback à l'intérieur
du conteneur web, sans publication de port ni modification du système/DNS hôte.
Ce proxy lance une instance de test du vrai code BFF ; le BFF normal du service
est aussi contrôlé par son healthcheck. **Pas de validation Traefik/VPS réelle.**

Les 13 contrôles couvrent : santé HTTPS, refus anonyme, CSRF, connexion/cookie
Secure/HttpOnly sans token retourné, uploads TXT et PDF, analyse classique et texte
extrait, isolation entre propriétaires, refus IA et connexion BYOK, cinq admissions
et notifications fictives, vérification email à usage unique et connexion publique
fictive, révocation de session.

Après six tentatives : **5 comptes publics, issued_count=5, aucun compte/mail pour
le sixième**, réponses génériques conservées. Deux comptes de laboratoire
préexistants au scénario ne consomment pas ces cinq admissions. **AIUsage=0,
AIReservation=0**. Les limites/settings publics ne concernent que ce réseau de
test inaccessible depuis l'extérieur, pas une ouverture réelle d'inscriptions.

### Incidents du harnais et diagnostic conservé

- Le générateur historique de recette crée des fichiers privés dont le mode
  rendait env inaccessible à Docker Desktop. Copies fictives neuves avec les
  permissions héritées du workspace, sans modifier les ACL d'origine/globales.
- Premier passage HTTPS : TXT/PDF acceptés mais analyse 422. Les logs démontrent
  que multiprocessing spawn réexécutait le bootstrap privé et son assertion de
  base vide. Le bootstrap de laboratoire a été placé sous garde __main__, sans
  réinitialiser les données fictives ; seul ce service API de laboratoire a été
  redémarré. Recette finale réussie, premiers refus conservés. **Pas de correction
  applicative, d'allongement de timeout ou d'attribution à R14-SQL-01.**

### Sauvegarde et restauration

API/BFF du laboratoire arrêtés gracieusement pour un snapshot cohérent, PostgreSQL
laissé en marche ; archives créées avec les commandes pg_dump/tar utilisées par
backup_local, puis restauration dans une **nouvelle base sans API attachée**.
`tools.verify_snapshot.verify_snapshot` réutilisé : **23 tables inchangées**, dont
les trois champs du quota. Fichiers extraits dans un nouveau répertoire sous var,
comparés aux noms/tailles/SHA-256 SQL : **4/4 conformes**.

- database.dump : `dfa852abb5cf1d26fdbaa956c8c8aab668db0c8045f1b16001921c5869e45163` ;
- documents.tar.gz : `75d71cc79c330d8dd690b9d8da1937194a6155887ecf931b6afa9f55318be6f7`.

Manifest qualification_only, migration=null et origine ORM explicités : **pas un
bundle de sauvegarde production 0007**. Le CLI complet backup_local/validate_restore
avec contrôle de révision/migrations n'a pas été présenté comme exécuté ; aucune
révision artificielle n'est créée pour le faire passer. Ni Restic/B2 ni restauration
de production. Le quota restauré conserve cinq admissions ; copie jamais exposée
à une API, aucun remboursement/réouverture implicite.

## 9. Préservation et retrait des ressources de test

Après les derniers healthchecks, labels/project/montages vérifiés contre l'inventaire
initial : retrait uniquement des conteneurs/réseau créés pour ce projet et de son
volume documents nouvellement créé, identifié explicitement et absent de l'état
initial. **Aucun down -v**. PostgreSQL de laboratoire est arrêté seulement à cette
clôture du projet jetable ; aucun PostgreSQL préexistant n'est touché.

Comparaison finale : **8 conteneurs préexistants** conservent leurs IDs, noms,
images et états ; **328 volumes préexistants** et les réseaux initiaux sont toujours
présents. Cela vérifie l'identité/l'état observables, pas l'état interne de toutes
les autres applications. Aucune commande n'a ciblé ces ressources ou la production.
Les images de qualification, reçus, backups fictifs et logs restent locaux sous
leurs noms de laboratoire ; pas de suppression d'images ou de matériau existant.

## 10. État RF10-03 et risques indépendants

| Axe | État factuel |
| --- | --- |
| Matériaux vérifiés | npm 368 archives et installations exactes ; Python acquis précédemment ; Debian index/deb/bibliothèque ; Alpine index et 38 APK ; source pgvector identifiée. |
| Origines authentifiées | HTTPS sur les origines autorisées ; signatures Debian/APK validées avec les trousseaux des bases officielles. Confiance dans ces bases conservée comme préalable. |
| Signatures/provenance | Signatures de registre npm vérifiées, mais 122 cas à clé expirée sans temps historique de confiance ; 125 documents npm disponibles, validation complète non faite. Limites PyPI/SLSA des bases et builder héritées de 14.7.10. |
| Dépendances reproductibles | Versions et contenus comparés identiques dans les deux sorties contrôlées. |
| Équivalence fonctionnelle | Preuves positives sur images a et overlay de tests ; inventaires/configs des b identiques. Pas une recette HTTPS complète séparée sur toutes les images b. |
| Bit à bit OCI | Non : IDs et couches différents. |
| Chaîne CI réelle | Les Dockerfiles/workflows suivis n'utilisent pas automatiquement ces entrées hors ligne ; aucune publication réelle ni provenance des futures images vérifiée. |

**RF10-03 réduit mais non résolu.** R14-SQL-01 reste inexpliqué ; R14-SQL-03
(admission commitée/notification absente) reste une décision opératrice distincte,
sans compensation automatique. R14-SQL-02 conserve son correctif et réussit les
fault tests sélectionnés, sans certification supplémentaire des cinq crash cases
exclus. RF10-04 reste applicable à une publication partielle : arrêt, preuves
conservées, aucun rerun/retagging/suppression automatiques.

## 11. Modifications futures proposées, non appliquées

1. Revoir les écarts des copies sous var avant d'adopter un verrouillage dans les
   Dockerfiles/CI : bases par digest, manifests hachés npm/Python, lock build
   séparé, source pgvector par commit et packages système identifiés/signés.
2. Définir une politique des signatures npm historiques avec horodatage/preuves
   disponibles, traitement des cas sans preuve et périmètre d'acceptation éventuel.
   Ne pas déclarer les 122 cas acceptés simplement parce que npm ci réussit.
3. Décider quelles preuves PyPI/npm/SLSA/builder sont obligatoires et qualifier les
   vérificateurs/trust roots correspondants avant leur adoption. Les octets de
   matériaux fixés ne sont pas un audit du code des éditeurs.
4. Politique de mise à jour de sécurité : snapshots/index signés datés pour chaque
   qualification, surveillance/advisories autorisés séparément, durée de validité
   du lot et requalification des bases/paquets. Ne pas geler éternellement ces
   versions ni leur attribuer une absence de CVE non démontrée.
5. Si la reproductibilité OCI stricte est exigée, définir un périmètre/méthode de
   comparaison exhaustifs et traiter les écarts ; ne pas fabriquer une promesse
   bit à bit à partir des seuls contenus critiques égaux.
6. Après une future adoption autorisée, CI des nouveaux SHA puis recette des
   **digests réellement publiés**, neuf fichiers et statement, approbation root,
   guards/backup/retour arrière. Migration et tests de restauration versionnés
   restent des validations séparées, non exécutées dans ce lot.

## 12. Verdict de préparation de décision humaine

**Preuves suffisantes pour poursuivre une revue humaine concrète des matériaux et
des variantes contrôlées**, avec six builds et tests positifs. **Obstacles précis
restants avant de présenter les images de la PR comme prêtes à publier** :

- écarts temporaires non revus/adoptés par les Dockerfiles et la chaîne CI suivis ;
- politique des signatures npm expirées et autres provenances critiques non close ;
- confiance/qualification complète du builder non démontrée ;
- non-reproductibilité OCI à traiter ou borner explicitement selon les exigences ;
- recette des futures sorties CI, bundle/digests et décisions de risques manquants.

Pas d'acceptation de risque au nom de l'exploitante. Une éventuelle autorisation
bornée de publication privée doit nommer version, run/attempt, écarts acceptés,
durée et RF10-04. L'ancienne exception Sprint 10 ne s'étend pas tacitement ici.
La fusion sur main peut déclencher publish automatiquement et reste interdite.
Déploiement et ouverture publique restent des décisions distinctes, non autorisées ;
aucune inscription réelle ou IA n'est activée.

## 13. Contrôles locaux de clôture

Seul ce nouveau rapport rejoint les fichiers Markdown non suivis. Aucun changement
applicatif, Dockerfile suivi, lock, workflow, migration ou .env.production ; aucun
commit/push/merge/PR/rerun/publication. Les rapports antérieurs et modifications
existantes sont préservés. Contrôles Git, index vide et blancs/UTF-8 du rapport
vérifiés à la clôture ; matériaux privés et harnais restent ignorés sous var.

**Arrêt après le rapport ; aucune adoption ni publication implicitement autorisée.**
