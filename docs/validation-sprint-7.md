# Validation Sprint 7 — automatisation des sauvegardes

## Correctif de confirmation Restic 0.14.0

Diagnostic précis : `JSONProgress.Finish` dans le code officiel de Restic 0.14.0 utilise
`snapshotID.Str()`, soit quatre octets représentés par **8 caractères hexadécimaux** dans le
résumé `backup --json`. Le contrôle précédent exigeait 64 caractères avant toute interrogation
de confirmation ; il rejetait donc un transfert réussi avant `snapshots --json`.

Le résumé peut maintenant fournir exactement 8 ou 64 caractères. La confirmation exige un
seul snapshot, un ID complet valide de 64 caractères correspondant à cette référence, les
deux tags exacts et le chemin exact. Un ID abrégé n’est jamais enregistré comme succès.
Les codes non nuls (notamment 3), sorties erronées, dry-runs, doublons de clés JSON/résumés,
ambiguïtés de préfixes, tags incorrects/supplémentaires et chemins différents restent refusés.

**236 tests ciblés passent** :

```text
python -m pytest tests/test_restic_upload.py tests/test_production_backups.py tests/test_deployment.py tests/test_https_probes.py -q
```

Le nouveau `tests/test_restic_upload.py` reconstruit le format JSON à partir du code versionné
0.14.0, puis utilise l’ID `3e6df673348bbc1de1fdbb8937854a2e65ef53d6248510356e30a85826faabb1`,
les tags et le chemin communiqués par l’administratrice. Aucune sortie réelle manquante n’a
été inventée comme preuve d’exécution : les compteurs du résumé sont des données de test et
les commandes sont simulées. Les versions 0.14.0 / Python 3.11.2 / Compose 2.35.1 et le succès
de `restic check` sont des constats fournis du VPS, pas des validations distantes de l’agent.

Compilation Python et erreurs d’espaces du diff : vérifiées. Avertissement Starlette/httpx
préexistant, sans échec. Aucun accès B2/VPS, modification de snapshot, restauration, init,
activation de timer ou push. Compose et unités systemd restent inchangés pour ce correctif.
Le code Restic consulté est référencé dans le guide Sprint 7 ; les anciens bilans suivent.

## Correctif de compatibilité avec la configuration Restic existante

Le lecteur accepte désormais `export NOM=valeur` et `NOM=valeur`, avec liste stricte des clés,
sans appel à un shell. `RESTIC_PASSWORD_FILE=/home/debian/.config/restic/password` est pris
en charge avec les variables B2 existantes. Le fichier de mot de passe est contrôlé par ses
métadonnées uniquement : régulier, privé, lisible par son propriétaire, non symlink et dans
le répertoire autorisé de la configuration. Les chemins relatifs, `..` et parents symlinks
sont refusés. Les deux méthodes de mot de passe ne peuvent pas coexister.

Les substitutions, commandes, doublons, concaténations ambiguës, clés inconnues et tentatives
de désactivation TLS sont refusés avant arrêt des services. Les secrets ne figurent ni dans
les arguments Restic ni dans les rapports. Les permissions POSIX sont testées par simulation
aussi sur Windows, avec acceptation 0400/0600 et refus des droits groupe/autres ou sans lecture.

**194 tests ciblés passent** : sauvegardes, déploiement et sondes HTTPS. La sauvegarde complète
avec le véritable lecteur de configuration export/PASSWORD_FILE est simulée jusqu’à la
confirmation du snapshot, sans lecture Python du mot de passe et sans accès B2.
Compilation Python, aide CLI, diff Git et actionlint sont vérifiés. L’avertissement
Starlette/httpx préexistant reste présent. Aucun test Debian/systemd réel n’est revendiqué.

Les chemins `/srv/documind-ai/current`, les volumes et leurs destinations de production sont
conservés et couverts par les tests existants. Les unités systemd appellent uniquement le
script séparé ; la lecture de la release active fonctionne sans `deploy_production.py` dans
le bundle de test. **Aucun nouveau déploiement applicatif n’est requis pour installer le script.**
Le contrôle de marqueur reste à respecter lors des futurs déploiements/rollbacks.
Documentation mise à jour ; aucune modification de secret, de configuration systemd distante,
de production, aucun push ni activation de timer n’a été effectuée.

