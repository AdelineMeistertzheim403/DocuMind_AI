# Correctif v2 - LayerSources historique

Decision : **REVIEW_ONLY_BLOCKED** ; formal_b1_contents_closed=false ;
tous les GO false. La validation de l'archive historique sur Debian 13
reste une operation distincte apres verification des nouvelles ancres.

## Modification bornee

La v1 refusait tout LayerSources non vide avec le code 30. La v2 accepte
le format effectivement fourni par l'operatrice et valide ses donnees
apres verification de la presence et du SHA-256 exact de la couche.

Exiger exactement une cle `sha256:<hash de la couche presente>`, egale
au Diff ID attendu. Exiger exactement les trois champs digest/mediaType/size,
sans champ ignore ou reference additionnelle. Digest doit egaler la cle ;
mediaType doit etre `application/vnd.oci.image.layer.v1.tar` ; size doit etre
un entier JSON non negatif et egal a la taille du payload externe mesure.
Les booleens, flottants et chaines sont refuses meme si numeriquement egaux.
Les cles JSON dupliquees sont refusees par le parseur existant.

Les erreurs sont code 20, jamais contournees ou transformees en succes.
Absence du champ, null et dictionnaire vide conservent leur comportement
anterieur pour les archives qui n'ont aucun descripteur LayerSources.
image_binding enregistre la presence du champ et son contenu valide.
Le schema de rapport devient p4-b1-oci-comparator-v2.

Aucune modification du parseur TAR, du streaming, des empreintes attendues,
des inventaires, du graphe OCI ou de la comparaison rootfs. LayerSources
ne permet pas de reclamer une autre entree externe ni une autre couche.
Les bornes, controles de couverture et politique de decision restent actifs.

## Separation des preuves de test

Le manifeste fourni (Config et Layers sous blobs/sha256, RepoTags=null,
cle/digest exacts, mediaType TAR, size=322534912) est reproduit dans une
fixture de test de docker_binding. Les metadata de cette fixture simulent
la sortie du parcours externe deja verifie : elles ne constituent pas un
nouveau hachage de la configuration ou couche historiques.

Un test de bout en bout utilise une petite archive synthetique, ses propres
ancres, un LayerSources non vide et un layout OCI complet. Les tailles et
hashes de ses payloads sont reellement mesures par le streaming. Ce test
verifie egalement le determinisme, la couverture et le profil racine absente.
Les tests negatifs couvrent chaque champ et la persistance des refus TAR/OCI.
Les tests preexistants de v1 sont conserves.

## Preservation et remise

La v1 a ete verifiee avant copie : manifeste ancre a
`2165b14ed3159362283de1df877f295ef110c4db64458e702df7f3b0dd059e56`,
et empreintes conformes pour ses 11 fichiers. Seuls ces fichiers ont ete
copies dans un nouveau dossier v2, sans reutiliser son SHA256SUMS.
La v1 n'est ni editee ni re-scellee. Les nouveaux tests et controles finaux
sont enregistres sous qualification/p4_b1_oci_comparator_v2.

La v2 dispose de son propre SHA256SUMS et du fichier d'ancres externe
docnelo-v51-p4-b1-oci-comparator-v2.anchors.json. Remettre l'ancre par un
canal physique independant de confiance ; SHA-256 n'est pas une signature.
Les preuves historiques P3/B1 ne sont pas ouvertes ou modifiees par ce
correctif. Ni reseau, installation, export, ni commande Docker.
