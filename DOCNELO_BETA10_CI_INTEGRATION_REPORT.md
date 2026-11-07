# Docnelo Public Beta 10 - Integration et qualification CI

Date : 2026-11-07.

**Decision : GO pour demander une nouvelle qualification CI distante du
candidat, apres autorisation explicite de commit/publication/lancement.
Production et ouverture des inscriptions : NO-GO.**

Les deux interventions sont compatibles. Les corrections Python sont deja
dans le commit parent ; le retrait Windows et ce rapport sont prepares dans
l'index pour un commit complementaire. Aucun nouveau commit, push, lancement
GitHub Actions, merge, deploiement, acces VPS ou changement de protection
GitHub n'a ete effectue pendant cette integration.

## 1. Etat Git initial et final

Le repertoire initial est sur `branding/docnelo`, HEAD
`1bc1a4a5bb49395acabdce5e7604d1a6b97dea61`, avec 59 fichiers suivis modifies
et de nombreux fichiers non suivis issus d'autres travaux. Il n'a pas ete
change de branche et ces modifications n'ont pas ete selectionnees.

Toutes les operations d'integration concernent exclusivement le worktree :
`deliveries\docnelo-public-beta-release-20261106\source`.

| Element | Etat constate |
|---|---|
| Branche du worktree cible | `release/docnelo-public-beta-10-20261106` |
| HEAD initial et final | `2f25a97087566a49b179bb17f93ef578803ca8c7` |
| Commit precedent | `d5eda52887fa4e5c0ada7f7fc55cbb43f409c5a8`, integration de l'effacement atteste |
| Commit des trois fixtures | `2f25a97087566a49b179bb17f93ef578803ca8c7`, avec le rapport d'analyse CI |
| Branche distante, lecture API du 2026-11-07 | `d5eda52887fa4e5c0ada7f7fc55cbb43f409c5a8` |
| Etat initial cible | 5 fichiers suivis modifies, rapport Windows non suivi, index vide |
| Etat final cible | 7 fichiers selectionnes dans l'index ; aucun changement hors index dans ce worktree |
| Nouveau commit | Non cree ; SHA non applicable, commit prepare seulement |

Le futur commit aura donc les trois corrections Python dans son ascendance,
sans les dupliquer, les ecraser, amender leur commit ou reecrire l'historique.
La branche distante n'a pas encore les corrections du parent.

## 2. Fichiers integres et preservation du perimetre

| Fichier | Origine et changement |
|---|---|
| `tests\test_ai.py` | Parent : IA mockee configuree avant le lifespan ; assertion du worker vivant |
| `tests\test_byok.py` | Parent : comptes, budgets et validateur prepares avant le lifespan ; assertion du worker vivant |
| `tests\test_ai_disabled_enforcement.py` | Parent : approbation explicite du seul compte public fictif autorise |
| `DOCNELO_BETA10_CI_FAILURE_ANALYSIS.md` | Parent : diagnostic et preuves de la mission Python |
| `.github\workflows\ci.yml` | Index : retrait Windows, controle Python/fuseau transfere sur Linux, dependances de publication adaptees |
| `tests\test_deployment.py` | Index : contrats des jobs Linux et des preuves critiques obligatoires |
| `tests\test_release_security.py` | Index : attente de `publish.needs` adaptee seulement |
| `README.md` | Index : contrat CI Linux actuel |
| `docs\sprint-10-rf01-rf02-validation.md` | Index : contextualisation de l'ancienne obligation Windows |
| `DOCNELO_CI_WINDOWS_REMOVAL_REPORT.md` | Index : rapport de la mission Windows conserve |
| `DOCNELO_BETA10_CI_INTEGRATION_REPORT.md` | Index : present rapport |

Une comparaison structurelle de tout `ci.yml` contre HEAD confirme exactement
trois changements : retrait de `jobs.windows`, insertion du controle Linux
Python 3.13/Europe-Paris, et `publish.needs: [python, frontend]`.
Les trois fichiers de fixtures et `deploy.yml` sont identiques octet pour
octet a HEAD. Aucun fichier backend, migration, Compose, production,
dependance ou frontend n'est modifie par les deux missions reunies.

Les fichiers temporaires, archives, images, donnees de laboratoire, secrets,
configurations de production et changements du worktree principal ne sont
pas selectionnes. Les preuves JUnit et actionlint restent hors Git, dans
`files` du dossier de session `12ffa574-cb17-4a50-a650-3af684ea07ab`.

## 3. Contrat CI et protections conservees

`ci.yml` contient uniquement `python`, `frontend` et `publish`, sur Ubuntu
24.04. Les deux jobs de tests sont inconditionnels ; la publication depend
de leur succes et reste reservee a `main`, hors pull request. Un lancement
manuel sur la branche release ne publiera donc pas d'image.

