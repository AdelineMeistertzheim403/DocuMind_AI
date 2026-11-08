# Qualification locale - pas un rejeu historique

Le 2026-11-05, **46 tests passes, aucun echec, aucun test ignore** sous
Python 3.11.2 deja installe, Debian **12** WSL2. Aucune installation,
connexion reseau, commande Docker ou lecture de preuve brute historique.
Ce n'est pas une validation de la VM Debian 13.7/Python 3.11.18 de l'operatrice.

Preuves independantes :
qualification/p4_b1_p3_layer_contents_v1/local-tests-02.
Le premier essai local-tests-01 est aussi conserve sans ecrasement.
Les recepisses enregistrent commande reelle, interpreteur/OS, hashes de
tous les modules, code 0 des tests et stdout/stderr exacts.
Un rejeu depuis la livraison scellee utilise un autre repertoire neuf.

Les 35 tests du noyau strict v2 sont conserves. Onze tests additionnels
mesurent le nouveau perimetre avec de petites archives synthetiques dont
les digests et tailles sont reellement calcules :

- A identique, tandis que le controle strict de la meme archive refuse
  toujours le blob non rattache avec 20.
- Identite reguliere distincte des divergences UID/GID, modes, repertoires
  et absence de la racine ; listes et comptes distincts.
- Fichier manque, modifie, remplace a compteur egal ou devenu hardlink.
- Ancres et tailles configuration/manifeste/couche/blob incorrectes.
- References index/OCI/Docker incoherentes, descriptors ambigus ou multiples.
- Autre blob/fichier/repertoire supplementaire refuse ; digest du nom
  d'un blob obligatoire meme hors graphe.
- Archive et inventaires authentifies avant interpretation.
- Traversal, doublon, fichier special, trailer cache et PAX non supporte.
- Rapport deterministe ; recepisse CLI complet avec code general 20 et
  A.scope_returncode=0 ; stdout/stderr, hashes et non-ecrasement.

Le noyau comparator.py copie est identique aux octets scelles v2
(SHA-256 63225aec80a257a246ca492acbaf1dcc73c66a0c49123ffaffc9ad73ee6c383a).
Les modules sont parses avec la grammaire Python 3.11, DECISION.json parse
et les six blocs Bash du protocole/transfert controles par bash -n, sans
execution de ces commandes. Aucun nouveau linter tiers.

Les ancres historiques, notamment le manifeste OCI de 402 octets, sont
constantes mais **pas** localement re-mesurees. Le JSON transmis reformate
n'est jamais utilise comme substitut des octets historiques.
A demeure a mesurer sur Debian ; B reste bloque et C non accorde.
REVIEW_ONLY_BLOCKED, aucun GO et aucune autorisation C5.
