# Provenance requise - base P4 v3

**Aucun fichier systeme approuve n'est fourni. Statut BLOCKED.**

## Ce qui est identifie

Les10 SONAME, leurs consommateurs et exigences GNU sont observes dans
les43 wheels preserves. Leurs SHA et les empreintes des ELF sont dans
les JSON livres. L'origine immediate de ces wheels est le paquet v2
scelle ; cela ne cree pas une nouvelle approbation de leurs editeurs.
Les verifications PyPI PyYAML/pip de v2 restent de la corroboration
HTTPS historique, pas des signatures. Aucun GET n'est refait en v3.

common.py, record.py, wheels.py et preserve.py sont des copies exactes
de fichiers v2, avec provenance et SHA dans INPUTS.json. Les nouveaux
scripts ELF/rootfs/image sont locaux a v3. Aucun import depuis une
ancienne livraison n'est requis pour les utiliser.

## Chaine Debian a apporter, pas a telecharger dans le laboratoire

Depuis une source d'approvisionnement autorisee distincte :

1. Distribution/suite Debian13 approuvee, architecture amd64, date de
   snapshot et URL/origine consignees, pas seulement une etiquette.
2. InRelease signe ou Release + Release.gpg, trousseau Debian et
   empreintes des cles obtenus/valides par canal independant.
   Verifier signature, statut des cles, date/validite de Release.
   Une archive historique expiree exige une decision documentee ;
   ne pas neutraliser silencieusement les controles.
3. Index Packages exact couvert par Release (SHA et taille), puis chaque
   .deb selectionne couvert par Packages (nom, version Debian complete,
   architecture, Filename, Size, SHA256). Les .deb Debian ne sont pas
   supposes individuellement signes : la chaine est celle des index.
4. Control metadata de chaque .deb : Package, Version, Architecture,
   Source, Depends/Pre-Depends, copyright/license, scripts et contenu.
   Fermer aussi les dependencies de paquets, sans confondre cette
   fermeture avec la fermeture ELF ou celle des fonctionnalites stdlib.
5. Pour libc6:amd64, libgcc-s1:amd64, libstdc++6:amd64, zlib1g:amd64 et
   toute extension de selection : fichiers reguliers et liens exacts,
   SHA par fichier, SONAME, build-id si present, arch, versions requises
   et fournies. La revision exacte reste inconnue avant reception.
6. Associer chaque chemin final au paquet exact et au membre archive,
   ou a un resultat de build CPython trace. Tout ajout/configuration,
   suppression ou collision demande une justification signee/attestee
   selon la politique du laboratoire. Aucun hash n'est une signature.

Ne pas copier /lib, /usr/lib ou le venv du systeme hote. Un dpkg-query
sur l'hote ne prouve pas que le fichier copie est celui du paquet.
Ne pas melanger chargeur/libc issus de revisions ou racines differentes.

## CPython3.11.18

Deux voies possibles, aucune qualifiee ici :

- Runtime immutable accompagne de ses bytes, SHA, build recipe,
  configuration, compilateur/linker, dependencies et preuves d'origine.
- Source officielle CPython3.11.18 verifiee, signature/attestation si
  disponible et reconnue par la politique, archive/hash exacts, puis
  toolchain de build approuvee et complete offline.

Ne pas fabriquer de signature ou d'URL d'artefact qualifie. Le numero
3.11.18 du source ne prouve pas celui du binaire resultant. Capturer
sys.version, sys.implementation, SOABI, EXT_SUFFIX, sysconfig,
configure flags, build-id, fichier executable/libpython et lib-dynload.
Pas d'ensurepip non inventorie ; venv futur --without-pip et pip25.2
depuis son wheel hashe seulement, comme specifie dans v2.

Les dependencies de compilation ne vont pas automatiquement dans le
runtime. Inversement, libssl/libcrypto, libffi, bz2/lzma/sqlite/expat,
readline/ncurses et besoins NSS/locale doivent etre determines depuis
les vrais modules et usages retenus. Les noms proposes dans les JSON
ne valent pas selection/version de paquet validee.

## P3

Le controle9771 rapporte est un resultat operateur ; son manifeste et
son ancre doivent etre transmis separement pour reproduction. La copie
de travail autorisee devra etre neuve, sans hardlinks vers P3, preservee
en lecture seule. Pas de chmod, rsync --delete, remplacement de librairie,
execution de Python ou inspection contenant des secrets sur P3.
Le rootfs historique peut servir de comparaison, pas de source approuvee
par heritage. Aucun conteneur/image historique n'est touche.
