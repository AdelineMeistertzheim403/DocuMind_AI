# Sprint 7 — sauvegarde quotidienne de production

## Périmètre et état confirmé

La restauration indépendante du snapshot B2 `51ac3259` a été validée **par l’administratrice** :
PostgreSQL 17, schéma `0006`, deux utilisateurs, deux documents, SHA-256 conformes et deux PDF
extraits ; conteneur et volume de test supprimés. Ces opérations n’ont pas été répétées par l’agent.
Le code livré ne réalise aucune installation distante, modification de secrets ou publication.

Le script `tools/backup_production.py` s’installe séparément dans `/srv/documind-ai/ops/`.
Il lit la release via `/srv/documind-ai/current`, réutilise **son** `backup_local.py`, son manifeste,
son `images.env` et son Compose. Le Compose et `backup_local.py` existants sont conservés.
Il ne dépend pas de modules Python tiers sur le VPS : Python **3.11+**, Docker/Compose et Restic
existants suffisent. Restic doit supporter `backup --json`, son résumé `snapshot_id` et
`snapshots --json` ; vérifier la version installée avant activation.

## Déroulement et garanties

1. Prendre `deployment.lock` en exclusif et sans attente, comme le déployeur. Un conflit donne
   une erreur non nulle, sans toucher aux services. Le verrou est gardé jusqu’à la confirmation B2.
2. Résoudre `current` sous ce verrou : lien valide directement dans `releases/`, fichiers complets,
   pins/digests concordants, rapport de déploiement réussi, trois services du seul projet
   `documind-prod`. Vérifier images, montages, santé et schéma réel compatible. Le digest PostgreSQL
   conservé lors d’une reprise est pris dans le rapport actif, s’il y figure.
3. Lire la configuration Restic privée et ouvrir le dépôt **existant** via `restic cat config`.
   Aucun `init` ni `unlock` automatique. Vérifier au moins 8 GiB disponibles.
4. Écrire un marqueur privé `var/backup-maintenance.json`, puis arrêter **uniquement `api web`**
   avec un délai gracieux de 150 s. Vérifier l’espace pour 125 % de la taille estimée DB/documents
   plus 8 GiB. Réutiliser la sauvegarde cohérente existante, limitée à 30 min pour cette tâche.
5. Même si l’arrêt ou la sauvegarde échoue, tenter le redémarrage dans `finally` :
   `up -d --no-deps --no-recreate --pull never --wait --wait-timeout 180 api web`.
   Vérifier les trois services healthy et **HTTPS `/bff/health`** sans redirection, avec validation
   TLS. Attente limitée pour les 404/502/503/504 transitoires de Traefik. Retirer le marqueur
   uniquement après rétablissement vérifié. Aucun changement de configuration appliqué aux
   conteneurs existants, aucun démarrage de dépendance PostgreSQL.
6. Après rétablissement, transférer le répertoire complet dont les empreintes ont été vérifiées
   vers Restic, tagué `documind-ai` et avec un identifiant de tâche unique. Le code contrôle déjà
   les empreintes avant le rétablissement ; l’envoi suit le rétablissement vérifié.
   Un timeout de 2 h borne la commande de transfert.
7. Exiger code zéro et résumé JSON unique en fin de sortie. Restic **0.14.0** émet un
   `snapshot_id` abrégé à **8 caractères** ; les versions émettant 64 caractères sont aussi prises
   en charge. Utiliser cette référence uniquement pour `restic snapshots --json <référence>`.
   Exiger exactement un résultat, son identifiant complet valide de 64 caractères concordant
   avec la référence, les **deux tags exacts** (ordre indifférent) et le chemin de source exact.
   Seul cet identifiant complet confirmé est enregistré. Plusieurs résultats pour un préfixe,
   un résumé multiple/non final, une sortie JSON ambiguë ou un dry-run sont refusés.
   Un code Restic 3 (snapshot incomplet) reste un **échec**, même si un snapshot existe.

