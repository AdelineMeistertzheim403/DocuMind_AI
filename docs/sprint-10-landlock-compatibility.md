# Sprint 10 — Étude de compatibilité Landlock ABI 2

> Actualisation du contexte : l'administratrice confirme la migration du VPS Debian 12
> vers `6.12.95+deb12-cloud-amd64`, ABI 6 dans l'hôte et l'API, avec restriction Landlock
> effectivement appliquée dans Docker. Aucun nouvel accès distant n'a été réalisé.
> Le blocage ABI 2 étudié ici est donc levé selon ce diagnostic ; aucune adaptation ABI 2
> n'est implémentée. Voir la [revalidation du lot 1](sprint-10-pdf-isolation-revalidation.md).
> Les constats et recommandations ci-dessous sont conservés comme étude historique.

Étude du 20 octobre 2026. Statut : **décision à valider, aucune adaptation du confinement implémentée**.

## Décision proposée

**Ne pas abaisser le minimum ABI 3 dans le moteur actuel.** Une simple adaptation du
masque Landlock à ABI 2 laisserait passer une troncature par `open`/`openat`, malgré
le filtre seccomp actuel. Les sondes locales ci-dessous reproduisent cette lacune.

L'option **B, noyau maintenu avec ABI mesurée ≥ 3**, est la recommandation pour conserver
le modèle de sécurité actuel et limiter la maintenance d'une politique spécifique.
Elle exige une fenêtre de maintenance commune aux applications du VPS et une validation
séparée du changement de noyau. Aucun redémarrage n'est autorisé par cette étude.

Si cette maintenance est exclue, **A constitue une piste de développement ciblée**, avec
filtrage seccomp complémentaire explicite et certification sur un véritable noyau ABI 2.
**A n'est pas validée pour la production** : l'environnement local disponible est ABI 7,
et aucun profil compensatoire n'a été implémenté ou certifié.

**C apporte une séparation supplémentaire intéressante**, mais impose une évolution du
protocole, du déploiement et de l'orchestration des sauvegardes. Un autre conteneur
utilise toujours le noyau de l'hôte : il ne résout pas à lui seul l'exigence ABI 3.

En attendant la décision, conserver la release opérationnelle. Le nouveau moteur doit
continuer à refuser son démarrage si ses protections sont indisponibles. Aucun passage
automatique au mode development, aucun profil seccomp Docker désactivé.

## Périmètre et éléments établis

Les informations suivantes proviennent de l'administratrice, sans inspection distante :

| Élément VPS | État communiqué |
| --- | --- |
| Noyau actif | `6.1.0-50-cloud-amd64`, Debian `6.1.176-1` |
| Noyau installé, inactif | `6.1.0-54-cloud-amd64`, Debian `6.1.190-1` |
| Landlock | Compilé, chargé, ABI détectée **2** |
| Docker | 28.1.1, AppArmor et seccomp actifs |
| Exploitation | Plusieurs applications ; sauvegardes, surveillance et conservation Sprints 7–9 |

L'audit porte sur les fichiers locaux, qui peuvent différer de la release active :

- `documind_extractor/sandbox.py`, `runner.py`, `contract.py` : politique et protocole ;
- `backend/services/extraction.py` : lancement et contrôle du processus ;
- `Dockerfile`, `compose.production.yaml`, `compose.pdf-isolation-test.yaml` : environnement ;
- `tests/test_extraction_linux.py`, `tests/test_extraction_protocol.py` : preuves existantes ;
- `tools/deploy_production.py`, `tools/backup_production.py` : invariants d'exploitation.

Le noyau installé mais inactif ne change pas les capacités du noyau en cours.
Un autre paquet de la même série 6.1 ne constitue pas une preuve de disponibilité ABI 3.
Les rétroportages éventuels doivent être établis par la mesure effective, dans l'hôte
puis dans l'image et sous les restrictions réellement utilisées.

## Différences ABI 2 / ABI 3

