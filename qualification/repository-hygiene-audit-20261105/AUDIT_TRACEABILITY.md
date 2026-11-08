# Tracabilite de l'audit Git

Date de l'audit : 2026-11-05. Portee : depot local et metadonnees Git accessibles,
sources courantes selectionnees et references de livraison. **Lecture seule hors
des dix nouveaux fichiers expressement demandes dans ce dossier.**

## Ancrage

```text
branch=branding/docnelo
HEAD=1bc1a4a5bb49395acabdce5e7604d1a6b97dea61
last_commit_date=2026-10-29T19:19:09+01:00
initial_inventory_utc=2026-11-05T13:00:03.247747+00:00
initial_status_entries=4236
tracked_changed=44
untracked_entries=4192
staged_changes=0
BETA_10_GO=false
REGISTRATION_OPENING_AUTHORIZED=false
P4_GO=false
formal_b1_contents_closed=false
```

| Objet de controle | SHA-256 avant ecriture des rapports |
|---|---|
| `.gitignore` | `1c4222f5593b72a5d409ccb898c1d1194ca641e11871452dd8bd9b8b5713dd9b` |
| `.git\index` | `5bdb87bea4d076c752292905e75e3316edb0bc099d4bd4625936e93c5473cd2b` |
| `.git\info\exclude` | `8d2b4a088b08e59dfe7eca95441eeedb6e7ee16db20149d81046e0ecbeaaef5a` |
| `qualification\b1-review-20261105\b1-evidence.tar` | `49418c8f928de66e82b49c5b9834ae1ce0254245a4092898ca0e5b3d28f971cd` |
| `qualification\b1-review-20261105\B1_INDEPENDENT_REVIEW.md` | `edc2309dbef2d302f45767806d5b870489584a9c02591868a23b73344e3d88e0` |

Les ancres B1 concordent avec la revue precedente. Ce controle ponctuel ne vaut
ni nouvelle qualification de tous les octets historiques ni cloture B1.
Les ancres originales P3, couches et inventaires ne sont pas regenerees ici.

## Methode reproductible sans executer l'application

Outils observes : Git `2.44.0.windows.1`, Python `3.13.7`, Windows/PowerShell.
Cette version de Python est celle de l'analyse statique locale, pas une nouvelle
exigence runtime ni une requalification des comparateurs P4 destines a Debian.
Git en consultation avec `GIT_OPTIONAL_LOCKS=0`, pagers desactives.
Sous-processus Python standard avec sorties capturees en bytes; delimitation
NUL, traitement des deux champs XY, consommation du second chemin pour un
renommage/copie, decodage filesystem des chemins. Aucun parsing par espaces ou
lignes des noms de fichiers.

Commandes de base, toutes avec code retour 0 :

```text
git status --porcelain=v1 -z --untracked-files=all
git ls-files -z --cached
git ls-files --others --exclude-standard -z
git ls-files --others --ignored --exclude-standard -z
git ls-files --cached --ignored --exclude-standard -z
git ls-files --stage -z
git rev-parse HEAD
git branch --show-current
git diff --stat
git diff --cached --stat
git worktree list --porcelain
git check-ignore -v --no-index --stdin -z
```

`check-ignore` retourne normalement 1 si aucun chemin ne correspond; cela ne
signifie pas erreur de lecture. Les checks de cas existants ont identifie les
regles et leur origine. Autres consultations : configuration et origine des
reglages, date de commit, refs/reflogs et noms historiques sans blobs prives,
HEAD/statut de chaque worktree imbrique, `git show HEAD:<chemin>` capture en
memoire pour comparer les seuls fichiers source du manifeste de la candidate.

`lstat` fournit taille, type et indicateurs reparse des chemins retournes.
L'inventaire inclut quatre racines de worktrees, pas leur contenu recursif :
deux non suivies et deux ignorees. Les tables de tailles des rapports excluent
leurs tailles de repertoire et comptent uniquement les fichiers ordinaires.
Les quatre statuts internes ont egalement ete consultes sans modification.

Classification ordonnee et disjointe : composants de chemin de cache/generation
et extensions pyc/pyo/tsbuildinfo; puis chemins/noms de tests; puis extensions
source (y compris styles et scripts, SQL sous migrations); documentation;
artefacts/archives/bases/logs et JSON de preuve hors configurations connues;
assets; configurations/modeles/manifestes; reste.
Les dossiers « dist » classes generes restent conserves comme preuves possibles.
Ce classement explique les comptes; il ne decide jamais une suppression.