Le rapport JSON final dans journald contient statut, phase, SHA Git, chemin local, tentative de
redémarrage et identifiant confirmé. Aucun stdout/stderr brut Docker/Restic, secret, document ou
contenu du fichier de configuration n’est envoyé aux journaux. L’application est déjà rétablie
pendant l’envoi B2 ; ses sessions et clés BYOK en RAM doivent être reconnectées après l’arrêt.

Le programme ne lance jamais `down`, ne redémarre pas PostgreSQL, ne modifie aucun volume et ne
supprime aucune archive ou snapshot. Seul le marqueur de maintenance est supprimé après reprise.
Les snapshots Restic sont chiffrés ; les archives locales restent **en clair**, dans un répertoire
privé mode 0700 et avec des fichiers privés. Prévoir la surveillance du disque : aucune rotation
locale automatique n’est activée non plus.

## Installation manuelle préparée, non exécutée

Les unités utilisent `debian`, `/home/debian` et le groupe `docker`. Vérifier que ce compte a
l’accès Docker, peut lire `.env.production` et les fichiers de la release active, et peut écrire
dans `/srv/documind-ai/var/` et ouvrir `deployment.lock`. Ne pas modifier les droits d’autres
applications ou lancer de `chown` récursif. Le compte membre de `docker` dispose de privilèges
élevés sur le VPS : réserver son accès aux administrateurs.

L’installation de la sauvegarde **ne nécessite aucun nouveau déploiement applicatif**, changement
d’image ou migration : le script séparé réutilise les helpers déjà présents dans `current`.
Les futurs déploiements doivent conserver le contrôle du marqueur de maintenance du déployeur
Sprint 7. Ne pas utiliser un ancien déployeur/rollback si une sauvegarde interrompue a laissé
`var/backup-maintenance.json` ; rétablir d’abord l’application avec `--resume`. Le verrou commun
existant protège les exécutions ordinaires ; le marqueur protège l’intervalle de reprise après
interruption. Cette précaution d’exploitation n’impose pas de redéployer l’application pour
installer les unités systemd.

Transférer manuellement les fichiers revus dans un répertoire de préparation privé, par exemple
`/home/debian/documind-backup-sprint7/`, avec l’arborescence `tools/` et `ops/systemd/` conservée.
Utiliser votre accès SSH habituel avec clé hôte vérifiée. Les commandes suivantes s’exécutent
**sur le VPS**, après ce transfert et revue, sans exécuter un déploiement applicatif :

```bash
python3 --version
restic version
docker compose version
id debian
sudo -u debian test -r /srv/documind-ai/.env.production
sudo -u debian test -r /home/debian/.config/restic/documind.env
sudo -u debian test -w /srv/documind-ai
readlink -f /srv/documind-ai/current

SOURCE_DIR=/home/debian/documind-backup-sprint7
sudo install -d -o root -g root -m 0755 /srv/documind-ai/ops
sudo install -o root -g root -m 0644 \
  "$SOURCE_DIR/tools/backup_production.py" /srv/documind-ai/ops/backup_production.py
sudo install -d -o debian -g debian -m 0700 /home/debian/.cache/restic
sudo install -o root -g root -m 0644 \
  "$SOURCE_DIR/ops/systemd/documind-backup.service" /etc/systemd/system/documind-backup.service
sudo install -o root -g root -m 0644 \
  "$SOURCE_DIR/ops/systemd/documind-backup.timer" /etc/systemd/system/documind-backup.timer
sudo install -o root -g root -m 0644 \
  "$SOURCE_DIR/ops/systemd/documind-backup-alert.service" /etc/systemd/system/documind-backup-alert.service
sudo systemctl daemon-reload
sudo systemd-analyze verify /etc/systemd/system/documind-backup.service \
  /etc/systemd/system/documind-backup.timer /etc/systemd/system/documind-backup-alert.service
systemd-analyze calendar '*-*-* 03:00:00 Europe/Paris'
```

