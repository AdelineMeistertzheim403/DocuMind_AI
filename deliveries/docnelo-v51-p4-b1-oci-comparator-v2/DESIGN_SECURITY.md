# Conception et securite - P4 B1 OCI Comparator v2

## Perimetre et provenance

Outil neuf, independant des comparateurs et outils B1 existants. Aucune
importation du code applicatif, aucun sous-processus dans comparator.py.
record_tests.py lance uniquement l'interpreteur courant et unittest avec des
arguments fixes, jamais un shell ni une commande fournie par une archive.
seal.py n'ouvre que la nouvelle livraison pour generer son manifeste.

Les ancres P3 sont constantes dans comparator.py, sans option CLI permettant
de les remplacer. La fonction interne de test accepte des ancres de fixtures ;
ce n'est pas une commande de qualification P3. Le fichier DECISION.json
separe les references rapportees des observations locales.

Le controle D1 rapporte PASS_ANCHORED_PROOF_BYTES_ONLY ne clot pas B1.
Le rapport historique D2 n'atteste pas le code retour ni les octets du code
ancien. La recherche historique a rencontre un dossier inaccessible :
pas de modification de permissions et aucune allegation d'exhaustivite.

## Algorithme et couverture

1. Lire les deux inventaires limites a 16 MiB chacun ; verifier chaque SHA-256
   avant parsing. Formats ASCII LF stricts : `TYPE MODE UID:GID CHEMIN` avec
   types f/d, mode octal de 3-4 chiffres et identifiants decimaux ; et
   `SHA256<deux espaces>CHEMIN`, hash hexadecimal minuscule de 64 caracteres.
   Aucun echappement GNU, CRLF ou type inconnu n'est interprete implicitement.
2. Normaliser uniquement en memoire un prefixe `./` et, pour les repertoires
   TAR, un slash terminal. La racine `.` est exclusivement un repertoire.
   Rejeter doublons apres normalisation, chemins absolus, `..`, composants
   vides ou `.`, controles, backslash, deux-points, caracteres non ASCII et
   whiteouts. Verifier tous les parents dans l'inventaire source.
3. Ouvrir l'archive reguliere en lecture seule et conserver le descripteur.
   Authentifier le SHA-256 de l'archive complete avant toute lecture TAR.
4. Premier parcours sequentiel : verifier chaque checksum d'en-tete TAR ;
   hacher chaque payload regulier ; indexer les chemins, types et tailles.
   Pas de getmembers(), extraction, copie de couche ou lecture non bornee.
   Seuls les JSON/metadata sont tamponnes, 16 MiB par entree, 64 MiB cumules.
   Les couches TAR, meme petites, sont lues par blocs et non tamponnees.
5. Valider exactement un manifeste Docker, une config Linux amd64, une seule
   couche non comprimee et un seul diff_id. Le SHA de la configuration est
   l'image ID attendu ; celui de la couche brute est le diff_id attendu.
   LayerSources absent, null ou vide reste admis pour les archives sans
   descripteur. S'il est non vide, exiger exactement une cle egale a
   `sha256:<hash mesure de la couche>` et un objet comprenant exclusivement
   digest, mediaType et size. Le digest doit correspondre a cette cle,
   mediaType doit etre `application/vnd.oci.image.layer.v1.tar` et size doit
   etre un entier JSON (ni booleen, ni flottant, ni chaine), positif ou nul,
   egal a la taille du payload TAR externe effectivement present et hache.
   Les cles/champs inconnus, manquants ou repetes, references supplementaires
   et divergences sont des erreurs 20. Le descripteur valide est expose dans
   image_binding ; aucune nouvelle entree d'archive n'est reclamee par lui.
   RepoTags n'est jamais une preuve d'identite. Si presents, repositories
   et le graphe OCI index/manifest/descriptors sont verifies et rattaches
   aux memes octets (digests et tailles). Les blobs sont aussi controles
   contre leur nom digest. VERSION legacy = 1.0 ; json legacy doit etre un
   objet valide, sans revendication supplementaire de provenance.
   Tout fichier externe non rattache et tout repertoire non parent d'un
   fichier rattache sont refuses. Les parents implicites TAR sont admis.
6. Second parcours sequentiel de l'archive complete : parser la couche
   selectionnee via une vue bornee sur son payload, sans extraction.
   Hacher chaque fichier regulier ; conserver ses metadata et chaque lien.
   Rehacher l'archive complete pour chacun des deux parcours, comparer les
   inventaires externes et l'identite/stat du descripteur avant/apres.
