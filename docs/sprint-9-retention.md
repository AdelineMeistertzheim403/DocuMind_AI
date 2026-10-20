# Sprint 9 — simulation de conservation des sauvegardes

## Livraison et limites

`tools/retention_production.py` calcule un plan local/B2 et ne dispose d'aucune fonction de
suppression. La commande sans argument équivaut à `--simulate`. `--execute` retourne **2**
avant toute lecture de configuration ou commande externe, même avec `--approved-plan` et
`--plan-sha256`. Aucun paramètre, fichier ou variable ne déverrouille cette version.

Les snapshots restaurés `51ac3259`, historique `3e6df673` et dernier automatisé
`9c1cfddc2d2e56f5a99e750ff028a643990e8750e3a4d82a8e1aca0e5b9bed3a` sont des constats
fournis par l'administratrice. Cette livraison n'a effectué aucune inspection distante.
La présence unique des deux préfixes historiques est exigée à chaque simulation. Le fait que
`51ac3259` a été restauré est une déclaration administrative conservée dans le rapport,
pas une nouvelle preuve de restauration produite par le simulateur.

Le script lit `/srv/documind-ai/current/release.json` avec le validateur du bundle actif :
`current` doit être un lien vers un répertoire directement sous `releases`. La migration attendue
provient de cette release (actuellement `0006`), PostgreSQL attendu reste **17**. Il ne contacte
ni Docker, ni PostgreSQL, ni l'API/BFF, et n'effectue aucune migration ni interruption.
Le Compose, `backup_local.py`, les volumes et les timers des Sprints 7/8 restent inchangés.

## Sélection et preuves

Les seules archives locales éligibles sont les répertoires directement sous
`/srv/documind-ai/var/backups/`, nommés `daily-<UTC YYYYMMDDTHHMMSSZ>-<UUID hex minuscule>`.
Chaque archive doit contenir exactement `manifest.json`, `integrity.json`, `database.dump`
et `documents.tar.gz`, fichiers réguliers sans lien symbolique ni lien physique supplémentaire.
Les chemins canoniques, la date, le schéma, PostgreSQL 17, les SHA-256 et la structure des
empreintes de tables sont contrôlés. Les deux métadonnées JSON sont limitées à 1 Mio chacune.

Le snapshot associé exige un identifiant complet de 64 caractères hexadécimaux, exactement
les deux tags `documind-ai` et son tag quotidien, et l'unique chemin correspondant à l'archive.
Les doublons d'identifiant ou d'exécution, dates incohérentes et chemins suspects bloquent le plan.
Les autres usages du dépôt, les snapshots historiques et les tags supplémentaires sont exclus
des propositions. Les archives locales associées à un snapshot protégé le restent aussi.
Les répertoires manuels et temporaires de restauration ne sont jamais parcourus ni sélectionnés.

La présence d'un snapshot ne suffit pas. Le script lit ses métadonnées, puis calcule en flux
les SHA-256 et tailles des deux archives via `restic dump`, sans les restaurer sur disque.
Les quatre fichiers distants sont comparés octet pour octet par empreinte et taille avec leurs
copies locales. Les propositions distantes sans archive locale reçoivent aussi cette vérification
complète contre leur manifeste. Le dernier snapshot quotidien est toujours vérifié intégralement
et doit dater de moins de 36 heures. Les snapshots conservés uniquement par calendrier peuvent
rester non vérifiés : ils ne servent alors pas de preuve autorisant une suppression locale.

Une incohérence locale ou distante retire **toutes** les propositions du rapport, en préservant
les copies concernées. Un dépôt inaccessible ou ambigu ne produit aucun plan utilisable.
L'inventaire complet et l'identité du dépôt sont relus à la fin : un changement de snapshot,
de métadonnées ou de dépôt pendant l'analyse invalide le plan. L'ordre d'affichage seul ne
constitue pas un changement. Cela ne remplace pas les contrôles juste avant une éventuelle
suppression future ; ce rapport reste une observation, pas une réservation de l'état du dépôt.

## Politique calculée

- Local : préserver les sept dernières archives automatiques **valides et confirmées**.
  La plus récente reste protégée, même si elle est invalide ou non appariée.
- B2 : union des représentants les plus récents de **7 jours occupés**, **4 semaines ISO
  occupées** et **6 mois occupés**, en Europe/Paris, plus le dernier snapshot valide et les
  historiques protégés. Plusieurs exécutions un même jour ne consomment pas plusieurs jours.
- Une paire locale/distante n'est jamais proposée des deux côtés dans un même plan : si son
  snapshot est candidat distant, son archive locale est conservée. Ce garde-fou peut maintenir
  plus de sept archives locales. Les exclusions protégées s'ajoutent toujours à la politique.

