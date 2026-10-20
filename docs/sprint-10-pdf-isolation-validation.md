# Sprint 10 phase B, lot 1 — validation du confinement

> Reprise ultérieure : voir le [rapport de revalidation](sprint-10-pdf-isolation-revalidation.md).
> Docker Desktop est désormais disponible et les preuves dans l'image ont été exécutées.
> Les limitations Docker décrites ci-dessous concernent la première session, conservée
> comme historique. L'administratrice confirme désormais Linux 6.12 et ABI 6 sur le VPS.

Date : 20 octobre 2026, Europe/Paris. Voir [architecture et procédures](sprint-10-pdf-isolation-design.md).
Tous les documents, secrets et comptes des tests sont fictifs. Aucun accès au VPS, push,
déploiement, changement de secrets réels, volume de production, activation d'inscriptions
ou appel IA n'a eu lieu. Aucun PDF d'exploitation réel n'a été utilisé.

## Environnement réellement utilisé

- Windows : Python 3.13.7, venv applicatif existant ; suite portable avec adaptateur explicitement
  `development`, qui n'est pas une preuve de confinement.
- Ubuntu WSL : Python 3.12.3, noyau `6.18.54.1-microsoft-standard-WSL2`, UID 1000,
  **Landlock ABI 7**, libseccomp disponible. Ce système n'est pas le VPS Debian.
- Venv Linux jetable sous `var/pdf-isolation-linux-env/`, indépendant du venv Windows et
  des paquets système ; dépendances installées depuis PyPI avec les contraintes du dépôt.
  Aucun apt/install système Ubuntu, changement du noyau ou de configuration WSL.
- Docker Desktop Linux Engine : endpoint local absent, même après sonde autorisée hors
  restriction. Aucun moteur n'a été démarré ni installé pour contourner cela.

La première sonde WSL Debian a constaté l'absence de Python ; Ubuntu préexistant a ensuite
été utilisé. L'installation Python de test n'a ni consulté les documents utilisateur ni copié
de `.env` privé. Les enfants reçoivent seulement la locale, pas l'environnement de cette session.

## Résultats des séries exécutées

| Série | Résultat | Interprétation |
|---|---|---|
| Non-régression Windows complète | **485 réussis, 27 ignorés**, 268,44 s | Tests Linux ignorés sur Windows, pas validés par cette série |
| Protocole portable final | **32 réussis**, 4,29 s | Inclut UTF-8/surrogate et deux jobs admis avec troisième refusé |
| Suite Linux ciblée étendue | **412 réussis**, 103,75 s | Protocole, confinement, PDF/TXT, moteur, transactions, déploiement et Sprints 7–9 |
| Protocole et preuves Linux finaux | **65 réussis**, 19,37 s | 32 cas de protocole et 33 preuves Linux, dont descripteurs, liens et bibliothèques read-only |
| Compilation Python | Réussie | Nouveaux modules, adaptateur et tests |
| actionlint CI/deploy | Réussi | Aucun workflow GitHub exécuté |
| Diff/format et YAML | Contrôles locaux | Pas un build ou démarrage Docker |

Ces séries se recoupent ; leurs nombres ne doivent pas être additionnés. Les derniers tests
de liens/descripteurs ont été ajoutés après la collecte de la suite Windows complète : son
nombre d'ignorés reflète cette collecte, pas le nombre final de tests Linux. Les séries ciblées
ont été relancées après les durcissements concernés.

Un avertissement existant concerne la dépréciation Starlette/httpx des tests. Le premier
passage WSL signalait aussi l'impossibilité d'écrire le cache pytest partagé Windows ; les
passages Linux finaux utilisent `-p no:cacheprovider`, sans cet avertissement ni changement
des permissions du dépôt.

## Preuves Linux et portée

