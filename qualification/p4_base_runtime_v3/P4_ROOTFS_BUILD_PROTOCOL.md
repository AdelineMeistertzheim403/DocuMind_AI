# Procedure P4 rootfs v3 - hors ligne et review-only

**Revision BLOCKED. Les sections d'assemblage et d'execution sont une
specification pour une autorisation future, pas des commandes a lancer.**

## V0 - transfert, avant toute constitution du rootfs

Suivre TRANSFER.md ; verifier d'abord le SHA256SUMS externe via son ancre
independante, puis l'archive et le manifeste interne exact. Python hote
approuve >=3.11 ; packaging26.3 deja qualifie pour wheels.py. Les autres
nouveaux outils utilisent seulement la stdlib. Pas d'installation.

Definir PY (absolu), PAQUET (extraction), ANCRE_PAQUET (recue) et E
(evidence absolue neuve hors tout historique, parent existant).
Executer individuellement et conserver les retours numeriques :

```sh
umask 077
mkdir -m 0700 -- "$E"
"$PY" -I -B "$PAQUET/common.py" verify "$PAQUET" --anchor "$ANCRE_PAQUET"
"$PY" -I -B "$PAQUET/record.py" --out "$E/wheels-command" --timeout 120 -- \
  "$PY" -I -B "$PAQUET/wheels.py" \
  --inventory "$PAQUET/inputs/DEPENDENCIES_OBSERVED.json" \
  --wheel-dir "$PAQUET/inputs/wheels" --out "$E/wheels.json"
mkdir -m 0700 -- "$E/review"
"$PY" -I -B "$PAQUET/record.py" --out "$E/native-command" --timeout 120 -- \
  "$PY" -I -B "$PAQUET/review.py" --root "$PAQUET" --out-dir "$E/review"
```

Le dernier retour attendu est **2/BLOCKED**, pas un PASS build. Comparer
les trois JSON aux rapports livres. Aucun script ne doit ecrire dans
le paquet scelle. Ne pas masquer les retours par `|| true`, reutiliser E
ou passer a la suite en cas de refus, interruption ou retour inconnu.

## V1 - ARRET AVANT ASSEMBLAGE et AVANT BUILD

Recevoir les materiaux detailles dans P4_BASE_PROVENANCE.md dans une
nouvelle livraison. Aucun acces reseau Debian, apt/pip download,
docker pull, copier-coller des libs hote ou collecte de donnees reelles.
La seule etiquette Debian13 ou presence d'un SONAME n'est pas une preuve.

Faire examiner un plan exact de selection : paquets/versions/arch/hashes,
sources CPython, toolchain, fichiers et liens attendus, licences,
dependencies de paquets et graphe ELF. Si un composant est absent,
garder BLOCKED ; ne pas substituer une revision au moment du build.

Une collecte future de P3 demande un mandat explicite de lecture seule
et une copie/export autorise sans toucher aux images/conteneurs anciens.
Elle est **hors execution de cette preparation**. Ne pas reconstituer
les9771 hashes depuis le seul nombre ni reutiliser le controle historique
comme preuve du nouveau rootfs.

## V2 - specification d'assemblage offline futur

1. Namespace neuf `p4-rootfs-v3-*`, hors r3/P3/v1/v2 et preuves anciennes.
   Aucun hardlink/reflink mutable partage avec ces sources.
2. Verifier chaine des index et chaque .deb avant toute extraction.
   Inspecter les membres/chemins/liens et scripts avec outils approuves.
   Extraire chaque paquet dans un espace distinct ; ne pas executer
   maintainer scripts ni dpkg -i. Une extraction brute ne fait pas une
   installation Debian : reproduire explicitement les seules
   configurations necessaires, chacune justifiee et inventoriee.
3. Fusion par liste de chemins approuvee, sans suivi de symlink vers
   l'hote, sans collision silencieuse. Traiter usr-merge et les liens
   absolus **dans la racine virtuelle**. Interdire sockets, devices,
   FIFO, setuid/setgid, capabilities et ACL/xattrs non approuves.