Les declencheurs, permissions, concurrences, timeouts restants et actions
epinglees sont conserves. Aucun `continue-on-error`, nouveau `skip`, `xfail`,
filtre de suite ou condition permettant de sauter une commande Python n'est
ajoute. Les deux suites completes SQLite et PostgreSQL restent sans filtre.

| Protection / domaine | Verification du workflow conserve |
|---|---|
| PostgreSQL et migrations | Image PostgreSQL 17/pgvector, disponibilite TCP, groupe requis sans saut et suite complete ; migrations Alembic executees par les fixtures |
| Approbation et concurrence | Groupe PostgreSQL requis incluant approbation, quota et concurrence, avec `--require-no-skips` |
| Isolation native | Preuves Landlock/seccomp et cible Docker `isolation-tests`, sans reseau, racine en lecture seule, capabilities retirees |
| Effacement | Groupe root isole avec DSN de test, API irrevocablement non-root, `--require-no-skips` |
| Autorite / approbation independante | Preuves root et non-root distinctes, chacune avec `--require-no-skips` |
| Restauration / reprise | Tests lifecycle, sauvegarde, snapshots et quarantaines conserves dans les suites completes ; protocoles PostgreSQL requis |
| Parcours public reel local | Preparation HTTPS/SMTP/Chromium et test e-mail E2E requis sans saut |
| Frontend / BFF | `npm run test:ui`, `npm run test:bff`, `npm run build` obligatoires |
| Livraison | Digests immuables, inventaire contraint, bundle atteste et refus d'ecraser un tag SHA conserves |

`deploy.yml` reste exclusivement manuel, limite a `main` et a l'environnement
`production`. Il exige des reviewers configures, un run CI reussi du meme
depot et du SHA exact de `main`, les attestations du bundle, et les controles
HTTPS/SSH. Ces gardes ont ete lues ; leur configuration reelle complete dans
l'environnement GitHub production n'a pas ete requalifiee ici.

Les valeurs par defaut `ai_enabled=False` et `registration_mode='disabled'`
sont conservees. L'activation IA de test precede uniquement le lifespan des
fixtures positives ; les vrais clients OpenAI restent interdits par les mocks.
Les controles d'e-mail, d'approbation et de compte desactive ne sont pas
affaiblis. Aucun etat de production ni porte SQL existante n'a ete consulte
ou modifie.

### Protection actuelle de main

Lecture seule API realisee le 2026-11-07 :
`branches/main/protection/required_status_checks` exige **python** et
**frontend**, chacun associe a GitHub Actions (`app_id=15368`), avec
`strict=true`. L'API des rulesets du depot retourne une liste vide.

La protection actuelle est compatible avec le retrait Windows. Les mentions
d'une adaptation manuelle encore necessaire dans le rapport Windows et le
README correspondent a la situation historique du 2026-11-06 : cette
adaptation n'est plus necessaire selon la lecture actuelle. Aucune regle
n'a ete modifiee pendant cette mission. Relire les protections avant une
eventuelle integration ulterieure ; ne jamais recreer un faux statut Windows
ni contourner les controles.

## 4. Qualification locale effectivement executee

| Controle | Resultat |
|---|---|
| Premier essai fixtures Windows, dossier temporaire pytest par defaut | 5 reussis, 50 erreurs de preparation, aucun saut ; code 1 |
| Fixtures Windows avec dossier temporaire dedie a la session | 55 reussis, 0 echec, 0 erreur, 0 saut ; `--require-no-skips`, 281,02 s |
| Quatre fichiers de contrats Windows | 250 reussis, 5 sauts, 0 echec/erreur ; 31,13 s |
| Huit fichiers fixtures et contrats reunis sous Linux non-root | 306 reussis, 4 sauts, 0 echec/erreur ; 202,14 s |
| Verification JUnit des seules fixtures Linux | Les 55 cas sont reussis, aucun saut |
| Commande Linux Python/fuseau extraite de `ci.yml` | Succes dans le conteneur Linux |
| Actionlint 1.7.12 sur `ci.yml` et `deploy.yml` | Succes ; shellcheck et pyflakes externes non executes (`-shellcheck= -pyflakes=`) |
| Comparaison structurelle et preservation des fixtures/deploy | Succes |
| `git diff --check` et controle de l'index | Succes |

Le premier essai a echoue sur `PermissionError [WinError 5]` en accedant
au repertoire partage `Temp\pytest-of-Adeline`. Ses erreurs sont conservees
dans `integration-fixtures.xml` ; aucun droit de ce repertoire n'a ete
change. La reprise utilise seulement `--basetemp` dans le dossier de session,
sans changement de test, garde ou dependance.

