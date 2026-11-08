# Transfert physique - nouvelle livraison uniquement

Aucun reseau, scp, curl ou commande Docker. Copier uniquement ce dossier
et son fichier externe d'ancres, jamais les images, rootfs ou preuves B1/v2.
Remettre l'ancre par un canal physique independant controle : le fichier
adjacent seul n'est pas une authentification ni une signature.

## Windows

Depuis la racine du depot, vers des chemins neufs du support physique :

```powershell
$Source = Join-Path (Get-Location) 'deliveries\docnelo-v51-p4-b1-p3-layer-contents-v1'
$Anchors = Join-Path (Get-Location) 'deliveries\docnelo-v51-p4-b1-p3-layer-contents-v1.anchors.json'
$Target = 'E:\docnelo-v51-p4-b1-p3-layer-contents-v1'
$External = 'E:\docnelo-v51-p4-b1-p3-layer-contents-v1.anchors.json'
if ((Test-Path -LiteralPath $Target) -or (Test-Path -LiteralPath $External)) {
    throw 'ARRET : destination existante'
}
Copy-Item -LiteralPath $Source -Destination $Target -Recurse -ErrorAction Stop
Copy-Item -LiteralPath $Anchors -Destination $External -ErrorAction Stop
$Expected = (Get-Content -LiteralPath $Anchors -Raw | ConvertFrom-Json).sha256sums
if ((Get-FileHash -LiteralPath (Join-Path $Target 'SHA256SUMS') -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Expected) {
    throw 'ARRET : manifeste transfere different'
}
```

Parents controles, support sans auteur concurrent. En cas d'erreur conserver
la tentative, ne pas la recouvrir. Verifier chaque fichier ensuite sur Debian.

## Debian

Chemins POSIX a utiliser uniquement en Bash sur Debian :

```bash
set -euC
umask 077
MEDIA="/media/support-controle"
DEST="/chemin/nouveau/docnelo-v51-p4-b1-p3-layer-contents-v1"
EXTERNAL="/chemin/nouveau/docnelo-v51-p4-b1-p3-layer-contents-v1.anchors.json"
test -d "$MEDIA/docnelo-v51-p4-b1-p3-layer-contents-v1" || exit 1
test ! -e "$DEST" && test ! -L "$DEST" || exit 1
test ! -e "$EXTERNAL" && test ! -L "$EXTERNAL" || exit 1
cp -a --no-clobber -- "$MEDIA/docnelo-v51-p4-b1-p3-layer-contents-v1" "$DEST" || exit 1
cp --no-clobber -- "$MEDIA/docnelo-v51-p4-b1-p3-layer-contents-v1.anchors.json" "$EXTERNAL" || exit 1
```

ARRET si parent douteux/symlink ou destination existante. Pas d'ecriture
concurrente. Ne pas extraire l'archive Docker, ni re-sceller sur Debian.
Suivre DEBIAN_PROTOCOL.md : le nouveau CLI retourne **20 meme quand A est
identique**, pour maintenir le blocage general. Verifier A dans le rapport,
pas uniquement le code shell.

Copier ensuite les nouvelles preuves et remettre leurs propres ancres
independamment, sans remplacer les preuves v2. REVIEW_ONLY_BLOCKED,
formal_b1_contents_closed=false, tous les GO false.
