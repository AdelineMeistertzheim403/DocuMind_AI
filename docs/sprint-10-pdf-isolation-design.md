# Sprint 10 phase B, lot 1 — confinement PDF/TXT

## Décision et périmètre

Un processus neuf par document applique **Landlock et une allowlist seccomp** avant de lire
l'entrée ou d'importer PyMuPDF. Il reçoit uniquement un document en mémoire par stdin et
renvoie un JSON borné par stdout. Il n'importe ni FastAPI, ni sa configuration, ni les comptes.
Le parent impose en plus un délai et une borne de sortie, puis récupère systématiquement
le processus. Une indisponibilité des protections interdit l'extraction, sans repli automatique.

La frontière est constituée par deux politiques **du noyau Linux**, pas par le seul subprocess,
le retrait de variables ou un changement d'UID. Le worker garde l'UID de l'API, mais ne peut
ni lire son stockage ni utiliser ses secrets, sockets ou interfaces d'accès aux processus.
Cette identité partagée est explicite : aucun changement d'UID ou namespace distinct n'est
revendiqué. Les permissions MAC et le filtrage de syscalls sont irréversibles pour ce processus.

L'architecture conserve les **trois services** `db`, `api`, `web`, les réseaux, Traefik,
PostgreSQL 17/pgvector et les deux volumes persistants. Aucun socket Docker n'est ajouté,
aucun nouveau service de production ni volume de communication n'est nécessaire. Les
validateurs stricts du déployeur et des sauvegardes gardent leurs attentes d'identité/montage.
Authentification, sessions, quotas, analyses classiques et IA ne sont pas modifiés.
SEC10-02 et les autres lots de l'audit restent des travaux séparés.

## Alternatives examinées

| Solution | Appréciation |
|---|---|
| Multiprocessing, environnement nettoyé ou UID différent seuls | Insuffisant : pas de frontière complète fichiers/réseau/processus |
| Service extracteur réseau | Ajouterait une surface, une authentification de service et une gestion de files ; inutile pour deux jobs locaux |
| Conteneur préexistant sans réseau, protocole Unix | Possible, mais exige transport partagé, traitement de l'accès entre jobs et adaptation des validateurs à un quatrième service |
| Bubblewrap/namespaces privilégiés | Contraintes de capacités/user namespaces et du profil Docker à valider ; aucun ajout SYS_ADMIN, privileged ou socket Docker retenu |
| Landlock + seccomp par extraction | Retenu : politiques locales sans privilège, aucun transport réseau/montage, processus jetable et preuves testables |

Cette solution impose un noyau avec **Landlock ABI ≥ 3**, Linux x86_64 ou aarch64, et
`libseccomp.so.2`. Le nom Debian ou la seule version de Docker ne garantissent pas ces capacités.
Un noyau/profil Docker qui les bloque fait refuser le démarrage de la nouvelle API ; aucune
mise à niveau noyau ni désactivation de sécurité n'est effectuée automatiquement.

## Flux et éléments de confiance

1. L'API autorise l'utilisateur, conserve l'import et ses contrôles existants, puis acquiert
   son slot de traitement. Elle écrit son temporaire à nom serveur, sans utiliser le nom original
   comme chemin d'exécution. L'admission HTTP avant bufferisation reste hors de ce lot.
2. Le broker ouvre ce fichier régulier sans suivre le lien final (`O_NOFOLLOW`), refuse les
   liens physiques supplémentaires et lit au plus la taille autorisée plus un octet.
3. Le broker lance l'interpréteur avec `-I -S`, un script fixe, environnement réduit à la locale,
   `close_fds=True`, stdin/stdout en pipes, stderr vers `/dev/null`, groupe de processus propre.
   L'emplacement de bibliothèque Python provient de `sysconfig` du parent, jamais du document.
   Ce paramètre permet les venv Python 3.12/3.13 malgré `-S`, sans exécuter leurs fichiers `.pth`.
4. Avant toute entrée non fiable : limites de ressources, `no_new_privs`, désactivation des
   dumps/inspection du worker, règles Landlock, puis chargement seccomp. Les bibliothèques
   nécessaires aux politiques sont chargées avant leur application ; aucun parseur de document
   n'est importé avant cette frontière.
5. Le worker valide l'en-tête, lit le seul blob annoncé, importe le moteur indépendant et
   extrait en mémoire. Aucun fichier documentaire ou temporaire n'est ouvert par le parseur.
6. Le parent draine et borne stdout en continu, valide UTF-8/JSON, le job, les types et limites.
   Il ne traite jamais stdout comme du pickle, une commande ou un chemin. Il rend les pages
   au service existant pour les chunks et la transaction SQL habituels.