7. Comparer tous les chemins attendus, manquants et supplementaires.
   Comparer contenu, type, mode (y compris bits speciaux), UID/GID separement.
   Les hardlinks sont resolus en memoire pour le contenu seulement :
   leurs propres modes/UID/GID restent intacts et leur type/lien est signale.
   Cycles, cibles non regulieres, chemins dangereux et ancetres non
   repertoires sont refuses. Aucun lien d'archive n'est suivi sur l'hote.

Chaque parcours exige deux blocs nuls de fin, un trailer entierement nul et
aligne, et un padding de payload nul. Les TAR concatenes, queues cachees,
troncatures, doublons, fichiers speciaux/sparse et payloads sur non-reguliers
sont refuses. Maximum 100 000 en-tetes physiques par TAR ; graphe OCI borne.

PAX local : path/linkpath et mtime/atime/ctime seulement, attributs uniques.
Les noms GNU longs sont pris en charge et comptabilises. Les overrides
conflictuels et extensions orphelines sont refuses. Extensions globales,
xattrs/ACL/capabilities PAX ou autres attributs non supportes provoquent
CONTROL_INCOMPLETE, pas une reussite silencieuse.
Le rapport compte tous les en-tetes physiques, les entrees logiques, les
extensions (attributs et hashes), le trailer et chaque chemin logique.
`all_bytes_accounted` n'est emis qu'apres un parcours complet.

## Mesures et limites

Les 9 771 chemins reguliers et les 10 335 entrees metadata doivent correspondre
aux inventaires authentifies. Ces compteurs ne remplacent jamais l'egalite des
ensembles ni la verification de chaque SHA-256.

`regular_contents_equal` exige les memes chemins TAR de type regulier et les
memes empreintes. Un fichier devenu hardlink reste une difference de type,
meme si ses octets resolus sont identiques. Les liens sont exposes separement.
Les tailles TAR sont mesurees ; leur egalite au rootfs ne peut pas etre
directement controlee car la taille source n'est pas inventoriee.

La racine absente est `root_directory.absent_from_layer=true`, jamais un
missing_regular. Elle suffit au code 10 et empeche l'egalite des metadata
controlees. Les autres divergences ne sont pas supprimees. Les 10 334
divergences UID/GID historiques sont une reference, pas un compteur force :
le nouvel outil publie exclusivement celles mesurees.

Timestamps TAR/PAX, uname/gname et topologie hardlink sont exposes, mais
incomparables aux inventaires source. Xattrs, ACL, capabilities, tailles
source et topologie inode source ne sont pas controles. Le rapport indique
toujours `complete_metadata_equality_established=false`.

La comparaison porte sur les inventaires historiques, pas sur le rootfs
vivant. Le code 0 historiquement rapporte pour sha256sum sur Debian reste
une observation distincte fournie par l'operatrice. Aucune signature n'est
verifiee ; SHA-256 ne prouve pas l'auteur ni l'origine d'une preuve.

## Menaces et controles d'exploitation

L'archive n'ecrit aucun fichier ; les seules ecritures sont des rapports
JSON/logs dans un repertoire neuf hors livraison. Les entrees hote doivent
etre regulieres, avec composants sans symlink. Les preuves utilisent mkdir
exclusif et open xb ; les sorties existantes ne sont jamais remplacees.
L'operatrice doit choisir un parent de preuves independant non modifiable par
un tiers, des entrees stabilisees et une livraison verifiee, sans auteur
concurrent. Ces controles ne constituent pas une isolation contre un
administrateur hostile ni une garantie atomique contre toutes les courses
de namespace. Un fsync de fichier ne garantit pas a lui seul la durabilite
du repertoire en cas de coupure : archiver les preuves hors machine.

Verifiez l'ancre du manifeste avec l'outil Debian deja approuve **avant**
d'executer le Python livre. L'auto-verification du code controle les fichiers
sur disque, pas la confiance initiale dans un interpreteur ou un outil SHA
compromis. Un fichier externe adjacent n'est pas un canal de confiance :
remettre son empreinte independamment, sur support physique controle.
Ne pas relancer seal.py sur Debian pour remplacer une ancre.

Les lectures sont bornees en memoire ; les fichiers d'image ne le sont pas
en taille/temps. L'operatrice peut fixer une limite de temps avec timeout.
Une interruption ou un disque plein peut laisser started.json sans receipt
complet : controle incomplet, aucun PASS. Ne pas effacer cette tentative.

Ce document est une analyse de conception, pas un audit independant certifie.
Les tests negatifs et positifs ne qualifient pas l'archive historique absente
localement, Debian 13 de l'operatrice ou la securite d'execution du runtime.