Les quatre sauts Linux sont les deux preuves root de registre/approbation
et les deux cas necessitant une base PostgreSQL jetable :
`test_real_postgresql_history_and_disabled_account_guard` et
`test_postgresql_close_serializes_with_last_inflight_admission`.
Windows ignore en plus la preuve d'autorite non-root Linux. Les motifs
complets sont visibles avec `-rs` et dans les JUnit. Aucun de ces cas n'est
annonce comme qualifie par ces groupes locaux ; leurs etapes CI dediees
restent obligatoires.

Environnements : Windows CPython 3.13.7, environnement virtuel existant ;
Linux CPython 3.13.18, pytest 9.1.1, image locale
`docnelo-ci-fixture-proofs:20261106`,
`sha256:3fa1e6edeec428f942ea32820a9abcc273542df7a4bb4a03ef3530080417b585`.
Docker Desktop local a ete demarre ; les conteneurs de controle ont termine
et ont ete retires avec `--rm`. Aucun serveur PostgreSQL ou service de
production n'a ete demarre. Sources montees en lecture seule, UID 1000,
sans reseau, rootfs en lecture seule, privileges et capabilities restreints.

Un avertissement Starlette/httpx preexistant reste visible. Actionlint Windows
a ete telecharge depuis sa release officielle et son SHA-256 compare au
fichier de checksums. Les resultats de suites completes, PostgreSQL et
effacement cites dans les rapports precedents sont des preuves historiques,
pas de nouvelles executions de cette integration. Le frontend n'a pas ete
rejoue localement, aucun fichier frontend n'ayant change.

Commandes pytest ciblees, depuis le worktree release :

```powershell
python -m pytest -q -rs -p no:cacheprovider --require-no-skips tests\test_ai.py tests\test_long_summary.py tests\test_ai_disabled_enforcement.py tests\test_byok.py --basetemp=<dossier-session-dedie>
python -m pytest -q -rs -p no:cacheprovider tests\test_deployment.py tests\test_release_security.py tests\test_pinned_builds.py tests\test_public_beta_authorization.py --basetemp=<autre-dossier-session-dedie>
```

La campagne Linux execute les huit fichiers ensemble avec les memes options
de diagnostic, sans `--require-no-skips` pour le groupe mixte dont les quatre
prerequis manquent. Les preuves sont `integration-fixtures-retry.xml`,
`integration-contracts.xml` et `integration-linux.xml`. Les compteurs de ces
campagnes se recouvrent et ne doivent pas etre additionnes.

## 5. Commit prepare et conditions de CI distante

L'index contient exactement les sept fichiers de la seconde mission et de
l'integration. Proposition de message pour le futur commit :

```text
ci: integrate beta ten fixture qualification and Linux-only gates

Preserve the committed Python fixture fixes, require Linux Python and
frontend qualification, and record integration evidence and current main checks.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
```

Conditions necessaires, dans cet ordre :

1. Revoir l'index limite a ce perimetre, creer le commit, relever son SHA
   complet et verifier un worktree release propre.
2. Obtenir une autorisation explicite de push et de lancement Actions.
   Publier la branche sans force, puis verifier que son SHA distant est
   exactement celui du candidat local.
3. Lancer seulement `ci.yml` sur la branche release, jamais `deploy.yml`,
   et verifier le `headSha` du run.
4. Exiger `python` et `frontend` verts, aucun job Windows, publication
   ignoree sur cette branche, et toutes les preuves natives requises sans saut.

Le push de cette branche release ne declenche pas la CI actuelle, dont le
declencheur push est limite a `main` ; un lancement manuel autorise ou une
pull request est necessaire. Un run sur un autre SHA ne qualifie pas ce
candidat. Un succes local ne remplace pas cette nouvelle qualification.

## 6. Risques residuels et verdict

La CI hebergee complete reste a executer : contraintes du runner Ubuntu,
timeout Python de 35 minutes conserve, Docker, PostgreSQL/pgvector,
navigateur/SMTP, preuves root et etapes apres les anciennes erreurs SQLite.
La compatibilite Windows n'est plus garantie automatiquement, volontairement.
Les protections et approbations GitHub peuvent evoluer apres leur lecture.

**GO conditionnel pour lancer la qualification CI apres les autorisations
explicites requises.** Aucun conflit ou regression observe sur le perimetre
integre ; les sauts locaux sont identifies, non transformes en preuves.
**NO-GO production**, publication officielle, merge vers `main`, deploiement
et ouverture des inscriptions : aucune de ces operations n'est autorisee
par ce rapport.
