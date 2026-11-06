# Docnelo beta 10 - Analyse des echecs CI

Date : 2026-11-06.

Branche : `release/docnelo-public-beta-10-20261106`.

Run analyse : [42258058708](https://github.com/AdelineMeistertzheim403/DocuMind_AI/actions/runs/42258058708).
Commit analyse : `d5eda52887fa4e5c0ada7f7fc55cbb43f409c5a8`.

**Production : NO-GO.** Aucun push, nouveau lancement GitHub Actions, merge,
publication d'image officielle, acces VPS, migration ou changement des
inscriptions n'a ete effectue. `REGISTRATION_MODE=disabled` et la porte SQL
restent inchanges et fermes dans le candidat ; aucune verification ni
modification de l'etat reel de production n'a ete entreprise.

## 1. Sources et diagnostic confirme

Les journaux complets du job Python puis du run termine ont ete recuperes,
avec leurs premieres exceptions et traces, et pas seulement leur bilan.

| Preuve conservee dans le dossier `files` de cette session | SHA-256 |
|---|---|
| `ci-42258058708-python.log` | `8d2dd81e7ba4aefab9c9b38b16d817ff8215a920528382173689d7385339314f` |
| `ci-42258058708-full.log` | `ede06276be60ec70e306954abf3652e56f160d4c226dca057291cb13b0b20ae6` |
| `ci-42258058708-materials\runner-materials-linux.json` | `71aefb75d1d73a1fbcf463f11bc430d14042072b921723f94d100afd6e72b21d` |

### Groupe A - Worker jamais demarre par les fixtures positives

Le lifespan de `backend\main.py:112-114` demarre le worker de resumes
uniquement si l'IA est deja activee au demarrage de l'application.
Cette protection, issue de `a3d2adb5`, est intentionnelle et conservee.

Les fixtures `ai` et `accounts` recevaient respectivement `client` et
`gateway_client` comme dependances. Ces clients avaient donc deja entre
le lifespan avec `ai_enabled=False` lorsque les fixtures passaient ensuite
ce reglage a `True`. La file acceptait les jobs, mais aucun thread ne les
consommait. Ce n'est pas une exception du fournisseur IA ou une difference
confirmee de dependance propre a GitHub Actions.

Traces du journal Python :

- Lignes 1107-1143 : le test de document long appelle `wait_job`, qui expire
  dans `tests\test_long_summary.py:25` avec
  `Summary worker did not reach an expected status`.
- Lignes 1364-1384 : l'evenement du fournisseur attendu par `entered.wait(10)`
  n'arrive jamais.
- Lignes 1430-1463 : le scenario BYOK attend `partial`, mais observe `pending`.

Correction : configurer les reglages et les mocks avant
`request.getfixturevalue('client')` ou
`request.getfixturevalue('gateway_client')`. Une assertion immediate verifie
que le thread attendu par ces scenarios positifs est vivant.
Le lifespan existant garde la responsabilite de son arret.

Les tests de desactivation en cours d'execution disposent ainsi d'un vrai
worker de test, puis coupent l'IA pour verifier les protections live.
Aucun demarrage automatique sur soumission de job n'a ete ajoute.

### Groupe B - Compte public verifie mais non approuve

Les huit erreurs `[public]` se produisent pendant la preparation de
`disabled_account`, au `login` partage dans `tests\test_byok.py`.
La premiere trace complete figure aux lignes 835-869 du journal Python :
reponse `401` au lieu du `200` attendu.

Cette fixture renseignait `registration_kind='public'` et
`email_verified_at`, mais laissait `approved_at` nul. Le refus etait donc
correct : `public_access_allowed` exige aussi l'approbation administrative
lorsque celle-ci est requise, comme dans cette configuration.

Correction : la fixture renseigne explicitement `approved_at` pour son
compte public fictif autorise, dans sa base de test isolee.
Les variantes `legacy` restent sans approbation publique.
Ni la connexion ni ses controles d'e-mail, d'approbation et de desactivation
ne sont modifies.

### Job Windows distinct

Le job distant Windows a ete annule apres environ 25 minutes, sans bilan
complet. Son journal contient un `KeyboardInterrupt` dans SQLAlchemy et
un `KeyError` du stash pytest pendant le teardown interrompu
(journal complet, lignes 530-565). Cette trace d'interruption ne demontre
pas une troisieme cause des 13 echecs et 8 erreurs du job Linux.
Le delai maximal du workflow reste inchange ; le nouveau job distant
Windows devra encore aboutir normalement.

## 2. Modifications selectionnees

| Fichier | Modification |
|---|---|
| `tests\test_ai.py` | Preparer l'activation IA fictive et le fournisseur mocke avant le lifespan ; verifier le worker. |
| `tests\test_byok.py` | Preparer les comptes, budgets, reglages et validateur fictifs avant le lifespan ; verifier le worker. |
| `tests\test_ai_disabled_enforcement.py` | Renseigner explicitement l'approbation du compte public fictif qui doit pouvoir se connecter. |
| `DOCNELO_BETA10_CI_FAILURE_ANALYSIS.md` | Present rapport de diagnostic et de qualification. |

Aucun code backend, migration, fichier Compose, configuration de production,
dependance ou workflow n'est modifie. Aucun nouveau `skip`, `xfail`,
allongement de delai ou retrait d'assertion n'est introduit.

## 3. Qualification avant/apres

| Execution | Resultat |
|---|---|
| CI distante initiale, job Python SQLite | 1 202 reussis, 13 echecs, 8 erreurs, 126 ignores ; 24 sous-tests reussis ; code 1. |
| Reproduction locale avant correction, document long et premiere variante publique en erreur | 1 echec et 1 erreur, memes causes, 34,75 s. |
| Quatre fichiers IA/BYOK apres correction, Windows | 55 reussis, aucun echec, 222,25 s. |
| Suite complete Linux SQLite apres correction | 1 223 reussis, 126 ignores, 24 sous-tests reussis ; aucun echec ni erreur ; 1 208,40 s. |
| Suite portable Windows complete apres correction, selection `-m 'not posix'` | 1 119 reussis, 82 ignores, 148 deselectionnes, 24 sous-tests reussis ; aucun echec ni erreur ; 835,52 s. |
| Regression beta et IA sur PostgreSQL/Linux | 167 reussis, aucun ignore, echec ou erreur ; `--require-no-skips` ; 192,58 s. |
| Effacement standard, integration et preuves root PostgreSQL/Linux | 73 reussis, aucun ignore, echec ou erreur ; `--require-no-skips` ; 149,28 s. |

Les compteurs des suites se recouvrent : ils ne constituent pas un total de
tests distincts. Les exclusions POSIX Windows et les sauts existants des
suites SQLite ne remplacent pas la qualification PostgreSQL/root sans saut.
La suite Linux recupere les 21 cas en echec/erreur, conserve exactement
les 126 sauts initiaux et ne masque donc aucun de ces cas.
Un avertissement de deprecation Starlette/httpx subsiste dans les deux
suites completes ; aucune dependance n'est modifiee pour le supprimer.

La suite PostgreSQL de 167 tests couvre `test_ai_disabled_enforcement.py`,
`test_byok.py`, `test_accounts_saas.py`, `test_public_beta.py`,
`test_public_beta_state.py`, `test_public_beta_approval.py`,
`test_public_beta_postgresql_concurrency.py`,
`test_public_beta_authorization.py` et `test_public_beta_email_abuse.py`.
Elle verifie notamment les autres modes d'inscription, l'approbation,
le refus avant verification/approbation, la fermeture, les dix admissions
cumulatives, les courses d'inscription et l'IA desactivee.

Les 73 preuves natives couvrent `test_standard_erasure.py`,
`test_erasure_deployment.py`, ainsi que
`test_real_root_registry_permissions_and_symlinks` et
`test_real_approval_and_installed_backup_guard_end_to_end` de
`test_release_security.py`. Elles conservent les scenarios de refus,
d'interruption/reprise et de verification physique independante.

### Environnements et reproductibilite

Linux : CPython **3.13.18**, comme l'artefact du run analyse.
Chaque version de paquet et les outils de build ont ete compares a
`runner-materials-linux.json` : parite verifiee, notamment pip 26.2.1,
setuptools 84.2.1, wheel 0.48.0, pytest 9.1.1, FastAPI 0.146.0,
Starlette 1.9.0, AnyIO 4.15.1 et SQLAlchemy 2.0.55.

Image de preuve locale : `docnelo-ci-fixture-proofs:20261106`,
identifiant `sha256:3fa1e6edeec428f942ea32820a9abcc273542df7a4bb4a03ef3530080417b585`.
Cette image est exclusivement un outil de laboratoire ; aucune image
de livraison n'a ete publiee. Les sources sont montees en lecture seule.
Le conteneur SQLite s'execute sans root et sans reseau.
Il s'agit de Debian slim, pas d'un clone integral du runner Ubuntu.

Windows local : CPython **3.13.7**, et non le patch Python Linux distant.
Ce resultat complementaire ne remplace donc pas une nouvelle CI Windows.

PostgreSQL : **17.11**, image construite depuis le `Dockerfile.db` de la
release, stockage ephemere en tmpfs, aucun port publie, identifiants fictifs.
Les clients de test rejoignent uniquement son espace reseau isole.
Les preuves root utilisent des bases `erasure_case_*` jetables.
Ce serveur a ete arrete et retire apres les tests, sans acces au VPS.

Les processus de test recoivent `AI_ENABLED=false`, une cle OpenAI vide
et `REGISTRATION_MODE=disabled`. Seules les fixtures positives activent
explicitement l'IA mockee de leur propre application de test.
Les vrais clients OpenAI restent interdits par les mocks existants.
Les rapports JUnit des suites completes et PostgreSQL sont conserves
dans `files\ci-fixes-windows-full.xml` et
`files\ci-fixes-linux-results` du dossier de session.

Commande ciblee, depuis le worktree release et avec l'interpreteur de test :

```powershell
python -m pytest -q tests\test_ai.py tests\test_long_summary.py tests\test_ai_disabled_enforcement.py tests\test_byok.py
```

La suite Linux complete utilise `python -m pytest -q` sans filtre de tests ;
seuls la sortie de diagnostic, le cache et les chemins temporaires/JUnit
sont adaptes. Les groupes PostgreSQL sont executes separement avec les
DSN exclusivement locaux et `--require-no-skips`.

## 4. Protections et risques residuels

L'IA reste desactivee par defaut et aucune configuration de production
n'est activee par une fixture. Les controles d'e-mail, d'approbation,
de compte desactive, de session, de quota serveur et d'effacement sont
inchanges. L'API ne recoit aucun privilege root.

Le job frontend du run analyse etait vert, y compris ses controles BFF
et sa compilation. Il s'agit du resultat distant initial, pas d'une
nouvelle execution locale du frontend : aucun fichier frontend n'a change.

Une nouvelle CI complete sur le commit corrige reste obligatoire,
notamment pour les etapes apres la suite SQLite initialement en echec,
les environnements heberges et l'achevement du job Windows.
La qualification locale ne vaut ni attestation de release, ni approbation
independante, ni validation de l'environnement reel de production.
Les preconditions operationnelles, SMTP/HTTPS, juridiques et de conservation
du rapport de preparation restent applicables. **Production NO-GO.**

## 5. Commit propose et nouvelle CI

Le commit propose est le nouveau commit de cette branche qui introduit
ensemble ce rapport et les trois corrections de fixtures. Son identifiant
exact se resout sans ambiguite apres creation :

```powershell
$branch = 'release/docnelo-public-beta-10-20261106'
$sha = git log -1 --format=%H --diff-filter=A -- DOCNELO_BETA10_CI_FAILURE_ANALYSIS.md
if ($LASTEXITCODE -ne 0 -or -not $sha) { throw 'Commit de qualification absent' }
if ((git branch --show-current) -ne $branch) { throw 'Mauvaise branche' }
if ((git rev-parse HEAD) -ne $sha) { throw 'HEAD different du commit qualifie' }
if (git status --porcelain) { throw 'Worktree non propre' }
git show --stat --oneline $sha
```

Les actions reseau suivantes sont **proposees seulement** et exigent une
autorisation explicite. Aucun `--force`, merge main ou publication d'image :

```powershell
git push origin $branch
if ($LASTEXITCODE -ne 0) { throw 'Publication de branche echouee' }
$remote = git ls-remote origin "refs/heads/$branch"
if ($LASTEXITCODE -ne 0 -or ($remote -split '\s+')[0] -ne $sha) {
    throw 'La branche distante ne pointe pas sur le commit qualifie'
}
gh workflow run ci.yml --repo AdelineMeistertzheim403/DocuMind_AI --ref $branch
```

Verifier ensuite le `headSha` du nouveau run : il doit etre strictement
egal a `$sha`. Un run d'un autre commit n'est pas une preuve de qualification
de ce candidat. L'execution CI sur cette branche de release ne remplace
aucune autorisation de deployer ni d'ouvrir les inscriptions.
