# Validation Sprint 9 — conservation en simulation

Validation locale Windows, le 20 octobre 2026. Aucun accès VPS/B2/SMTP, push, déploiement,
installation systemd, activation de timer, suppression d'archive ou modification de production.
Les opérations Restic et les notifications sont simulées dans les tests.

## Fichiers de cette livraison

- `tools/retention_production.py` : inventaires en lecture seule, preuves SHA-256 locales et
  distantes, politiques locale/7-4-6, protections, verrous, rapports privés et refus de l'exécution réelle.
- `tools/gmail_monitor_alert.py` : ajout de modèles de notification de conservation dans
  l'interface Sprint 8 ; conservation des variables Gmail et du hook historique indépendant.
- `ops/systemd/documind-retention.service` et `.timer` : service non privilégié, isolé du
  socket Docker, simulation seulement, 09 h Europe/Paris.
- `tests/test_retention.py`, `docs/sprint-9-retention.md`, ce rapport et le lien README.

Le Compose, les volumes, le déployeur et les outils de sauvegarde/moniteur ne sont pas modifiés
par ce sprint. Des modifications/fichiers des sprints précédents étaient déjà présents dans
l'arbre de travail ; ils ont été conservés.

## Commandes et résultats

```powershell
.venv/Scripts/python.exe -m pytest tests/test_retention.py tests/test_monitoring.py tests/test_restic_upload.py tests/test_production_backups.py tests/test_deployment.py tests/test_https_probes.py -q
.venv/Scripts/python.exe -m compileall -q tools/retention_production.py tools/gmail_monitor_alert.py tests/test_retention.py
.venv/Scripts/python.exe tools/retention_production.py --help
.\var\tools\actionlint\actionlint.exe -shellcheck= -pyflakes= .github/workflows/deploy.yml .github/workflows/ci.yml
git -c safe.directory=C:/Users/Adeline/Documents/DocuMind_AI -c core.whitespace=blank-at-eol,blank-at-eof,space-before-tab,cr-at-eol diff --check
```

Résultat du passage final : **353 tests réussis**, dont **58 tests de rétention**.
Compilation Python, aide CLI, workflows et contrôle des espaces : sans erreur.
Un avertissement existant Starlette/httpx signale la dépréciation de cette intégration de tests.
Les workflows ne sont pas modifiés par cette livraison.

## Couverture et protections vérifiées

- 0, 1, 7, 8, 30 archives ; absence de snapshot quotidien ; union de jours, semaines ISO et
  mois occupés sur 270 jours ; plusieurs exécutions un même jour.
- Archives incomplètes, inconnues, vides même avec SHA conforme, corrompues ; mauvais schéma,
  PostgreSQL et intégrité ; colonne réelle `sha256` admise dans les métadonnées.
- Liens symboliques de répertoire/fichier refusés, chemins suspects, copie locale sans snapshot,
  snapshot sans copie locale, comparaison des quatre fichiers et détection des divergences.
- Copies historiques et tags spéciaux protégés, copie restaurée `51ac3259` requise et unique,
  répertoires manuels/restauration intacts, autres usages et snapshots sans tags exclus.
- Dépôt inaccessible/invalide, doubles identifiants/exécutions, préfixes ambigus, dates futures
  ou sauvegarde obsolète ; ajout/modification de snapshot ou changement de dépôt pendant
  l'analyse refusé ; réordonnancement seul admis.
- Verrous occupés (simulation, sauvegarde/déploiement), marqueur de maintenance signalé,
  release active absente/incohérente, absence de modification des archives et du verrou commun.
- Mode réel refusé avec ou sans paramètres d'approbation, avant toute sonde/commande externe.
- Rapports hachés, exclusions assainies, absence de secrets dans rapports/notifications,
  e-mails réservés aux anomalies et dédupliqués, échec SMTP réessayé, risque disque signalé.
- Commandes Restic limitées à la lecture ; flux de dump bornés et retour non nul rejeté ;
  aucune commande Docker ni suppression présente dans le simulateur.

## Contrôles Debian restant manuels

Les appels réseau, le coût/temps des lectures B2, les permissions effectives des archives,
le verrouillage POSIX et le confinement systemd doivent être contrôlés sur Debian lors du
premier essai autorisé. Les tests de verrous et de symlinks simulent leurs interfaces pour
fonctionner sous Windows ; ils ne remplacent pas un essai Linux. La syntaxe des unités et
le calendrier doivent être vérifiés avec les commandes `systemd-analyze` du guide avant
activation manuelle du seul timer de simulation.

Le script ne réalise pas de nouvelle restauration : la restauration de `51ac3259` reste le
constat administratif fourni. Sa présence est contrôlée, son contenu n'est jamais sélectionné
pour suppression. Une suppression future exigera une preuve de restauration revue et un
nouveau développement explicitement autorisé. Aucune purge n'est livrée ni activable ici.
