# Livraison minimale V5 — Docnelo Public Beta

Bundle d'outillage uniquement, préparé localement le 31 octobre 2026. Aucun déploiement automatique. Les huit sources Python du dépôt sont copiées octet pour octet, sans adaptation pour le déploiement. Les commandes ci-dessous sont à exécuter manuellement après revue.

## Transfert PowerShell par SCP

Depuis le poste Windows ; remplacer le nom d'hôte. Le répertoire distant de destination doit être absent avant le transfert pour éviter toute fusion de livraison.

```powershell
$Bundle = 'C:\Users\Adeline\Documents\DocuMind_AI\deliveries\docnelo-public-beta-backup-v5-20261031'
$VpsTarget = 'debian@VOTRE_HOTE_VPS'
Get-FileHash -Algorithm SHA256 -LiteralPath "$Bundle\SHA256SUMS"
scp -r "$Bundle" "${VpsTarget}:/home/debian/"
if ($LASTEXITCODE -ne 0) { throw 'Transfert SCP en échec' }
```

Conserver localement l'empreinte affichée du manifeste pour la comparaison indépendante. SCP est le seul transfert prévu ; aucun secret ni fichier .env n'est contenu dans le répertoire.

## Vérifier et installer dans une nouvelle release Debian

Ces commandes ne touchent ni à la release actuelle ni à ses configurations. Le répertoire de réception doit avoir été créé par SCP, sans contenu antérieur.

```bash
set -euo pipefail
umask 077
INCOMING=/home/debian/docnelo-public-beta-backup-v5-20261031
TOOL_RELEASE=/opt/documind-public-beta/backup-tools-v5-20261031
cd "$INCOMING"
sha256sum SHA256SUMS
# Comparer cette empreinte avec celle calculée sur Windows avant de poursuivre.
sha256sum --check --strict SHA256SUMS

# mkdir refuse une destination déjà existante ; aucune fusion ni écrasement.
sudo mkdir -m 0700 "$TOOL_RELEASE"
sudo chown debian:debian "$TOOL_RELEASE"
cp -a "$INCOMING"/. "$TOOL_RELEASE"/
cd "$TOOL_RELEASE"
sha256sum --check --strict SHA256SUMS
```

Si la comparaison indépendante ou un contrôle d'empreintes échoue, arrêter la procédure. Un manifeste non signé prouve l'intégrité par rapport à l'empreinte conservée, pas à lui seul l'identité de l'expéditeur. Le manifeste couvre tous les fichiers livrés sauf lui-même ; `INVENTAIRE.md` et `SOURCE_AUDIT.json` sont eux-mêmes couverts.

## Vérification réelle Python 3.11, sans capture ni réseau

Pointer PYTHON vers l'interpréteur 3.11 déjà préparé, éventuellement dans son venv. Aucun paquet n'est installé ici.

```bash
PYTHON=/CHEMIN/DU/PYTHON3.11_PREPARE
cd "$TOOL_RELEASE"
"$PYTHON" -B check_python311.py
"$PYTHON" -B -m tools.public_beta_backup --help
"$PYTHON" -B -m tools.validate_restore --help
```

Exiger `status=passed`. Le contrôle importe les huit sources du bundle, vérifie les versions exactes de SQLAlchemy/Psycopg, construit leur dialecte sans connexion, compile en mémoire et teste fcntl sur un fichier temporaire. Il ne lit pas les secrets, ne contacte ni Docker, ni Restic, ni PostgreSQL et ne crée pas de bytecode.

La vérification statique locale est décrite dans COMPATIBILITE.md. Le contrôle réel 3.11 Debian n'a pas été exécuté à distance par l'agent.

## Vérifier l'image API, séparément des scripts hôte

Les fichiers backend livrés sont nécessaires dans l'image, pas seulement dans la release d'outillage. L'opérateur peut vérifier une image locale approuvée Public Beta sans volumes ni réseau ; aucune image ne doit être téléchargée pour ce contrôle :

```bash
API_IMAGE=REMPLACER_PAR_IMAGE_PUBLIC_BETA_APPROUVEE
docker run --rm --pull=never --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges --entrypoint python "$API_IMAGE" -B -c \
  'import hashlib, pathlib, backend.lifecycle_snapshot as s, backend.lifecycle_backup_lock as l; print("snapshot", hashlib.sha256(pathlib.Path(s.__file__).read_bytes()).hexdigest()); print("lock", hashlib.sha256(pathlib.Path(l.__file__).read_bytes()).hexdigest())'
```