| Opération | ABI 2 | ABI 3 | Conséquence pour DocuMind |
| --- | --- | --- | --- |
| Lecture de fichier | `READ_FILE` | Identique | Autoriser seulement le runtime nécessaire |
| Ouverture en écriture | `WRITE_FILE` | Identique | Ne l'accorder à aucun chemin du parseur |
| Liste de répertoire | `READ_DIR` | Identique | Ne pas inclure le stockage documentaire |
| Création | Droits `MAKE_*` | Identique | Ne pas les accorder |
| Suppression | `REMOVE_FILE`, `REMOVE_DIR` | Identique | Ne pas les accorder |
| Liens/renommages entre répertoires | `REFER`, ajouté en ABI 2 | Identique | Ne pas l'accorder ; conserver les syscalls concernés interdits |
| Troncature | Aucun droit dédié | `TRUNCATE`, bit 14 | Différence bloquante pour le profil actuel |

Les droits s'appliquent aux hiérarchies autorisées et aux opérations prises en charge,
pas à toute opération possible sur un objet. La documentation ABI 2 signale notamment
l'absence de contrôle de `truncate`, `chmod`, `chown`, des attributs étendus, `ioctl`
et `fcntl`. Une règle « lecture seule » Landlock ABI 2 n'équivaut donc pas à un
montage en lecture seule. [Documentation Linux 6.1](https://www.kernel.org/doc/html/v6.1/userspace-api/landlock.html)

### Troncature : distinction essentielle

`WRITE_FILE` porte sur l'ouverture en écriture. `O_RDONLY | O_TRUNC` peut néanmoins
tronquer un fichier existant. ABI 3 ajoute le contrôle `TRUNCATE` pour cette opération,
ainsi que pour `truncate` et `ftruncate`. L'effet de cette combinaison de flags n'est
pas portable ; il ne faut pas compter sur son rejet.
[Documentation Linux 6.2](https://www.kernel.org/doc/html/v6.2/userspace-api/landlock.html),
[manuel open(2)](https://man7.org/linux/man-pages/man2/open.2.html)

Dans le code actuel, le masque `(1 << 15) - 1` inclut ce droit et le contrôle exige ABI 3.
Sur ABI 2, abaisser uniquement ce contrôle laisserait un masque non pris en charge ;
en retirer aussi le bit 14 supprimerait précisément cette protection.

Le filtre actuel interdit `truncate`, `ftruncate` et `creat`, mais autorise **`open`
et `openat` sans contrôle de leurs flags**. Le test local montre que `RLIMIT_FSIZE=0`
ne bloque pas le raccourcissement à zéro. Ce n'est pas une limite compensatoire suffisante.

### Descripteurs et mémoire hérités

Une politique ne retire pas rétroactivement toutes les capacités des fichiers déjà
ouverts. En ABI 3, les droits de troncature sont associés au fichier ouvert ; un
descripteur obtenu avant le confinement peut conserver cette capacité. `read`/`write`
utilisent également les droits acquis à l'ouverture. Des mappings déjà établis doivent
aussi être exclus du périmètre transmis au parseur.
[Droits associés aux descripteurs](https://docs.kernel.org/userspace-api/landlock.html#rights-associated-with-file-descriptors)

Le lanceur actuel effectue un nouvel `exec`, avec `close_fds=True`, environnement réduit,
stdin/stdout par pipes et stderr vers `/dev/null`. Il transmet les octets du document,
sans son chemin ni son descripteur. Cette séparation est indispensable **dans les deux
ABI**. La sonde avec un descripteur volontairement préouvert démontre un risque à éviter,
pas une fuite constatée du lanceur actuel.

`write`/`writev` restent nécessaires au protocole. Il faut donc prouver que les sorties
du parseur sont bien les pipes attendus, jamais un document, un secret, un socket de
contrôle ou un descripteur d'un autre traitement. Ne pas ajouter de réception de
descripteurs `SCM_RIGHTS`, de réouverture par `/proc/self/fd`, ou de récupération via
`pidfd_getfd`. Garder une nouvelle instance monothread par extraction avant installation
de la politique ; des threads préexistants ne doivent pas échapper au confinement.

### Seccomp et Docker : protections complémentaires

Ni ABI 2 ni ABI 3 n'apporte ici de politique réseau Landlock. Le blocage actuel des
sockets, connexions, exécutions, créations de processus, opérations de namespace et
changements de limites repose sur **le filtre seccomp du parseur**, appliqué après
installation Landlock. Le filtrage est un refus par défaut, non un assouplissement
du profil Docker. [Interfaces Landlock](https://man7.org/linux/man-pages/man7/landlock.7.html)

Le profil seccomp Docker vise une compatibilité générale : il ne remplace pas cette
liste minimale ni les règles sur les chemins. Les couches de filtrage se cumulent ;
une permission dans le filtre du parseur ne réautorise pas une opération interdite
par Docker. [Seccomp Docker](https://docs.docker.com/engine/security/seccomp/)

Les namespaces et capacités Docker réduisent la surface accessible, mais les conteneurs
partagent le noyau hôte. AppArmor actif ne prouve pas qu'un profil spécifique sépare le
parseur de l'API : le profil effectif reste à vérifier en environnement jetable.
Aucune de ces couches ne garantit l'absence de faille noyau.
[Sécurité Docker](https://docs.docker.com/engine/security/)

Constats propres au Compose audité :

- L'API est non privilégiée dans l'image, `read_only: true`, avec `no-new-privileges`.
- Son volume documentaire est **inscriptible** sur `/app/var` ; `STORAGE_DIR` désigne
  `/app/var/documents`. `/tmp` est un tmpfs inscriptible, plafonné à 256 Mio.
- Le runtime autorisé par Landlock est dans la racine en lecture seule, hors de ces
  montages. Cela apporte une défense contre la troncature des bibliothèques en production,
  mais ne rend pas le volume ni les descripteurs hérités inoffensifs.
- L'API rejoint les réseaux `data`, `application` et `outbound`. Elle doit accéder à
  PostgreSQL et aux fournisseurs IA ; son enfant n'est donc pas isolé du réseau par
  ce seul Compose. Le refus seccomp reste nécessaire.
- Aucun socket Docker n'est monté. API et PostgreSQL n'ont aucun port publié.
- Les limites API sont 1536 Mio, 2 CPU, 64 PID ; un seul processus Uvicorn.

**La troncature locale d'un faux runtime inscriptible ne démontre pas une exploitation
du Compose actuel en lecture seule.** Elle démontre que la politique ABI 2 naïve ne
fournirait pas, à elle seule, la garantie attendue, et dépendrait davantage des montages.

## Options étudiées

### A — ABI 2 avec profil compensatoire vérifiable

**Architecture envisagée, non implémentée.** Un profil explicitement identifié ABI 2,
distinct du profil ABI ≥ 3, conserverait les droits lecture seuls, sans `TRUNCATE`
non pris en charge, et imposerait des filtres d'arguments seccomp supplémentaires.

Exigences avant de pouvoir le considérer :

1. Refuser `O_TRUNC` dans `open` et `openat`, y compris avec `O_RDONLY`. Refuser aussi
   les ouvertures en écriture, création et fichiers temporaires anonymes ; contrôler
   les masques de flags avec leurs valeurs par architecture.
2. Garder interdits `openat2` (arguments indirects non inspectables par un simple filtre
   seccomp), `creat`, `truncate`, `ftruncate`, `fallocate`, `ioctl`, `fcntl`, les écritures
   alternatives et `io_uring`. Examiner également les effets de mappings partagés.
3. Conserver refus réseau, exécution, fork/clone, ptrace, namespaces, montages et
   élévation des limites ; aucun ajout général pour faire passer un test fonctionnel.
4. Prouver l'absence de descripteurs et mappings sensibles au démarrage ; préserver
   les bornes d'entrée/sortie, les délais et la destruction/récupération des processus.
5. Refuser les architectures et modes d'appels système non certifiés, y compris les
   variantes de compatibilité ; vérifier les refus sur x86_64 et aarch64 si elles sont publiées.
6. Vérifier l'installation effective de toutes les règles ; toute erreur doit empêcher
   l'extraction et la disponibilité du nouveau moteur. Aucun repli ABI 2 automatique.

**Garanties visées :** mêmes interdictions observables pour ce parseur, obtenues par une
combinaison différente de Landlock et seccomp. Ce ne serait pas une équivalence générale
entre ABI 2 et ABI 3, ni une politique réutilisable sans revue pour d'autres programmes.

**Risques résiduels :** oublis de flags/syscalls, différences d'architecture, évolution
PyMuPDF/Python/libc, dépendance accrue à la fermeture des descripteurs et aux montages.
Une nouvelle dépendance demandant un syscall doit entraîner une revue et une nouvelle certification.

**Exploitation :** pas de nouveau service, volume ou format de sauvegarde ; les invariants
des Sprints 7–9 et les trois services restent compatibles. Nouveau build, CI sur ABI 2
réelle, revue de sécurité et approbation nécessaires. Maintenance du filtre plus coûteuse
que B ; pas de redémarrage des autres applications, seulement un déploiement DocuMind ultérieur.

**Tests :** toute la matrice d'acceptation ci-dessous, d'abord sans dépendre de la racine
Docker en lecture seule pour masquer un défaut, puis dans l'image/Compose exacts.

### B — Noyau maintenu offrant ABI ≥ 3

**Garanties :** conserve le contrôle Landlock de troncature et le filtre actuel, sans
nouvelle branche de compatibilité. ABI 3 a été introduite en amont avec Linux 6.2 ; ce
numéro historique ne recommande pas d'installer un vieux noyau 6.2. Choisir un noyau
encore maintenu, compatible avec la distribution et l'hébergeur, puis mesurer l'ABI.
[Historique Landlock](https://man7.org/linux/man-pages/man7/landlock.7.html)

**Modifications :** maintenance du noyau et redémarrage de l'hôte après validation ; aucune
modification du moteur nécessaire pour ce motif. Une image Docker plus récente ne suffit pas.
Le nom de paquet à installer ne peut pas être déduit ici : version Debian et offre de
l'hébergeur doivent être confirmées avant préparation d'une procédure administrative.

**Risques/maintenance :** impact global au redémarrage, compatibilité stockage/réseau,
Docker, AppArmor, seccomp et pgvector à vérifier. Maintenance applicative plus simple ;
les risques de FD hérités et de faille noyau demeurent. Ne pas mettre à niveau à distance
sans console de secours et possibilité de sélectionner le noyau précédent.

**Compose/sauvegardes :** aucun changement de volumes, services ou format Restic. Prévoir
une sauvegarde hors VPS vérifiée et le traitement des tâches systemd persistantes au
redémarrage. Organiser la fenêtre de maintenance pour toutes les applications et éviter
un conflit avec les sauvegardes/conservation. Aucun timer des Sprints 7–9 n'est modifié ici.

**Tests :** VM locale jetable avec le noyau candidat, même image et restrictions Docker ;
matrice complète, puis validation séparée des autres applications. Le retour au noyau
ABI 2 rendrait le nouveau moteur indisponible : préparer aussi un retour applicatif
compatible, sans restaurer ni rétrograder arbitrairement PostgreSQL.

### C — Service extracteur séparé, sans réseau ni données sensibles

**Architecture envisagée :** un service extracteur sans réseau IP (`network_mode: none`),
sans volume documentaire, base, `.env`, clés, socket Docker ni accès au répertoire hôte.
Racine en lecture seule, utilisateur non privilégié, capacités retirées, tmpfs minuscule
si nécessaire, limites cgroup et seccomp. L'API conserve seule le stockage et envoie
uniquement les octets du document et les bornes d'extraction.

Un canal IPC local minimal peut relier l'API à un courtier de confiance. Un socket Unix
de contrôle éventuel exige un montage **dédié**, jamais le volume documentaire ; il ne
doit pas être utilisable par le parseur compromis. Le parseur reçoit des pipes par job,
sans descripteur d'écoute ni capacité de lire les autres jobs. `network_mode: none`
ne suffit pas à interdire les sockets Unix : leur séparation et les refus seccomp
doivent être testés. Aucun accès Docker dans l'API pour créer des conteneurs à la demande.

**Garanties :** même une erreur de règle sur les chemins ne donne pas accès aux volumes
sensibles absents du conteneur. Séparation des cgroups du parseur et de l'API. La gestion
de l'IPC, l'isolation entre jobs et la validation des résultats deviennent critiques.

**Limite de compatibilité :** même noyau ABI 2 ; le moteur actuel y refuse toujours le
démarrage. Il faut soit B, soit concevoir et certifier une politique différente tenant
compte du conteneur minimal. Retirer le contrôle ABI sans cette démonstration est exclu.

**Modifications/maintenance :** nouveau service/image, courtier, authentification/permissions
IPC, limites par job, healthcheck et protocole borné. Coût supérieur à A/B pour ce seul besoin.
Pas de garantie absolue contre une vulnérabilité du noyau partagé.

**Compose/sauvegardes :** les déployeurs et le préflight de sauvegarde exigent aujourd'hui
exactement `db`, `api`, `web`, et contrôlent les montages. Ajouter un service ferait
échouer ces contrôles. Une évolution explicite des manifestes, CI, contrôles de reprise,
sondes et arrêt/drainage de l'extracteur serait nécessaire avant installation. Préserver
le verrou commun et la reprise après erreur ; aucune exclusion silencieuse dans les
sauvegardes. L'extracteur ne doit pas introduire de données persistantes à sauver.

**Autres applications :** pas de reboot imposé par cette option, mais réserver CPU/RAM,
PID et disque ; aucune modification de Traefik ou de la Registry. Tester l'IPC hostile,
deux jobs concurrents, récupération après crash et cohérence de sauvegarde en plus de
la matrice commune. Les Sprints 7–9 restent inchangés pendant l'étude.

## Tests locaux effectués

### Environnement et portée

WSL Ubuntu local, Python 3.12.3, noyau `6.18.54.1-microsoft-standard-WSL2`, ABI **7**,
libseccomp disponible. Chaque sonde utilise un processus à usage unique, un répertoire
temporaire et des fichiers marqués `FAKE-*`, supprimés à la fin. Aucun PDF réel, secret,
socket Docker ni répertoire de production n'est utilisé ; aucune connexion réseau tentée.

Une sonde diagnostique non livrée, sous le répertoire ignoré `var/landlock-study/`, charge
des règles Landlock minimales : autoriser seulement `READ_FILE|READ_DIR` sur un faux
runtime inscriptible, traiter soit les bits 0–13, soit les bits 0–14. Selon le scénario,
elle installe ensuite **la liste seccomp existante**, sans filtre d'arguments nouveau,
avec `RLIMIT_FSIZE=0` et `RLIMIT_CORE=0`. Les cas sans seccomp servent de témoins pour
attribuer le refus à la bonne couche. Les codes et tailles finales sont vérifiés par
le parent, avec un délai de cinq secondes par processus.

**Cela compare deux masques sur ABI 7, pas deux noyaux.** Les correctifs et différences
historiques d'un vrai noyau ABI 2 ne sont pas reproduits. Ces essais réfutent une adaptation
naïve ; ils ne certifient pas une solution A.

### Résultats des 22 scénarios

Chaque ligne a été exécutée avec chacun des deux masques ; toutes les assertions ont réussi.

| Opération sur données fictives | Seccomp actuel | Bits 0–13 | Bits 0–14 |
| --- | --- | --- | --- |
| Lecture dans runtime autorisé | Oui | Réussit | Réussit |
| Lecture hors runtime | Oui | EACCES | EACCES |
| Création hors runtime | Oui | EACCES | EACCES |
| Création socket IPv4, sans connexion | Oui | EPERM | EPERM |
| `open(O_RDONLY\|O_TRUNC)` dans runtime | Oui | **12 → 0 octet** | EACCES, inchangé |
| `openat(O_RDONLY\|O_TRUNC)` dans runtime | Oui | **12 → 0 octet** | EACCES, inchangé |
| `truncate` par chemin hors runtime | Non, témoin | **12 → 0 octet** | EACCES, inchangé |
| Même `truncate` | Oui | EPERM, inchangé | EPERM, inchangé |
| `ftruncate` sur FD préouvert en écriture | Non, témoin | **12 → 0 octet** | **12 → 0 octet** |
| Même `ftruncate` | Oui | EPERM, inchangé | EPERM, inchangé |
| Lecture d'un FD privé préouvert | Oui | **Réussit** | **Réussit** |

Les dernières lignes justifient le maintien de `close_fds`, de l'exec propre et du filtre
seccomp, même avec ABI 3. Aucune lecture hors périmètre par chemin ne réussit dans ces sondes.

La suite existante a également été exécutée, sans modifier le moteur :

```text
var/pdf-isolation-linux-env/bin/python -m pytest \
  tests/test_extraction_linux.py tests/test_extraction_protocol.py -q -p no:cacheprovider
```

Résultat : **65 tests réussis en 19,78 secondes**, un avertissement de dépréciation
Starlette/httpx. Ces tests portent sur le profil actuel ABI ≥ 3, pas sur une nouvelle
politique ABI 2. Aucun test Docker ou noyau ABI 2 réel n'est revendiqué par cette étude.

Les empreintes SHA-256 de `sandbox.py`, `extraction.py` et `compose.production.yaml`
sont identiques avant et après les sondes. Le contrôle `git diff --check` est passé.

## Matrice d'acceptation avant tout déploiement

Exécuter uniquement en VM/conteneurs locaux jetables, sans secrets ni volumes réels.
Pour A, imposer un noyau où le syscall retourne réellement **2**, puis un contrôle
ABI ≥ 3. Tester l'image finale, ses bibliothèques, le profil Docker/AppArmor effectif
et chaque architecture publiée ; aucun `privileged`, `seccomp=unconfined` ou skip
transformé en succès pour contourner un échec.

| Preuve exigée | Critère d'acceptation |
| --- | --- |
| Disponibilité | ABI et installation des filtres contrôlées ; capacité absente/erreur de règle ⇒ refus du moteur |
| Autres documents | Marqueurs de plusieurs comptes inaccessibles, par chemins absolus/relatifs, symlinks, liens et `/proc` ; empreintes inchangées |
| Secrets | Marqueurs PostgreSQL/BYOK/SMTP/Restic inaccessibles ; environnement enfant vide de secrets ; aucun contenu dans erreurs/logs |
| Création/modification | Échec hors périmètre et dans runtime lecture seule : create, rename, link, unlink, chmod/chown/xattr, écritures et mappings partagés |
| Troncature | Échec `open` ET `openat` avec toutes combinaisons `O_TRUNC`, `truncate`, `ftruncate`, `creat`, `openat2`, `fallocate` et chemins alternatifs ; tailles/empreintes identiques |
| FD préouvert | `ftruncate` refusé par seccomp sur FD fictif volontairement préouvert ; en bout en bout, aucun FD sensible ne survit au lanceur, lecture comprise ; sorties uniquement vers les canaux attendus |
| Réseau | IPv4/IPv6, TCP/UDP et Unix refusés ; socket préouvert absent ; tests de création et d'usage sans émission extérieure, contrôle des familles alternatives |
| Docker | Ni montage ni FD du socket, ni connexion Unix/TCP ou accès à une API Docker distante ; pas de création de conteneur depuis le parseur |
| Ressources | Refus fork/clone/exec, augmentation de rlimits/cgroup/ns ; allocations, boucle CPU, flux infini et blocage ⇒ terminaison bornée, processus récupéré, API toujours disponible |
| Concurrence | Deux extractions au maximum, refus/saturation bornée, aucune lecture croisée ; limites globales CPU/RAM/PID vérifiées sous charge |
| Protocole | Identifiants/tailles/pages/champs stricts ; sortie malformée, trop grande ou tardive rejetée sans données sensibles |
| Fonctionnel | PDF/TXT valides, vides/corrompus et limites de taille/pages ; même extraction classique attendue sans appel IA |
| Exploitation | Healthchecks, import/isolation des comptes, sauvegarde/reprise des seuls services attendus ; aucun impact sur les projets voisins |

Pour les tests de modification, employer aussi un faux runtime inscriptible dans la VM :
un refus dû seulement au montage Docker en lecture seule ne prouve pas le filtre
compensatoire A. Ensuite réexécuter dans la configuration finale en lecture seule.
Pour B, tester les autres applications et le retour au noyau précédent en environnement
de recette. Pour C, ajouter les attaques sur l'IPC, les descripteurs du courtier, les
jobs simultanés et la quiescence pendant sauvegarde.

Ces vérifications constituent un seuil d'acceptation, sans prouver l'absence de toute
vulnérabilité noyau ou de tout canal auxiliaire. CPU/RAM cgroup et rlimits n'offrent pas
une garantie universelle contre tout déni de service ; surveiller aussi la charge de
l'hôte et conserver des marges pour ses autres applications.

## Validation attendue et suite

1. Valider B et préparer séparément une maintenance du noyau, **ou** autoriser un lot
   de conception/implémentation A avec environnement de certification ABI 2 réel.
2. Si C est retenue pour sa séparation structurelle, approuver d'abord l'évolution
   du protocole et des contrôles d'exploitation. Ne pas ajouter seulement un service au Compose.
3. Exiger les preuves ci-dessus et une revue du diff avant toute nouvelle release.
4. Autoriser ultérieurement le déploiement par la procédure habituelle, sans toucher aux
   volumes, au schéma ou aux secrets pour résoudre un problème de confinement.

Pendant cette étude : aucun accès VPS, redémarrage, déploiement, push, changement de
production, de politique de confinement, de Compose, de seccomp ou des Sprints 7–9.
Le présent rapport est le seul nouveau livrable versionnable de cette étude.
