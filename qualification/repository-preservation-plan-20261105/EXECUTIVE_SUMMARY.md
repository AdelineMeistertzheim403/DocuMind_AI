# Phase 2 - plan de preservation, pas sauvegarde

**PLAN_READY_CAPTURE_BLOCKED. Les sept documents sont prepares, aucune copie,
transformation, sauvegarde, restauration ou application du patch n'est executee.**

```text
BACKUP_EXECUTED=false
RESTORE_TEST_EXECUTED=false
PRESERVATION_VERIFIED=false
GITIGNORE_APPLICATION_AUTHORIZED=false
BETA_10_GO=false
REGISTRATION_OPENING_AUTHORIZED=false
P4_GO=false
formal_b1_contents_closed=false
```

## Constate

HEAD/branche et 44 fichiers modifies inchanges. Le statut avant ce plan est
44 modifies + **4 202 entrees non suivies**, les dix livrables de phase 1 expliquant
l'ecart avec les 4 192 historiques. Les quatre worktrees imbriques et la racine
partagent `.git`; la candidate dix reste au commit `8b11d4d...`, distincte du
worktree principal. Les deux ancres B1 controlees restent conformes.
Le patch existant passe `git apply --check` sans application.

Controle documentaire : exactement sept nouveaux documents non indexes; les
338 empreintes suivies, les 44 contenus modifies, les 96 refs, la carte des
worktrees, index/config/exclusions, dix livrables de phase 1 et deux ancres B1
controlees sont inchanges. Les 15 fichiers du manifeste source de la candidate
dix restent conformes. Le statut constate apres creation du plan est 44 modifies
et 4 209 entrees non suivies. Ces controles ne sont pas un test de sauvegarde.

Un parcours physique sans suivre les liens a enumere **11 607 939 985 octets**
accessibles, dont environ 630 Mo de `.git`, 146 885 fichiers ordinaires et
18 186 repertoires. Aucun changement taille/mtime n'a ete detecte au second
passage des fichiers enumeres; cela ne prouve pas une capture coherente.

## Blocages et informations manquantes

**115 refus de permission** sont listes dans `PRESERVATION_SCOPE.md`.
**Sept reparse/liens** restent a preserver comme tels, dont cinq objets Linux
non lisibles par `os.readlink` ici. Les deux jonctions node_modules ont une cible
interne connue; aucun lien n'a ete suivi.
Cinq couples SQLite WAL/SHM existent : activite/inactivite des writers inconnue.
Pas de copie de ces fichiers ni protocole SQL lance.

Manquent : resolution autorisee des zones inaccessibles sans contournement,
gel coherent des writers, methode validee pour reparse/ADS/ACL et autres
metadonnees, deux supports physiques independants, conservation E separee,
chiffrement/reprise des cles testes, lieu isole de restauration et volume complet.
Deux configurations Git externes et un contexte `GIT_CONFIG_COUNT` necessitent
un releve prive des dependances pertinentes, sans export de leurs valeurs ici.

## Espace et protection

C libre observe : **302,73 Go**; ce n'est pas une destination de sauvegarde
independante ni une preuve de chiffrement. Sur le minimum accessible actuel,
prevoir environ **15,10 Go par support A/B** avec marge de 30 %, autant pour
un essai R, **plus la conservation E et sa replique**. Le vrai besoin sera plus
grand si les zones inconnues, ADS ou autres metadonnees l'exigent; aucun chiffre
final de capacite n'est encore valide. Ne pas supposer la compression.

Procedure : gel autorise, inventaire physique prive et manifeste SHA-256 exhaustif
M0, captures independantes A/B protegees, conservation E des preuves sans
reecriture, controle M0/M1 et copies integral, puis essais R-A/R-B et recuperation
des cinq worktrees en isolement. Git bundle/clone/patch seuls sont insuffisants.
Les donnees privees, logs, historiques et manifestes restent chiffres hors Git.

## Prochaine decision

Les informations suffisent a etablir ce plan, **pas a certifier une sauvegarde
complete coherente ni a commencer `.gitignore`**. La prochaine autorisation doit
designer les supports et la protection, les responsables/fenetre de quiescence
et le traitement des trous de couverture et metadonnees. Toute capture partielle
reste explicitement incomplete et n'ouvre aucune porte de nettoyage.

Apres captures et restaurations effectivement PASS, une autorisation distincte
pourra porter sur le patch exact : 596 chemins de cache + une cle candidate
attendus, liste privee exhaustive et exceptions/source/tests/preuves controles.
Le cache restera physiquement conserve. Ni ce plan ni une preservation reussie
ne qualifient la beta, ne ferment B1 ou n'autorisent un deploiement.