7. Erreur, timeout ou sortie non conforme : arrêt/récupération du worker, erreur HTTP contrôlée
   et nettoyage du temporaire par le service d'import. Un crash ne termine pas le parent.

Base de confiance : noyau, runtime conteneur et son profil extérieur, interpréteur/stdlib,
libseccomp, code du broker/runner/politiques, fichiers immuables des bibliothèques. Un attaquant
contrôle les octets PDF/TXT et peut, par hypothèse, obtenir l'exécution native **dans le worker**.
Il ne contrôle pas la commande du broker, les chemins de bibliothèques, les mounts ou la configuration.

## Politiques du noyau

### Fichiers

Landlock traite les droits ABI 3, dont création, écriture, suppression, déplacement et
troncature. Seuls les répertoires du module extracteur, de la bibliothèque Python et des
bibliothèques/fonts nécessaires peuvent être lus. Ils ne sont pas autorisés en écriture.
Ils doivent rester sans secrets et immuables dans l'image de production.

Le stockage `/app/var`, `.env`, HOME, `/tmp`, `/proc`, les configurations SMTP/Restic et le
socket Docker ne figurent pas dans cette allowlist. Ni `/app` entier ni `/etc` entier n'est
autorisé. Le document courant n'est pas ajouté à une allowlist de chemins : seuls ses octets
entrent par le pipe. Les autres documents restent dans le volume auquel le worker n'a pas accès.

Landlock ne cache pas toutes les métadonnées (`stat` notamment) et ne crée pas de chroot.
Les tests prouvent le refus de lecture/écriture, pas la disparition de toute information
sur les chemins. Les fichiers préouverts échappent en partie à une politique de chemins :
c'est pourquoi aucun descripteur applicatif n'est transmis, hors des trois flux dédiés.

### Appels système et réseau

Seccomp refuse par défaut avec EPERM, et autorise uniquement les opérations nécessaires de
lecture, mémoire, horloge, signaux internes et terminaison, sur l'architecture native.
Les appels socket/connect, y compris Unix, sont absents : aucun Internet, DB, réseau Docker,
DNS ou socket Docker. Il n'y a aucun socket réseau hérité à réutiliser.

Fork/clone/exec, ptrace, process_vm, pidfd, kill, namespaces, mount, io_uring, bpf et capacités
ne sont pas autorisés. `fcntl` et `ioctl` sont aussi refusés pour éviter notamment des signaux
asynchrones vers le parent via les pipes. Les sorties autorisées sont les pipes bornés vers
le parent, pas un canal arbitraire vers d'autres processus.

