# Docnelo Public Beta 10 - Qualification CI distante

Date : 2026-11-07.

**Verdict : GO pour poursuivre la qualification du candidat. La CI distante
autorisee est reussie sur le SHA exact publie. Aucun GO production,
deploiement, merge ou ouverture des inscriptions n'est donne.**

## 1. Candidat, publication et provenance

| Element | Preuve |
|---|---|
| Worktree | `deliveries\docnelo-public-beta-release-20261106\source` |
| Branche | `release/docnelo-public-beta-10-20261106` |
| SHA qualifie | `733f224dd7881fbd088e04a23726dc4a07c922c1` |
| Parent contenant les trois corrections Python | `2f25a97087566a49b179bb17f93ef578803ca8c7` |
| Commit cree | `ci: integrate beta ten fixture qualification and Linux-only gates` |
| Publication | Push normal, sans force, de `d5eda528` vers `733f224d` |
| Verification distante apres push | `git ls-remote` identique au SHA local complet |
| Workflow | `.github/workflows/ci.yml`, uniquement |
| Execution | [42362474054](https://github.com/AdelineMeistertzheim403/DocuMind_AI/actions/runs/42362474054), tentative 1 |
| Evenement / branche du run | `workflow_dispatch` / branche release ci-dessus |
| `headSha` du run | `733f224dd7881fbd088e04a23726dc4a07c922c1`, egal au candidat |
| Conclusion GitHub | `completed / success` |
| Creation / fin | 10:05:43 / 10:30:23 UTC, soit 11:05:43 / 11:30:23 CET |

Les sept fichiers de l'index ont ete verifies puis commites, sans ajout
d'autres travaux : `ci.yml`, les deux rapports d'integration/retrait Windows,
`README.md`, `docs\sprint-10-rf01-rf02-validation.md`,
`tests\test_deployment.py`, `tests\test_release_security.py`.
Les trois fichiers de fixtures et `deploy.yml` sont conserves identiques
au parent. Le commit inclut le trailer Co-authored-by prevu.

Le worktree release etait propre apres commit et apres push. Le present
rapport est cree ensuite, localement, non commite et non publie : il ne
change pas le SHA qualifie. Aucun second commit ou push n'est effectue.
Le worktree principal reste sur `branding/docnelo`, avec ses 59 fichiers
suivis modifies et ses travaux non suivis non selectionnes.

## 2. Resultats des jobs

| Job | Identifiant | Conclusion | Duree GitHub |
|---|---|---|---|
| `frontend` | `128373552325` | Succes | 32 s, 10:05:47-10:06:19 UTC |
| `python` | `128373552540` | Succes | 24 min 35 s, 10:05:47-10:30:22 UTC |
| `publish` | `128378810935` | Ignore, aucune etape executee | Sans execution |
| `windows` | Aucun | Job absent | Sans execution |

Aucun echec de test, erreur de preparation, timeout ou annulation CI.
La limite Python de 35 minutes n'a pas ete atteinte ; elle reste inchangee.
Toutes les etapes de qualification Python et frontend sont reussies.

### Frontend

| Etape | Resultat |
|---|---|
| React / Vitest | 11 fichiers, 67 tests reussis, aucun saut annonce |
| BFF / Node | 54 tests reussis, 0 echec, 0 annulation, 0 saut |
| TypeScript et compilation frontend | Succes ; Vite 4,38 s |

Les evenements BFF `ERROR system.api.unavailable` presents dans les logs
appartiennent aux scenarios de refus/indisponibilite volontairement testes ;
le bilan TAP confirme 54 succes et aucun echec. Ils ne sont pas effaces ni
interpretes comme une panne de production.

### Python et preuves natives

| Etape | Reussis | Ignores | Duree pytest |
|---|---:|---:|---:|
| Landlock/seccomp et protocole d'extraction sur le runner | 73 | 0 | 7,53 s |
| Runtime Docker isole, sans reseau ni volumes | 73 | 0 | 12,19 s |
| Suite complete SQLite / POSIX / migrations | 1 223 | 126 | 471,77 s |
| Qualification PostgreSQL requise | 57 | 0 | 47,71 s |
| Effacement root isole et API irrevocablement non-root | 71 | 0 | 176,18 s |
| Parcours navigateur / HTTPS / SMTP requis | 8 | 0 | 20,92 s |
| Preuves natives d'autorite et approbation root | 2 | 0 | 0,72 s |
| Preuve native d'autorite non-root | 1 | 0 | 1,85 s |
| Suite complete PostgreSQL / pgvector | 1 262 | 87 | 599,33 s |

Chaque suite complete contient en outre 24 sous-tests reussis.
Les groupes requis PostgreSQL, effacement, navigateur et autorite ont bien
ete executes avec `--require-no-skips` : aucun saut n'a ete tolere dans ces
groupes. Les compteurs se recouvrent ; ils ne forment pas un total de cas
distincts.

La suite SQLite recupere les 21 anciens echecs/erreurs du run
`42258058708` : 1 223 reussis au lieu de 1 202, sans les 13 echecs et
8 erreurs initiaux, avec les 126 sauts inchanges.
Les fixtures IA/BYOK sont incluses dans les deux suites completes.
L'avertissement de deprecation Starlette/httpx reste visible dans les
campagnes Python ; aucune dependance n'a ete changee pour le supprimer.

## 3. Examen des tests ignores

Les logs distants utilisent `pytest -q`, sans `-rs` ni JUnit des suites
completes : ils donnent les totaux et les marqueurs `s`, pas les motifs
nominatifs de chaque saut. Aucun inventaire JUnit distant n'est invente.

Une collecte locale **sans execution des tests**, sur les sources du SHA
publie, dans Linux non-root et sans les options de laboratoire dediees,
retrouve 1 349 cas et exactement 87 sauts declares par `skipif`.
La lecture des gardes de fixtures explique les 39 sauts PostgreSQL
supplementaires de SQLite. Ce rapprochement est une reconstruction des
conditions de saut, distincte des bilans distants effectivement observes.

| Famille de garde | SQLite | PostgreSQL complet | Preuve complementaire du meme run |
|---|---:|---:|---|
| Effacement / overlay exigeant root et laboratoire isole | 71 | 71 | 71 reussis dans le groupe root dedie |
| Autorite / approbation root | 2 | 2 | 2 reussis dans l'etape root dediee |
| Navigateur / SMTP opt-in | 8 | 8 | 8 reussis dans l'etape E2E dediee |
| Projet Docker snapshot explicite absent | 6 | 6 | Non execute dans ce run |
| Prerequis PostgreSQL | 39 | 0 | Groupe PostgreSQL requis et suite complete reussis |
| Total observe / rapproche | 126 | 87 | Aucun saut dans les groupes requis |

Les 39 cas conditionnes a PostgreSQL se repartissent en 23 cas du protocole
`test_lifecycle_lot210_protocol.py`, 11 scenarios reels de concurrence beta,
et 5 preuves individuelles : derniere admission avec temoin independant,
inventaire transactionnel, fence du writer documentaire, historique/compte
desactive et fermeture serialisee avec la derniere admission.

Les six variantes de snapshot Docker dans `test_public_beta_snapshot.py`
exigent `TEST_SNAPSHOT_COMPOSE`, non fourni par cette CI. Elles restent une
limite de qualification explicite : le succes CI ne vaut pas preuve de ces
parcours de sauvegarde/restauration sur un projet Docker de laboratoire.
Aucun test, `skip`, `xfail` ou contournement n'a ete ajoute pour cette mission.

## 4. Verification des preuves de securite et restauration

Les journaux complets confirment la construction du runtime de test et de
l'image PostgreSQL 17/pgvector, la disponibilite TCP de la base jetable,
et le succes des commandes natives Linux.

Les preuves Landlock/seccomp et Docker conservent `--network none`,
`--read-only`, `--cap-drop ALL` et `no-new-privileges`. Le controleur
d'effacement est execute dans un conteneur root dedie, avec base de test ;
ses 71 cas couvrent la separation irrevocable de l'API non-root, les
autorisations, refus, reprise et controles physiques prevus par ces tests.
Les deux preuves d'autorite/approbation root et la preuve non-root sont
separees et reussies.

Le groupe PostgreSQL requis conserve les migrations, protocoles lifecycle,
temoin independant, approbation et concurrence publique. Les suites
completes incluent les tests de sauvegarde, restauration et reprise,
notamment les trois cas `test_restore_quarantine.py` et les quatre cas
`test_recovery_quarantine.py`, sans garde de saut dans ces fichiers.
La limite des six snapshots Docker opt-in reste celle de la section 3.

L'IA reste desactivee dans l'environnement des jobs ; les scenarios positifs
utilisent les fixtures mockees corrigees. Les controles d'e-mail,
d'approbation, de compte desactive, de quota et de fermeture ne sont pas
modifies. Aucun etat reel de production ou d'inscription n'a ete consulte.

### Materiaux et absence de publication

Un seul artefact est present :
`documind-runner-materials-linux-733f224dd7881fbd088e04a23726dc4a07c922c1`,
ID `13570987252`, 1 941 octets compresses, non expire.
Son digest GitHub est
`sha256:2503df20a90ad4f369b05831ce846e6b44b9ee5c1807f1eab4b5df8f474c7f08`.

L'inventaire contient Python 3.13.18, une couverture complete des contraintes,
aucune anomalie de dependance, et les hashes des workflows, Dockerfiles,
scripts et manifests. Tous ces hashes, ainsi que ceux de `requirements.lock`
et `pyproject.toml`, correspondent aux fichiers du candidat local publie.
L'inventaire indique aussi `npm.downloaded_bytes_verified=false` : il ne
constitue pas une verification independante de tous les octets npm.

L'API des jobs confirme exactement `python`, `frontend`, `publish`, avec
`publish` ignore et zero etape. Aucun login registre, build-push officiel,
bundle `documind-release-*` ou job Windows n'est execute.
Les images construites par le job Python restent des images de test du
runner, non publiees. L'API des runs du SHA ne retourne que ce lancement
de `ci.yml`, aucun lancement de `deploy.yml`.

La protection de `main` a ete relue seulement : `python` et `frontend`
associes a GitHub Actions, `strict=true`. Aucune protection n'a ete modifiee.
Aucun merge vers `main`, acces VPS Debian, deploiement ou ouverture des
inscriptions n'a ete effectue.

## 5. Conservation des preuves

Preuves locales hors Git, dans `files` de la session
`12ffa574-cb17-4a50-a650-3af684ea07ab` :

| Fichier | Usage / SHA-256 |
|---|---|
| `remote-ci-run.json` | Conclusion, SHA, jobs et etapes du run termine |
| `remote-ci-full.log` | Copie texte complete obtenue via gh sous Windows ; `1bcdbdaf024eb26181b174fa70dc494d6c936e0afa76de6b891ede38468533d0` |
| `remote-ci-full-readable.log` | Copie UTF-8 sans sequences de couleur, pour lecture ; original conserve |
| `remote-ci-materials\runner-materials-linux.json` | Inventaire extrait ; `1e7eaede5a8745e5c90c7107757213dc8d7866a8ef1bd6a2c257557a3abf200a` |
| `remote-ci-static-collection.json` | Reconstruction locale des gardes, pas un resultat d'execution distante |
| `remote-ci-watch.log` | Suivi du run, termine avec code 0 |

Les erreurs intermediaires de lecture CLI (quoting jq sous PowerShell et
refus de sequences de couleur pour les logs bruts) ont ete resolues par
lecture JSON PowerShell et conservation des logs dans un fichier.
Elles n'ont entraine ni nouveau run, ni annulation, ni modification du candidat.

## 6. Decision pour la suite

**GO : candidat publie et qualifie par la CI complete autorisee sur le SHA
exact, avec les deux jobs obligatoires verts et les preuves critiques
dediees sans saut.** Aucun correctif supplementaire n'a ete applique.

Restent distincts : les six snapshots Docker opt-in, la qualification
operationnelle de l'environnement Debian reel, les approbations independantes
et les preconditions de production/juridiques deja documentees. Le retrait
Windows supprime volontairement la detection automatique de ses regressions.

**NO-GO pour toute operation de production ou ouverture publique dans cette
mission.** La poursuite de la qualification ne vaut pas autorisation de
merge, publication d'image officielle, lancement de `deploy.yml`,
deploiement VPS ou modification des inscriptions.
