# Conception et securite - controle limite des contenus P3

## Identites independantes

Les constantes de layer_contents.py fixent avant toute lecture :

| Objet | SHA-256 | Taille |
|---|---|---|
| Archive Docker complete | ffec209c1b5eb3a8861e60585266c18069896adf05c8fe8f98c558d682351c2d | Mesuree |
| Configuration | bbe90dab376fcd41b3495cad1264c017323ed68ed0915c601ea5fd229cbf6abd | 835 |
| Manifeste OCI | c4c9b897d2e3dea6bbcc3da95b078ce5ffa556f5e4c52020a40da8be784ccc44 | 402 |
| Couche brute | 7b1b9ae269d164c3b88d386714f2def703acb15812a6d6f813c10064f57c766e | 322534912 |
| Blob non rattache, non approuve | eec772146db049680bf51af9758854bd4c210bff907cac5d73a10deec0775653 | 829 |
| Inventaire SHA-256 P3 corrige | a37f1847df7c7212c2d1b004e5ab3b0d654323a8ab2d425e20d89c551279527f | Mesuree |
| Metadata P3 | 64863f4ebc2aaddb717d83147e623e37942716728736afa40f5bd39d1083db36 | Mesuree |

Le SHA du manifeste est fourni independamment par l'operatrice, avec une
confirmation directe sur Debian (MANIFEST_HASH_EXIT=0 rapporte).
Le JSON formate fourni est une description du schema, **pas** les 402 octets
a rehacher. L'outil verifie les octets presents dans l'archive.

## Algorithme

1. Authentifier les deux inventaires avant parsing ASCII LF strict :
   `TYPE MODE UID:GID CHEMIN`, f/d uniquement, et
   `SHA256<deux espaces>CHEMIN`. Egalite exacte des ensembles reguliers entre
   les inventaires ; 9 771 fichiers et 564 repertoires attendus.
2. Authentifier toute l'archive avant interpretation TAR. Conserver son
   descripteur regulier en lecture seule. Aucune extraction ni execution.
3. Parcourir le TAR externe sequentiellement, hacher tous les fichiers
   (y compris le blob non rattache), verifier chaque nom blobs/sha256 contre
   son contenu et comptabiliser chaque entree, extension, padding et trailer.
4. Verifier les trois blobs principaux contre leurs constantes et tailles.
   Exiger le schema attendu et une seule reference explicite :
   index.json -> manifeste OCI ancre -> configuration/couche ancres.
   Les descriptors ne contiennent que mediaType/digest/size ; types JSON,
   tailles et mediaTypes exacts. Verifier egalement le Docker manifest.json,
   sa configuration, LayerSources et diff_id avec le noyau v2.
5. Fournir l'inventaire externe **complet** a docker_binding v2, inchange :
   conserver son refus 20 dans B.new_strict_binding_check. Cette observation
   est le controle de binding, pas une nouvelle execution du CLI v2 historique.
   Le recepisse historique v2 reste une reference distincte non remplacee.
6. Pour A uniquement, verifier la presence, le digest exact et la taille du
   seul blob auxiliaire historique ancre. Former une vue du graphe principal
   omettant **uniquement ce chemin constant**, puis verifier ce graphe via le
   noyau strict. Ce n'est pas une validation de l'archive complete : celle-ci
   reste code 20 et tous ses chemins et anomalies restent dans le rapport.
   Aucun wildcard, option de tolerance generale ou autre blob non rattache.
   Des references/descriptors/entrees supplementaires sont refuses.
7. La couche est selectionnee seulement par les references explicites
   concordantes Docker/OCI et ses ancres, jamais par un nom trouve au hasard
   ou par le contenu du blob auxiliaire. Second parcours de toute l'archive :
   vue bornee sur la couche, parser et hacher chaque fichier en streaming.
   Rehacher l'archive complete pour les deux parcours, comparer les inventaires
   externes, les couvertures et le stat du descripteur avant/apres.
8. Comparer tous les ensembles de chemins reguliers et chaque SHA-256.
   Publier manquants/supplementaires, contenu, type, permissions, UID/GID,
   liens et repertoires, y compris la racine absente. Les metadata des
   hardlinks ne sont pas remplacees par celles de leur cible.

## Refus et bornes

Le noyau copie reste octet pour octet identique a comparator.py v2,
SHA-256 `63225aec80a257a246ca492acbaf1dcc73c66a0c49123ffaffc9ad73ee6c383a`.
Ses tests preexistants sont conserves. Aucun correctif ou re-scellement v1/v2.

Chemins absolus, traversal, composants ambigus, backslash, controles,
whiteouts, doublons normalises et fichiers speciaux/sparse sont refuses.
Les cibles de liens dangereuses et cycles sont refuses sans lien suivi
sur l'hote. Les JSON a cles repetees sont refuses. Seule une couche TAR brute
Linux amd64 est supportee. PAX local path/linkpath/timestamps et GNU longnames
sont controles et comptabilises ; xattrs/ACL/capabilities PAX inconnus et
extensions globales arretent la mesure comme incomplete.

Chaque TAR exige checksums valides, padding nul, deux blocs de fin nuls,
trailer nul aligne et aucune queue cachee. Maximum 100 000 en-tetes par TAR.
Lectures de couche par blocs, jamais tamponnee/extrait sur disque ; JSON
limite a 16 MiB par entree et 64 MiB cumules, inventaires a 16 MiB chacun.
Limites de temps et disque restent du ressort de l'operatrice.

## Interpretation et limites

REGULAR_LAYER_CONTENTS_IDENTICAL_ONLY exige les memes chemins **reguliers**
et hashes que l'inventaire. Un hardlink ne remplace pas implicitement un
fichier regulier. Des differences de repertoires ou metadata peuvent coexister
avec A identique ; elles restent listees. Les repertoires ont leurs comptes
et listes propres, la racine `.` un indicateur distinct (jamais fichier
regulier manquant). Aucun compteur de divergences historique n'est force.

Les inventaires ne fournissent pas tailles source, timestamps, xattrs,
ACL, capabilities ou topologie inode/hardlink. Les metadata TAR sont exposees
mais non considerees egales sur ces attributs. Toujours
complete_metadata_equality_established=false. Le rootfs vivant n'est pas lu.
L'identite A n'est ni une egalite de couche complete, ni une signature,
ni une attribution de provenance, ni une qualification runtime/base P4.

Le blob auxiliaire n'est jamais approuve : son auto-coherence SHA-nom
ne cree aucun rattachement cryptographique. Sa taille/digest constants
servent seulement a identifier l'anomalie connue, pas a lui donner confiance.

Preverifier SHA256SUMS avec l'outil Debian approuve et une ancre remise par
canal physique independant avant execution du Python livre. La verification
sur disque n'atteste pas un interpreteur hostile ou une concurrence hostile.
Entrees stabilisees, parents de preuves controles, sans symlinks ni auteur
concurrent ; sorties exclusives hors sources/livraison. Pas d'ecrasement.
Une interruption/disque plein peut laisser une tentative incomplete :
conserver les traces et arreter. fsync de fichier seul ne prouve pas la
durabilite des repertoires lors d'une coupure.

Analyse de conception, pas audit certifie. Aucun GO, aucune cloture C5.