4. Installer le runtime CPython3.11.18 qualifie a son prefix fige.
   Aucun backend/entrypoint Docnelo, .env, cache pip/apt, cle,
   donnee restauree ou venv hote. Fermer tous les lib-dynload retenus.
5. Conserver chargeur et glibc coherents ; inclure les vraies DSO de
   compatibilite requises. Ne pas simuler libdl/libpthread/librt avec
   des symlinks vers libc. Verifier ld cache/config/search paths ou
   leur absence intentionnelle, pas seulement `find ... lib*.so*`.
6. Tracer paquet/membre source -> chaque fichier SHA final, liens,
   modes et UID/GID. Toute transformation doit etre approuvee.
   Fixer un epoch entier approuve pour les mtimes des fichiers,
   symlinks et repertoires ; ordre reproductible et aucune pycache.
7. Geler la racine et sa source sous-jacente en lecture seule,
   proprietaire/operateurs controles, sans redacteur concurrent.
   Faire l'inventaire ci-dessous vers E, pas dans le rootfs.

```sh
"$PY" -I -B "$PAQUET/record.py" --out "$E/rootfs-command" --timeout 120 -- \
  "$PY" -I -B "$PAQUET/rootfs_check.py" \
  --rootfs "$NOUVEAU_ROOTFS_P4" --out "$E/rootfs.json"
```

rootfs_check.py exige Linux et une racine `p4-rootfs-*`. Il ne modifie
ni n'execute ses fichiers. Il refuse liens externes non resolus, cycles,
hardlinks externes, xattrs et fichiers speciaux ; il ne constitue pas un
snapshot atomique. La source doit rester gelee pendant le controle.
Les liens absolus sont resolus dans la racine virtuelle, jamais sur
le filesystem hote. Aucun fallback hote.

L'inventaire fournit SHA, modes, UID/GID, mtime_ns, groupes hardlinks,
symlinks et ELF/dynsym/versions. La liste de candidats SONAME recursive
est volontairement **non resolutive** : ce n'est pas un emulateur glibc.
Les comparaisons de symboles par candidat sont directes, pas un jugement
d'echec ABI si une DSO de compatibilite delegue au scope global.
Un rc0 signifie inventaire produit, pas fermeture native PASS.

## V3 - revue native recursive obligatoire

Pour le Python, son PT_INTERP, libpython, chaque extension et fournisseur
de DT_NEEDED : reconstruire chemins de recherche reels, RPATH herite,
RUNPATH direct, cache/config, SONAME et symlinks dans cette racine.
Traiter chaque fournisseur recursivement jusqu'a un point fixe et
consigner chaque arrete -> chemin/SHA/package/version. Aucun nom absent
ne peut etre absorbe par la phrase "c'est integre a glibc".

Verifier verneed/verdef et symboles nommes + versions dans le scope
global reel (Python inclus), bindings faibles/forts, TLS, relocations,
IFUNC et ISA CPU. Un noeud GLIBC_2.2.5 exporte sans le symbole attendu
ne prouve rien ; inversement une DSO compat delegue parfois a libc.
Les symboles non versionnes ne peuvent pas etre attribues a un DT_NEEDED
par simple correspondance de nom de bibliotheque.

Utiliser outils statiques deja approuves (ex. readelf sur des bytes
verifies) et une revue de resolution du chargeur ; ne pas executer ldd
ou le chargeur d'un binaire non qualifie. Le scanner Python livre
apporte les tables, pas une preuve complete de recherche/relocation.
Tout besoin dlopen/NSS/locale/certificats necessaire aux probes doit
etre inventorie, ou son exclusion explicitement demontree.

## V4 - specification image et identite, apres autorisation build distincte

