# Procedure future de capture controlee

**Aucune commande de copie, chiffrement, bundle ou transformation ci-dessous n'a
ete executee. Autorisation distincte obligatoire avant execution.**
Le perimetre et ses 115 points d'arret sont dans `PRESERVATION_SCOPE.md`.

## 1. Decisions et prerequisites obligatoires

L'operateur doit renseigner un identifiant de capture et les champs suivants :

| Parametre | Exigence avant execution |
|---|---|
| Source | Racine exacte, cinq worktrees et `.git` commun confirms; pas seulement fichiers visibles par Git |
| A et B | Deux supports physiques independants, hors source et hors l'un de l'autre; pas deux partitions du meme disque ni deux dossiers de C |
| E | Conservation distincte des preuves scellees, avec ses propres copies et ancres; pas un dossier supplementaire dans A comme unique separation |
| R | Emplacement neuf de restauration, protege et isole de l'original |
| Protection | Chiffrement operationnel et teste, ACL limitees, recuperation des cles independante de la sauvegarde |
| Coherence | Fenetre de quiescence approuvee couvrant fichiers, cinq worktrees, Git et toute base concernee |
| Acces/types | 115 refus resolus par une decision autorisee, sans contournement automatique; methode de capture/restitution des sept reparse validee |
| Outil/metadonnees | Methode deja disponible, capable de conserver les bytes, flux et metadonnees declares; essai representatif avant le vrai perimetre |

Si un refus subsiste, le resultat ne peut etre qu'une capture partielle nommee
comme telle : **aucune porte de nettoyage ne s'ouvre**. Reclasser une zone hors
perimetre demande un accord explicite et ne permet pas de dire « tout sauvegarde ».
Ne pas escalader les droits ni changer les permissions de la source dans ce lot.

## 2. Dimensionnement

Volume logique accessible observe : **11 607 939 985 octets**, avant les sept
documents et hors zones inaccessibles/flux non mesures. Sur C, espace libre
observe : **302 731 366 400 octets**, total volume 1 999 090 216 960.
Cela ne valide aucun support externe ni le chiffrement.

Definir S = volume complet mesure apres resolution des trous, en tenant compte
des ADS, de l'allocation du format cible et d'une restitution eventuelle de sparse/
hardlinks. Reserver **au moins 1,30 x S par support A et B**, et autant pour R;
augmenter si conteneurs intermediaires, verification ou fichiers volumineux
necessitent plus. Avec le seul minimum connu : environ **15,10 Go par cible**,
30,20 Go pour A+B, 45,30 Go pour A+B+R, **plus E et ses copies**.
Ce sont des planchers de travail arrondis, pas une capacite suffisante attestee.
Ne compter ni compression ni deduplication comme acquise.
FAT32 est inadapte aux futurs gros fichiers et aux metadonnees NTFS.

## 3. Gel coherent : arret avant toute lecture de capture de base

Identifier les writers reels : IDE/autosave, Git/agents, builds/watchers, services,
outils de sauvegarde, processus utilisant SQLite et tout stockage externe requis.
Obtenir la fenetre et son responsable; aucune commande d'arret n'est lancee ici.

**Ne pas ouvrir SQLite, faire un checkpoint, supprimer WAL/SHM ou declencher SQL.**
Ne pas copier une base active en fichiers successifs. Les cinq couples connus
et leurs bases font partie d'un meme etat a conserver avec temoins/latch/pending.
Une simple stabilite taille/mtime, un dump ancien ou un snapshot filesystem non
qualifie pour l'application ne prouve pas une coherence entre plusieurs stores.

Si les writers ne peuvent etre rendus inactifs avec preuve selon une procedure
distinctement autorisee, ARRET. Une alternative de capture applicativement
coherente exige sa propre autorisation et validation; ce document ne l'accorde
pas. Ne rien lancer sur Docker, SQL ou le VPS pour lever ce blocage.

## 4. Point de capture M0 et inventaire prive

Apres le gel, creer les artefacts uniquement dans l'espace protege des sauvegardes,
jamais dans le depot source. Inclure les dix documents de phase 1 et les sept
documents de ce plan dans le perimetre gele.

Enregistrer commandes exactes, versions, parametres non secrets, horaires,
codes retour, stdout/stderr prives, erreurs et identite des supports.
Capturer les flux Git NUL en bytes, sans conversion PowerShell vers du texte :
HEAD/branche, toutes refs, references symboliques, cinq HEAD/index, statut XY
et noms, index/config/exclude, liste et liens des worktrees, contexte Git effectif.

Consultations de reference, a capturer en prive par un outil qui conserve les bytes :

```powershell
$env:GIT_OPTIONAL_LOCKS = '0'
git -c core.fsmonitor=false -c core.untrackedCache=false --no-pager rev-parse HEAD
git -c core.fsmonitor=false -c core.untrackedCache=false --no-pager status --porcelain=v1 -z --untracked-files=all
git --no-pager for-each-ref --sort=refname --format='%(refname)%00%(objectname)%00%(objecttype)'
git --no-pager worktree list --porcelain -z
```

Ne pas faire une redirection texte PowerShell 5 d'un flux NUL/binaire. Utiliser
`subprocess.run(..., capture_output=True)` et l'ecriture binaire du resultat dans
l'espace chiffre lors de la future implementation autorisee. Rien n'est cree ici.

