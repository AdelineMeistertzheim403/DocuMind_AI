# Porte prealable a un futur lot .gitignore

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

**Porte fermee.** Le plan n'est pas une sauvegarde. Aucune application du patch,
suppression, relocalisation ou operation d'index n'est autorisee ici.

## 1. Ancres preparatoires, sans contenu sensible

| Objet | SHA-256 observe |
|---|---|
| `.gitignore` | `1c4222f5593b72a5d409ccb898c1d1194ca641e11871452dd8bd9b8b5713dd9b` |
| `.git\index` | `5bdb87bea4d076c752292905e75e3316edb0bc099d4bd4625936e93c5473cd2b` |
| `.git\config` | `348faa61a1944308d9f071510b565acde1d0e4f109ce01adba6d285be2ccec83` |
| `.git\info\exclude` | `8d2b4a088b08e59dfe7eca95441eeedb6e7ee16db20149d81046e0ecbeaaef5a` |
| Proposition de phase 1 `GITIGNORE_PROPOSAL.patch` | `438e11eb508f28ed0027c0ae1ec8302a1dcbad44a229c5388fefacae546a4843` |
| 96 refs, format ci-dessous | `de62260fb319631a7e482166c8ca6d45ef7af04f31e790853a2e02ca9ae951b8` |
| 338 couples chemin/empreinte suivis | `e03fd7700a9961b1db8183a7e5119827f5a121a82e63d99b8ee7383418a95494` |
| 44 couples chemin/empreinte modifies | `01e0b973e4ca6179c17ff43cf020f8d4686a2293f9a537fbc303d1aa70cc3bb8` |
| Dix couples nom/empreinte des livrables de phase 1 | `2155abee03907bbb5c5bdba35d1bb4e94b62d67d5c807a24d195c68d57618240` |

Refs : bytes de sortie `git for-each-ref --sort=refname
--format=%(refname)%00%(objectname)%00%(objecttype)`, avec LF emis par Git.
Couples suivis/modifies : tri des enregistrements `chemin Git UTF-8 + NUL +
SHA-256 hex ASCII des bytes + NUL`. Chemins Git avec `/`, sans traduction de
fins de ligne. Pour les livrables, nom du fichier puis empreinte, meme encodage.
Les `/` ici sont la representation Git canonique, pas une commande filesystem.
Les ancres des deux preuves B1 sont dans `RESTORE_VERIFICATION_PLAN.md`.

HEAD attendu : `1bc1a4a5bb49395acabdce5e7604d1a6b97dea61`.
Ces ancres ne remplacent pas le point M0 a creer apres le gel. Un ecart legitime
avant la capture demande une nouvelle base examinee, pas l'utilisation forcee
de chiffres historiques.

## 2. Conditions toutes necessaires

| Controle | Preuve future requise | Etat actuel |
|---|---|---|
| Perimetre complet | 115 refus traites sans omission cachee, liens/ADS/ACL captures, zero zone inconnue indispensable | BLOQUE |
| Coherence | Writers identifies et protocole autorise, M0=M1, bases/WAL/SHM coherents | NON ETABLI |
| Deux copies | A/B independants, chiffres, tous fichiers/flux verifies, cles recuperables | NON EXECUTE |
| Preuves separees | E/replique et ancres externes, B1 et autres manifestes intacts | NON EXECUTE |
| Restaurations | R-A et R-B completes, cinq worktrees recuperes, zero ecart non autorise | NON EXECUTE |
| Etat source | HEAD/refs/index/config/exclude, 44 modifies, non suivis utiles et preuves inchanges entre capture et lot | A RECONTROLER |
| Confidentialite | Supports/logs/manifestes proteges, pas de secret dans la revue publique | A VALIDER |
| Autorisation du lot | Accord explicite sur ce patch exact et seulement celui-ci | ABSENTE |

Tout FAIL/INCOMPLETE maintient la porte fermee. Si du travail utile change apres
les sauvegardes, capturer et verifier ce delta avant nettoyage ou refaire le point
de capture. Ne pas considerer une sauvegarde ancienne comme protection automatique
de nouveaux non suivis ou changements de DB.

## 3. Proposition existante examinee, non appliquee

Le 2026-11-05, `git apply --check` sur le patch de phase 1 retourne **0** contre
le worktree courant. Le patch est LF, 23 lignes ajoutees apres la ligne 36;
aucune source candidate ou manifeste n'a ete modifie pour ce controle.
Le controle est non mutant; il ne demontre pas seul la semantique des exclusions.

Les regles ajoutent caches racine/frontend precis, variantes `.env.*` racine
avec exceptions, un cache npm precis et un chemin de cle precis. Pas d'exclusion
globale des sources, SQL, logs, archives, dist scelles ou quatre familles de preuves.

