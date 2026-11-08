# Preservation et recuperation des worktrees

**Procedure future, non executee.** Aucun `worktree add/repair`, checkout,
clone, bundle, changement de ref ou reparation n'est lance sur le depot courant.

## 1. Carte verifiee

Les cinq worktrees partagent `.git`; les quatre fichiers `.git` imbriques
pointent vers leurs repertoires administratifs, pas vers des sous-modules.

| Identifiant / chemin relatif | HEAD | Branche ou etat | Administration | Suivis / statut |
|---|---|---|---|---|
| W0, racine | `1bc1a4a5bb49395acabdce5e7604d1a6b97dea61` | `branding/docnelo` | `.git` | 338 / 44 modifies et 4 202 non suivis avant ce plan |
| W1, `deliveries\docnelo-web-branding-r1\source` | `22b6428f961e98c6482a9881579361f53c114934` | `branding/docnelo-public-beta-web-r1` | `.git\worktrees\source` | 298 / aucune entree retournee |
| W2, `deliveries\docnelo-web-branding-r2\source` | `b046e5d8256d45b65bf575a8a006351616b69fc9` | `branding/docnelo-public-beta-web-r2` | `.git\worktrees\source1` | 347 / aucune entree retournee |
| W3, `deliveries\docnelo-lifecycle-10-api\source` | `8b11d4daf47bd7c3c6766b9f5231ea8a84fdbf71` | `preparation/docnelo-public-beta-lifecycle-10` | `.git\worktrees\source2` | 1 546 / aucune entree retournee |
| W4, `deliveries\docnelo-signup-e2e-lab\source` | `b046e5d8256d45b65bf575a8a006351616b69fc9` | HEAD detache | `.git\worktrees\source3` | 347 / aucune entree retournee |

Aucune entree de statut ne signifie pas absence d'ignores. W2/W3 sont masques
par les exclusions locales du parent. Les racines W1/W4 sont chacune une entree
non suivie du parent, pas un inventaire de leurs centaines de fichiers.

## 2. Bytes et relations a preserver

Capturer tout `.git`, y compris les quatre dossiers administratifs, leurs HEAD,
index, logs, commondir/gitdir, config et refs pertinents; tout le contenu physique
de W0-W4, y compris ignores et leurs marqueurs `.git`.
Le `commondir` de chaque worktree rejoint le meme depot commun. Les fichiers de
liaison peuvent utiliser des chemins absolus propres a cette machine.
Ne copier aucun seul gitfile comme substitut a la base objets et aux index.

| Worktree | SHA-256 du gitfile | SHA-256 de son index |
|---|---|---|
| W1 | `c1ece9541bfec50921b3b01b7127a05fe20962345752390043f568efafdac8b7` | `f3c184b5bed25f930b0f1a8b7775835ff246d5c56edf602cd1696591cbae016e` |
| W2 | `fde321e71a6deb310c3f35485852634e187b4a01e99c6e1cf24108fe9e5bf202` | `ae71d397069c29e07f266a685314d3436d002b205e6244d48b1ee289880bf886` |
| W3 | `a4c18bee6206a26a345e6800ec23b41eb49f84809ad46af57c645ac92f18c146` | `9f044728f088f4678bf44c70b72238f3b170aa075f023bfebc797642fc1218af` |
| W4 | `c700a6fc1b50ac4049bf2b49bfcf20976c751d20f053560ffdef8d409e111a76` | `9fd18546f1183c6afded41c9b6a85ba99ef16b2fa438174fc93de8a0586a69d0` |

SHA-256 de chacun des quatre fichiers `commondir` observes :
`340ddcb67a6204f742cd1e28e5b462622dde7daaa8ee36001897196aacdc6d47`.
Ces ancres preparatoires seront reverifiees au gel; elles ne sauvegardent pas
les fichiers qu'elles identifient.

## 3. Historique et contexte Git

Conserver les 96 refs enumerees et les commits detaches, les reflogs et tout le
stockage objets, y compris objets utiles non accessibles par les seules refs.
Pas de gc, prune ou nettoyage. Un bundle `--all` ne preserve pas automatiquement
un HEAD detache sans ref, les seuls objets de reflog, les index ou les non suivis.
La copie brute coherente de `.git` est donc la base, le bundle un complement.

Pas d'alternates, shallow ou LFS observes dans les points controles; reverifier
les dependances au gel. La configuration globale/systeme et l'environnement
`GIT_CONFIG_COUNT` demandent un releve prive des reglages pertinents.
Ne pas recopier tout le profil personnel ni publier les URL/identifiants Git.
Conserver les hooks comme donnees, sans les executer.

## 4. Recuperation derivee en environnement isole

1. Restituer tous les bytes et metadonnees depuis A ou B vers R neuf et protege.
   Verifier la copie brute contre M0, avant toute commande qui reecrit des liens.
2. Garder les copies maitres et E intactes. L'original ne doit pas etre accessible
   en ecriture depuis R. En particulier, ne pas lancer Git depuis un worktree
   imbrique restaure dont `.git` pointe encore vers l'ancien chemin.
3. Etablir la correspondance privee W0-W4 vers leurs nouveaux chemins absolus.
   Verifier que les nouveaux chemins et leurs parents ne passent pas par un lien
   vers l'original. Les chemins de liaisons et de configuration doivent rester
   confines a l'environnement de restitution.
4. Autoriser une reparation administrative seulement dans la restitution derivee.
   Depuis W0 restaure, `git worktree repair` avec les quatre nouveaux chemins peut
   retablir les liaisons selon la version Git validee. Cette commande peut reecrire
   des marqueurs `.git` et gitdir : journaliser chaque difference et ne pas
   l'executer si l'isolement de l'original n'est pas garanti.
5. Pour toutes les commandes, desactiver fsmonitor, hooks, maintenance/gc
   automatiques et transport reseau dans l'environnement de test. Utiliser un
   repertoire de hooks vide cree pour cet essai autorise; ne modifier aucune
   configuration de la source originale. N'autoriser que les inclusions de
   configuration privee pertinentes et controlees dans R.
6. Consulter dans chaque worktree restaure `--absolute-git-dir`, `--git-common-dir`,
   HEAD, branche/detached, index et statut NUL. Tous doivent pointer vers le
   nouveau depot commun. Comparer les identities et les etats de M0, pas les
   chemins absolus ni les hashes des marqueurs volontairement relocalises.
7. Verifier les objets/refs et tous les fichiers courants, dont les non suivis
   et ignores, sans checkout/restore/reset ou reconstruction des sources.

Si une reparation necessite davantage que la relocalisation administrative
declaree, ARRET et revue. La relocalisation ne s'effectue jamais dans les
livraisons scellees maitres; leurs gitfiles originaux restent conserves dans A/B/E.
Un hash change apres reparation n'est acceptable que pour le fichier administratif
declare, pas pour un fichier source ou une preuve.

## 5. Candidate dix admissions distincte

W3 et ses manifests ne sont ni fusionnes ni recopies dans W0 pour recuperer W0.
Preserver source-release, payload, archives, logs/rapports et leur contexte.
Verifier les 15 SHA-256 source declares, sans reexecuter les 227+50+11 tests.
Ces tests restent historiques; la restauration du depot ne vaut ni qualification
de la candidate ni autorisation d'ouverture de dix inscriptions.
