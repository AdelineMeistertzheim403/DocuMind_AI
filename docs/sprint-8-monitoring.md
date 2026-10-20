# Sprint 8 — surveillance du VPS et des sauvegardes

## État de référence et périmètre

Constats fournis par l’administratrice : sauvegarde quotidienne à 03 h Europe/Paris,
Restic/B2 opérationnel, restauration indépendante `51ac3259`, dernier snapshot automatisé
confirmé `9c1cfddc2d2e56f5a99e750ff028a643990e8750e3a4d82a8e1aca0e5b9bed3a`.
La partition racine de 79 Go, avec environ 39 Go libres, porte actuellement Docker et DocuMind.
Ces constats ne sont pas une inspection distante réalisée pendant ce sprint.

Livraison : `tools/monitor_production.py`, `tools/gmail_monitor_alert.py`, les unités
`ops/systemd/documind-monitor.service` et `.timer`, les tests et ce guide.
L’installation se fait séparément dans `/srv/documind-ai/ops/`, sans nouvelle image, migration
ou déploiement applicatif. Aucun Compose ni unité de sauvegarde du Sprint 7 n’est modifié.

Le hook existant `/srv/documind-ai/ops/gmail_backup_alert.py` reste **intact**, avec ses arguments
`--test` et `documind-backup-failed`, ainsi que `documind-backup-alert.service`.
La nouvelle interface dédiée utilise le **même fichier Gmail et les mêmes six variables**,
avec STARTTLS obligatoire :

```text
SMTP_HOST  SMTP_PORT  SMTP_USERNAME  SMTP_PASSWORD  ALERT_FROM  ALERT_TO
```

Aucun secret ne doit être copié dans ce dépôt ou dans une unité systemd.

## Contrôles effectués sans interruption

### Stockage

Le script interroge `/srv/documind-ai` et `/var/lib/docker`. Il utilise `statvfs` et
`f_bavail * f_frsize`, donc l’espace disponible pour le compte non privilégié, plutôt que
les blocs réservés à root. `st_dev` déduplique les chemins : une seule interrogation pour
la partition actuellement commune. Si les chemins sont sur deux partitions, les deux sont
contrôlées et le **niveau le plus sévère** constitue l’alerte de stockage agrégée.

| Espace disponible | État | Événement |
|---|---|---|
| ≥ 20 Gio | normal | aucun |
| < 20 Gio et ≥ 10 Gio | avertissement | `disk-warning` |
| < 10 Gio et ≥ 8 Gio | critique | `disk-critical` |
| < 8 Gio | urgence | `disk-emergency` |

Les seuils sont en Gio (2³⁰ octets). Les chemins de documents, archives et identifiants
de périphériques n’apparaissent ni dans les messages ni dans l’état anti-spam.

### Snapshots B2

Le lecteur sécurisé Sprint 7 conserve `/home/debian/.config/restic/documind.env`, les
déclarations `export`, `RESTIC_PASSWORD_FILE` et le contrôle privé de son fichier de mot de passe.
Seule cette commande Restic est exécutée :

```text
restic --no-lock snapshots --json --tag documind-ai
```

Il n’y a ni sauvegarde, restauration, initialisation, purge, déverrouillage ou suppression.
`--no-lock` évite même de créer un verrou dans B2 pour cette lecture. Le cache éventuel
reste sous `/var/lib/documind-monitor/restic-cache`, pas dans les volumes documentaires.

Chaque candidat doit avoir un ID complet hexadécimal de 64 caractères, exactement le tag
`documind-ai` et un tag `daily-<UTC>-<UUID hex>`, ainsi que l’unique chemin correspondant
`/srv/documind-ai/var/backups/<tag daily>`. L’heure du snapshot doit correspondre à cette
exécution, avec une marge maximale de quatre heures, et ne pas être dans le futur de plus
de cinq minutes. Le plus récent **candidat validé** est utilisé, jamais le dernier élément
affiché aveuglément. Au-delà de 36 heures, `backup-stale` est émis.

Les états sont distingués : liste vide (`backup-missing`), sauvegarde ancienne (`backup-stale`),
dépôt inaccessible (`restic-unavailable`, raison `repository-unavailable`) et réponse invalide
(`restic-unavailable`, raison `invalid-response`). Des métadonnées historiques non conformes
plus anciennes qu’une sauvegarde quotidienne valide récente ne provoquent pas de fausse
alerte ; elles ne peuvent jamais servir de preuve de fraîcheur. Une entrée inconnue/malformée
sans date vérifiable ou plus récente reste une anomalie. Un ancien snapshot valide ne masque
pas une sauvegarde actuelle absente : le seuil de 36 heures reste applicable.