Références primaires : [Landlock, noyau Linux](https://docs.kernel.org/userspace-api/landlock.html),
[API libseccomp](https://github.com/seccomp/libseccomp/blob/main/include/seccomp.h.in).
ABI 3 est exigée pour disposer notamment du contrôle de troncature ; les politiques s'ajoutent
à celles du conteneur et aux permissions existantes. Elles ne peuvent pas assouplir ces dernières.

## Protocole version 1

Entrée binaire : longueur d'en-tête sur 4 octets big endian, JSON UTF-8 de **1 à 1024 octets**,
puis exactement le nombre d'octets annoncé jusqu'à fermeture de stdin.

```json
{"version":1,"job_id":"0123456789abcdef0123456789abcdef","extension":".pdf","size":1234,"max_pages":200,"max_chars":1000000}
```

Champs exacts, pas d'extra, nom original, chemin, identifiant utilisateur, secret ou référence
à un autre document. Les types entiers excluent les booléens. Extension `.pdf`/`.txt` seulement,
mais le moteur vérifie encore signature, vraie ouverture et contenu ; le MIME client est ignoré.

Succès : `{"version":1,"job_id":"…","pages":["Texte page 1","Texte page 2"]}`.
Erreur : mêmes version/job, champ `error` limité à `invalid_document`, `resource_limit`,
`sandbox_unavailable`. Aucun message natif, chemin, stdout/stderr brut ou exception de fournisseur
ne remonte. Un refus d'installation des politiques termine le runner avec code 78.

Le parent rejette doublons JSON, NaN/Infinity, UTF-8 invalide, surrogates isolés, extra-fields,
mauvais job, pages non textuelles, limites dépassées et sortie vide/partielle/non conforme.
L'identifiant opaque est créé par le serveur pour chaque tentative ; le processus est détruit
après chaque document, sans cache partagé de texte ou de résultat.

## Ressources et erreurs

| Ressource | Borne |
|---|---|
| Entrée | 10 Mio maximum, ou limite configurée plus petite |
| En-tête | 1024 octets |
| Sortie brute | 8 Mio, contrôlés pendant la lecture, avant décodage |
| Texte | 1 000 000 caractères maximum, ou limite configurée plus petite |
| Pages | 200 maximum, ou limite configurée plus petite |
| Temps mural | 30 s maximum depuis le lancement, ou délai configuré plus court |
| Temps CPU | RLIMIT_CPU plafonné à 30 s ; le superviseur garde aussi son délai mural |
| Espace d'adressage | RLIMIT_AS ≤ 512 Mio par worker |
| Descripteurs | RLIMIT_NOFILE = 32 |
| Processus/threads | RLIMIT_NPROC = 1 ; fork/clone/exec refusés par seccomp |
| Temporaires/dumps | Aucune écriture de chemin autorisée ; RLIMIT_FSIZE et CORE = 0 |
| Concurrence API | Deux slots partagés extraction/analyse, imposés en production |

Les limites de pages/caractères peuvent être abaissées, pas augmentées au-delà du contrat
dans le mode confiné. Un `MAX_UPLOAD_BYTES` supérieur à 10 Mio ne rend pas le parseur capable
d'accepter davantage : le broker refuse au-delà du plafond, sans troncature silencieuse.

Le budget mémoire est un espace d'adressage, pas un cgroup par job. Deux limites de 512 Mio
restent à dimensionner avec la mémoire de l'API et ses buffers dans les 1536 Mio du conteneur.
Les cgroups Docker, CPU/PIDs/tmpfs et l'arrêt gracieux existants restent en place. Un OOM de
l'ensemble du conteneur ou du noyau ne peut pas être exclu par une simple limite par processus.

Le parent utilise des pipes non bloquants et une échéance commune ; aucune attente illimitée
sur stdout ou `wait`. Il tue le groupe du worker encore actif et fait `wait` avant de rendre
la main. Les erreurs sont 413 (entrée trop volumineuse), 422 (document/sortie/limite) ou 503
(confinement indisponible), sans exposer les détails internes.

L'annulation d'une opération qui échoue ou dépasse le délai récupère le worker. Ce lot
n'ajoute pas d'endpoint d'annulation d'upload : une déconnexion HTTP après admission n'est
pas une annulation immédiate garantie du traitement synchrone, qui reste borné à 30 secondes.

## Intégration, développement et sauvegardes

`EXTRACTION_MODE=sandbox` est le défaut sûr. Au démarrage, une sonde confinée importe le
vrai moteur natif et valide un petit texte ; si elle échoue, l'API ne démarre pas. Le Compose
de production impose explicitement sandbox, 512 Mio, 30 s et deux slots. Les valeurs d'un
env_file ne peuvent pas les remplacer dans cette configuration. Aucun fallback selon l'OS.

Pour Windows hors Docker uniquement : `EXTRACTION_MODE=development` choisit explicitement
l'ancien adaptateur multiprocessing **non confiné**. Il conserve l'analyseur de bureau et
les tests portables ; il n'est jamais une preuve de sécurité ni un mode de production.
Ne pas modifier le `.env` réel automatiquement : l'exemple et le README décrivent ce choix.

`documind_extractor/engine.py` reprend l'extraction existante, désormais depuis des octets.
Le moteur d'analyse classique et le reste de `run_worker(..., 'analyze', ...)` restent intacts.
Fichiers vides, corrompus, réparés, nécessitant un mot de passe, binaires/TXT invalides,
limites de pages/texte et numéros de pages conservent leur traitement métier.

Aucun schéma SQL, migration, montage documentaire, format de sauvegarde ou métadonnée Restic
n'est modifié. Les helpers Sprints 7/8/9 continuent d'attendre trois conteneurs et les mêmes
montages. Arrêt gracieux API/BFF et redémarrage fonctionnent comme avant ; le délai worker
est inférieur aux 150 secondes de grâce. Un hôte qui perdrait ses capacités Landlock pourrait
faire échouer le redémarrage API, ce qui sera signalé ; ne jamais contourner cela en désactivant
le confinement. Le guide Sprint 7 demeure la procédure de reprise des sauvegardes.

## Validation locale et Docker jetable

Tests natifs Linux : `tests/test_extraction_linux.py`. Un Linux dépourvu de politiques fait
échouer ces tests ; ils sont ignorés seulement sur un OS non Linux. Les tests de protocole
portables sont distincts. Les fixtures générales choisissent explicitement le mode development
pour les régressions ; les preuves Linux activent réellement la sandbox.

Le Dockerfile fournit une cible `isolation-tests`, puis une cible finale `production` qui
hérite uniquement de l'application. Les tests et leurs dépendances ne sont pas dans cette
image finale. `.dockerignore` autorise leur COPY ciblé, sans exposer `.env`, `var` ou les PDF.

Lorsque le moteur Docker local est disponible :

```bash
docker compose -f compose.pdf-isolation-test.yaml build proofs
docker compose -f compose.pdf-isolation-test.yaml run --rm --no-deps proofs
```

Cette configuration distincte n'a ni env_file, volume, port publié ni réseau ; caps supprimées,
rootfs read-only, no-new-privileges, ressources bornées et seul tmpfs privé `/tmp`.
Elle ne réutilise pas les volumes ou le projet de production. Ne pas changer ces restrictions
pour rendre les tests verts. La CI exécute aussi ces preuves dans l'image Python 3.13, avant
publication. Aucun push ni run GitHub n'a été lancé dans ce lot.

## Mise à jour contrôlée — procédure non exécutée

1. Faire relire le code/politiques et les preuves ; lever les limites du
   [rapport de validation](sprint-10-pdf-isolation-validation.md). Exiger une CI réussie,
   notamment les preuves dans l'image, et confirmer l'architecture du VPS.
2. Avant toute interruption, l'administratrice vérifie explicitement ABI Landlock ≥ 3,
   libseccomp dans l'image et compatibilité du profil Docker sur le VPS. Le test autonome
   suivant, **après approbation de l'image et de cette action**, ne monte aucune donnée ni secret :

```bash
# BACKEND_IMAGE doit être la référence @sha256 du manifeste CI approuvé, jamais latest.
docker run --rm --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges --memory 512m --cpus 1 --pids-limit 16 \
  --entrypoint python "$BACKEND_IMAGE" -I -S /app/documind_extractor/runner.py \
  512 5 /usr/local/lib/python3.13/site-packages --check
```

   Exiger code 0 et `{"status":"ready"}`. Le chemin de bibliothèque correspond au Dockerfile
   Python 3.13 livré ; le broker l'obtient normalement par sysconfig. Ne pas lire `.env` pour
   ce test, ajouter SYS_ADMIN, utiliser `--privileged`, enlever seccomp ou activer development.
   Un refus impose l'arrêt de la mise à jour et un diagnostic noyau/profil, pas un contournement.
3. Utiliser ensuite le workflow de déploiement **manuel approuvé** du Sprint 6, avec SHA/run
   exacts, `initialize=false` et sans approbation de changement de schéma. Le schéma reste
   `0006` ; une divergence doit être diagnostiquée. Conserver la sauvegarde préalable et les
   contrôles de compatibilité, healthchecks, HTTPS, CSRF et isolation utilisateur existants.
4. Vérifier deux imports fictifs PDF/TXT, une erreur documentaire contrôlée, analyse classique,
   expiration/session et accès intercompte refusé. Aucun document utilisateur réel et aucun
   appel IA nécessaire. Vérifier le prochain cycle de sauvegarde/reprise avant de clore le lot.

Ce guide ne vaut pas autorisation de ces opérations distantes. Aucune commande n'est exécutée
sur le VPS par l'agent. L'ouverture des inscriptions et l'activation IA restent hors périmètre.

## Retour arrière — procédure non exécutée

Conserver l'ancien bundle validé, ses images par digest et la sauvegarde préalable. Aucun
changement de schéma ne résulte de ce lot. Choisir l'ancien SHA/run dans le workflow manuel
approuvé, opération `rollback`, sans initialize ni migration autorisée. Le déployeur vérifie
que l'ancienne application prend en charge la révision courante ; aucun downgrade/restauration
de PostgreSQL ni changement de volumes n'est nécessaire.

Si le démarrage de la nouvelle release échoue, le déployeur existant tente de redémarrer
l'application précédente uniquement si le schéma est compatible. Vérifier son rapport et les
healthchecks avant toute nouvelle tentative. Ne pas inventer `current`, modifier un manifeste
ou un ancien rapport, supprimer un verrou, ni utiliser une procédure de première installation.
En cas d'état ambigu, arrêter et diagnostiquer selon le Sprint 6. Ne jamais utiliser `down -v`.

Revenir à l'ancien binaire réintroduit le risque SEC10-01 : ce retour arrière doit être accepté
explicitement, sous accès privé. Il ne consiste pas à désactiver la sandbox de la nouvelle version.

## Risques résiduels

Le worker partage le noyau et l'UID, pas une VM ; une faille noyau/runtime ou de la politique
reste possible. Le code de confinement lui-même demande revue et maintenance. Les bibliothèques
autorisées doivent rester sans secrets ; un stockage de secrets dans ces chemins violerait
le modèle. Une sortie typée ne garantit ni exactitude documentaire ni innocuité de tout PDF.
Les métadonnées de fichiers et certains canaux auxiliaires ne sont pas entièrement masqués.

Ce lot ne règle ni l'admission HTTP avant réception, ni les logs de sécurité, ni la totalité
des alertes supply chain de l'audit. Les profils Docker, kernels et architectures exacts non
testés doivent être validés avant mise à jour. Aucun engagement de résistance à une saturation
de l'hôte ou à une compromission de l'API/administrateur Docker n'est revendiqué.
