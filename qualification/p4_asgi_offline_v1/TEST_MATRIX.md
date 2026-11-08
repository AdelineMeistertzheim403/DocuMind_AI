# Matrice P4 standard / beta_lite

**Toutes les executions Docker ci-dessous sont NON EXECUTEES.**
`matrix.py` est la selection machine bornee de cette revision.
Chaque ligne se repete dans deux campagnes independantes, standard et
beta_lite, avec nouveaux namespace, evidence, conteneur et processus.

| Cas | Startup | Actions apres startup -> probes dans le meme processus |
|---|---|---|
| D03 | ready | publish quarantined -> closed |
| D04 | ready | publish quarantined -> closed ; publish ready -> sentinel |
| D05 | quarantined | publish ready -> closed |
| D06 | ready, nouveau processus | publish ready -> sentinel |
| D07 | ready | remove enfant -> closed |
| D08-invalid-json | ready | publish not-json -> closed |
| D08-invalid-utf8 | ready | publish octet FF -> closed |
| D08-duplicate | ready | publish double cle state -> closed |
| D08-boolean | ready | publish format true -> closed |
| D08-unknown | ready | publish etat unknown -> closed |
| D08-extra | ready | publish cle extra -> closed |
| D08-oversized | ready | publish1025 octets -> closed |
| D09-latch-ready | ready | publish ready -> sentinel ; latch000 -> closed ; latch0440 -> sentinel |
| D09-directory-ready | ready | publish ready -> sentinel ; directory0700 -> closed ; directory0750 -> sentinel |
| D09-latch-quarantined | quarantined | publish ready -> closed ; latch000 -> closed ; latch0440 -> closed |
| D09-directory-quarantined | quarantined | publish ready -> closed ; directory0700 -> closed ; directory0750 -> closed |
| D11-child | ready | remove enfant, parent present/stable -> closed ; **aucun create absent/D11 rejoue** |
| D12-symlink | ready | enfant remplace par symlink dangling P4 -> closed ; jamais FIFO/device |

Total coeur : **18 cas x2 profils =36 executions**, 54 probes au total.
Le cas D06 est un conteneur neuf ; il ne reutilise pas un processus D05.
La fermeture persiste dans le processus D05 meme quand l'enfant est ready.
Ne pas en deduire une autorisation de reouverture d'un latch reel.

## Oracles conjoints

`startup` doit preceder l'action1. Chaque action terminee/fsync doit
preceder son probe, qui doit preceder l'action suivante. Les logs Docker
`--timestamps`, receipts et stdin.log doivent rendre cet ordre verifiable.
Un simple changement de fichier avant startup ne teste pas la propagation.

| Oracle | Standard | beta_lite |
|---|---|---|
| closed, requetes non authentifiees + authentifiees | 503 pour chaque couple route/methode | 403 uniquement routes Lite bloquees, 503 pour les autres |
| closed, compte total | 2 x routes startup | 403 +503 =2 x routes startup, deux categories non vides |
| closed, aval/corps | delta sentinelle0, corps jamais consomme | meme oracle |
| sentinel | GET health auth =500 synthetique, delta aval1 | meme oracle, pas403 |
| startup quarantined | tous les compteurs workers0 | tous0 |
| startup ready | summary_recover/index_recover/summary_start/thread_start/cleanup_schedule =1 | trois premiers0, thread_start/cleanup_schedule =1 |
| probes ulterieurs | compteurs inchanges, aucune E/S interdite | meme oracle, autorite Lite jamais lue |

`routes` est l'inventaire reel de ce candidat, pas une liste simplifiee
recrite dans le complement. Le test fige verifie les codes par route.
Les comptes 403/503 de l'evaluateur sont une verification supplementaire,
pas un remplacement des assertions du test. HEAD ne doit pas produire
de corps ; aucun refus ne doit consommer le corps de la requete.

Pour publish : parent device/inode constant ; nouvel inode enfant,
hash payload exact, UID0/GIDlecteur0440, fichier single-link,
fsync fichier -> replace -> fsync repertoire. D09 chmod conserve l'inode
de l'objet vise. D07/D11-child prouvent ENOENT avec parent toujours present.
Le symlink D12 est un defaut synthetique cible, pas une source de montage
acceptee par le preflight ; la garde source interdit les symlinks.

## D14 et perimetre non revendique

D14 multi-consommateur est un lot complementaire distinct : deux
processus ASGI deja demarres pour chaque profil, meme controle P4 stable
RO, deux repertoires evidence0700 **distincts**, quatre inspections de
configuration au minimum pour les deux profils, publications apres leurs
startup et probes dans chacun, hashes frais concordants. Conserver les
deux IDs, chaque inode/historique et les stops controles.

L'inspecteur de cette revision est volontairement mono-conteneur et
refuse un second alias du controle, meme RO : il ne faut pas l'affaiblir
pour faire passer D14. Ce lot requiert une nouvelle recette multi-lecteur
revue avec allowlist de peers exacts et leurs inspections conjointes.
Il est **INCOMPLETE/non couvert** ici ; aucun PASS D14 ne peut etre
deduit de deux executions sequentielles ou deux controles distincts.

D01/D02/D10/D11-create/D13/D15-D20 et la chaine Lite signee ne sont pas
requalifies par ce paquet P4. Ne pas rejouer P2, D11-create ou P3.

## Conditions de verdict

**PASS_CASE_ONLY** : transfert et image approuves, protections Engine et
DAC effectives conformes avant start, autorisations enregistrees, toutes
les actions/probes du cas presentes avec ordre prouve, oracles HTTP/
workers/isolation corrects, sortie JSON stop explicite, capture start
et wait CLI0, wait stdout0, State.ExitCode0 sans OOM/erreur, resultat
lanceur PASS monte, exactement1 cas pytest passe sans skip/xfail,
JUnit/cases concordants, manifestes exacts et revue independante complete.

**FAIL** : preuve positive d'ecart (mauvais HTTP, 403 a la place de503,
500 non sentinelle, corps consomme, aval atteint en closed, thread/SQL/
reseau, droits/montage/identite divergents, inode parent remplace, hash
faux, publication ou commande non nulle, pytest echoue, OOM, tampering).
Un refus attendu d'un outil de garde peut prouver cette garde seulement ;
il ne satisfait jamais le cas P4 bloque.

**INCOMPLETE** : image/approbation manquante, campagne non commencee,
code numerique perdu, SSH/EOF/interruption/timeout sans fin verifiable,
startup/probe/stop/receipt/manifest/revue manquant, ordre non demonstrable,
horloge instable ou couverture partielle. Une divergence deja prouvee
reste FAIL meme si d'autres preuves manquent. Ne jamais corriger un
historique incomplet par une valeur estimee ou un fichier reconstitue.

Pour la matrice coeur, les36 cas doivent etre PASS avec une chaine
d'evidence scellee ; tout FAIL fait echouer la campagne et tout cas
manquant rend sa couverture INCOMPLETE. La decision P4 globale doit
mentionner D14 non couvert tant qu'il n'a pas ete execute dans son lot
revu. Aucun verdict technique ne donne un GO Docker applicatif/production.
