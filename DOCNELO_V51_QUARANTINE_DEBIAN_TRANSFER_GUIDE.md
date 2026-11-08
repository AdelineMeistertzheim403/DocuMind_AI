# Docnelo V5.1 — Transfert Quarantine vers Debian

## Statut et limites

Paquet autonome de **preparation**, pour Debian 13 x86_64 et **CPython
3.11.18**. La campagne cible doit produire **42 passed, 0 failed, 0 error,
0 skipped**, sans socket ni service externe. Le resultat Windows 3.13
n'est pas un resultat Debian. Aucun GO global n'est accorde.

La liaison au **veritable latch restaure** et la **qualification Docker**
restent deux etapes distinctes. Les workers reels, transactions, mails,
documents reels, permissions POSIX et annulation de traitements engages
ne sont pas qualifies par cette campagne synthetique.

Le backend, ses middlewares, les outils Backup/Restore, les releases
scellees et les preuves anterieures ne sont pas modifies. `venv-tests`
reste intact. PostgreSQL 17/55432 n'est jamais contacte : ne pas le demarrer,
le configurer ou fournir de DSN pour cette campagne.

## Contenu a transferer

Dossier de livraison Windows :
`deliveries\docnelo-v51-quarantine-debian-20261102`.
Copier **tous ses fichiers**, sans les renommer, dans le dossier Debian
`/home/adeline/docnelo-lab/development/v5.1-hardening/quarantine-debian-transfer-20261102`.
Ne pas y ajouter d'autres fichiers.

| Fichier | Role |
|---|---|
| `quarantine-sources.zip` | Sources applicatives sur liste explicite, test inchange, profil autonome, lanceur, inventaire et ce guide |
| `quarantine-wheels-cp311-linux-x86_64.zip` | Wheels uniquement, Linux x86_64/CPython 3.11 ou ABI stable/universelle ; aucune sdist |
| `requirements.lock` | Fermeture exacte des dependances, une version et un SHA-256 par wheel |
| `verify_transfer.py` | Verification stricte et extraction dans un dossier inexistant |
| `SHA256SUMS` | SHA-256 de chaque fichier de livraison, sauf lui-meme |
| `DOCNELO_V51_QUARANTINE_DEBIAN_TRANSFER_GUIDE.md` | Ce guide |

Chaque ZIP contient egalement son propre `SHA256SUMS`, exhaustif sauf
auto-reference. `PACKAGE.json`, dans les sources, contient les empreintes
des fichiers d'origine, versions, tags ABI et empreintes des wheels.
L'inventaire couvre les octets transferes, pas seulement leurs noms.
L'archive sources contient 63 fichiers inventories et son `SHA256SUMS` ;
l'archive wheels contient 42 wheels inventories et son `SHA256SUMS`.
Conserver l'empreinte du `SHA256SUMS` externe par un canal de confiance :
les sommes detectent une alteration, mais ne sont pas une signature.

Le perimetre applicatif provient des imports observes pendant les 42 cas.
Il comprend les modules `backend` effectivement charges et les modules
`analyseur_documents.core` requis par `backend.schemas`. Le fichier
`backend.main` est conserve bien que le harness le retire de `sys.modules`.
Les imports differes des endpoints non executes ne sont pas embarques :
ce paquet n'est **pas une distribution executable du service**.
Ni `conftest.py`, ni `pyproject.toml`, ni `alembic.ini`, ni migrations,
ni outils, frontend, Dockerfile, `.env`, credentials, bases, documents,
caches, fichiers temporaires ou artefacts de production ne sont inclus.

Alembic, Psycopg et OpenAI sont presents **uniquement comme bibliotheques
d'import requises par le harness**. Aucune commande Alembic ou migration
n'est executee. Les fonctions correspondantes sont interdites par les
sentinelles du test. PyMuPDF, Uvicorn et les extras serveur sont absents.
`python-dotenv` est une dependance de Pydantic Settings, pas une autorisation
de lire un `.env` : les sources des Settings restent synthetiques.

## 1. Verifier et extraire dans un espace neuf

Commandes **Bash Debian**, depuis une session dediee, sans activation de
`venv-tests`. Ne pas executer avec sudo. Aucun telechargement n'est effectue.
Les chemins Linux ci-dessous sont intentionnels.

