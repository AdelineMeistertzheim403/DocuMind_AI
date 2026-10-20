# Validation Sprint 8 — surveillance

Travail local préparé le **20 octobre 2026**. Aucun accès VPS/B2/Gmail réel, interruption,
installation, activation de timer, modification de secrets, push ou déploiement effectué.

## Livraison

- `tools/monitor_production.py` : lecteurs `statvfs`, métadonnées systemd et snapshots Restic,
  validation temporelle/identité, maintenance, verrou propre, transitions et état atomique privé.
- `tools/gmail_monitor_alert.py` : interface structurée indépendante, modèles français,
  mêmes six clés Gmail confirmées, STARTTLS avec validation TLS, aucun contenu libre dans les mails.
- `ops/systemd/documind-monitor.service` et `.timer` : 08 h Europe/Paris, compte debian,
  sans capacité, socket Docker masqué, écritures limitées à l’état/cache privé.
- `tests/test_monitoring.py`, guide `docs/sprint-8-monitoring.md`, lien README.

Le hook Gmail historique, les unités Sprint 7, le Compose et Traefik ne sont pas modifiés.
Les modifications des sprints précédents déjà présentes dans le workspace sont conservées.

## Tests exécutés

```text
python -m pytest tests/test_monitoring.py tests/test_restic_upload.py tests/test_production_backups.py tests/test_deployment.py tests/test_https_probes.py -q
295 passed
```

Les **59 nouveaux cas de surveillance** couvrent : seuils exacts 20/10/8 Gio, `f_bavail`,
déduplication d’un même système de fichiers, transitions/retour normal, rappels critiques,
non-répétition, envoi SMTP échoué puis réessayé, récupération échouée puis réessayée, métadonnées
de snapshots absentes/anciennes/invalides/fraîches/futures, vieux snapshots manuels, B2 inaccessible,
timer désactivé/absent/inactif/sans prochaine date/cohérence Paris, résultat de service,
sauvegarde active/trop longue, occupation prolongée, maintenance, verrou détenu, écriture atomique
échouée, recul d’horloge et données temporelles non finies. Ils vérifient aussi l’absence de données
sensibles dans les sorties, la connexion STARTTLS avant login et les interfaces CLI de test/legacy.

Les commandes Docker/Restic/SMTP/systemd et `statvfs` sont simulées ; aucune commande de
modification de production n’est exécutée. Le test d’écriture atomique utilise seulement un
répertoire temporaire local. Les 236 autres tests confirment la non-régression d’exploitation.

Compilation Python des nouveaux fichiers et aide CLI des deux scripts : réussies.
Actionlint valide les workflows existants, sans modification CI/CD. Diff Git sans erreur
d’espaces. Avertissement Starlette/httpx préexistant, sans échec de test.

## Validation manuelle restante avant activation

Le runtime Windows ne valide pas les unités contre un gestionnaire systemd Debian réel.
`systemd-analyze verify`, calendrier, accès non privilégié aux chemins disque/DBus, permissions
des fichiers privés et sandbox restent à vérifier sur le VPS suivant le guide. Un email de test
réel via `gmail_monitor_alert.py --test` doit être déclenché uniquement par l’administratrice.

La présence du hook Gmail et des six variables STARTTLS est confirmée par l’administratrice.
Son code n’a pas été lu sur le VPS : une nouvelle interface utilise la même configuration sans
remplacer le hook ni ses arguments. Les snapshots `51ac3259` et `9c1cfddc…` sont des constats
fournis, pas des restaurations ou requêtes exécutées par l’agent.

La surveillance ne prouve pas une restauration complète ni le code historique de chaque backup
Restic 0.14 à partir de ses seules métadonnées. Le contrôle Sprint 7 et les exercices indépendants
restent complémentaires. Les alertes utilisent le pire niveau si les deux chemins sont sur des
partitions différentes ; aucune identité de périphérique/chemin privé n’est divulguée.

L’anti-spam est fondé sur l’acceptation SMTP suivie d’une persistance atomique. Une panne entre
ces deux étapes peut entraîner un doublon au prochain passage ; une erreur d’envoi n’est jamais
enregistrée comme livrée. Un moniteur dont l’état ou les permissions sont invalides retourne un
code non nul et un journal sans secret ; son état doit être réparé après diagnostic manuel.

Aucune purge, suppression d’archive/snapshot, mutation de volume, commande Docker, arrêt d’API/BFF/DB
ou modification de planification de sauvegarde n’est introduite. Seuls les fichiers temporaires
créés pour l’état du moniteur sont retirés après leur propre écriture.