La liste de snapshots ne prouve pas une restauration complète ni, avec Restic 0.14, le code
de sortie historique de chaque `backup`. Les confirmations Sprint 7 et les restaurations
indépendantes restent nécessaires. Aucun `restic check` lourd n’est lancé par ce contrôle.

### Planification et fenêtres d’activité

Le contrôle lit seulement les propriétés de `documind-backup.timer` et `.service` via
`systemctl show`. `busctl get-property` fournit l’heure numérique de la prochaine exécution,
sans dépendre d’un texte de date localisé. Sont exigés : timer présent, enabled, active,
prochaine exécution dans les 26 heures à **03 h Europe/Paris**, dernier résultat de service
`success` et statut zéro. La marge de 26 heures couvre le changement d’heure.
Le résultat systemd est celui disponible depuis le démarrage ; il ne remplace pas le contrôle B2.

Une sauvegarde active depuis moins de quatre heures ou un verrou de déploiement détenu diffère
les contrôles sauvegarde/planification, sans envoyer un faux retour à la normale. Le moniteur
teste le verrou partagé puis le libère immédiatement : il ne conserve pas le verrou des
déploiements pendant ses sondes et ne provoque pas leur échec pour une longue lecture B2.
Une sauvegarde réellement active depuis plus de quatre heures est une anomalie. Un verrou
encore observé lors d’un passage ultérieur après plus de quatre heures est aussi signalé ;
cela signifie « occupation observée à plusieurs passages », pas une preuve de continuité.

Les alertes disque restent actives pendant ces fenêtres. Un déploiement commençant après
le test de verrou n’est jamais interrompu : la requête Restic est indépendante et en lecture seule.

## État privé, alertes et codes de sortie

`/var/lib/documind-monitor/` est privé (0700), créé par `StateDirectory` dans systemd.
Un verrou `monitor.lock` empêche deux contrôles simultanés. `state.json` conserve seulement
les événements déjà acceptés par SMTP, leurs dates et des horodatages de contrôle.
Il n’enregistre aucun mot de passe, ID de snapshot, chemin d’archive ou contenu documentaire.
Les écritures passent par un fichier temporaire privé, fsync et remplacement atomique.

- Un incident identique n’envoie pas un nouveau message à chaque contrôle.
- Un changement de niveau/raison envoie une nouvelle alerte.
- Une résolution envoie `recovery`, une fois, uniquement si l’incident avait été notifié.
- Un incident critique/urgent inchangé est rappelé après **72 heures** par défaut, au prochain passage.
  Les avertissements n’ont pas de rappel. Zéro désactive les rappels, pas les changements d’état.
- Un échec SMTP ne marque pas l’alerte comme envoyée ; le prochain passage réessaie, y compris
  pour un retour à la normale. Les succès sont persistés individuellement.
- Un recul d’horloge supérieur à cinq minutes diffère les contrôles temporels et émet une alerte
  `clock-inconsistent`, sans réinitialiser les anciennes alertes ni déclencher une rafale de rappels.

Les mails français proviennent exclusivement de modèles et de champs autorisés. Aucun corps
libre, sortie brute de commande ou exception SMTP ne passe dans un message ou journal.
Les retours SMTP sont des confirmations d’acceptation du serveur, pas des garanties d’arrivée
dans la boîte principale. Si la machine tombe après acceptation SMTP mais avant persistance,
un doublon reste possible : on privilégie le nouvel essai plutôt que la perte d’une alerte.

Codes : **0** normal ou contrôles temporairement différés ; **1** incident, échec d’envoi ou
erreur interne. Un incident inchangé conserve un code 1 sans réenvoyer d’email. Le service
peut donc apparaître failed lors d’une anomalie correctement signalée : lire son rapport JSON.
Il n’utilise pas `OnFailure=documind-backup-alert.service`, qui doublerait les notifications et
annoncerait à tort un échec de sauvegarde pour une anomalie du moniteur.

## Installation manuelle sur Debian — non exécutée par l’agent

Prérequis : Python 3.11+, données de fuseau Europe/Paris, Restic 0.14+ opérationnel,
`systemctl` et `busctl`, accès sortant SMTP/B2 et les fichiers privés déjà utilisés par Sprint 7.
Le compte **debian** est réutilisé pour lire ces fichiers 0600, sans sudo depuis le script,
nouveau groupe ou privilège ajouté. Le service n’a aucune capacité et masque le socket Docker.
Il ne peut écrire que son répertoire d’état, son cache et son espace temporaire privé.
Vérifier qu’il peut lire les métadonnées des deux chemins disque sans changer les permissions
de `/var/lib/docker` ni rendre les secrets publics.

