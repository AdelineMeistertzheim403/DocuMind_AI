# Docnelo - Retrait du job Windows de la CI

Date : 2026-11-06.

Perimetre : worktree de livraison, branche
`release/docnelo-public-beta-10-20261106`,
base `2f25a97087566a49b179bb17f93ef578803ca8c7`.

**Resultat local :** le job Windows est retire et la publication reste
conditionnee au succes de `python` et `frontend`, tous deux sur Linux.
Les modifications ne sont ni commitees ni publiees par cette mission.
Aucune CI distante, publication d'image ou operation VPS n'est declenchee.
La protection GitHub de `main` reste a adapter manuellement.

## 1. Inventaire exhaustif des workflows de livraison

Les deux seuls fichiers suivis dans `.github/workflows` ont ete lus
integralement. Aucun workflow reutilisable ou matrice d'OS n'est present.

| Workflow | Declencheurs | Jobs avant modification | Decision |
|---|---|---|---|
| `ci.yml` - CI and registry release | Pull requests, push sur `main`, lancement manuel | `python` Ubuntu 24.04 / 35 min ; `windows` Windows 2022 / 25 min ; `frontend` Ubuntu 24.04 / 15 min ; `publish` Ubuntu 24.04 / 60 min | Retrait de `windows`, transfert du controle Python/fuseau, adaptation de `publish.needs`. |
| `deploy.yml` - Approved VPS deployment | Uniquement `workflow_dispatch` | `deploy` Ubuntu 24.04 / 40 min, branche `main`, environnement `production` | Aucun changement. |

`windows` n'avait aucun `needs`, sortie, service de production,
environnement GitHub ou secret applicatif. Sa seule dependance sortante
etait `publish.needs: [python, windows, frontend]`.
Le deploiement exige un run CI completement reussi sur le SHA exact de
`main`, mais ne reference aucun job Windows individuellement.

Les declencheurs, permissions, concurrences et conditions existantes sont
conserves. Aucun timeout restant n'est augmente.
La condition de publication reste : evenement autre qu'une pull request
et reference `refs/heads/main`, apres succes des deux dependances Linux.
Le deploiement conserve ses approbations humaines, ses controles
d'attestation/digests, de provenance du run et de configuration HTTPS/SSH.

## 2. Commandes et couverture Windows retirees

Le job utilisait Python 3.13 x64 et `pwsh`, avec checkout epingle et sans
conservation des credentials. Ses commandes etaient :

| Controle | Commande ou comportement | Equivalent Linux / decision |
|---|---|---|
| Outils de build | `python -m venv .ci-venv`, installation avec `--require-hashes -r requirements.build.lock`, ajout de `Scripts` au PATH avec controle des codes de sortie | Venv et installation hash-pinnee deja presents dans `python`, avec chemins Linux. |
| Dependances de test | `python -m pip install --index-url https://pypi.org/simple --no-build-isolation --check-build-dependencies -c requirements.lock '.[test]' tzdata` | Meme installation contrainte deja presente sur Linux ; ajout Windows de `tzdata` non necessaire si la base IANA systeme existe, ce qui est desormais verifie. Aucun manifeste de dependances modifie. |
| Plateforme et fuseau | Assertion `sys.platform == 'win32'`, Python 3.13, puis `ZoneInfo('Europe/Paris')` | Transfere dans `python`, assertion de plateforme remplacee par `linux`. |
| Inventaire | `python tools/build_materials.py --require-pins --npm-lock frontend/package-lock.json` | Deja obligatoire sur Linux, artefact Linux conserve 90 jours. |
| Suite portable | Retrait de `TEST_DATABASE_URL`, creation du dossier de diagnostics, pytest ci-dessous, propagation de son code de sortie | Les deux executions Linux sans filtre couvrent deja ces fichiers et les cas POSIX. |
| Diagnostics Windows | XML pytest conserve 14 jours, inventaire Windows conserve 90 jours | Artefacts propres au runner retire supprimes ; journaux et inventaire Linux conserves. Ce ne sont pas des cas de test. |

Invocation pytest exacte retiree :

```text
python -m pytest -q -p no:cacheprovider -m "not posix" --durations=0 --durations-min=0.1 --junitxml=ci-artifacts/windows-pytest.xml
```

