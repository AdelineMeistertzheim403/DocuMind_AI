# Docnelo V5.1 - P4 Base Runtime v3

**Decision : BLOCKED. Review-only. Aucun GO build, create, start ou production.**

Cette livraison est nouvelle et independante. r3, P4 v1/v2, P3 et les
preuves historiques ne sont pas modifies. Aucune commande Docker, aucun
telechargement, aucune installation, aucun acces aux donnees restaurees
reelles pendant cette preparation. Les archives factices des tests sont
des fichiers de test, pas des images construites ou chargees par Docker.

## Entrees disponibles et limite determinante

Le paquet v2 local a ete verifie avec son SHA256SUMS
`2c40bfed4b6662a8abd6cce9197b790e62722ba0d5d32b64d2b251335dbf7cbb`.
Son inventaire43 conserve exactement l'ancre
`60f0d9f0b668409bba75914b5ef40027036c54ac69de96b05b8e813032813c20`.
Les43 wheels sont copies bytes-identiques dans cette livraison, sans
dependance d'execution aux outils des anciens paquets.

Le rootfs P3 corrige, son manifeste9771 et l'archive de son image
**n'ont pas ete fournis a ce poste de preparation**. Leur chemin Debian,
les octets des bibliotheques, versions et empreinte du manifeste ne
sont pas disponibles ici. Une recherche de noms de materiaux dans
l'espace de travail et les inventaires v2 n'a pas identifie ces entrees.
Cela ne nie pas leur presence sur la VM.

L'ID P3 fourni par l'operateur est
`sha256:bbe90dab376fcd41b3495cad1264c017323ed68ed0915c601ea5fd229cbf6abd`.
FROM scratch, COPY rootfs, USER65534:65534, entrypoint Python3.11 et
controle SHA des9771 entrees sont des **constats operateur rapportes**,
pas de nouvelles observations locales. Python3.11 ne prouve pas3.11.18.
L'ID de config ne fournit pas les octets ni leur provenance.

## Resultats nouveaux, scopes statiques

| Controle | Resultat | Limite |
|---|---|---|
|43 wheels | SHA/taille/RECORD/metadonnees/tags reverifies | ABI cible non executee |
|32 ELF | ELF64 x86_64, dynsym, GNU verneed/verdef/versym relus | Pas un chargeur |
|31 liens prives wheels |1223 references de symboles versionnes coherentes, aucune absence forte directe ni version manquante | Recherche globale/relocations non prouvees |
|89 liens systeme |10 SONAME avec consommateurs, versions et imports nommes | Aucun fournisseur systeme fourni |
|Autres imports dynsym |2210 references non versionnees sans attribution de scope | Inclut API CPython et autres symboles ; pas2210 erreurs |
|Rootfs P3 |4 noms declares presents,6 absents | Aucun hash/ELF/provenance de ces fichiers ici |
|Rootfs P4 |Procedure et controleurs prepares | Aucun rootfs constitue, aucun ID image P4 |

`P4_NATIVE_CLOSURE_REVIEW.json` contient les symboles/exportations,
versions et SHA par ELF, puis les31 comparaisons directes et10 groupes
systeme. Ce n'est pas une preuve de relocation ou d'execution.
Les ISA CPU, TLS, IFUNC, dlopen et l'ordre des objets globaux restent
a qualifier. Les extensions tests greenlet sont conservees.

## Proposition de base

Nouveau rootfs **Debian13/linux-amd64 coherent**, issu de paquets Debian
verifies d'une meme selection approuvee, plus CPython3.11.18 de provenance
et compilation documentees, prefix propose `/opt/p4-python`.
Une construction CPython shared est une option proposee, a figer dans
une recette source revue ; ni flags, compilateur ni hash ne sont inventes.
Un runtime CPython deja qualifie serait une autre entree possible,
mais il n'en est fourni aucun ici.

Ne pas utiliser FROM P3 ni enrichir son rootfs en place. Ne pas
promouvoir les fichiers P3 par simple copie : l'origine et l'ABI des
quatre bibliotheques presentes sont elles aussi inconnues ici.
La fermeture de CPython/lib-dynload peut exiger plus que les10 SONAME
des wheels. Les familles conditionnelles dans les composants ne sont
pas une liste apt fermee.

| Noms requis par les wheels | Famille Debian candidate, non verifiee |
|---|---|
|ld-linux, libc, libm, libdl, libpthread, libresolv, librt |libc6:amd64 coherent |
|libgcc_s.so.1 |libgcc-s1:amd64 |
|libstdc++.so.6 |libstdc++6:amd64 |
|libz.so.1 |zlib1g:amd64 |

Versions exactes, hashes et provenance des fournisseurs : **null** dans
`P4_RUNTIME_COMPONENTS.json`, car aucun .deb ni binaire n'est disponible.
Les versions exigees observees incluent GLIBC jusqu'a2.25,
GLIBCXX3.4.21, CXXABI1.3.9 et GCC4.2.0 ; ce ne sont pas des versions de
paquets ni la fermeture du futur CPython.

## Cas glibc historique : pas de raccourci

Sur des glibc recentes, certaines fonctions autrefois dans libdl,
libpthread ou librt sont integrees a libc. Cela ne supprime pas un
DT_NEEDED encode dans un ELF existant, ni ses contraintes de versions.
Il faut verifier l'existence et la recherche du SONAME demande, les
DSO de compatibilite du **meme paquet libc6**, les noeuds de versions,
puis les symboles dans le scope global reel. Une DSO de compatibilite
peut deleguer des symboles a libc : absence d'une exportation dans
cette DSO seule n'est pas automatiquement une erreur ABI.

Interdits : ignorer DT_NEEDED, creer des symlinks libdl/libpthread/librt
vers libc, supprimer les dependencies avec patchelf ou recopier des libs
au hasard. libresolv, libm et le chargeur doivent aussi etre verifies
selon leurs ELF effectifs. Les31 comparaisons directes ici concernent
les fournisseurs prives des wheels, pas cette resolution globale glibc.

## Blocages et decision

B1 : rootfs P3 corrige/manifeste9771/ancre/archive non remis localement.
B2 : fournisseurs Debian exacts et coherents non remis.
B3 : runtime/source/compilation/stdlib CPython3.11.18 non qualifies.
B4 : fermeture recursive, scope chargeur, symboles/ABI/ISA non qualifies.
B5 : bootstrap, imports, pip check et ASGI cible non executes.
B6 : equivalence rootfs/couche/config et builder offline non qualifies.
B7 : approbations independantes et recette executable absentes.

Le blocage n'est donc **pas resolu par cette preparation**. Elle fournit
les exigences exactes observees, les controles et la procedure pour
recevoir/qualifier les composants manquants dans une revision suivante.
Pas de Dockerfile executable, image fictive ou approbation inventee.

PASS_STATIQUE signifie seulement coherence des octets/observations
scopes. FAIL : contradiction de hash/version/symbole/metadata prouvee.
INCOMPLETE : materiau absent, outil non qualifie, interruption ou retour
perdu. FAIL et INCOMPLETE maintiennent BLOCKED. Un rc0 d'inventaire,
un nom de fichier ou un SHA seul ne constitue jamais une validation P4.
Meme READY_FOR_INDEPENDENT_REVIEW ne donnerait aucun GO d'execution.