Arrêter en cas de prérequis manquant. Ne pas initialiser un nouveau dépôt B2 pour résoudre
une erreur d’accès au dépôt existant. Les vérifications système/systemd doivent être effectuées
sur Debian ; elles n’ont pas été exécutées sur le VPS depuis cette session.

## Configuration des secrets, uniquement sur le VPS

Conserver `/home/debian/.config/restic/documind.env`, mode **0600**, lisible par `debian`, et
son répertoire parent privé. Le fichier de mot de passe existant
`/home/debian/.config/restic/password` reste en place : ne modifier aucun secret pour installer
ce correctif. Ne pas imprimer ces fichiers, ni les ajouter à GitHub ou au dépôt.
Le script lit les valeurs littérales ; il ne source pas le fichier dans un shell. Format accepté :

```dotenv
# Valeurs existantes à conserver ; ceci est un exemple de structure sans identifiants.
export RESTIC_REPOSITORY='adresse du dépôt Restic B2 existant'
export RESTIC_PASSWORD_FILE=/home/debian/.config/restic/password
# Selon votre méthode existante :
# export B2_ACCOUNT_ID='identifiant existant'
# export B2_ACCOUNT_KEY='clé existante'
# OU AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION / AWS_REGION pour S3 B2.
```

Les déclarations littérales `export NOM=valeur` et `NOM=valeur` sont acceptées, y compris
dans le même fichier. Utiliser des quotes pour espaces et `#`. Une seule valeur est acceptée
par déclaration ; les doublons sont refusés. Le lecteur n’exécute aucun shell. Les substitutions,
variables à développer (`$…`), accents graves, concaténations de tokens, commandes, redirections,
clés inconnues et options de désactivation TLS sont refusés. Le dépôt doit utiliser `b2:` ou
`s3:https://` ; un endpoint HTTP est refusé. Une erreur est signalée avant arrêt de l’application,
sans valeur sensible dans les journaux. Ne pas remplacer la configuration opérationnelle par
les textes d’exemple.

`RESTIC_PASSWORD_FILE` doit être absolu, sans traversée `..`, dans le répertoire autorisé du
fichier de configuration (`/home/debian/.config/restic/` en production). Le fichier doit être
régulier, non symlink et privé (0600 ou 0400 recommandés, aucun droit groupe/autres). Les chemins
passant par un répertoire symlink sont refusés aussi. Python vérifie uniquement les métadonnées :
**seul Restic lit le mot de passe**. `ProtectHome=read-only` laisse lire les deux fichiers privés
au service ; aucune modification des unités ou du fichier de mot de passe n’est nécessaire.

`RESTIC_PASSWORD` reste accepté comme alternative littérale si nécessaire, mais il ne doit
jamais coexister avec `RESTIC_PASSWORD_FILE`, même si l’une des valeurs est vide. Les seules
clés autorisées restent les deux méthodes de mot de passe, `RESTIC_REPOSITORY` et les variables
B2/AWS indiquées. Aucune méthode `RESTIC_PASSWORD_COMMAND` n’est autorisée.
Les secrets sont transmis dans l’environnement **des seuls processus Restic**, jamais dans
les arguments, les conteneurs applicatifs ou l’environnement du hook d’alerte.

## Validation puis activation à 03 h 00

Une sauvegarde de validation provoque une interruption API/BFF : choisir une fenêtre approuvée.
Ne pas lancer directement la commande Python en parallèle du service. Pour le premier essai :

```bash
sudo systemctl start documind-backup.service
sudo systemctl status documind-backup.service --no-pager
sudo journalctl -u documind-backup.service -n 50 --no-pager
curl --fail --show-error https://documind.adelinemeistertzheim.fr/bff/health
```