Ensemble attendu d'entrees actuellement visibles qui changeraient de couverture :

| Ensemble defini exactement sur le statut NUL de reference | Nombre |
|---|---:|
| Tous les chemins commencant par `deliveries/docnelo-web-branding-r1/npm-cache/` | 596 |
| Chemin exactement `deliveries/docnelo-signup-e2e-lab/tls/lab.key` | 1 |
| Total | 597 |

Empreinte de la **liste de ces 597 chemins**, tries, encodes UTF-8 et chacun suivi
de NUL : `6f7d88d209113289d5822b6189d36cc5e3f5c307254e3cc56cdce9afc519d62d`.
Ce hash identifie des chemins, pas leurs contenus et pas un resultat nouveau de
Git avec patch applique. La simulation Git de phase 1 avait donne 597; ici le
comptage par ensemble retrouve 597 et le controle d'applicabilite est refait.
La preuve semantique complete par Git reste exigee lors du futur lot.

Il n'est pas necessaire de publier les 596 noms de cache dans un rapport : le
lot futur doit produire leur **liste exhaustive privee**, non un echantillon,
avec regle/origine, type, taille, hash de contenu et reference a A/B.
Tout autre chemin nouvellement ignore est un ecart bloquant a examiner.

## 4. Controle semantique dans une restitution derivee apres preservation

Avant application au worktree original, utiliser une restitution R validee,
avec ses exclusions locales reconstituees. Autorisation specifique de l'essai :
capturer les ensembles suivis/non suivis/ignores de tous les worktrees, ainsi que
les 338 empreintes suivies et manifeste physique. Puis appliquer uniquement le
patch dans cette restitution, jamais dans une candidate scellee.

Apres l'essai, enumerer par Git les chemins de reference avec
`check-ignore -v --no-index --stdin -z`. Capturer les quadruplets
source/ligne/motif/chemin. Une negation `!` ou un motif vide ne compte pas comme
exclusion positive. Ne pas confondre code 1 (aucune correspondance) et erreur.
Comparer l'ensemble nouvellement ignore a la liste exhaustive privee attendue,
pas seulement au nombre 597; verifier aussi tous les fichiers physiques et tous
les chemins suivis. Un fichier suivi peut rester visible malgre une exclusion :
`--no-index` est necessaire pour detecter ce masquage potentiel.

Matrice positive/negative minimale, puis couverture de toutes les sources/tests/
preuves presentes dans le manifeste et de tous les modeles `.env.*.example` :

| Chemin de controle, reel ou synthetique | Resultat attendu |
|---|---|
| `.env.preview`, `.ruff_cache\probe`, `frontend\.vite\probe` | Ignore par ajout |
| `.env.example`, `.env.production.example`, `.env.public-beta.example`, `.env.public-beta.images.example` | Non ignore par ajout |
| `backend\main.py`, `tests\test_public_beta.py`, migrations source | Aucun nouvel ignore |
| `qualification\b1-review-20261105\b1-evidence.tar`, manifestes, recus et rapports | Aucun nouvel ignore |
| Dist de reference R1, exports, candidates et sources scellees | Aucun nouvel ignore |
| TLS `lab.key` | Ignore par chemin precis, bytes sauvegardes inchanges |
| TLS `lab.crt` | Aucun nouvel ignore |

Conserver les exclusions locales existantes : ne pas exiger qu'une candidate
deja ignoree devienne visible. L'invariant est **aucun nouvel ignore accidentel**.
L'index ne change pas; aucun `git add`/`git rm` ou reindexage n'est autorise par
ce lot. Aucun suivi actuel ne doit devenir couvert par une nouvelle exclusion.

## 5. Autorisation finale eventuelle et apres-lot

Apres recepisses PASS et revue de la simulation, demander un accord distinct sur
le patch exact et sa liste d'effets. Juste avant application eventuelle a l'original,
recontroler tous les invariants de l'etape 2; toute derive arrete le lot.
Apres application autorisee, seul `.gitignore` doit changer en contenu.
HEAD, refs, index, configuration, les 44 contenus modifies historiques, preuves,
candidates, caches et cles doivent rester byte a byte preserves. Le statut pourra
ajouter `.gitignore` aux 44 modifies; ce changement est attendu, pas une perte.

Les 596 fichiers npm ne sont **jamais supprimes** par une exclusion Git.
Conserver leur sauvegarde et leurs bytes source tant que la fermeture offline
des materiaux, leur reproductibilite et une suppression distincte ne sont pas
explicitement validees. Rien n'autorise a nettoyer les 27 distributions de preuve.
Une restauration des propres changements du lot requerrait elle aussi une action
autorisee; pas de `git restore` ou reset global comme « rollback » automatique.
