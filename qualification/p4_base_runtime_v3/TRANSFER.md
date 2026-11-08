# Transfert Debian - P4 Base Runtime v3

**Review-only, BLOCKED. Aucun GO build/create/start/production.**

Nouvelle livraison : `deliveries/docnelo-v51-p4-base-runtime-v3`.
Archive : `p4-base-runtime-v3.zip`.
Les ancres finales SHA256SUMS livraison/paquet sont remises separement.
Les confirmer par un canal de confiance independant avant execution.
SHA256SUMS est un controle d'integrite, pas une signature.

Contenu autonome : rapports, composants encore non approuves,
revue ELF et symboles, procedure rootfs, scripts stdlib/tests,
43 wheels preserves et inventaire v2 original. Aucun rootfs,
.deb, fichier systeme approuve, image, Dockerfile executable, donnee
restauree ou preuve Debian reconstruite n'est embarque.

1. Copier vers un repertoire development neuf hors des historiques.
   Comparer SHA du manifeste externe a l'ancre recue, puis utiliser
   sha256sum -c SHA256SUMS avec outil deja approuve. Controler aussi la
   liste exacte (archive, transfer.py/common.py/wheels.py et ce guide).
2. N'executer les scripts qu'apres verification de leurs octets :

```sh
"$PY" -I -B "$LIVRAISON/transfer.py" extract --delivery "$LIVRAISON" \
  --anchor "$ANCRE_LIVRAISON" --destination /development/p4-base-runtime-v3-neuf
```

Destination absolue neuve, parent existant, aucun symlink. L'extracteur
refuse doublons, traversal, ZIP chiffre/symlink/fichier special, verifies
les listes exactes externe et interne et toutes les empreintes. Cette
extraction est celle du **paquet de revue**, jamais celle d'un rootfs.
Une interruption laisse une sortie partielle a conserver, pas a reutiliser
ni a declarer conforme.

3. Verifier SHA256SUMS interne avec son ancre et common.py. Le repertoire
   inputs porte les43 wheels et l'inventaire d'ancre
   `60f0d9f0b668409bba75914b5ef40027036c54ac69de96b05b8e813032813c20`.
4. Suivre V0 de P4_ROOTFS_BUILD_PROTOCOL.md dans E neuf. Les outils
   originaux du paquet restent RO. review.py doit retourner2/BLOCKED.
   Aucun besoin de reouvrir ou modifier v1/v2 pour ces controles.
5. Recolter les retours numeriques, heures UTC/ns, stdout/stderr et hashes.
   Un test de transfert conforme ne valide ni le rootfs ni P4.

Les donnees P3 operateur ne sont pas des preuves reproduites :
ID bbe90dab...,9771 entrees,4 noms presents/6 absents, hash manifeste
non remis. Pour poursuivre, faire approuver une nouvelle livraison
de composants et provenance ; ne pas ajouter des libs dans un paquet
scelle ou remplir ses champs null pour le faire passer.

Les9 tests locaux utilisent CPython Windows et des archives unitaires
factices, sans commandes Docker ni bibliotheques Linux executees.
Le controle POSIX d'un vrai rootfs et l'ABI Debian sont NON EXECUTES.
Ne pas interpreter leur absence comme un PASS.
