# Transfert P4 Build Materials v2

**Review-only ; decision BLOCKED. Aucun GO build, create, start ou production.**

Livraison nouvelle : `deliveries/docnelo-v51-p4-build-materials-v2`.
Archive : `p4-build-materials-v2.zip`.
Les ancres finales paquet/archive/manifeste externe sont remises avec
la livraison. Les confirmer par un canal de confiance independant avant
d'executer un script. SHA256SUMS n'est pas une signature.

## Contenu autonome

Rapports demandes, inventaires,43 wheels exacts copies depuis des
entrees verifiees, lock propose, metadonnees PyPI archivees, receipts,
scripts offline et preuves locales. Aucune base Docker compatible
n'est incluse, aucune image P4, aucun rootfs, donnee restauree, secret
ou namespace historique. Les neuf archives d'images rejetees ne sont
pas copiees : seules leurs metadonnees limitees et hashes sont livres.

Les scripts de verification n'ont pas besoin du code des outils v1.
Les campagnes ASGI et les checks r3/v1 restent des entrees externes
figees pour une etape future ; v2 ne les modifie ni ne les remplace.
Les43 wheels sont presentes dans `materials/wheels` et peuvent etre
verifiees sans reouvrir les anciens transferts.

Ancre inventaire v1/Debian :
`60f0d9f0b668409bba75914b5ef40027036c54ac69de96b05b8e813032813c20`.
Ancre du SHA256SUMS paquet v1 :
`389f070088a0f56d626ebe04a8dbce686e253522a438f1950bdccd4bf0e8f1d1`.
Ancre du SHA256SUMS r3 :
`5f3cc1598423107c5616d630d63d31b849b939cbd9f3ce9ce25fc0bf3440f8d4`.

## Verification/extraction Debian hors ligne

1. Support approuve, destination development neuve, parent existant sans
   symlink, hors toute release, source, namespace ou evidence historique.
   Conserver dates UTC, tailles et empreintes avant/apres transfert.
2. Avec sha256sum deja approuve, comparer l'empreinte de SHA256SUMS a
   l'ancre externe recue, puis `sha256sum -c SHA256SUMS` dans la livraison.
   Verifier la liste de fichiers. Ne pas faire confiance au verificateur
   avant d'avoir controle ses octets.
3. Le Python hote approuve suffit a extraire ; aucun paquet a installer :

```sh
"$PY" -I -B "$TRANSFER/transfer.py" extract \
  --transfer "$TRANSFER" --anchor "$TRANSFER_SUMS_ANCHOR" \
  --destination /chemin/development/p4-build-materials-v2-neuf
```

Le manifeste externe exact couvre l'archive et le verificateur. Celui-ci
refuse destination existante, traversal, doublon, ZIP chiffre, symlink
et fichier special. Le manifeste interne exact couvre tous les octets,
y compris les43 wheels. En cas d'interruption, conserver la sortie
partielle, ne pas la reutiliser ni la declarer conforme.

4. Verifier le paquet avec common.py et son ancre. Pour les controles
   de tags/graphe, packaging26.3 doit deja etre verifie dans le venv hote ;
   ne pas installer depuis Internet. La fermeture de l'outil hote ne
   prouve pas celle de l'image. Ecrire toutes les nouvelles sorties
   dans une nouvelle evidence E, jamais dans le paquet scelle.
5. Recalculer les checks43 et l'analyse native avec wheels.py/native.py
   selon `P4_DOCKER_BUILD_PROTOCOL.md`. Comparer les JSON aux preuves
   livrees ; la presence de chemins Windows dans les receipts d'origine
   ne les transforme pas en preuves Debian.
6. gate.py produit BLOCKED, retour2. Conserver ce resultat comme NO-GO,
   pas un succes de construction. Le H1 precedent rc1 reste intact.

Les deux acquisitions HTTPS ont eu lieu sur la machine Windows de
preparation seulement. Ne pas rejouer curl/les commandes reseau des
receipts dans la VM Debian ; comparer les metadonnees archivees offline.
Ne pas charger ou lancer une des images rejetees pour chercher une base.

## Ajouts ulterieurs

Toute base/provenance/fermeture manquante doit arriver dans une nouvelle
livraison scellee et faire l'objet d'une revue independante. Ne pas
modifier les valeurs null ou les approbations dans v2 pour passer un gate.
Ne pas ajouter des fichiers dans un paquet/preuve deja scelle.
Une autorisation de build sera distincte ; create et start conserveront
leurs propres points d'arret. Ne pas relancer D11 ni toucher aux preuves
P1/P2/P3/D11/H1 ou au lecteur P3 conserve.
