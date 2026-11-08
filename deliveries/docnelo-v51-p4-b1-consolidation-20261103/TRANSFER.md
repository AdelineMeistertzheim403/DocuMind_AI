# Transfert du complement B1 - 20261103

Livraison nouvelle : `deliveries/docnelo-v51-p4-b1-consolidation-20261103`.
Archive : `p4-b1-consolidation-20261103.zip`.
**Review-only, BLOCKED, tous les GO false.**

Le paquet contient rapports/decisions, registre des hashes rapportes,
protocole Debian, scripts stdlib/tests et preuves des controles locaux.
Il ne contient pas les preuves B1 brutes, le rootfs P3, une archive image,
des wheels ou une base P4. Les anciennes livraisons ne sont pas modifiees
ni necessaires a l'execution du petit controleur de copies de preuves.

Verifier l'empreinte du SHA256SUMS de livraison par le canal de confiance
independant ayant remis l'ancre, puis `sha256sum -c SHA256SUMS` et la
liste exacte : archive, common.py, transfer.py, TRANSFER.md.
Un manifeste n'est pas une signature. Ne pas executer un verificateur
avant d'avoir verifie ses propres octets.

```sh
"$PY" -I -B "$LIVRAISON/transfer.py" extract --delivery "$LIVRAISON" \
  --anchor "$ANCRE_LIVRAISON" --destination /development/p4-b1-consolidation-neuf
```

Python hote approuve >=3.11, aucune installation. Destination absolue
neuve, parent existant sans symlink, hors tous historiques/paquets scelles.
L'outil refuse chemins dangereux, doublons, ZIP chiffre, symlinks et
fichiers speciaux ; manifestes externe/interne exacts et tailles bornees.
Une extraction interrompue n'est pas conforme : conserver sa sortie,
ne pas la reutiliser. Apres extraction, verifier le manifeste interne
avec son ancre recue et common.py ; suivre le protocole Debian D0-D3.

Ancres historiques conservees, pas de nouveau verdict de qualification :

| SHA256SUMS | Ancre |
|---|---|
|Paquet v3 |`be64e25c43b33255c2d6a9172faa574fad9c7c749ccb5a0ed048befb2d015fc7` |
|Livraison v3 |`23f817a08cc8844ae3a53a4e51bf7b55a88fd555f9590342f8f379388514d6ca` |

common.py, record.py, preserve.py sont copies bytes-identiques de v3
(TOOLS_ORIGIN.json). Les scripts ne lisent pas les images/conteneurs ni
les donnees restaurees. evidence_check.py lit seulement les quatre
copies explicites ; aucun telechargement, installation ou commande Docker.
Les tests locaux utilisent des copies factices, pas les preuves Debian.
Une preuve brute ancree ici n'est pas encore une revue de sa methode :
formal_b1_contents_closed reste false jusqu'a l'acte habilite C5.