Le job fixait `AI_ENABLED=false`, la cle OpenAI vide,
`REGISTRATION_MODE=disabled`, `DATABASE_URL=sqlite://`,
`BFF_SERVICE_KEY` vide et `API_KEYS={}`.
Sur Linux, les gardes IA existantes restent inchangees et les fixtures
creent leurs bases SQLite temporaires ou utilisent les DSN PostgreSQL
de laboratoire explicitement fournis. Aucun secret de production n'est
injecte dans le job de tests.

Cette selection Windows etait un sous-ensemble de la collection pytest
Linux sans filtre. L'audit des conditions de plateforme dans `tests` n'a
identifie aucun cas metier execute exclusivement sur Windows.
Les exceptions de plateforme concernent les preuves POSIX/Linux, les
permissions/liens ou le choix de l'executable OpenSSL ; le parcours
natif Linux correspondant reste couvert.

Le test de contrat imposant l'existence du job Windows est remplace par
un contrat imposant les suites completes et preuves critiques Linux.
Aucun test metier, de securite ou d'authentification n'est supprime,
ignore ou transforme en `xfail`.
Les aides locales Windows et les rapports de campagnes historiques restent
conserves ; ils ne constituent plus le contrat CI de production.

## 3. Couverture critique conservee

| Domaine | Execution obligatoire conservee dans `python` ou `frontend` |
|---|---|
| Suite portable et POSIX | `python -m pytest -q` complet sur SQLite, puis complet avec PostgreSQL/pgvector ; aucun filtre `not posix`, exclusion de fichier ou filtre `-k`. |
| Isolation et securite natives | Landlock/seccomp et protocole d'extraction ; construction/execution de la cible Docker `isolation-tests`, sans reseau, racine en lecture seule, capabilities retirees. |
| Authentification et beta dix comptes | Suites completes incluant comptes, sessions, approbation, autorisations, refus avant approbation, quota cumulatif et fermeture ; approbation et concurrence PostgreSQL avec `--require-no-skips`. |
| Resumes et IA desactivee | `test_ai.py`, `test_long_summary.py`, `test_byok.py`, `test_ai_disabled_enforcement.py` inclus dans les deux suites completes ; mocks et interdiction des vrais clients IA conserves. |
| PostgreSQL et migrations | Image PostgreSQL 17/pgvector de `Dockerfile.db`, groupe PostgreSQL requis sans saut, suite PostgreSQL complete et migrations Alembic des fixtures. |
| Sauvegarde, restauration et reprise | Suites completes incluant lifecycle/durabilite, `test_restore_quarantine.py`, `test_recovery_quarantine.py`, snapshots et controles de release/deploiement ; groupe PostgreSQL lifecycle requis sans saut. |
| Effacement physique | Controleur root isole, API irrevocablement non-root, `test_standard_erasure.py` et `test_erasure_deployment.py`, avec `--require-no-skips`. |
| Autorite et approbation independante | Preuves natives root et non-root separees, chacune avec `--require-no-skips`. |
| Parcours HTTPS/SMTP reel local | Preparation Chromium et frontend, `test_public_beta_email_e2e.py` avec `--require-no-skips`, services exclusivement de laboratoire. |
| Frontend et BFF | `npm run test:ui`, `npm run test:bff`, `npm run build`, dans le job `frontend` obligatoire. |
| Integrite de livraison | Actions epinglees, inventaire de dependances contraint, images `linux/amd64`, bundle et digests attestes avant livraison ; approbation independante de deploiement conservee. |

Une comparaison semantique de l'integralite de `ci.yml` avec la base Git
a confirme exactement trois differences : retrait du job Windows,
transfert du controle Python/fuseau dans le job Linux et retrait de
`windows` dans `publish.needs`. Toutes les autres etapes, y compris les
commandes Linux ci-dessus, leurs environnements et conditions, sont
identiques. `deploy.yml` est egalement identique a la base Git.

## 4. Fichiers modifies

| Fichier | Modification |
|---|---|
| `.github/workflows/ci.yml` | Retrait du job Windows, controle Python/fuseau Linux, `needs: [python, frontend]`. |
| `tests/test_deployment.py` | Adaptation des dependances attendues ; remplacement du contrat Windows par le contrat de couverture Linux ; maintien des gardes sans `continue-on-error` ni saut conditionnel des commandes Python. |
| `tests/test_release_security.py` | Adaptation de l'attente `publish.needs`, sans modification des controles d'attestation. |
| `README.md` | Documentation CI/CD courante, Linux obligatoire, Windows local facultatif, protection de branche a adapter. |
| `docs/sprint-10-rf01-rf02-validation.md` | Avertissement de contexte historique et lien vers le present contrat, sans effacer les anciens resultats. |
| `DOCNELO_CI_WINDOWS_REMOVAL_REPORT.md` | Present rapport. |