```bash
set -euo pipefail
umask 077
PY=/opt/docnelo-lab/python311/bin/python3.11
BASE=/home/adeline/docnelo-lab/development/v5.1-hardening
TRANSFER="$BASE/quarantine-debian-transfer-20261102"
test -x "$PY"
test -d "$BASE"
test "$("$PY" -I -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')" = 3.11.18
test "$("$PY" -I -c 'import platform; print(platform.machine())')" = x86_64
test "$("$PY" -I -c 'import sys; print(sys.implementation.name)')" = cpython
test "$(uname -s)" = Linux
test "$( . /etc/os-release; printf '%s:%s' "$ID" "$VERSION_ID" )" = debian:13
cd "$TRANSFER"
sha256sum SHA256SUMS
# Comparer cette empreinte a celle conservee sur le poste de preparation.
sha256sum --strict -c SHA256SUMS

RUNS="$BASE/quarantine-debian-runs"
PROOFS="$BASE/quarantine-debian-evidence"
mkdir -p -- "$RUNS" "$PROOFS"
RUN=$(mktemp -d "$RUNS/run-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXXXX")
PROOF=$(mktemp -d "$PROOFS/run-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXXXX")
export RUN PROOF
printf 'RUN=%s\nPROOF=%s\n' "$RUN" "$PROOF" | tee "$PROOF/paths.txt"
"$PY" -I -B "$TRANSFER/verify_transfer.py" \
  --transfer "$TRANSFER" --destination "$RUN/payload" \
  2>&1 | tee "$PROOF/transfer-verification.log"
SOURCE="$RUN/payload/source"
WHEELS="$RUN/payload/wheels"
cd "$SOURCE"
sha256sum --strict -c SHA256SUMS > "$PROOF/source-verification.log"
cd "$WHEELS"
sha256sum --strict -c SHA256SUMS > "$PROOF/wheel-verification.log"
cp -- "$TRANSFER/SHA256SUMS" "$PROOF/transfer-SHA256SUMS"
cp -- "$SOURCE/SHA256SUMS" "$PROOF/source-SHA256SUMS"
cp -- "$WHEELS/SHA256SUMS" "$PROOF/wheels-SHA256SUMS"
cp -- "$SOURCE/PACKAGE.json" "$TRANSFER/requirements.lock" \
  "$TRANSFER/DOCNELO_V51_QUARANTINE_DEBIAN_TRANSFER_GUIDE.md" "$PROOF/"
```

Le verificateur refuse fichiers absents, supplementaires, empreintes
incorrectes, membres ZIP dupliques, symlinks et chemins traversants.
Il refuse une destination existante et tout chemin `release`, `releases`,
`fixtures` ou `artifacts`. Aucun fichier n'est extrait dans les espaces
scelles ou `artifacts/qualification`. En cas d'erreur, **arreter** :
ne pas contourner l'inventaire ou reutiliser la destination partielle.

## 2. Creer un venv distinct et installer strictement hors ligne

Pip est fourni dans les wheels pour ne dependre ni d'Internet, ni du pip
systeme, ni d'ensurepip. Pas d'installation du projet avec `pip install .` :
cela chargerait le profil et les dependances globales.

```bash
cd "$RUN"
mkdir -- "$RUN/home"
"$PY" -I -B -m venv --without-pip "$RUN/venv-quarantine"
VENV="$RUN/venv-quarantine"
PIP_WHEEL="$WHEELS/pip-25.2-py3-none-any.whl"
test -f "$PIP_WHEEL"
env -i HOME="$RUN/home" PATH=/usr/bin:/bin LANG=C.UTF-8 \
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PIP_WHEEL" \
  "$VENV/bin/python" -B -m pip --isolated install \
  --no-index --no-cache-dir --disable-pip-version-check \
  --only-binary=:all: --find-links "$WHEELS" --require-hashes \
  -r "$SOURCE/qualification/quarantine_debian/requirements.lock" \
  2>&1 | tee "$PROOF/install.log"
env -i HOME="$RUN/home" PATH=/usr/bin:/bin LANG=C.UTF-8 \
  "$VENV/bin/python" -I -B -m pip --isolated check \
  2>&1 | tee "$PROOF/pip-check.log"
```

Ne pas ajouter `--extra-index-url`, retirer `--require-hashes`, installer
une sdist ou remplacer une version. Les wheels binaires Psycopg evitent
une dependance sur une installation locale de libpq. Un wheel incompatible,
une dependance manquante ou une contrainte non satisfaite est bloquante.
Le lanceur compare ensuite **toutes** les distributions installees au
lock : meme un paquet supplementaire non utilise provoque un refus.