Transférer manuellement les deux nouveaux scripts et les deux unités après revue vers un
répertoire privé de préparation, par exemple `/home/debian/documind-monitor-sprint8/`, en
conservant `tools/` et `ops/systemd/`. Utiliser votre connexion SSH habituelle avec clé hôte
vérifiée. Puis, sur le VPS :

```bash
python3 --version
restic version
command -v systemctl busctl
sudo -u debian test -r /home/debian/.config/documind-alerts/gmail.env
sudo -u debian test -r /home/debian/.config/restic/documind.env
sudo -u debian test -r /home/debian/.config/restic/password
sudo -u debian stat -f /srv/documind-ai /var/lib/docker
sudo -u debian test -r /srv/documind-ai/deployment.lock

# Vérifier les helpers installés, sans lire ni afficher les secrets.
sudo -u debian python3 - <<'PY'
import sys
sys.path.insert(0, '/srv/documind-ai/ops')
import backup_production
assert callable(backup_production.restic_environment)
assert callable(backup_production.restic_json)
print('Helpers Sprint 7 disponibles')
PY

SOURCE_DIR=/home/debian/documind-monitor-sprint8
sudo install -o root -g root -m 0644 "$SOURCE_DIR/tools/monitor_production.py" /srv/documind-ai/ops/monitor_production.py
sudo install -o root -g root -m 0644 "$SOURCE_DIR/tools/gmail_monitor_alert.py" /srv/documind-ai/ops/gmail_monitor_alert.py
sudo install -o root -g root -m 0644 "$SOURCE_DIR/ops/systemd/documind-monitor.service" /etc/systemd/system/documind-monitor.service
sudo install -o root -g root -m 0644 "$SOURCE_DIR/ops/systemd/documind-monitor.timer" /etc/systemd/system/documind-monitor.timer
sudo systemctl daemon-reload
sudo systemd-analyze verify /etc/systemd/system/documind-monitor.service /etc/systemd/system/documind-monitor.timer
systemd-analyze calendar '*-*-* 08:00:00 Europe/Paris'
```

Ne pas écraser `gmail_backup_alert.py`, les unités Sprint 7 ou les fichiers privés.
Le helper `backup_production.py` installé doit contenir le correctif Restic 0.14 du Sprint 7.
S’il manque, remettre à niveau ce script d’exploitation revu séparément ; aucun redéploiement
de FastAPI/BFF/PostgreSQL n’est requis. Arrêter l’installation si une validation échoue.

## Test Gmail sans panne de production

Après installation et revue, un seul test explicite envoie un vrai email de test :

```bash
sudo -u debian python3 /srv/documind-ai/ops/gmail_monitor_alert.py --test
```

Le sujet contient `test-notification` ; le corps précise qu’aucune panne n’a été simulée.
Le test ne crée pas d’état d’incident et ne modifie aucun service. Le hook historique conserve
son propre `--test` ; inutile d’envoyer deux tests pour valider la nouvelle interface.
Les tests locaux utilisent un faux SMTP et n’envoient aucun message réel.

Premier contrôle réel, **sans activer le timer** :

```bash
sudo systemctl start documind-monitor.service
sudo journalctl -u documind-monitor.service -n 30 --no-pager
sudo systemctl status documind-monitor.service --no-pager
```

Ce contrôle est sans interruption applicative, mais peut envoyer les alertes correspondant à
l’état réel. Exiger un rapport `normal` ou examiner les incidents/différés avant activation.
Ne pas vider l’état pour multiplier les essais d’email.

Activation seulement après validation manuelle :

```bash
sudo systemctl enable --now documind-monitor.timer
systemctl list-timers --all documind-monitor.timer
```

Horaire : **08 h Europe/Paris**, indépendant de la sauvegarde de 03 h. Le service n’a ni
`Requires` ni `PartOf` avec la sauvegarde ; il ne la démarre ou l’arrête jamais.
`Persistent=true` rattrape une échéance manquée lors du démarrage/activation du timer : un
contrôle et éventuellement un email peuvent donc partir à une autre heure. Les contrôles en
cours de sauvegarde sont différés comme décrit ci-dessus.

Pour changer le rappel, créer un override avec `sudo systemctl edit documind-monitor.service` :

```ini
[Service]
ExecStart=
ExecStart=/usr/bin/python3 /srv/documind-ai/ops/monitor_production.py --reminder-hours 24
```

Puis `sudo systemctl daemon-reload`. Aucun secret n’entre dans cet override.

## Fenêtre de maintenance prévue

