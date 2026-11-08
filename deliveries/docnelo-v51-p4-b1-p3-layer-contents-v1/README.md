# P4 B1 - P3 Layer Regular Contents v1

**Decision generale : REVIEW_ONLY_BLOCKED. Code retour general : 20.**
formal_b1_contents_closed=false ; tous les GO false.

Livraison independante, Python 3.11 et bibliotheque standard, sans installation,
reseau, Docker, extraction de couche ou execution du rootfs.
Utiliser **layer_contents.py**, pas comparator.py, pour la mesure limitee.

| Perimetre | Decision possible |
|---|---|
| A - chemins et SHA-256 des fichiers reguliers de la couche P3 | NOT_ESTABLISHED, REGULAR_LAYER_CONTENTS_DIFFERENT ou REGULAR_LAYER_CONTENTS_IDENTICAL_ONLY |
| B - conformite stricte de toute l'archive | BLOCKED, status ERROR, returncode 20, blob auxiliaire non approuve |
| C - qualification base P4 et provenance | Non accordees |

La mesure A peut etablir l'identite des 9 771 contenus reguliers, mais pas
l'egalite des repertoires, UID/GID, modes, liens ou attributs non inventories.
La racine `.` absente demeure une difference. Les divergences sont publiees
integralement, sans neutraliser les metadonnees.

Le refus v2 est conserve avec ses ancres de preuves rapportees. Une copie
**identique** du noyau strict v2 (comparator.py) est livree et testee, sans
modifier la livraison v2. Sa verification sur l'inventaire externe complet
doit toujours refuser le blob eec772146... non rattache.
Seul le graphe principal explicitement reference et ancre peut identifier
la couche pour A ; le blob auxiliaire reste present dans le rapport B.
Aucun autre blob supplementaire ou reference ambigue n'est accepte.

Lire DESIGN_SECURITY.md et EXIT_CODES.md. DEBIAN_PROTOCOL.md fournit les
arrets et controles de recepisses ; TRANSFER.md le transfert physique.
Le code, les tests et documents sont figes dans SHA256SUMS, ancre par le fichier
externe adjacent `docnelo-v51-p4-b1-p3-layer-contents-v1.anchors.json`.

Les octets historiques ne sont pas disponibles ici. Les confirmations Debian
13 et empreintes fournies par l'operatrice restent des references rapportees,
pas un nouveau rejeu local. C5 exige une revue independante autorisee.