## 3. Executer la campagne et conserver les preuves

Le lanceur appelle `pytest.main` avec la commande equivalente suivante :

```text
python -m pytest -c qualification/quarantine_inprocess/pytest.ini \
  --noconftest -p no:cacheprovider -x -q --tb=short \
  -o junit_family=legacy --basetemp <TEMPORAIRE_NEUF> \
  --junitxml <PREUVES_NEUVES>/campaign/junit.xml \
  tests/test_recovery_quarantine_inprocess.py
```

**Utiliser le lanceur ci-dessous**, pas la commande nue : il ajoute
l'inventaire, la compilation Python 3.11, le controle des dependances,
le refus des skips/xfail et la verification JUnit. Il ne modifie aucun
test ni middleware. Le profil garde `--noconftest`, aucun plugin tiers
n'est charge automatiquement et aucun conftest du depot n'est importe.

```bash
cd "$RUN"
set +e
env -i HOME="$RUN/home" PATH=/usr/bin:/bin LANG=C.UTF-8 \
  PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1 \
  "$VENV/bin/python" -I -B \
  "$SOURCE/qualification/quarantine_debian/run_campaign.py" \
  --evidence "$PROOF/campaign" --basetemp "$RUN/pytest-tmp" \
  2>&1 | tee "$PROOF/pytest.log"
CAMPAIGN_STATUS=${PIPESTATUS[0]}
set -e
export CAMPAIGN_STATUS
"$PY" -I -B - <<'PY'
import hashlib, os
from pathlib import Path
proof = Path(os.environ["PROOF"]).resolve(strict=True)
(proof / "exit-code.txt").write_text(os.environ["CAMPAIGN_STATUS"] + "\n")
files = sorted(p for p in proof.rglob("*") if p.is_file() and p.name != "SHA256SUMS")
with (proof / "SHA256SUMS").open("w", encoding="ascii", newline="\n") as out:
    for path in files:
        with path.open("rb") as stream:
            sha = hashlib.file_digest(stream, "sha256").hexdigest()
        out.write(f"{sha}  {path.relative_to(proof).as_posix()}\n")
PY
cd "$PROOF"
sha256sum --strict -c SHA256SUMS
test "$CAMPAIGN_STATUS" -eq 0
test -f "$PROOF/campaign/junit.xml"
```

Si l'execution echoue, ses logs et eventuelles preuves partielles restent
conserves. Une erreur de preflight peut preceder la creation du JUnit :
elle ne constitue jamais une campagne reussie. Ne pas relancer avec le
meme `PROOF`, `campaign` ou `pytest-tmp` : reprendre a l'etape 1 avec de
nouveaux dossiers.

Conditions cumulatives de reussite fonctionnelle :

- processus a code 0 ; exactement 42 cas collectes depuis le seul fichier
  autorise, puis 42 cas passes ; aucun skip, xfail ou xpass ;
- JUnit avec exactement 42 `testcase`, zero failure/error/skipped ;
- `environment.json` indique `target_python_3_11_18: true`,
  `preparation_only: false`, `verdict: "42_PASS_NO_SKIP"` et
  `forbidden_io_events: []` ;
- inventaires sources et wheels conformes, dependances strictement egales
  au lock, et aucune modification des sources pendant la campagne.

Le harness original interdit sockets, connexions PostgreSQL/SQLite,
SMTP, clients IA, commandes de migration, sous-processus et vrais threads.
Ses violations restent bloquantes meme si une exception est interceptee.
Le lanceur ajoute un audit Python permanent **avant la collecte et les
imports de l'application** : tout evenement `socket.*`, connexion SQLite,
creation de sous-processus ou fork est refuse et comptabilise. Aucun
serveur HTTP, DNS, socket localhost ou service externe n'est requis.
La boucle ASGI conserve son selecteur sans descripteur et sans self-pipe.
L'audit Python n'est pas une trace systeme de tous les appels natifs ;
la garantie ici porte sur ce harness, ses sentinelles et les chemins
executes, pas sur tout code arbitraire ou tout autre mode de demarrage.

## 4. Nettoyage borne, sans toucher aux preuves