Aucun Dockerfile executable n'est delivre. La recette future pourra
utiliser scratch et un unique payload filesystem integral, jamais FROM
P3 ni un tag flottant. Le payload doit conserver les metadonnees definies,
y compris la racine logique `.`. Le choix COPY/ADD/format attend les
preuves du builder et de cette equivalence ; ne pas copier aveuglement
le Dockerfile historique.

Qualifier frontend/driver deja locaux, zero registry/builder pull,
absence de #syntax distant et reseau des etapes coupe. --network=none
et --pull=false ne suffisent pas seuls a prouver zero resolution reseau.
Fixer contexte, toolchain, epoch, mode, ordre et racine. Pas de secrets,
ONBUILD, VOLUME, port, healthcheck ou entrypoint applicatif.

Apres build autorise, capturer logs/retour, iidfile/ID config complet,
inspect image, archive Docker-save et SHA. Ne pas create/start pour cette
comparaison statique. Le controleur accepte **une image, une couche
filesystem non compressee**, type scratch, sans whiteout/PAX. Il ne
reconstruit pas un overlay multicouche. Un format non supporte est
INCOMPLETE/NO-GO, pas un ecart que l'on ignore.

```sh
"$PY" -I -B "$PAQUET/record.py" --out "$E/image-command" --timeout 120 -- \
  "$PY" -I -B "$PAQUET/image_check.py" --archive "$EXPORT_P4" \
  --archive-sha256 "$EXPORT_SHA" --image-id "$IIDFILE_ID" \
  --prepared "$E/rootfs.json" --out "$E/image-identity.json"
```

Le controle recalcule hash archive, config ID et diff ID sur les bytes
de la couche, puis compare **ensemble exact** des chemins, SHA/taille,
modes, UID/GID, mtimes, symlinks et hardlinks au rootfs prepare.
Une racine `.` absente, parent implicite ou metadata inconnue interdit
un PASS d'equivalence. Atime/ctime, numeros inode/device de l'hote et
organisation physique du filesystem ne sont pas des metadonnees image.
Pas de promesse d'egalite bit-a-bit entre deux exports Docker sans preuve
distincte ; l'identite de config, le diff ID, le manifest digest OCI et
le hash de l'archive ne sont pas interchangeables.

## V5 - ARRET AVANT CREATE et ARRET AVANT START

Apres revue de l'image seule, obtenir une autorisation **create**
distincte pour un namespace synthetique P4 neuf. ID immuable et pull
never, utilisateur/GID non-root, groupe lecteur explicite, network none,
aucun port ni socket Docker, cap-drop ALL, no-new-privileges, racine RO,
limites memoire/CPU/swap/processus. Candidat complet RO /candidate,
controle synthetique RO /run/documind-control, nouvelle evidence0700 RW
/evidence et /tmp tmpfs. Aucun container historique concerne.

Inspect obligatoire du conteneur created jamais demarre : tous les
montages, sources/aliases/RO/RW, USER/groupes, limites, environment et
entrypoint Python explicite. Autorisation **start** ulterieure distincte.
Pas de docker run de diagnostic, meme pour --version ou pip check.

Apres autorisation adaptee, probes isolees : Debian/CPython3.11.18,
SOABI/sysconfig, fermeture effectivement chargee et SHA, imports stdlib
ssl/sqlite3/ctypes/zlib/bz2/lzma et modules P4, pip25.2/bootstrap wheel-only,
pip check et inventaire43 exact. Pas d'installation reseau ou sdists.
Le bootstrap doit lui aussi avoir un plan et une autorisation propres ;
ce controle ne suppose pas que tous les tests post-build etaient deja
possibles avant le build.

Tests ASGI standard puis beta_lite selon les outils/protocoles r3/v1
figes, sans les reecrire : ASGITransport sans serveur, RCD_EVENT,
publication atomique apres startup, probes closed/sentinel,503 de
quarantaine distincts des403 Lite, arret JSON controle et collecte
complete. Aucun P1/P2/P3/D11/H1 relance. Un EOF, refus, interruption,
code retour perdu ou probe manquante ne devient jamais PASS.