Exiger `status=success`, `phase=complete`, `restart_healthy=true` et un `snapshot_id` complet
dans le rapport. Archiver cet ID hors journald pour les exercices de restauration. Le succès
prouve la confirmation de l’écriture, pas une relecture exhaustive de tous les blocs B2.
Planifier séparément des restaurations indépendantes comme celle du snapshot `51ac3259`.

Après succès et validation de l’horaire :

```bash
sudo systemctl enable --now documind-backup.timer
systemctl list-timers --all documind-backup.timer
sudo journalctl -u documind-backup.service -u documind-backup-alert.service --since today
```

Le timer utilise explicitement **Europe/Paris**, pas le fuseau du VPS, et suit l’heure d’été/hiver.
Les identifiants de tâches et dates JSON sont en UTC. `Persistent=true` rattrape un horaire
manqué au prochain démarrage/à l’activation : une sauvegarde peut donc commencer hors de 03 h.
Tenir compte de cette interruption lors de l’activation. Aucun autre timer/service n’est modifié.

## Alerte configurable sans fournisseur imposé

Sans configuration, `OnFailure` crée un événement explicite dans `documind-backup-alert.service`.
Pour une notification externe, installer **vous-même** un exécutable local revu, dont le fichier
n’est pas modifiable par le groupe ou les autres utilisateurs. Il reçoit un seul argument
`documind-backup-failed`, sans secret Restic. L’exécutable doit gérer ses propres secrets en
dehors du dépôt et retourner un code non nul s’il échoue. Son stdout/stderr est capturé.

Créer avec `sudoedit /etc/documind-backup-alert.conf` :

```ini
DOCUMIND_BACKUP_ALERT_HOOK=/chemin/absolu/vers/votre-hook
```

Ce chemin est à remplacer par un exécutable réellement installé. Le fichier de configuration
est réservé à cet usage ; ne pas y mettre de clés B2. Tester le hook après revue :

```bash
sudo systemctl start documind-backup-alert.service
sudo journalctl -u documind-backup-alert.service -n 20 --no-pager
```

## Échec, reprise et désactivation

- Échec Restic avant arrêt : l’application est laissée en place. Examiner la phase, vérifier
  réseau, droits B2, mot de passe et accès au dépôt existant sans imprimer les secrets.
- Échec de dump/archive : le `finally` redémarre API/BFF ; aucun transfert n’est crédité.
  Les fichiers incomplets sont conservés pour diagnostic et jamais utilisés comme succès.
- Échec de transfert : API/BFF sont déjà rétablis. Les archives locales restent en place.
  Corriger l’accès B2 puis relancer le service dans une fenêtre approuvée : il produira une
  nouvelle sauvegarde cohérente. Aucun snapshot existant n’est supprimé, même incomplet.
- Échec de redémarrage/HTTPS : marqueur conservé, code non nul et `ExecStopPost --resume`
  tente la reprise sous le même verrou. Un échec principal reste un échec même si le secours
  réussit ; vérifier santé et journaux avant de réinitialiser l’état d’échec.
- SIGTERM/SIGINT : déclenchement du `finally`, puis secours systemd si nécessaire. Une panne
  machine ou SIGKILL ne peut pas garantir une reprise immédiate : après retour du VPS, vérifier
  le marqueur et lancer la reprise avant tout déploiement. Ne pas employer `kill -9` pour arrêter
  cette tâche ; le service désactive l’escalade automatique SIGKILL.
- Verrou déjà détenu : aucun arrêt applicatif ; attendre la fin du déploiement/de la sauvegarde,
  puis relancer. Ne jamais supprimer le fichier `deployment.lock` pour « libérer » un flock.
- `current` absent, modifié ou incohérent : refus. Examiner le déploiement actif et ses preuves,
  sans inventer de pointeur ni modifier les anciens rapports.

Reprise manuelle après diagnostic :