Analyse de copies : SHA-256 sur les 2 268 fichiers code/tests en attente, sans
execution. AST sur les sources Python actives analysees; comparaison structurelle
des corps d'au moins dix lignes, mesure de longueur et recherche textuelle des
references, completees par lectures ciblees. Recherche des exports frontend,
imports lazy, routes, CLI, Compose/Dockerfile, Alembic, tests et procedures.
Ces techniques n'etablissent pas l'absence de consommateurs externes.

Revue sensible deleguee a un agent en lecture seule, limitee aux metadonnees :
pas de lecture des cles/dumps/documents prives ni d'ouverture des archives.
Les noms personnels reperes historiquement ne sont pas reproduits.

Les scripts et JSON de comptage sont conserves dans l'espace prive de session,
hors du depot; ils ne constituent pas une sauvegarde du worktree. Les tableaux
et la methode ici restent consultables independamment de cet espace.
Aucun nouvel outil, dependance ou fichier d'audit supplementaire n'est installe
dans le depot.

| Artefact prive de reproductibilite | SHA-256 |
|---|---|
| `repository_inventory.py` | `363c0fc047f214fd640e680cd62527bcf410fdb0e9b75384cd5e6ce673d63bff` |
| `repository_inventory.json` | `05593b1de5abc050ba44504f27141001a80375f536ef8e2c5f6b99d76d0426db` |
| `repository_code_analysis.py` | `06fb9f7960a8393646ffefbe43bd239da7a04c7daa8a37b89acf719801a2205c` |
| `repository_code_analysis.json` | `69dcfbaecaa9170e1966fef79f106cc06eb1dd4b601a0d8cc72239335d8c44c9` |
| `repository_candidate_comparison.json` | `ec0014eb941bcde56a515f4071dcfe667f88e1c55af517e59b28204f5e6e84fd` |

## Points de comparaison et preuves anterieures

`deliveries\docnelo-lifecycle-10-api\source-release.json:1-67` :
commit `8b11d4daf47bd7c3c6766b9f5231ea8a84fdbf71`, reference
`a323afc5c9d63a8a9f59ac10c365710b58d1c868`; 15/15 SHA-256 source reverifies.
Les 37 entrees payload et les 288 tests appartiennent a la revue beta precedente,
pas a une nouvelle execution dans cet audit.

References : `qualification\beta-10-readiness-audit-20261105\AUDIT_TRACEABILITY.md`,
`BETA_10_GO_NO_GO.md`, `BETA_10_TEST_GAPS.md`;
rapports API release/provenance/lifecycle dix; inventaire branding R1 et rapport
R2; rapports et manifestes P4/B1 existants. Aucun de ces fichiers n'est reecrit.

## Limites et non-actions

117 avertissements d'enumeration ignoree : 115 permissions et deux fonctionnalites
non implementees. Code Git 0 ne signifie donc pas acces exhaustif. Les zones
inaccessibles ne sont ni ouvertes par un autre droit ni declarees vides.
Le compteur reparse de l'inventaire retourne et les sept points rencontres par
la revue sensible ont des perimetres differents; aucun total physique exhaustif
n'est deduit de ces nombres.

Tailles logiques, pas allocation disque ni taille de sauvegarde; `.git`, liens
non suivis et contenus internes des worktrees imbriques non additionnes.
Pas de scan complet des secrets, objets inatteignables, historique distant,
archives privees ou fichiers de donnees. Absence de secrets non attestee.
Pas de preuve dynamique de code mort ou de tests de comportement nouveaux.

Aucun acces reseau/VPS, Docker, installation, test applicatif, migration,
execution d'un script de maintenance, changement de DB, compteur, permission,
preuve, source, regle d'exclusion ou contenu d'index. Pas de stash, nettoyage,
reset, restore, git rm, commit ou push.

## Resultats de verification documentaire

Controle termine avec code retour 0 : exactement les dix nouveaux fichiers
demandes, tous non suivis; aucune difference entre les 338 empreintes suivies
avant/apres, aucune difference taille/mtime parmi les 4 530 chemins visibles
preexistants; index, exclusions et deux ancres B1 inchanges.

Le patch fourni est au format LF et passe `git apply --check` sans application.
Simulation par configuration `-c core.excludesFile` limitee au processus, avec
regles dans l'espace de session : exactement 597 entrees initiales masquees
(596 cache npm, une cle candidate). Les modeles, migration, archive B1 et dist
de reference echantillonnes restent visibles. Aucune configuration persistante
n'est modifiee. Les 29 citations explicites resolubles controlees ne depassent
pas les bornes des fichiers.

Etat final constate : 44 modifies et 4 202 entrees non suivies, soit 4 246
entrees; la seule difference au statut initial est l'ajout des dix livrables.
Ces livrables ne sont pas indexes et ne constituent pas une decision GO.