| Contrôle | Preuve réalisée sans exploitation native |
|---|---|
| Accès à un autre document | Fichier PDF fictif placé hors allowlist, lecture refusée malgré le même UID |
| Secrets API/DB/SMTP/Restic | Fichiers fictifs lisibles par le parent, lecture refusée après Landlock |
| Environnement et FD hérités | Variables fictives absentes ; FD de secret marqué inheritable côté parent fermé dans le processus neuf |
| Internet, PostgreSQL, Docker | Création de sockets AF_INET, AF_INET6 et AF_UNIX refusée ; aucun essai de connexion externe nécessaire |
| `/proc` et accès interprocessus | Ouverture interdite ; ptrace, process_vm_readv et kill de signal 0 refusés par seccomp |
| Signaux indirects | F_SETOWN via fcntl interdit pour empêcher le ciblage du parent à travers un pipe |
| Création de processus | Fork refusé ; aucune commande secondaire exécutée |
| Écriture/temporaire | Écriture sur chemin fictif hors politique refusée ; fichier public autorisé en lecture aussi protégé en écriture |
| Descripteurs | Ouvertures de fichiers publics de bibliothèque bornées sous le hard limit 32 |
| Mémoire | Allocation de 600 Mio refusée sous la limite 512 Mio ; processus parent et sonde suivante disponibles |
| CPU | Boucle inoffensive arrêtée par la limite CPU ; échec worker attendu avant le timeout mural de 5 s du test |
| Délai / blocage | Sleep inoffensif arrêté par échéance courte du parent ; processus récupéré |
| Sortie hostile | Sortie brute dépassant 8 Mio rejetée pendant sa lecture ; worker arrêté et récupéré |
| Crash | Exit 9 simulé ; HTTP 422, API encore saine, temporaire nettoyé et import suivant réussi |
| JSON falsifié | Mauvais job, champs en trop, types incorrects, pages/texte hors limites, doublons et constantes non JSON refusés |
| Liens d'entrée | Broker refuse réellement lien symbolique et hardlink vers un fichier fictif, contenu original inchangé |
| Documents | PDF deux pages et TXT valides ; vides, malformés et chiffrés nécessitant un mot de passe rejetés |
| Isolation métier | Espace de l'autre propriétaire toujours vide après import, succès ou erreur |
| Concurrence | Deux imports bloqués admis ; troisième refusé 503 ; slots libérés et transactions cohérentes ensuite |
| Démarrage | Sonde native sous politique réussie ; indisponibilité injectée fait refuser le startup, sans fallback |

Les sondes système emploient le même `confine()` et le même lanceur borné que le runner ;
leur code de preuve, fourni par le test et non par un PDF, remplace ce que pourrait tenter
un parseur compromis. Le code malveillant n'est pas une fonctionnalité du protocole : aucun
champ d'entrée ne permet de choisir un script, une commande ou ces sondes. Les imports et
crashs HTTP testent aussi le vrai broker/runner/parseur sur les données synthétiques.

Refuser la création d'une socket prouve l'impossibilité d'une connexion vers n'importe quel
hôte via cette famille, sans contacter Internet ou une base réelle. Ce n'est pas un test
de routage du VPS. Les secrets refusés sont exclusivement des marqueurs fictifs temporaires.

## Commandes de validation

Windows, à la racine du dépôt :

```powershell
Remove-Item Env:TEST_DATABASE_URL -ErrorAction SilentlyContinue
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m pytest tests/test_extraction_protocol.py -q
.venv/Scripts/python.exe -m compileall -q documind_extractor backend/services/extraction.py backend/services/worker.py tests/test_extraction_linux.py tests/test_extraction_protocol.py
.\var\tools\actionlint\actionlint.exe -shellcheck= -pyflakes= .github/workflows/ci.yml .github/workflows/deploy.yml
```

Linux natif avec venv de test dédié, base de test temporaire par défaut et aucun
`TEST_DATABASE_URL` de production :

```bash
python -m pytest -p no:cacheprovider tests/test_extraction_linux.py tests/test_extraction_protocol.py -q
python -m pytest -p no:cacheprovider \
  tests/test_extraction_linux.py tests/test_extraction_protocol.py \
  tests/test_documents.py tests/test_engine.py tests/test_transactions.py \
  tests/test_deployment.py tests/test_production_backups.py tests/test_restic_upload.py \
  tests/test_monitoring.py tests/test_retention.py -q
```

