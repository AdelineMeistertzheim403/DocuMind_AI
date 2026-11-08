# P4 B1 OCI Comparator v2

**Decision generale : REVIEW_ONLY_BLOCKED. Tous les GO restent false.**

Livraison autonome, uniquement Python **3.11** et bibliotheque standard.
Ni Docker, ni reseau, ni extraction d'archive image, ni execution du rootfs.
Les trois entrees sont ouvertes en lecture seule : archive Docker-save deja
existante, ROOTFS-SHA256SUMS corrige et ROOTFS-METADATA.txt historiques.
Aucun inventaire n'est converti, regenere ou remplace.

Le comparateur authentifie les octets avant leur interpretation, rattache
manifest/configuration/couche a l'image attendue, puis compare les ensembles
de chemins et les empreintes, pas seulement les compteurs. Le TAR est parcouru
sequentiellement, y compris ses extensions, bourrages et octets de fin.
Les rapports contiennent les chemins, empreintes et differences exhaustives.

Lire DESIGN_SECURITY.md, EXIT_CODES.md et DEBIAN_PROTOCOL.md avant utilisation.
TRANSFER.md decrit le transfert physique hors ligne et l'ancrage independant.
SHA256SUMS fige **tous** les fichiers livres, dont comparator.py et ses tests.
L'ancre de ce manifeste est remise dans le fichier externe adjacent
`docnelo-v51-p4-b1-oci-comparator-v2.anchors.json`.

Cette v2 valide strictement le descripteur LayerSources observe dans le
manifeste P3 : cle unique, digest, mediaType TAR non comprime et taille
identiques a la couche effectivement presente et hachee. Les champs ou
references supplementaires sont refuses. Voir REVISION_REPORT.md.
La livraison v1 et son manifeste ne sont ni modifies ni re-scelles.

Les tests utilisent exclusivement des fixtures synthetiques. Les mesures
P3/D1/D2 fournies par l'operatrice restent des references rapportees jusqu'au
rejeu sur sa VM Debian 13. Aucun resultat de ce nouveau comparateur sur les
octets historiques n'est pretendu ici. Le code retour et le hash de l'ancien
comparateur demeurent inconnus.

L'absence de `.` et les divergences UID/GID ne sont pas neutralisees.
Une identite des contenus ne prouve ni une egalite complete des metadonnees,
ni la provenance cryptographique, ni la qualification runtime.
La revue C2-C4 utilise ce dossier ; C5 exige une decision distincte autorisee.
