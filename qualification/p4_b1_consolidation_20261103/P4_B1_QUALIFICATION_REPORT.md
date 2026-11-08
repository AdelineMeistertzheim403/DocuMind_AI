# Docnelo V5.1 - Complement B1 apres comparaison couche/rootfs P3

**Decision generale : BLOCKED. Review-only. Tous les GO restent false.**

Les resultats transmis etayent l'identite des **contenus des9771 fichiers
reguliers P3**, pas l'egalite complete des metadonnees ni l'approbation
d'une base P4. La cloture formelle de ce perimetre restreint est preparee,
mais **non prononcee ici** : les octets du rapport B1, du comparateur
et des captures ne sont pas joints a la demande.

Ce complement est independant : aucun texte, outil, decision ou preuve
v3 n'est reecrit. Aucun Docker, acces reseau Debian, installation,
lecture de donnees restaurees ou changement P3/r3/P1/P2/P3/D11/H1.
Les1184 fichiers historiques locaux scopes sont controles avant/apres ;
cela ne pretend pas reverifier les preuves distantes sur la VM.

## 1. Nature des entrees

La reproduction statique Debian des trois rapports v3 est annoncee
identique. Elle confirme cette reproduction, pas une ABI ou un runtime.
Les nouvelles valeurs B1 ci-dessous sont **rapportees par l'operateur**,
pas mesurees une seconde fois dans cette preparation. Leur registre
machine est P4_B1_OBSERVED_REFERENCES.json.

| Objet distinct | Empreinte SHA-256 rapportee |
|---|---|
|ID de configuration image P3 |`bbe90dab376fcd41b3495cad1264c017323ed68ed0915c601ea5fd229cbf6abd` |
|Diff ID de couche |`7b1b9ae269d164c3b88d386714f2def703acb15812a6d6f813c10064f57c766e` |
|Archive docker image save |`ffec209c1b5eb3a8861e60585266c18069896adf05c8fe8f98c558d682351c2d` |
|Dockerfile historique |`605418eb09c102b5757dab88ad3ecbd1a70eb750bfea22615784ede4d9259e47` |
|ROOTFS-SHA256SUMS corrige |`a37f1847df7c7212c2d1b004e5ab3b0d654323a8ab2d425e20d89c551279527f` |
|ROOTFS-METADATA.txt |`64863f4ebc2aaddb717d83147e623e37942716728736afa40f5bd39d1083db36` |
|p3-layer-comparison.json |`2e7eef48a5b66d82e03e59f9c936d935d8317670d647d00917cec51813db7cf0` |

Un ID de config n'est ni un digest de manifest OCI, ni un diff ID, ni
le hash de l'archive. Le diff ID porte sur la couche **non compressee** ;
ne pas l'assimiler au digest d'un blob compresse sans relire la capture.
La verification de config/blob est annoncee faite ; il faut examiner
ses preuves existantes, pas reexporter/reimporter l'image.
Le hash du manifeste rootfs n'est pas le hash d'un filesystem concatene.
Ces hashes ne sont pas des signatures ou des preuves d'origine.

## 2. Lecture exacte de la comparaison

| Perimetre rapporte | Source corrigee | Couche |
|---|---|---|
|Fichiers reguliers |9771 |9771 |
|Repertoires |564, dont `.` |563 |
|Total fichiers + repertoires |10335 |10334 |
|UID:GID |1000:1000 |0:0 |

Absents : seulement `.`. Aucune divergence de contenu, permission ou
type ; aucun supplement ni entree speciale. Source sans symlink
inventorie. Controle sha256sum du manifeste corrige : retour **0 rapporte**.

**10334 = 9771 + 563** : le nombre de divergences UID/GID correspond
exactement aux entrees presentes dans la couche. Il ne faut pas y ajouter
la racine absente, ni annoncer10335 egalites/differences comparees.

L'absence de `.` concerne un enregistrement de repertoire, **pas les
octets d'un fichier regulier manquant**. En revanche, sa metadata ne
peut pas etre declaree identique. Les UID/GID different effectivement ;
ne pas les normaliser dans les preuves pour obtenir un PASS.
Les permissions/type egaux sont ceux compares sur les entrees presentes,
selon la methode du comparateur ; cela ne prouve pas ACL/xattrs/mtime.
La topologie hardlink n'est pas demontree et n'entre pas dans la
decision de contenus seuls.

COPY sans --chown peut expliquer un ownership root dans une couche,
mais cette cause doit etre confirmee dans le Dockerfile et la collecte
captures, pas deduite du hash seul. USER65534:65534 regit l'execution
par defaut, pas la propriete des fichiers copies. Aucune conclusion
de provenance, de lisibilite P4 non-root ou de securite n'en decoule.