Les résultats ci-dessous conservent le bilan initial avant ce correctif.

Livraison préparée localement le **20 octobre 2026**, sans connexion au VPS, appel B2, push,
installation, activation de timer ou modification de données de production.

## Fichiers livrés

- `tools/backup_production.py` : orchestration séparée qui lit la release active, réutilise son
  `backup_local.py`, verrouille les déploiements, sauvegarde, rétablit API/BFF, puis confirme
  le snapshot Restic par résumé JSON et relecture de ses métadonnées.
- `tools/deploy_production.py` : refus supplémentaire si une maintenance de sauvegarde est en
  attente ; le verrou existant reste conservé. Aucune modification du Compose ou de `backup_local.py`.
- `ops/systemd/documind-backup.service`, `.timer` et `documind-backup-alert.service` : planification
  quotidienne Europe/Paris, secours `ExecStopPost`, OnFailure et hook local configurable.
- `tests/test_production_backups.py`, test de conflit ajouté à `tests/test_deployment.py`.
- Guide installation/validation/désactivation/récupération `docs/sprint-7-backups.md` et lien README.

## Vérifications locales

**154 tests ciblés passent** :

```text
python -m pytest tests/test_production_backups.py tests/test_deployment.py tests/test_https_probes.py -q
```

Ils couvrent succès avec snapshot confirmé, véritables branches d’échec `pg_dump` et archive du
helper existant, échec Restic ou ID différent, redémarrage après erreur/arrêt partiel, santé Docker
et HTTPS, verrou détenu, reprise de maintenance, changement de release, `current` absent ou
incohérent, pins/images/montages/projets incorrects, configuration Restic et sorties sans secrets,
délai de sauvegarde, commande de reprise sans dépendances/recréation/pull, absence de rétention,
horaire systemd et conflit avec le déployeur. Les opérations Docker/Restic/HTTPS sont simulées.

Compilation Python des fichiers concernés et aide CLI : vérifiées. YAML Compose et les workflows
restent couverts par les tests de déploiement ; actionlint vérifie les workflows existants.
Le diff Git est vérifié pour les erreurs d’espaces. Un avertissement Starlette/httpx préexistant
reste présent. Les suites métier backend/BFF/PostgreSQL n’ont pas été rejouées pour cette
orchestration indépendante. Aucun appel OpenAI réel n’est lancé.

Les unités systemd sont contrôlées statiquement par les tests. **systemd-analyze verify**, la
résolution réelle du calendrier, les permissions Debian, les versions Docker/Restic et les
sandbox systemd doivent être validés sur le VPS par l’administratrice avant activation ;
ce runtime Windows ne permet pas de déclarer ces vérifications Debian effectuées.

## Limites et contrôles avant activation

La restauration du snapshot `51ac3259` et ses résultats sont les constats de l’administratrice,
pas un test rejoué ici. La confirmation des métadonnées d’un nouveau snapshot ne remplace pas
des exercices de restauration indépendants. Les identifiants B2 et le mot de passe Restic doivent
rester uniquement dans le fichier VPS privé prévu, avec un dispositif de récupération sûr.

Un SIGKILL, crash machine ou indisponibilité Docker ne permet pas de garantir un redémarrage
immédiat. Le marqueur, le `finally`, le secours systemd et `--resume` permettent la reprise
vérifiée ; le timer doit rester désactivé tant qu’un incident de reprise n’est pas résolu.
Les anciens déployeurs sans le contrôle de marqueur ne doivent pas être utilisés pendant cet état.

Aucune purge n’est livrée ou activée. La politique 7 quotidiens / 4 hebdomadaires / 6 mensuels
reste une proposition non validée. Toutes les archives locales et tous les snapshots restent
conservés : surveiller capacité disque et stockage B2. Les journaux n’exposent pas les sorties
brutes d’outils ; diagnostiquer un accès B2 manuellement sans publier les identifiants.