Inventorier physiquement, sans suivre les reparse et sans limites dues a Git :
chemin relatif exact, type, taille logique, identite/relations hardlink, attributs,
timestamps avec precision declaree, SHA-256 de chaque fichier ordinaire, tous
flux alternatifs avec leur taille/SHA-256, ACL/proprietaire/groupe/audit utiles,
tags et donnees brutes des reparse, cible des liens lorsqu'interpretable.
Repertorier aussi les repertoires vides. Les descripteurs de securite restent prives.

Pour chaque fichier et flux, ouvrir en lecture sans suivre de lien, verifier type/
identite avant/apres lecture et hacher en streaming; relever les changements du
jeu de chemins par deux enumerations. Toute disparition, ajout, changement ou
erreur annule le point M0 : stabiliser puis recommencer dans une capture neuve.
Ne pas appliquer cette lecture de contenu aux bases tant que l'etape 3 bloque.
Pour NTFS, atime n'est pas un invariant de stabilite fiable : documenter sa
politique, sans modifier les reglages du systeme pour cet audit.

Le manifeste prive doit etre deterministe : schema et encodage fixes, chemins
echappes sans ambiguite, tri explicite, aucun chemin absolu de destination comme
identifiant de fichier source. Distinguer erreurs d'inventaire et divergences.
Ancrer son SHA-256 a l'exterieur des copies; un hash stocke uniquement avec les
bytes qu'il controle ne donne pas une ancre independante d'integrite.

## 5. Deux captures independantes A et B

Sous le meme gel, capturer A depuis la source et B depuis la source, avec
verifications independantes contre M0; ne pas prendre A comme seule autorite de B.
Les destinations doivent etre neuves et hors de l'arbre source, sans jonction
retournant vers celui-ci. Pas de synchronisation destructive.

La voie conseillee est un support NTFS chiffre avec acces restreint, plus un
catalogue chiffre des metadonnees source. Ne pas appliquer aux copies les ACL
source potentiellement trop larges : conserver ces ACL comme donnees privees
restituables, tout en maintenant la protection restrictive de A/B.

Robocopy est present. Exemple **conditionnel**, utilisable seulement apres
validation de la methode complete, des variables et des etapes precedentes :

```powershell
# $Source et $Destination : chemins absolus approuves; $PrivateLog : sur support chiffre.
# Destination neuve, non partagee et hors Source; aucun writer de la source.
robocopy $Source $Destination /E /COPY:DAT /DCOPY:DAT /XJ /SL /R:0 /W:0 /LOG:$PrivateLog
$CopyExitCode = $LASTEXITCODE
if ($CopyExitCode -ge 8) { throw 'Echec de copie : aucun nettoyage autorise.' }
if ($CopyExitCode -ne 0 -and $CopyExitCode -ne 1) { throw 'Extras ou differences a examiner.' }
```

**Ce bloc seul n'est pas une sauvegarde complete.** `/XJ` laisse les jonctions
a traiter explicitement; `/SL` ne garantit pas les reparse Linux. Les sept liens,
leurs tags/donnees et leurs relations doivent etre captures et restituables par
la methode supplementaire validee; sinon ARRET. Hardlinks, ACL/owner/audit, EFS,
sparse/compression et ADS doivent egalement passer leur controle specifique.
Les ADS doivent etre verifies, pas supposes preserves par le drapeau DAT.
Une copie ordinaire ne preserve pas automatiquement la topologie des hardlinks.
Ne pas utiliser `/MIR`, `/PURGE`, `/MOVE`, `/MOV` ou un mode de contournement
de securite. Un code Robocopy non fatal n'est jamais une preuve d'exhaustivite.

Un export Git bundle peut etre ajoute plus tard comme redondance utile, avec
verification de ses refs; il n'est pas necessaire a la capture brute de `.git`
et ne remplace ni index/reflogs/objets non references ni aucun fichier courant.
Ne faire ni clone/checkout ni regeneration de sources a la place de leurs bytes.

## 6. Conservation E des preuves scellees

Constituer une liste explicite avant copie : B1, versions de comparateurs,
candidates, sources/materials, manifestes, recus et decisions NO-GO, archives
opaques privees pertinentes. Le volume E complet reste a mesurer.
Copier sans reconditionner les archives, convertir leurs fins de ligne, normaliser
permissions ou reecrire les manifestes historiques.

E doit avoir un support/protection distincts des copies de travail, idealement
une seconde replique hors ligne de ses preuves. Comparer les hashes aux ancres
existantes avant et apres transfert. Sceller le nouveau catalogue de conservation
separement, jamais en remplacant un manifeste historique.
Documenter operateur, dates, source logique, destination privee et chaque transfert.

## 7. Verification totale et fin du gel

Reenumerer la source et refaire M1 : meme jeu de chemins et contenu que M0,
metadonnees selon les invariants declares, refs/HEAD/index/config/exclude et
preuves inchanges. Comparer integralement A puis B a M0 : tous fichiers/flux/
repertoires/liens/metadonnees declares, zero manquant, extra ou divergence.
Comparer E a ses ancres; verifier decryptage et recuperation des cles.

N'arreter le gel qu'apres constat d'une capture coherente; tout changement pendant
la fenetre oblige a rebaseliner et a recommencer sous autorisation, pas a retoucher
M0 pour masquer les differences. Garder tout resultat partiel sous statut explicite.
Conserver les copies maitres intactes, effectuer les essais de restauration sur R.
Appliquer ensuite `RESTORE_VERIFICATION_PLAN.md`, puis seulement evaluer
`POST_BACKUP_CLEANUP_GATE.md`. Aucun GO beta n'est implique.
