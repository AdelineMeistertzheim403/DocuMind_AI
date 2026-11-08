# Transfert du complement P4 - offline, sans GO

## Contenu et ancres

Livraison nouvelle : `deliveries/docnelo-v51-p4-asgi-offline-v1`.
Elle contient l'archive du complement, un manifeste externe exact,
le verificateur et ce guide. L'archive contient son propre SHA256SUMS,
les outils, rapports, inventaires et preuves locales de preparation.
Elle ne contient pas l'image P4, de base/CPython binaire, de dependances
installees, de donnees restaurees, de secrets ou de namespace historique.

Les ancres finales (manifeste paquet, archive, manifeste livraison) sont
publiees avec la remise. Confirmer **independamment** leurs valeurs avant
d'executer un script. Ne pas auto-approuver un hash recalcule sur un
support inconnu. SHA256SUMS n'est ni une signature ni un certificat.

Entrees externes conservees en lecture seule et transferees separement :

| Entree | Ancre SHA256 |
|---|---|
| r3 `SHA256SUMS` | `5f3cc1598423107c5616d630d63d31b849b939cbd9f3ce9ce25fc0bf3440f8d4` |
| r3 `INPUTS.json` | `c33358f734bcee252a39b1b10f9ed7a459c4ee30d29f46630523ac1aad208ed2` |
| Transfert historique FastAPI `SHA256SUMS` | `8cccb3511981326e5eb97490c0623c4efaccf56ef080791f588d366ec0a4f25b` |
| Archive 42wheels CP311 | `55907b272e57a21e4815db2e7e65f4c211601eb911b6c864260002b192365026` |
| Lock CP311 historique | `9fe00d4247e9a8a3afa1935b7acaa814ff337e336c1136eef743deeca6f24fae` |
| Wheel PyYAML CP311 observe | `b8bb0864c5a28024fac8a632c443c87c5aa6f215c0b126c449ae1a150412f31d` |

Le candidat doit rester **complet**, sans pycache ni fichier supplementaire.
Ne pas copier ce complement a l'interieur de r3 ni modifier ses manifests.
Si les entrees sont deja sur Debian et concordent, les reutiliser RO ;
ne pas reextraire/reprovisionner les anciens transferts/namespaces.

## Procedure de transfert

1. Utiliser un support de transfert approuve, hors ligne cote VM ; noter
   origine, date UTC, taille et empreintes avant/apres transfert dans une
   nouvelle evidence. Aucun telechargement ni installation sur Debian.
2. Sur Debian, verifier avec l'outil systeme deja approuve l'empreinte
   de SHA256SUMS contre l'ancre recue independamment, puis
   `sha256sum -c SHA256SUMS` dans la livraison. Controler aussi la liste
   de fichiers (le script fait ensuite le controle exact).
3. Executer avec le Python hote approuve, dans une nouvelle destination
   development dont le parent existe, sans symlinks :

```sh
"$PY" -I -B "$TRANSFER/transfer.py" extract \
  --transfer "$TRANSFER" --anchor "$TRANSFER_SUMS_ANCHOR" \
  --destination /chemin/development/p4-asgi-offline-v1-neuf
```

Le script refuse extraction sur chemin existant, traversal, symlink,
ZIP chiffre, doublon, fichier special et inventaire manquant/supplementaire.
Une extraction interrompue est conservee et ne doit pas etre reutilisee.
Les scripts importes sont ceux prealablement verifies par le manifeste
externe ; cette verification initiale est indispensable.

4. Verifier le SHA256SUMS du paquet extrait et r3 ; reproduire
   l'inventaire dans une sortie neuve et comparer les enregistrements.
   Une empreinte wheel observee ne vaut toujours pas approbation.
5. **S'arreter au gate build.** Ce transfert seul ne permet pas de
   construire l'image. Collecter composants manquants et approbations
   dans une livraison ulterieure distincte et scellee.

Les outils des futurs conteneurs seront copies depuis un paquet P4
verifie dans l'image uniquement par la recette ulterieure approuvee.
Le candidat reste monte complet RO, jamais patche pour y ajouter les outils.

## Retour des preuves

Chaque cas garde un manifeste interne lanceur et un manifeste operateur
externe distinct, plus les IDs exacts et la reference du plan/image.
Une campagne globale nouvelle contient les hashes des36 cas ou declare
les manquants. Les preuves partielles restent partielles.

Ne pas ouvrir puis modifier un repertoire deja scelle. Ajouter une
annexe dans une nouvelle evidence, avec reference au SHA du manifeste
precedent. Conserver les conteneurs P4 arretes, les namespaces et les
receipts, meme en echec. Aucun prune/rm/down ni nettoyage de P3/P2.

Lors d'une coupure SSH, reprendre uniquement la **collecte en lecture**
du nouvel ID P4 confirme, dans une nouvelle annexe. Un retour manque
ne se reconstitue pas par estimation ; classer INCOMPLETE si la chaine
necessaire n'est pas entierement prouvee. Ne pas rejouer D11.
