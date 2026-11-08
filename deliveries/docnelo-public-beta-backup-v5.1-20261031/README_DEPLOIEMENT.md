# Installation de l'outillage Public Beta V5.1

Cette livraison corrige uniquement la validation des clés archivées et leur extraction dans un laboratoire privé. Format de sauvegarde : 5 ; version de l'outillage : 5.1. Aucun déploiement, aucune relance de sauvegarde ni de service n'a été effectué. L'installation doit préserver la release V5 actuelle et l'application healthy.

## Transfert manuel PowerShell

Le nom d'hôte doit être remplacé. Le répertoire de réception distant doit être absent pour éviter toute fusion de livraisons.

```powershell
$Bundle = 'C:\Users\Adeline\Documents\DocuMind_AI\deliveries\docnelo-public-beta-backup-v5.1-20261031'
$VpsTarget = 'debian@VOTRE_HOTE_VPS'
Get-FileHash -Algorithm SHA256 -LiteralPath "$Bundle\SHA256SUMS"
scp -r "$Bundle" "${VpsTarget}:/home/debian/"
if ($LASTEXITCODE -ne 0) { throw 'Transfert SCP en échec' }
```

Conserver l'empreinte du manifeste affichée sur Windows. Aucun fichier .env, clé réelle, dump ou donnée utilisateur n'est transféré.

## Vérification et installation Linux dans un répertoire neuf

```bash
set -euo pipefail
umask 077
INCOMING=/home/debian/docnelo-public-beta-backup-v5.1-20261031
TOOL_RELEASE=/opt/documind-public-beta/backup-tools-v5.1-20261031
cd "$INCOMING"
sha256sum SHA256SUMS
# Comparer avec l'empreinte conservée sur Windows avant de poursuivre.
sha256sum --check --strict SHA256SUMS

# mkdir échoue si cette destination existe ; aucun écrasement de release.
sudo mkdir -m 0700 "$TOOL_RELEASE"
sudo chown debian:debian "$TOOL_RELEASE"
cp -a "$INCOMING"/. "$TOOL_RELEASE"/
cd "$TOOL_RELEASE"
sha256sum --check --strict SHA256SUMS
```

Ces commandes écrivent uniquement dans la nouvelle release d'outillage. Ne pas copier les fichiers sur la V5 précédente, ni sur les modules d'une image ou d'une release applicative. Ne pas déplacer les captures partielles ni leur ajouter de manifeste.

## Contrôle Python 3.11 sans accès aux services

```bash
PYTHON=/CHEMIN/DU/PYTHON3.11_PREPARE
cd "$TOOL_RELEASE"
"$PYTHON" -B check_python311.py
"$PYTHON" -B -m tools.public_beta_backup --help
"$PYTHON" -B -m tools.validate_restore --help
```

Exiger status=passed. Le contrôle vérifie les neuf imports depuis cette livraison, SQLAlchemy 2.0.55, Psycopg 3.3.6, le dialecte sans connexion, la grammaire Python 3.11, fcntl et les permissions/UID réels de clés **synthétiques temporaires** après extraction des quatre profils autorisés. Il ne lit aucune vraie clé, ne contacte ni Docker, ni Restic, ni base, et ne lance pas l'orchestrateur. Ses fichiers temporaires sont supprimés à la fin ; aucune capture existante n'est touchée.

Il n'installe aucune dépendance et n'a pas été exécuté par l'agent sur le VPS. Le contrôle local de grammaire est statique ; il ne remplace pas ce contrôle Debian.

## Revue opérateur préalable à une future sauvegarde

- Confirmer indépendamment que l'image API effective emploie app avec GID 1000, que ce groupe est approuvé et que les seuls consommateurs du volume lifecycle sont les services de confiance prévus. Le Dockerfile ne fixe pas explicitement le numéro de groupe : arrêter si la valeur réelle diffère. Ne pas changer les identités réelles pour faire passer le validateur.
- Lire le rapport de sécurité : les protections root:app readonly ne prouvent pas l'immuabilité face à app, et le lecteur applicatif strict peut refuser l'ascendance app-owned. Ne pas interpréter l'acceptation d'archive comme une validation de remise en service après restore.
- Garder les chemins existants de Restic, de latch et de la release applicative ; ne pas les recopier dans la nouvelle livraison. Lors d'une future opération autorisée, le module sera chargé depuis TOOL_RELEASE mais --root désignera la release applicative physique existante. Il utilisera son Compose et ses fichiers privés déjà présents.
- La politique commune `tools/lifecycle_key_policy.py` doit accompagner les trois scripts corrigés. Ne pas transférer uniquement ces trois fichiers.

Les runbooks de capture/restauration sont inclus pour référence ; **ne pas exécuter leurs commandes de capture ou redémarrage lors de cette installation**. Les services Public Beta healthy restent tels quels. Aucune relance n'est incluse dans cette procédure.

## Restauration isolée

Les clés du laboratoire sont toujours restituées en 0400, sous keys/0700, au propriétaire effectif du processus de restauration. Aucun chown vers l'identité archivée et aucun accès de groupe hôte ne sont introduits. Elles ne sont pas prêtes à être montées dans une API d'un autre UID sans revue et provisionnement isolé explicite. Le laboratoire reste sans API exposée, avec latch quarantined ; la fermeture réelle du quota et la cohérence des lecteurs doivent être vérifiées séparément.

Le présent correctif ne provisionne pas de laboratoire et ne corrige aucune capture V5 partielle. Il ne modifie ni images, ni volumes, ni clés, ni configurations.

## Retour arrière

Cesser d'invoquer la V5.1 et sélectionner la release d'outillage précédente après revue. Conserver les deux releases, les preuves et captures ; aucune suppression ni remise en état de volume n'est nécessaire. L'ancienne V5 refusera toujours les archives 0440 : ne pas relancer une capture pour tester ce défaut connu. Les V5.1 avec UID/GID et profils de groupe doivent être examinées avec les validateurs V5.1. Aucun redémarrage ou changement de latch/secret n'est requis.