Aucun code metier, Compose, Dockerfile, script d'exploitation, migration,
parametre de production ou regle de protection GitHub n'est modifie.

## 5. Validations realisees

| Validation locale | Resultat |
|---|---|
| Actionlint 1.7.12 sur les deux workflows | Succes, aucune erreur de syntaxe/schema/actions/dependances. Analyse externe shellcheck et pyflakes non executee (`-shellcheck= -pyflakes=`). |
| Comparaison structurelle YAML avec la base Git | Succes : seules les trois differences attendues ; aucune reference `needs` orpheline ; aucun runner Windows ou matrice restant. |
| Execution de la commande de controle Python/fuseau extraite du nouveau workflow | Succes sous Linux Debian, CPython 3.13.18, `Europe/Paris` disponible. |
| Regression Linux des quatre fichiers de contrats | **251 reussis, 4 ignores, aucun echec ni erreur, 14,62 s**. |
| Verification des differences et espaces | `git diff --check` reussi. |

Fichiers executes : `test_deployment.py`, `test_release_security.py`,
`test_pinned_builds.py`, `test_public_beta_authorization.py`.
Execution dans l'image de laboratoire deja qualifiee
`docnelo-ci-fixture-proofs:20261106`, non-root, sans reseau, sources en
lecture seule, fichiers temporaires isoles. Le conteneur a termine et
a ete retire automatiquement. Aucun nouveau serveur PostgreSQL ou
conteneur de production n'a ete utilise.

Les quatre sauts preexistants correspondent aux deux preuves root
d'autorite/approbation et aux deux cas PostgreSQL
`test_real_postgresql_history_and_disabled_account_guard` et
`test_postgresql_close_serializes_with_last_inflight_admission`.
Les prerequis root/PostgreSQL n'etaient pas fournis a ce groupe local.
Leurs etapes CI dediees et la suite PostgreSQL restent conservees ; ces
sauts locaux ne constituent pas une qualification native de ces cas.
Un avertissement de deprecation Starlette/httpx reste visible.

Preuve JUnit conservee hors Git dans le dossier de session :
`files\ci-windows-removal-results\workflow-contracts.xml`.
Les suites metier completes et natives, deja qualifiees sur la base de
cette modification, ne sont pas annoncees comme rejouees dans cette mission.
Une nouvelle execution GitHub Actions reste necessaire apres publication
autorisee de la modification.

## 6. Actions GitHub manuelles et risques residuels

Lecture seule effectuee sur les protections GitHub :

- Seule branche protegee retournee : `main`.
- Protection classique de `main` : controles requis **`python`, `windows`,
  `frontend`**, application GitHub Actions `15368`, option `strict=true`.
- Aucun ruleset de depot retourne par l'API.

**Action manuelle indispensable :** apres revue et succes des controles
Linux du nouveau candidat, un administrateur doit ouvrir
**Settings > Branches > protection de `main` > required status checks**,
retirer uniquement **`windows`**, et conserver **`python`**, **`frontend`**,
leur association GitHub Actions et l'exigence de branche a jour.
Conserver toutes les autres protections et approbations.
Aucune modification API de ces regles n'a ete effectuee.

Tant que cette intervention n'est pas realisee, une pull request utilisant
le nouveau workflow peut rester bloquee en attente de `windows`.
Ne pas fabriquer un faux job Windows reussi ni contourner les protections.
Si les regles evoluent entre-temps, relire la protection et les rulesets
avant toute adaptation.

Apres autorisation distincte de publication, verifier sur le SHA exact :
jobs `python` et `frontend` verts, aucun job Windows, publication interdite
sur pull request ou branche autre que `main`.
La publication existante sur `main` reste distincte du deploiement :
`deploy.yml` demeure exclusivement manuel, protege par l'environnement
production et ses validations.

Les regressions specifiques Windows ne sont plus detectees automatiquement :
c'est une consequence volontaire, Windows n'etant pas une cible de
production. La CI reste sur un runner Ubuntu 24.04 avec ses preuves
Docker/Linux ; elle ne remplace pas la qualification du noyau, des droits
et de la configuration du VPS Debian reel.

**Aucun deploiement, acces VPS, secret, configuration de production,
inscription publique ou statut GO de production n'est autorise par
cette simplification.**
