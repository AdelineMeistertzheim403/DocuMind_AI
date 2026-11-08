# Transfert physique hors ligne

Aucun scp, curl, telechargement, Docker ou nouvel export. Copier uniquement
la nouvelle livraison et son fichier d'ancres externes sur un support physique
de confiance. Ne pas embarquer le rootfs, l'image ou des preuves B1.

## Windows : copie sans remplacement

Depuis la racine du depot, vers deux nouveaux chemins sur le support :

```powershell
$Source = Join-Path (Get-Location) 'deliveries\docnelo-v51-p4-b1-oci-comparator-v1'
$Anchors = Join-Path (Get-Location) 'deliveries\docnelo-v51-p4-b1-oci-comparator-v1.anchors.json'
$Target = 'E:\docnelo-v51-p4-b1-oci-comparator-v1'
$External = 'E:\docnelo-v51-p4-b1-oci-comparator-v1.anchors.json'
if ((Test-Path -LiteralPath $Target) -or (Test-Path -LiteralPath $External)) {
    throw 'ARRET : destination existante'
}
if (-not (Test-Path -LiteralPath $Anchors)) { throw 'ARRET : ancres absentes' }
Copy-Item -LiteralPath $Source -Destination $Target -Recurse -ErrorAction Stop
Copy-Item -LiteralPath $Anchors -Destination $External -ErrorAction Stop
$Expected = (Get-Content -LiteralPath $Anchors -Raw | ConvertFrom-Json).sha256sums
if ((Get-FileHash -LiteralPath (Join-Path $Target 'SHA256SUMS') -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Expected) {
    throw 'ARRET : manifeste transfere different'
}
```

Comparer ensuite chaque fichier copie a SHA256SUMS sur Debian. En cas
d'echec, conserver cette tentative, ne pas la recouvrir par une autre.
Le support doit etre sans ecriture concurrente. La seule copie de l'ancre
sur le meme support n'authentifie pas sa provenance : remettre aussi sa valeur
par un canal physique independant controle.

## Debian : importer dans un emplacement neuf

Les chemins POSIX ci-dessous s'utilisent seulement dans Bash sur Debian :

```bash
set -eu
umask 077
MEDIA="/media/support-controle"
DEST="/chemin/nouveau/docnelo-v51-p4-b1-oci-comparator-v1"
EXTERNAL="/chemin/nouveau/docnelo-v51-p4-b1-oci-comparator-v1.anchors.json"
test -d "$MEDIA/docnelo-v51-p4-b1-oci-comparator-v1" || exit 1
test ! -e "$DEST" && test ! -L "$DEST" || exit 1
test ! -e "$EXTERNAL" && test ! -L "$EXTERNAL" || exit 1
cp -a --no-clobber -- "$MEDIA/docnelo-v51-p4-b1-oci-comparator-v1" "$DEST" || exit 1
cp --no-clobber -- "$MEDIA/docnelo-v51-p4-b1-oci-comparator-v1.anchors.json" "$EXTERNAL" || exit 1
```

Ces commandes supposent des parents preexistants controles et aucune course
concurrente. **ARRET** si un parent est douteux ou si un chemin existe.
Ne pas extraire l'archive Docker. Cette livraison est un dossier, pas une
archive executable ou une image a importer.

Executer ensuite DEBIAN_PROTOCOL.md, avec l'ancre SHA256SUMS remise
independamment. Ne pas executer seal.py pour rendre conforme une copie
alteree. Archiver les nouvelles preuves sur un autre support avec leurs
propres ancres. Decision invariable : REVIEW_ONLY_BLOCKED, tous les GO false.