Facultatif, uniquement apres conservation et verification de `PROOF`.
Supprime **le seul RUN de cette execution**, y compris son venv et ses
temporaires. Ni `PROOF`, ni le transfert, ni `venv-tests`, ni les releases
ou preuves des campagnes precedentes ne sont supprimes.
Ne jamais appliquer une suppression recursive a `BASE`, `RUNS` ou `PROOFS`.

```bash
cd "$BASE"
"$PY" -I -B - <<'PY'
import os, re, shutil
from pathlib import Path
base = Path("/home/adeline/docnelo-lab/development/v5.1-hardening").resolve(strict=True)
raw = Path(os.environ["RUN"])
proof = Path(os.environ["PROOF"]).resolve(strict=True)
run = raw.resolve(strict=True)
assert not raw.is_symlink() and run.parent == base / "quarantine-debian-runs"
assert re.fullmatch(r"run-\d{8}T\d{6}Z-[A-Za-z0-9]{8}", run.name)
assert proof.parent == base / "quarantine-debian-evidence"
assert proof != run and not proof.is_relative_to(run)
assert (proof / "SHA256SUMS").is_file()
assert (proof / "exit-code.txt").is_file()
print("Suppression du seul espace temporaire :", run)
shutil.rmtree(run)
print("Preuves conservees :", proof)
PY
```

## Construction et verification sur le poste de preparation

La construction prend une liste explicite de fichiers, jamais une copie
recursive du depot. Les sources sont copiees octet pour octet ; leurs
empreintes avant/apres doivent coincider. Le fichier `requirements.pins`
est distinct des locks runtime existants, qui ciblent CPython 3.13.
Les versions de la campagne Windows sont conservees ; les empreintes
des extensions natives sont celles des wheels **Linux 3.11**, pas Windows
ni CPython 3.13. Les contraintes `Requires-Python` sont controlees.

Commande PowerShell de reconstruction sur un poste connecte, avec une
destination **nouvelle** ; Debian n'execute jamais cette commande :

```powershell
python -B qualification\quarantine_debian\build_transfer.py `
  --output deliveries\docnelo-v51-quarantine-debian-NOUVEAU
```

Le constructeur telecharge exclusivement des wheels publics depuis
l'index pip, avec `--only-binary=:all:`, `--no-deps`, cible CPython 3.11
et plateformes manylinux x86_64. Tous les transitifs sont explicitement
epingles ; `pip check` et le preflight Linux controlent leur fermeture.
Le builder peut aussi reutiliser un wheelhouse deja verifie avec
`--wheelhouse <DOSSIER_WHEELS_AVEC_SHA256SUMS>`, sans reseau.

Les scripts de preparation sont dans `qualification\quarantine_debian`.
Le ZIP ne contient que les scripts necessaires a l'execution/verifications,
pas le constructeur. Aucune connexion a la VM Hyper-V cible n'est realisee
par cette preparation. **Ne pas convertir un controle local WSL ou une
analyse de syntaxe en resultat Debian 13/Python 3.11.18.**

Controles de preparation effectues le 2 novembre 2026 :

| Controle | Resultat et limite |
|---|---|
| Sources applicatives et test originaux | Copie a l'identique, SHA-256 avant/apres identiques |
| Syntaxe Python 3.11 | AST cible 3.11 et compilation native des fichiers Python transferes |
| Installation Linux hors ligne | 42 wheels, `--no-index --require-hashes`, venv neuf sans pip initial ; `pip check` conforme |
| Campagne locale WSL Debian 12 / CPython 3.11.2 | 42 passed, 0 failed/error/skipped, aucun evenement I/O interdit observe |
| Controles des outils de transfert | 11 cas : derives d'inventaire, chemins ZIP et JUnit incomplet/non reussi refuses |
| VM Hyper-V Debian 13 / CPython 3.11.18 | **Non executee ici** ; suivre les etapes ci-dessus |

Le seul controle WSL utilise l'option explicite
`--allow-patch-mismatch` : son verdict est
`PREPARATION_ONLY_42_PASS_NO_SKIP`, jamais un resultat de qualification cible.
**Ne pas utiliser cette option dans la VM Debian.** Sans elle, le lanceur
refuse toute version differente de 3.11.18 avant les tests.
Les logs/JUnit locaux restent des preuves de preparation separees ; ils ne
sont pas embarques comme preuves d'une campagne Debian cible.
