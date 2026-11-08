# Politique des codes retour

| Code | Statut du rapport | Interpretation obligatoire |
|---|---|---|
| 0 | TECHNICAL_SUCCESS_WITH_LIMITS | Tous les controles pris en charge sont acheves ; aucune difference dans ce perimetre. Ni egalite complete des metadata ni GO. |
| 10 | DIFFERENCES_OBSERVED | Integrite et comparaison achevees ; differences listees, dont racine absente, UID/GID, modes, types, liens, contenu ou chemins. |
| 20 | ERROR | Integrite incorrecte, format ambigu/dangereux, fichier special, binding faux, erreur d'entree/sortie, livraison/code non scelle ou mauvaise version Python. Arret. |
| 30 | CONTROL_INCOMPLETE | Format/type d'inventaire inconnu ou capacite non prise en charge : PAX inconnu, graphe/limite memoire, multi-couche, etc. Arret, aucune conclusion d'identite. |

`REVIEW_ONLY_BLOCKED`, `formal_b1_contents_closed=false` et tous les GO false
dans tous les cas. Le code 10 n'est pas un succes d'egalite ; le code 0 n'est
pas une autorisation C5. Les attributes non presents dans les inventaires
source restent explicitement non controles meme au code 0.

Erreurs CLI argparse : code 2 avant creation des preuves. Refus de creation
d'un repertoire existant : code 20 sans le modifier. Si la sortie est neuve,
les erreurs traitees produisent un rapport et un recepisse. Une interruption,
un timeout, un signal, une erreur d'ecriture ou un crash peuvent empecher le
recepisse final. Absence de complete=true, code absent, hash incorrect ou
code shell different du recepisse : **controle incomplet**, jamais assimile
a 0. timeout peut retourner 124/137 ; conserver les traces existantes dans
leur repertoire, puis creer une autre tentative si autorisee.

record_tests.py reprend le code unittest (0/1), ou 30 si capture incomplete.
Un test ignore ou une version autre que Python 3.11 n'est pas une validation
Debian suffisante. Ses codes ne sont pas ceux de la comparaison OCI.
