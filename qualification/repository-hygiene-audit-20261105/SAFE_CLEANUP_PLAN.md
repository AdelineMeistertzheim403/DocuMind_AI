# Plan d'assainissement sur autorisations distinctes

**Phase 1 seulement realisee : diagnostic et dix livrables non indexes.**
Le patch n'est pas applique. Rien n'est supprime, deplace, renomme, retire de
l'index, commite ou deploye.

```text
BETA_10_GO=false
REGISTRATION_OPENING_AUTHORIZED=false
P4_GO=false
formal_b1_contents_closed=false
```

## Phase 2 - Preservation avant toute autre intervention

Trois objets independants sont necessaires. Un clone, un bundle, un patch ou un
stash seul n'est jamais une sauvegarde complete de ce depot.

| Objet | Contenu a preserver | Verification attendue |
|---|---|---|
| Historique Git | Refs locales, tags, commits des cinq worktrees, index, config, info/exclude et metadonnees de liaison worktree; politique specifique pour reflogs et objets non references utiles | Bundle de refs verifie et copie privee coherente des metadonnees; restauration dans un emplacement neuf |
| Travail courant | 44 modifies, tous non suivis utiles, fichiers ignores non reproductibles, sources candidates localement exclues, cles/config privees, sauvegardes et archives | Inventaire prive par chemin/type/taille/SHA-256, deux copies chiffrees independantes, verification integrale des empreintes |
| Preuves scellees | Sources, materiaux offline, archives et manifestes originaux avec ancres independantes et decisions NO-GO | Comparaison byte a byte/empreintes, registre de chaine de conservation, copie immuable separee et test de lecture |

Planifier une fenetre sans ecriture sur ces objets et confirmer leur stabilite
avant/apres capture; ne pas pretendre qu'une copie de SQLite/WAL ou d'un dump en
cours d'ecriture est coherente. Cet audit n'arrete pas de service et ne capture
pas de base active. La methode de capture coherente des donnees actives doit etre
autorisee separement, sans toucher au VPS dans ce lot.

La source imbriquee d'un worktree pointe vers des metadonnees Git communes :
copier uniquement son fichier `.git` ne suffit pas a la rendre autonome.
Un bundle n'inclut ni les non suivis, ni les ignores, ni les modifications non
commitees, ni automatiquement les seuls objets de reflog.
Un diff peut etre incomplet pour les fichiers binaires et ne sauvegarde pas
les non suivis. Inclure les exclusions locales et une correspondance des refs,
worktrees, chemins logiques et empreintes dans le catalogue prive.

**Arret obligatoire** si permission refusee, lien non maitrise, fichier instable,
manifeste incomplet, divergence d'empreinte, donnees privees non protegees ou
espace insuffisant. Les 10,94 Go enumeres ne dimensionnent pas une sauvegarde
exhaustive : `.git`, worktrees internes et zones inaccessibles sont en plus.
Ne pas modifier de permissions pour franchir cet arret.
La validation se fait dans un repertoire neuf, sans import ni execution des
preuves et sans copier des donnees sensibles vers Git.

## Phase 3 - Lots Git limites et reversibles

| Lot propose | Prerequis / effet | Reversibilite et impact qualification |
|---|---|---|
| A - Sauvegarde et catalogue prive | Phase 2 verifiee, sans application runtime | Copies source intactes; aucune qualification transferee |
| B - `.gitignore` cible | Autorisation sur le patch; simulation et revue des 597 entrees cache/cle; conserver exceptions de modeles | Sauvegarder regles avant modification; annuler seulement les propres changements du lot; ne change pas les bytes qualifies |
| C - Documentation/ancres expurgees | Revue confidentialite et listes explicites de fichiers | Aucun changement des manifestes historiques; commit documentaire distinct autorise seulement ulterieurement |
| D - Cache npm | Archivage verifie et fermeture des materiaux offline demontree, puis accord par chemin | L'exclusion seule suffit pour le statut; aucune suppression necessaire. Suppression eventuelle constitue encore un lot separe |
| E - Archives privees et instantanes | Catalogue avec hash, portee et emplacement externe, deux copies et preuve de recuperation | **Aucun deplacement maintenant**; relocalisation ulterieure ne vaut pas preuve de provenance nouvelle; conserver ancres et procedures |
| F - Sources/tests courants | Revue des differences et separation des fonctionnalites | Ne pas confondre mise en Git et approbation de release; qualification nouvelle pour runtime modifie |
| G - Refactoring local | Lot choisi, objectif sans changement de comportement et tests fixes | Nouvelle version si code qualifie touche; sources scellees inchangees |

A-D peuvent laisser intactes les qualifications existantes si aucun byte de leurs
entrees n'est change et si les preuves restent accessibles. E exige en plus
validation de la chaine de conservation et mise a jour du catalogue, jamais
reecriture des manifestes historiques. F/G conservent les anciennes preuves mais
**ne rendent pas ces preuves applicables a une nouvelle candidate**.

Pas de retrait de fichier suivi identifie comme automatique. Tout futur
`git rm --cached`, changement d'historique, effacement ou mouvement demande une
liste explicite, sa sauvegarde verifiee et une autorisation propre.
Ne jamais utiliser `git clean`, `reset --hard`, `restore`, `checkout --` ou un
stash automatique pour atteindre un objectif de compteur.

## Phase 4 - Organisation proposee des futurs commits

Apres autorisation seulement, construire dans une branche de travail nouvelle
une serie de lots examines : configuration Git; documentation expurgee;
sources et tests frontend/BFF d'une meme fonctionnalite; backend avec ses tests;
outils backup/restore avec tests; fonctionnalite capacite dix issue de la
candidate, avec ses migrations/contrats pertinents et sa qualification.

Ne pas separer artificiellement un correctif de ses tests indispensables.
Ne pas faire un commit unique de milliers de fichiers, ni `git add .`.
Selectionner des chemins puis des hunks mixtes avec revue privee du diff indexe;
exclure archives/donnees/cles. La candidate dix et le travail Lite restent des
lignes distinctes tant que leur compatibilite n'est pas qualifiee.

Les sources scellees ne servent pas de repertoire de developpement. Une future
release doit figer commit, tree propre de sa candidate, images/configuration,
manifestes et rapport de tests; un tag ne remplace pas ces controles.

## Lire le statut sans cacher le travail

Consultations possibles maintenant, sans modifier la configuration Git :

```powershell
$env:GIT_OPTIONAL_LOCKS = '0'
git --no-pager status --short --untracked-files=normal
git --no-pager diff --stat
git --no-pager status --short --untracked-files=all -- backend frontend tools tests ops
git --no-pager diff --cached --stat
```

La vue `normal` compacte les repertoires non suivis, mais l'inventaire de reference
reste `--porcelain=v1 -z --untracked-files=all`. Compacter l'affichage ne preserve
rien a lui seul et ne doit pas dissimuler les archives/prives a sauvegarder.
Le patch seul ferait surtout disparaitre un cache et une cle du statut, pas les
preuves utiles. Un statut lisible, non vide et explique est preferable a un
worktree artificiellement propre.

## Phase 5 - Ce qui attend la future qualification beta

Integration capacite dix, auth/session/inscription, effacement, durabilite,
pending/latch/quarantaine, restauration et nouvelles dependances; correction
BFF et parcours E2E; versions legales; provenance du runtime effectivement
destine a la beta; sauvegarde/restauration/rollback reels autorises.
Aucun compteur, witness, verrou ou garde ne doit etre reinitialise pour fusionner
les lignes. P4 et C5 restent des decisions distinctes, sans GO production.
