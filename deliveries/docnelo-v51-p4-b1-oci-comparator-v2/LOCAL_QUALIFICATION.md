# Qualification locale de la livraison

Le 2026-11-05, **35 tests passes, aucun echec, aucun test ignore** avec
Python 3.11.2 deja installe dans Debian **12** WSL2, sans installation,
reseau, Docker ni lecture des octets historiques P3. Ce n'est pas une
qualification de la VM Debian 13 de l'operatrice.

Preuves independantes dans le depot :
`qualification/p4_b1_oci_comparator_v2/local-tests-01/`.
Le recepisse capture la commande reelle, le lanceur, l'interpreteur, l'OS,
le code retour 0, stdout/stderr et les empreintes du code teste.
Les preuves de v1 restent intactes et ne sont pas reutilisees pour v2.

Cas couverts : identite et determinisme JSON ; profil racine absente/UID-GID ;
manquant, contenu modifie, remplacement de chemin a compteur egal ; doublons
TAR et inventaires ; chemins dangereux ; couche/configuration/diff_id faux ;
inventaires alteres et format inconnu ; type/mode/lien ; liens dangereux ou
cycliques ; fichiers speciaux ; outer TAR non rattache ; troncature, checksum,
padding et trailer ; PAX timestamp/xattr ; GNU longname ; layouts OCI et
metadata legacy ; lectures bornees ; refus de symlinks hote ; scellement du
code et non-ecrasement ; recepisses CLI pour codes 0, 10, 20 et 30.

Six nouveaux tests couvrent LayerSources : manifeste historique reproduit
exactement au niveau du contrat docker_binding (metadata de fixture, pas
octets historiques) ; parcours Docker/OCI complet avec descriptors et
payloads synthetiques effectivement haches ; tailles/digests/mediaTypes/
cles errones ; champs inconnus/manquants/repetes, references supplementaires
et types JSON ambigus ; maintien de la couverture et du controle de couche ;
compatibilite des LayerSources absent, null ou vide.

Les quatre modules ont ete parses avec la grammaire Python 3.11 ; DECISION.json
parse ; les six blocs Bash du protocole/transfert passent `bash -n` sans
execution. Aucun outil lint tiers ou dependance additionnelle n'a ete installe.

La validation finale du manifeste scelle et un rejeu des tests depuis la
livraison scellee sont enregistres dans de nouveaux dossiers de preuves
adjacents, sans modifier cette livraison.

Les resultats P3 historiques ne sont pas disponibles ici. Leur rejeu exige
DEBIAN_PROTOCOL.md sur la VM avec les trois fichiers existants. Une absence
de preuve brute ne se transforme pas en PASS ; C5 reste non autorise et la
decision generale demeure REVIEW_ONLY_BLOCKED, tous les GO false.