Le calcul utilise un groupe DocuMind global. Il n'applique pas aveuglément une politique Restic
par chemin, puisque les chemins `daily-*` sont tous différents. Le principe d'union temporelle
peut être comparé au [code de politique Restic 0.14](https://github.com/restic/restic/blob/v0.14.0/internal/restic/snapshot_policy.go).
Aucune commande `forget`, `prune`, `unlock`, `restore`, `init` ou `backup` n'est exécutée.
Les seules commandes sont `restic --no-lock cat config`, `snapshots --json` et `dump`.

Les vérifications intégrales peuvent télécharger des volumes significatifs depuis B2 et entraîner
des frais de lecture/transfert. Chaque commande est bornée à cinq minutes et systemd borne
l'ensemble à trente minutes. Un timeout impose un diagnostic, jamais une validation partielle.

## Verrous, rapports et alertes

Le simulateur conserve un verrou partagé sur le **fichier existant**
`/srv/documind-ai/deployment.lock` pendant toute l'analyse. Les sauvegardes et déploiements
utilisent son verrou exclusif ; une opération déjà active fait refuser la simulation. Une
opération lancée pendant l'analyse doit attendre ou signaler son verrou occupé suivant son
comportement existant. Ne pas supprimer/recréer ce fichier pour contourner l'exclusion.
Un marqueur `var/backup-maintenance.json` présent fait aussi refuser la simulation.
Deux simulations sont exclues par des verrous privés. Les autres producteurs Restic qui
n'utilisent pas ce verrou sont surveillés par la comparaison d'inventaire final.

Les rapports `plan-<UTC>-<UUID>.json`, mode 0600, sont écrits sous
`/var/lib/documind-retention/` (0700). Ils contiennent les compteurs examinés/éligibles,
conservations et motifs, candidats théoriques, octets locaux potentiels, exclusions, alertes,
identifiants DocuMind et empreintes vérifiées. Les octets sont des tailles logiques additionnées,
pas une garantie de gain physique ni une estimation de l'espace B2 dédupliqué.
`plan_sha256` est le SHA-256 du JSON canonique sans ce champ : il détecte une modification,
mais n'est ni une signature ni une preuve d'approbation. Les IDs/chemins des autres usages
sont remplacés par des références hachées ; les secrets et contenus documentaires sont absents.

La production et les archives sont lues uniquement. Les écritures nécessaires se limitent
au répertoire d'état, aux rapports, au cache Restic et aux fichiers temporaires privés du
service. La persistance anti-spam réutilise l'écriture atomique du Sprint 8, avec nettoyage
de ses seuls temporaires ; elle ne supprime aucune archive ni aucun snapshot.
Les rapports/cache ne sont pas purgés automatiquement : surveiller leur taille.

Le module Gmail du Sprint 8 reçoit seulement les anomalies : simulation impossible, dépôt
inaccessible, incohérence ou espace critique/urgent (< 10 / < 8 Gio). Les avertissements
< 20 Gio restent traités par Sprint 8. Un incident identique ne renvoie pas un email quotidien ;
une résolution efface l'incident sans mail normal. Un envoi échoué sera réessayé au passage
suivant. `gmail_backup_alert.py`, ses arguments et les six variables privées restent intacts.

Codes : **0** simulation achevée sans anomalie ; **1** simulation impossible/incohérence,
risque disque élevé ou échec de notification ; **2** exécution réelle refusée. Le journal ne
contient qu'un résumé assaini et le nom du rapport privé. Un service oneshot terminé peut
être `inactive (dead)` après succès : vérifier `Result` et `ExecMainStatus`.

## Installation manuelle Debian — à effectuer après revue

Aucune commande de cette section n'a été exécutée sur le VPS. Prérequis : Python 3.11+,
tzdata Europe/Paris, Restic 0.14+ existant, helpers Sprints 7/8 déjà installés et lisibles par
`debian`. Les mêmes fichiers privés Restic/Gmail sont utilisés sans modification. Le compte
doit pouvoir lire les archives 0700/0600 créées par Sprint 7 et les métadonnées disque.
Ne pas élargir les permissions des secrets ou des archives pour satisfaire le contrôle.

Transférer les fichiers revus vers `/home/debian/documind-retention-sprint9/` en conservant
`tools/` et `ops/systemd/`, par votre connexion SSH habituelle vérifiée. Sur le VPS :

```bash
python3 --version
restic version
readlink -f /srv/documind-ai/current
sudo -u debian test -r /srv/documind-ai/deployment.lock
sudo -u debian test -r /home/debian/.config/restic/documind.env
sudo -u debian test -r /home/debian/.config/documind-alerts/gmail.env
sudo -u debian stat -f /srv/documind-ai /var/lib/docker
sudo -u debian python3 - <<'PY'
import sys
sys.path.insert(0, '/srv/documind-ai/ops')
import backup_production, monitor_production
assert callable(backup_production.restic_environment)
assert callable(backup_production.load_helper)
assert callable(monitor_production.notify_changes)
from zoneinfo import ZoneInfo
ZoneInfo('Europe/Paris')
print('Helpers disponibles ; aucun appel distant effectué')
PY

SOURCE_DIR=/home/debian/documind-retention-sprint9
sudo install -o root -g root -m 0644 "$SOURCE_DIR/tools/retention_production.py" /srv/documind-ai/ops/retention_production.py
sudo install -o root -g root -m 0644 "$SOURCE_DIR/tools/gmail_monitor_alert.py" /srv/documind-ai/ops/gmail_monitor_alert.py
sudo install -o root -g root -m 0644 "$SOURCE_DIR/ops/systemd/documind-retention.service" /etc/systemd/system/documind-retention.service
sudo install -o root -g root -m 0644 "$SOURCE_DIR/ops/systemd/documind-retention.timer" /etc/systemd/system/documind-retention.timer
sudo systemctl daemon-reload
sudo systemd-analyze verify /etc/systemd/system/documind-retention.service /etc/systemd/system/documind-retention.timer
systemd-analyze calendar '*-*-* 09:00:00 Europe/Paris'
```

La mise à jour du module Gmail ajoute seulement les modèles de conservation ; elle préserve
les interfaces Sprint 8. Ne pas remplacer le hook historique, les helpers sauvegarde/moniteur,
le Compose ou les unités existantes. Aucun nouveau déploiement applicatif n'est nécessaire.
Arrêter l'installation si un prérequis échoue.

Premier essai manuel **après revue**, sans timer :

```bash
sudo systemctl start documind-retention.service
systemctl show documind-retention.service -p Result -p ExecMainStatus
sudo journalctl -u documind-retention.service -n 30 --no-pager
sudo -u debian ls -lt /var/lib/documind-retention/plan-*.json
```

Lire le rapport indiqué par le journal avec `sudo -u debian python3 -m json.tool <chemin-exact>`.
Vérifier le mode simulation, les protections historiques, les empreintes, les compteurs et
les exclusions. Ce premier essai lit réellement B2 et peut envoyer un email d'anomalie ; il
ne modifie pas les sauvegardes. Vérifier dans un terminal administrateur les tailles/modes
des répertoires si un refus de lecture apparaît, sans afficher les secrets.

Activation du **seul timer de simulation**, uniquement après votre validation manuelle :

```bash
sudo systemctl enable --now documind-retention.timer
systemctl list-timers --all documind-retention.timer
```

Horaire 09 h Europe/Paris. `Persistent=true` peut rattraper une échéance manquée dès activation
ou démarrage. Le service non privilégié masque le socket Docker et n'a d'écriture qu'à son
répertoire d'état/cache et ses temporaires. Il n'a aucune dépendance envers les services applicatifs.

## Désactivation et diagnostic

```bash
sudo systemctl disable --now documind-retention.timer
# Seulement si une simulation est encore en cours et doit être interrompue :
sudo systemctl stop documind-retention.service
```

Cela laisse les rapports, snapshots, archives et autres timers en place. Aucun nettoyage requis.
En cas d'échec, conserver le rapport et les copies existantes, lire les motifs, puis vérifier :
release active valide ; aucune sauvegarde/déploiement actif ni marqueur de maintenance résiduel ;
accès privé Restic ; inventaire stable ; archives compatibles avec le schéma actif ; présence
des copies historiques ; espace disponible ; connectivité SMTP. Ne jamais supprimer un verrou
ou un marqueur sans appliquer le guide de récupération Sprint 7. Un échec ne justifie ni
restauration automatique ni arrêt applicatif. Une fois la cause corrigée, relancer manuellement
le service de simulation. Un timeout ne donne aucun plan approuvable.

## Suppressions futures : décision et développement séparés

Cette livraison ne peut pas les activer. Une évolution explicitement autorisée devra vérifier
un plan récent (durée maximale à faire valider), son empreinte et son inventaire inchangés,
une preuve indépendante de restauration identifiant la copie préservée, le dernier snapshot
complet, un verrou **exclusif** partagé avec déploiement/sauvegarde, les identités et empreintes
juste avant **chaque** action et une limite de masse explicitement validée (nombre et octets).
La procédure devra être interrompue au moindre changement et préserver une paire restaurable.
`--approved-plan` et `--plan-sha256` réservent une interface, ils ne valent pas approbation.

La politique 7/4/6 et les sept locaux restent des propositions à valider. Aucun `forget --prune`
automatique n'est prévu : l'effet de la récupération des blocs sur l'ensemble du dépôt partagé
demande une étude et une autorisation distinctes, avec restauration de contrôle et sauvegarde
des métadonnées. Ne pas transposer les candidats du rapport en commandes de suppression.
