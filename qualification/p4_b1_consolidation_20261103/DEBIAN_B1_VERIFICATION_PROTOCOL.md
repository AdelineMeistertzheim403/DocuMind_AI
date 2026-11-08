# Verification Debian du complement B1

**Lecture de preuves existantes seulement. Aucun Docker ni acces reseau.
Pas de nouvelle qualification P3 ou de cloture automatique B1.**

## D0 - livraison et nouvelle evidence

Suivre TRANSFER.md ; verifier d'abord les outils par ancre externe.
Definir PY (Python hote approuve >=3.11 absolu), PAQUET (extraction),
ANCRE_PAQUET (ancre recue), E (nouveau chemin absolu d'evidence, parent
existant, hors paquets scelles et preuves historiques).

```sh
umask 077
mkdir -m 0700 -- "$E"
"$PY" -I -B "$PAQUET/common.py" verify "$PAQUET" --anchor "$ANCRE_PAQUET"
```

Le dossier E doit etre nouveau ; s'il existe ou si un controle echoue,
stopper. Tous les nouveaux resultats vont dans E, pas dans P3/v3.
Les tests locaux du complement ne relancent aucune campagne historique.

## D1 - controle limite des copies de preuves

PREUVES_B1 est un dossier deja disponible en lecture seule contenant
les copies des quatre fichiers nommes dans P4_B1_OBSERVED_REFERENCES.json :
Dockerfile, ROOTFS-SHA256SUMS, ROOTFS-METADATA.txt, p3-layer-comparison.json.
Ne pas y ecrire, ne pas dereferencer un symlink vers une autre source.
Ne pas transferer de rootfs, archive entiere ou donnees restaurees juste
pour ce controle. L'approvisionnement de ces copies doit etre trace.

```sh
"$PY" -I -B "$PAQUET/record.py" --out "$E/proof-command" --timeout 120 -- \
  "$PY" -I -B "$PAQUET/evidence_check.py" \
  --proof-directory "$PREUVES_B1" --out "$E/proof-hashes.json"
```

Retours :0 = hashes des quatre copies et syntaxe JSON conformes
**seulement** ;1 = hash de preuve transferee different ;2 = manque,
format non pris en charge, lecture impossible ou examen incomplet.
Une preuve modifiee interdit son utilisation ; ce n'est pas
automatiquement une divergence des fichiers P3 eux-memes.

Le schema du rapport B1 brut n'a pas ete fourni au preparateur.
Le controleur ne devine pas ses cles et ne deduit pas les compteurs
d'un format inconnu. Il garde BLOCKED et formally_closed=false meme0.
Il n'execute ni Dockerfile, ni comparateur historique, ni binaire P3.
Il ne relance pas sha256sum sur9771 fichiers et ne lit pas l'archive image.
Une interruption du controle ou un retour perdu reste INCOMPLETE :
pas de `|| true`, reutilisation de sortie ou promotion en PASS.

## D2 - revue des captures existantes, pas une reexecution

Lire le rapport brut et le code/version/hash exact du comparateur dans
leur contexte de capture. Verifier C1-C4 du rapport de qualification :
couverture exhaustive des chemins/bytes, definitions de compteurs,
normalisation, completude, retour numerique et politique de retour.
Un code non-zero pour differences de metadata n'est pas traduit en0.
Le code0 deja rapporte pour sha256sum doit etre lu dans sa capture
existante avec la bonne ancre de manifeste corrige.

Verifier depuis les captures config/couche/archive existantes leurs
liaisons aux trois identites et la chronologie de la source figee.
Pas de docker image save/inspect supplementaire si ces preuves suffisent,
et surtout pas de build/create/start/run/pull/import.
Confirmer la nature non compressee du flux portant le diff ID, ou la
decompression verifiee dans la methode existante.

Ne pas changer des UID/GID, recreer la racine `.` dans l'archive, refaire
le comparateur v3 strict ou demander des scans metadata hors du scope
contenus. Si une piece manque, documenter son nom et son role dans
C1-C4. Chercher la capture deja conservee ; seulement si la lacune est
irrecuperable, demander une collecte ciblee separement autorisee.
Aucune campagne P1/P2/P3/D11/H1 n'est relancee.

## D3 - decision formelle hors du paquet historique

Apres revue habilitee complete, creer dans une nouvelle evidence un
acte de revue C5 avec scope **contenus seuls**, ancres et references
des captures/code, explication des10334 differences UID/GID et de `.`,
limitations metadata, role/ID/date/attestation selon politique.
Ce n'est ni une provenance inventee ni une approbation de base P4.

L'acte pourra dire CLOSED_CONTENTS_ONLY seulement si toutes les
conditions sont verifiees ; sinon INCOMPLETE ou FAIL au scope concerne.
Il devra conserver statut general BLOCKED et tous les GO false.
Sceller ces nouvelles preuves selon la procedure du laboratoire,
sans ajouter de fichier ni changer un octet dans les preuves anciennes.

Continuer ensuite la preparation B2-B7 du document dedie. Un PASS de
transfert, un code0 de hash ou la future cloture B1 ne franchit aucun
des points d'arret build, create et start.