## 3. Conditions de cloture B1 - contenus seulement

**C1 - pieces ancrees.** Lire les copies de preuves existantes : les
quatre fichiers historiques ancres et les captures config/couche/archive.
Verifier les hashes des copies transferees. Aucun besoin de transmettre
ici le rootfs ou l'archive entiere si la revue independante sur Debian
peut consulter les preuves ancrees deja conservees.

**C2 - methode et completude.** Identifier le code/version/hash du
comparateur et examiner la capture terminee, les commandes, dates,
stdout/stderr et retour numerique. Le retour du comparateur n'est pas
fourni dans la demande ; il est **inconnu ici**, pas suppose perdu ou0.
Un non-zero peut signifier des ecarts de metadata : son interpretation
doit suivre la politique documentee de l'outil, sans le masquer.
Une interruption, exception ou rapport partiel interdit la cloture.

**C3 - chaine d'identite et chronologie.** Relier le rapport exact a
la config bbe90dab..., au diff ID7b1b9ae2..., a l'archive ffec209c...,
au manifeste corrige a37f1847... et a la collecte metadata64863f4e....
Confirmer depuis les captures la relation config -> couche, le format
et la decompression eventuelle. Le retour0 du controle rootfs doit
concerner ce manifeste et cette version figee des sources. Ne pas
inventer des timestamps : ceux des acquisitions ne sont pas fournis ici.

**C4 - couverture et exclusions.** La methode doit comparer l'ensemble
exact des chemins des9771 fichiers et leurs bytes/hash, sans se limiter
aux tailles/mtimes ou a un echantillon. Examiner normalisation des noms,
doublons, chemins, types et traitement des liens le cas echeant. Confirmer
que l'unique absence est un repertoire `.` et aucun fichier regulier.
Conserver les compteurs metadata originaux et leurs limites.

**C5 - decision de revue distincte.** Une autorite/role de revue habilite
peut alors enregistrer **CLOSED_CONTENTS_ONLY** dans une nouvelle evidence :
scope exact, references ancrees, preuve C1-C4, dates/ID de revue, limites,
signataire/attestation selon la politique, tous les GO false.
Ce nouvel acte ne modifie aucun rapport historique et n'approuve ni
le runtime, ni sa provenance, ni un build. Un SHA seul ne signe pas
cette decision. Il n'est pas delivre un tel acte dans ce paquet.

## 4. Decision actuelle et effets sur v3

| Question | Decision |
|---|---|
|Identite de contenus sur les resultats transmis |Etayee, sous reserve C1-C5 |
|B1 contenus formellement clos par ce paquet |Non ; revue des preuves brutes et acte C5 manquants ici |
|Egalite complete des metadonnees |Non : ownership different, racine non comparee |
|Provenance/ABI/base P4 approuvees |Non |
|Statut general / autorisations |BLOCKED / tous false |

Le manque d'ancres P3 mentionne historiquement dans v3 est maintenant
documente par ce complement au niveau des constats operateur. Ne pas
modifier retrospectivement le blocker B1 de v3. Les bytes/provenances
necessaires a B2-B7 ne sont pas derives de l'identite de contenus P3.

image_check.py de v3 demande une equivalence de metadata stricte et
une racine explicite ; ces entrees P3 ne satisfont pas ce perimetre.
Ne pas modifier cet outil, ajouter des flags ignore-uid/root ou
promouvoir son refus en PASS. Le jugement nouveau est limite aux
contenus P3 et n'assouplit pas les exigences de la future image P4.

## 5. Controles minimaux, sans repetition de campagne

Indispensables : revue des pieces/code/captures existants C1-C4,
verification d'integrite des copies recues et acte C5. Si un lien de
preuve manque, qualifier precisement le manque et demander une collecte
**ciblee, en lecture seule et autorisee**, pas une campagne generale.
Si les preuves existantes suffisent, aucun nouveau scan9771 ni export
d'image n'est necessaire pour clore contenus seuls.

Non demandes : refaire43 wheels/32 ELF/1223 references, reproduire encore
les trois rapports v3, relancer sha256sum sur toutes les sources deja
validees, reconstruire une image, relancer P1/P2/P3/D11/H1, chown/chmod
ou ajouter `.` a l'archive historique. Ne pas collecter atime/ctime ou
topologie hardlinks juste pour rendre tous les scopes egaux : ce serait
une qualification metadata distincte, non necessaire a contenus seuls.

evidence_check.py ne controle que hashes des quatre preuves copiees
et syntaxe JSON ; le schema brut n'etant pas fourni, il ne valide pas
automatiquement les compteurs et ne prononce jamais C5. Son rc0 n'est
ni une cloture B1, ni une approbation P4.