Comparer les empreintes à SHA256SUMS. Si elles diffèrent, contrôler la compatibilité de l'image avant capture ; ce bundle n'injecte aucun module dans les conteneurs et ne reconstruit aucune image. Ce contrôle manuel ne démarre pas l'API et n'accède pas aux données.

## Utilisation ultérieure, opérateur uniquement

APP_ROOT doit désigner la release applicative physique actuellement déployée, directement sous /opt/documind-public-beta, avec son Compose et ses deux fichiers privés existants. TOOL_RELEASE reste le nouveau répertoire d'outillage. Ne pas remplacer APP_ROOT par TOOL_RELEASE. Les captures seront écrites sous APP_ROOT/var/backups, conformément au script inchangé.

```bash
APP_ROOT=/opt/documind-public-beta/REMPLACER_PAR_RELEASE_APPLICATIVE_EXISTANTE
EXPECTED_BUCKET=REMPLACER_PAR_BUCKET_APPROUVE
EXPECTED_PREFIX=REMPLACER_PAR_PREFIXE_PUBLIC_BETA_APPROUVE
cd "$TOOL_RELEASE"
"$PYTHON" -B -m tools.public_beta_backup --root "$APP_ROOT" \
  --expected-bucket "$EXPECTED_BUCKET" --expected-prefix "$EXPECTED_PREFIX"
```

Cette dernière commande est une opération de sauvegarde : elle arrête api/web et les laisse arrêtés, même après succès. Elle n'est pas une étape d'installation. Consulter les runbooks livrés avant de la lancer. Si l'ID de dépôt manque, le mode --record-repo-id peut être utilisé séparément après validation des coordonnées ; il modifie uniquement le fichier Restic Public Beta existant. Ne jamais retirer un ID pour contourner un conflit.

Les chemins Restic et latch sont ceux fixés dans les sources. Aucun lien .env, aucune copie de secrets, aucun remplacement de Compose, aucune modification d'image ou de service n'est requis pour installer l'outillage.

## Restauration de contrôle

Le bundle inclut validate_restore, mais ne provisionne pas de laboratoire. Préparer hors production un cluster isolé selon DEPENDENCIES.md. Exiger une URL SQLAlchemy `postgresql+psycopg`, loopback avec port explicite et base `documind_restore_admin`, fournie par un mécanisme opérateur privé dans DOCUMIND_RESTORE_DATABASE_URL. Ne pas écrire cette URL dans la livraison ni dans l'historique du shell.

Le CLI exige DOCUMIND_RESTORE_LAB=isolated, un répertoire de laboratoire canonique contenant `.synthetic-only` avec les octets `documind-isolated-restore-lab-v1` suivis d'un saut de ligne, un nom neuf `documind_restore_<12 hex>` et le chemin exact de la capture. Exemple d'invocation, une fois ces préconditions satisfaites :

```bash
cd "$TOOL_RELEASE"
SNAPSHOT=/CHEMIN/ABSOLU/DE/LA/CAPTURE_V5
LAB_ROOT=/CHEMIN/ABSOLU/DU/LAB_ISOLE
LAB_DATABASE=documind_restore_0123456789ab
"$PYTHON" -B -c 'import json,sys; m=json.load(open(sys.argv[1] + "/manifest.json")); assert type(m.get("backup_format_version")) is int and m["backup_format_version"] == 5' "$SNAPSHOT"
DOCUMIND_RESTORE_LAB=isolated "$PYTHON" -B -m tools.validate_restore "$SNAPSHOT" \
  --database "$LAB_DATABASE" --restore-root "$LAB_ROOT"
```

Ne pas employer le nom d'exemple si une base correspondante existe. La validation refuse de réutiliser une base ou un répertoire de preuve existants. Lire dans DEPENDENCIES.md la réserve sur la fermeture du quota ; le latch quarantined n'autorise aucune remise en service.

## Retour arrière de l'outillage

Conserver la release d'outillage précédente et la release applicative actuelle. Pour revenir en arrière, cesser d'invoquer cette nouvelle release et employer le chemin de l'ancienne après revue de compatibilité V5. Aucun déplacement, écrasement, suppression de sauvegarde, modification de latch, changement de dépôt ou redémarrage n'est nécessaire. Aucun rollback de données n'est inclus. Une sauvegarde échouée conserve ses données locales et exige un diagnostic opérateur.