```bash
sudo systemctl disable --now documind-backup.timer
# Si une tâche tourne encore, attendre sa fin ou demander un arrêt gracieux :
sudo systemctl stop documind-backup.service
sudo -u debian /usr/bin/python3 /srv/documind-ai/ops/backup_production.py --resume
curl --fail --show-error https://documind.adelinemeistertzheim.fr/bff/health
sudo journalctl -u documind-backup.service -n 50 --no-pager
```

`--resume` ne fait rien sans marqueur. Avec marqueur, il exige la même release active, les images,
montages et schéma attendus et PostgreSQL healthy, puis ne redémarre qu’API/BFF. Si la reprise
échoue encore, laisser le timer désactivé, contrôler les logs **ciblés** API/BFF via les options
Compose de `current`, les healthchecks et Traefik. Ne pas exécuter `up db`, une migration, un
reset ou une restauration dans les volumes de production pour résoudre une panne de sauvegarde.
Ne pas supprimer le marqueur avant d’avoir rétabli la release prévue.

Après résolution :

```bash
sudo systemctl reset-failed documind-backup.service
sudo systemctl start documind-backup.service
# Réactiver le timer uniquement après succès de cette validation.
sudo systemctl enable --now documind-backup.timer
```

Pour une désactivation durable, conserver seulement `disable --now documind-backup.timer`,
arrêter gracieusement un service encore actif si nécessaire et vérifier HTTPS. Cela ne supprime
ni unités, ni archives, ni snapshots, ni volumes. Ne pas utiliser une commande de suppression
Docker ou de purge Restic pour désactiver la planification.

## Conservation et récupération des données

La proposition **7 quotidiens, 4 hebdomadaires et 6 mensuels n’est pas approuvée ni activée**.
Aucun `forget`, `prune`, `unlock`, nettoyage local ou suppression de snapshot n’est programmé.
La dernière sauvegarde valide reste conservée. Une future rétention exigera validation explicite,
sélection des seuls tags DocuMind, simulation, vérification d’un snapshot restaurable et garde
contre suppression de la dernière copie valide. Ne pas purger d’éventuels autres jeux de sauvegarde
dans le même dépôt Restic.

En cas de perte réelle de données, choisir un snapshot **confirmé**, restaurer ses archives dans
un répertoire privé neuf, vérifier les SHA-256 du manifeste, puis restaurer PostgreSQL 17 et les
PDF dans un environnement indépendant. Confirmer schéma, comptes, documents et extraction comme
pour `51ac3259`. Une restauration en production exige une intervention séparée approuvée, une
sauvegarde préalable de l’état disponible et une fenêtre d’arrêt ; elle n’est jamais automatique.
La restauration nécessite l’accès autorisé à la configuration Restic privée du VPS. Cette
automatisation ne copie pas ce fichier dans les archives, le dépôt Git ou les journaux et ne
crée aucun autre stockage de secrets.

## Tests et références

```bash
python -m pytest tests/test_production_backups.py tests/test_deployment.py tests/test_https_probes.py -q
python -m pytest tests/test_restic_upload.py -q
python -m compileall -q tools/backup_production.py tools/deploy_production.py
```

Voir [validation Sprint 7](validation-sprint-7.md). Les commandes Docker/Restic et les erreurs
sont simulées dans les tests ; aucun appel OpenAI, dépôt B2 ou VPS n’est utilisé.
Références officielles : [JSON et codes de sortie Restic](https://restic.readthedocs.io/en/stable/075_scripting.html),
[timers systemd](https://www.freedesktop.org/software/systemd/man/latest/systemd.timer.html).
Le format abrégé de Restic 0.14.0 est vérifié dans son code versionné :
[JSONProgress.Finish](https://github.com/restic/restic/blob/v0.14.0/internal/ui/backup/json.go#L168)
appelle [ID.Str](https://github.com/restic/restic/blob/v0.14.0/internal/restic/id.go#L55), qui conserve quatre octets.