Les commandes ont été exécutées via `wsl.exe -d Ubuntu --cd <dépôt sous /mnt/c> --exec
var/pdf-isolation-linux-env/bin/python ...`. Le venv n'avait pas de pip système disponible :
création `venv` sans pip, puis utilisation du runner pip déjà présent pour installer dans
ce seul venv avec `--isolated --index-url https://pypi.org/simple -c requirements.lock '.[test]'`.
Cette préparation de test n'est pas une nouvelle dépendance du runtime de production.

## Docker et CI : préparés, non exécutés ici

Le Dockerfile ajoute libseccomp2 et le module extracteur, une cible de preuve jetable et une
image finale de production sans tests. Le Compose principal conserve ses services, volumes
et réseaux, impose le mode sandbox et les ressources existantes/plafonnées. Aucune option
privileged, SYS_ADMIN, seccomp=unconfined ou socket Docker n'a été ajoutée.

`compose.pdf-isolation-test.yaml` permet un build/run local sans réseau, volume, secret ou
port. La CI Ubuntu 24.04 exige les tests natifs puis ceux dans l'image Python 3.13 restreinte,
avant ses autres validations et la publication. Cette étape n'a pas été exécutée sur GitHub.

Une sonde Docker locale a échoué avec endpoint
`npipe:////./pipe/dockerDesktopLinuxEngine` absent. Par conséquent, **construction des images,
preuve sous le profil Docker exact et extraction Python 3.13 en conteneur ne sont pas validées
dans cette session**. Les preuves WSL Python 3.12 ne les remplacent pas.

## Fichiers et compatibilité

- `documind_extractor/` : moteur PDF/TXT réutilisé, contrat strict, politiques noyau et runner.
- `backend/services/extraction.py` : broker sécurisé, limite de flux et récupération ;
  `worker.py` sélectionne ce chemin pour extract, conserve analyze et l'adaptateur development.
- `backend/config.py`, `backend/main.py` : mode explicite et contrôle de disponibilité au startup.
- Dockerfile, `.dockerignore`, Compose local/production et Compose de tests : intégration sans
  nouveau service de production ; aucune modification de montages ou schéma SQL.
- `pyproject.toml` : packaging du seul nouveau module ; dépendances Python métier inchangées.
- Exemples env et README : choix development explicite hors Docker, documentation du refus sûr.
- CI et tests : preuves natives/conteneur et non-régressions, sans nouvel appel fournisseur.

Les modifications antérieures de README, `tools/deploy_production.py` et
`tests/test_deployment.py`, et les livraisons Sprints 7–10 phase A déjà présentes, sont
conservées. Le déployeur, les outils de sauvegarde/rétention et leurs unités n'ont pas reçu
de correctif dans ce lot. Le répertoire `build/` produit par le packaging de test est un
artefact local, pas une livraison applicative.

## Limites et conditions avant production

La frontière protège lecture/écriture et syscalls, pas une VM, le noyau ou tout canal auxiliaire.
L'UID reste partagé et les métadonnées ne sont pas entièrement invisibles. Les chemins publics
autorisés doivent rester immuables et sans secrets. Un OOM global ou un incident du conteneur
n'est pas rendu impossible par RLIMIT_AS. La réception HTTP avant authentification reste
SEC10-02 ; aucun changement d'authentification n'a été effectué pour la contourner.

Aucun test Docker, arm64, PostgreSQL/pgvector réel, profil de sécurité du VPS ou permission
effective de ses volumes n'a été effectué ici. Les tests d'exploitation emploient des commandes
Docker/Restic simulées ; aucune sauvegarde B2, restauration ni purge n'est déclenchée.
Le lot ne ferme pas les autres constats de l'audit et ne justifie pas une ouverture publique.

Avant déploiement : revue du code de politique, CI native **et conteneur** réussie, validation
de l'image approuvée sur le noyau/profil cible sans données ni secrets, sauvegarde contrôlée
et rollback compatible, puis approbation manuelle propre au déploiement. Si le noyau ne
supporte pas Landlock ABI 3 ou si le profil refuse les politiques, conserver l'ancienne
production privée et diagnostiquer. Ne pas sélectionner development comme remède.