Une fenêtre privée, explicite et de **24 heures maximum**, peut différer uniquement les
canaux sauvegarde et/ou planification. Elle ne masque jamais les alertes disque. Exemple
manuel pour deux heures, une fois le répertoire d’état créé par le premier contrôle :

```bash
sudo -u debian python3 - <<'PY'
from datetime import datetime, timedelta, timezone
import json, os
from pathlib import Path
os.umask(0o077)
path = Path('/var/lib/documind-monitor/maintenance.json')
data = {'until': (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
        'scopes': ['backup', 'systemd']}
path.write_text(json.dumps(data))
path.chmod(0o600)
PY
```

Le fichier expiré est ignoré et peut rester en place ; aucune sauvegarde n’est supprimée.
Une fenêtre mal formée/trop longue provoque un code non nul, pas une suppression silencieuse
des alertes. Pour terminer plus tôt, éditer seulement `until` avec une date déjà passée.

## Diagnostic et reprise

- **Disque** : consulter `df -h /srv/documind-ai /var/lib/docker`. Identifier manuellement
  l’occupation sans supprimer de volume, snapshot ou archive. La surveillance ne fait aucun nettoyage.
- **Sauvegarde ancienne/absente** : consulter `journalctl -u documind-backup.service`, confirmer
  le dernier snapshot, résoudre l’incident suivant le [guide Sprint 7](sprint-7-backups.md).
  Un ancien snapshot restaurable n’est pas une preuve de succès de la tâche actuelle.
- **B2 inaccessible/réponse invalide** : vérifier versions, réseau et droits via l’environnement
  privé existant. Ne pas imprimer les secrets ou coller une sortie brute dans un email.
  Ne pas initialiser un dépôt et ne pas forcer la suppression d’un verrou Restic.
- **Timer/service** : lire `systemctl status documind-backup.timer documind-backup.service`
  et `systemctl list-timers --all documind-backup.timer`. Corriger manuellement après revue,
  sans redémarrer les conteneurs pour faire disparaître une alerte de planification.
- **Horloge** : lire `timedatectl status`, vérifier synchronisation et fuseau ; ne pas effacer
  les états envoyés pour contourner un recul d’horloge. Le prochain contrôle cohérent enverra
  le retour à la normale et reprendra les contrôles temporels.
- **SMTP** : tester la nouvelle interface avec `--test`, vérifier accès réseau et configuration
  privée. Un échec n’est pas marqué comme envoyé ; le timer réessaie au prochain passage.
- **État invalide/permissions/verrou** : lire le rapport non nul dans journald ; attendre une
  exécution en cours. Ne jamais supprimer `monitor.lock` pour libérer un flock. Un état corrompu
  doit être diagnostiqué et sauvegardé manuellement avant réparation ; ne pas le réinitialiser
  à chaque contrôle, ce qui ferait perdre l’anti-spam. Les erreurs internes/sandbox doivent
  être suivies dans journald même si SMTP n’est pas disponible.

Pour relancer une lecture après correction :

```bash
sudo systemctl start documind-monitor.service
sudo journalctl -u documind-monitor.service -n 30 --no-pager
```

Une remise à zéro de l’état systemd failed n’est pas nécessaire au prochain déclenchement.
Ne pas modifier l’état JSON pour déclarer un email livré alors qu’il a échoué.

## Désactivation

```bash
sudo systemctl disable --now documind-monitor.timer
# Facultatif : arrêter seulement un contrôle actuellement en cours.
sudo systemctl stop documind-monitor.service
```

Ces commandes ne touchent pas la sauvegarde, son timer, Traefik, les conteneurs ou les volumes.
Conserver l’état privé et les fichiers de configuration. Un arrêt pendant l’envoi SMTP peut
laisser une livraison incertaine et entraîner un nouvel essai lors de la réactivation.

## Validation locale et limites

Voir [validation Sprint 8](validation-sprint-8.md). Les sondes disque, systemd, B2 et SMTP sont
simulées en test ; aucun email réel ni commande distante n’a été exécuté pendant ce sprint.
La validation de `systemd-analyze`, des permissions du compte Debian et des sandbox réelles
reste une étape manuelle avant installation/activation. Aucun nouveau frontend/API n’est ajouté.

Références primaires : [propriétés D-Bus systemd](https://www.freedesktop.org/software/systemd/man/latest/org.freedesktop.systemd1.html),
[busctl](https://www.freedesktop.org/software/systemd/man/latest/busctl.html),
[format Restic 0.14](https://github.com/restic/restic/blob/v0.14.0/cmd/restic/cmd_snapshots.go).
