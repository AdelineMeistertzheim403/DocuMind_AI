# Docnelo V5.1 - Qualification FastAPI avec latch restaure

## Perimetre et statut

Campagne **in-process uniquement**, sans serveur. Le resultat Windows avec
latch synthetique n'est pas une qualification du fichier restaure Debian.
Seule une execution cible conforme peut produire le verdict
`LIMITED_GO_RESTORED_LATCH_FASTAPI_INPROCESS_ONLY`.

**Aucun GO Docker, chaine Backup/Restore globale, S2, Lifecycle 10, Public Beta
ou production.** Ne pas demarrer de service, contacter un VPS, executer une
migration ou charger un `.env`. Ne pas utiliser sudo.

Le latch cible doit deja exister, en etat `quarantined`, mode 0600 :

```text
/home/adeline/docnelo-lab/artifacts/qualification/capture-v51/roundtrip-restore/files/recovery-state.json
SHA-256 : 0a01b17bf9de4fe0d4eccdbae2da89f3345c261622bb8f11a2777c2f53229565
```

Il est lu seulement. Aucun fichier, temporaire, inventaire ou rapport ne doit
etre cree dans son dossier. Une empreinte incorrecte est bloquante : ne pas
reparer, remplacer, chmod, recopier ou faire passer ce fichier a `ready`.

## Nouveau transfert, ancien paquet intact

Copier **tous** les fichiers de
`deliveries\docnelo-v51-restored-latch-fastapi-20261102`
vers un **nouveau** repertoire Debian :

```text
/home/adeline/docnelo-lab/development/v5.1-hardening/restored-latch-transfer-20261102
```

Ce paquet contient exclusivement :

| Fichier | Contenu |
|---|---|
| `quarantine-sources.zip` | Sources applicatives sur liste explicite, harness original, nouveau test, profils, lanceurs/verificateur, lock, inventaire et guide |
| `quarantine-wheels-cp311-linux-x86_64.zip` | Les 42 wheels Linux deja inventories, reutilises sans modification |
| `requirements.lock` | Versions exactes et SHA-256 des wheels, pip compris |
| `verify_transfer.py` | Verificateur/extracteur standard-library, identique au precedent |
| `SHA256SUMS` | Inventaire exhaustif du transfert, sans auto-reference |
| Ce guide | Procedure hors ligne |

Chaque ZIP possede son propre `SHA256SUMS`. `PACKAGE.json` inventorie les
sources et wheels ainsi que les ajouts par rapport au precedent paquet.
L'ancien paquet n'est pas suffisant pour cette mission : il ne contient ni
`tests/test_recovery_quarantine_restored_latch.py`, ni le profil et lanceur
`qualification/restored_latch`, ni ce guide. Les imports applicatifs observes
restent couverts par ses sources ; aucun module applicatif n'est modifie.
Le nouveau paquet n'est **pas** une distribution complete du service :
les imports differes des routes metier non executees ne sont pas fournis.

Exclusions : `.env`, secrets, bases, documents, latch, anciennes preuves,
fixtures, conftest, frontend, Docker, releases, migrations, Uvicorn,
PyMuPDF et outils Backup/Restore. Alembic, Psycopg et OpenAI ne servent
qu'aux imports ; les operations externes sont interdites.

Comparer l'empreinte du `SHA256SUMS` externe avec celle conservee sur le
poste Windows par un canal de confiance. Ces sommes ne sont pas une signature.

## 1. Verifier, extraire, reserver de nouveaux chemins

Les commandes ci-dessous sont du **Bash Debian**, et non du PowerShell.
Utiliser une session dediee. `RUN` et `PROOF` sont nouveaux a chaque tentative ;
ne jamais reutiliser une destination partielle ou ecraser une ancienne preuve.

```bash
set -euo pipefail
umask 077
PY=/opt/docnelo-lab/python311/bin/python3.11
BASE=/home/adeline/docnelo-lab/development/v5.1-hardening
TRANSFER="$BASE/restored-latch-transfer-20261102"
LATCH=/home/adeline/docnelo-lab/artifacts/qualification/capture-v51/roundtrip-restore/files/recovery-state.json
EXPECTED=0a01b17bf9de4fe0d4eccdbae2da89f3345c261622bb8f11a2777c2f53229565
test "$( . /etc/os-release; printf '%s:%s' "$ID" "$VERSION_ID" )" = debian:13
test "$(uname -s):$(uname -m)" = Linux:x86_64
test "$("$PY" -I -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')" = 3.11.18
test -d "$BASE"
cd "$TRANSFER"
sha256sum SHA256SUMS
# Comparer cette empreinte a celle du rapport Windows avant de continuer.
sha256sum --strict -c SHA256SUMS

mkdir -p -- "$BASE/restored-latch-runs" "$BASE/quarantine-debian-evidence"
RUN=$(mktemp -d "$BASE/restored-latch-runs/run-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXXXX")
PROOF=$(mktemp -d "$BASE/quarantine-debian-evidence/restored-fastapi-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXXXX")
export RUN PROOF
printf 'RUN=%s\nPROOF=%s\n' "$RUN" "$PROOF" | tee "$PROOF/paths.txt"
test -f "$LATCH"
test ! -L "$LATCH"
test "$(stat -c '%a' "$LATCH")" = 600
printf '%s  %s\n' "$EXPECTED" "$LATCH" | sha256sum --strict -c - \
  | tee "$PROOF/latch-before-check.log"
sha256sum "$LATCH" > "$PROOF/latch-before.sha256"
stat -c 'mode=%a size=%s inode=%i mtime=%y' "$LATCH" > "$PROOF/latch-before.stat"

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
  "$TRANSFER/DOCNELO_V51_RESTORED_LATCH_DEBIAN_GUIDE.md" "$PROOF/"
```

## 2. Installer uniquement les wheels verifies, hors ligne

Venv distinct de `venv-tests` ; aucun `pip install .`, aucun index ni sdist.
Le pip embarque evite un telechargement ou une installation systeme.

```bash
mkdir -- "$RUN/home"
"$PY" -I -B -m venv --without-pip "$RUN/venv-restored"
VENV="$RUN/venv-restored"
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

Le lanceur verifie ensuite la fermeture exacte des distributions installees
contre le lock, leur emplacement dans le venv et leurs contraintes Python.
Un paquet supplementaire, manquant ou incompatible est bloquant.

## 3. Executer la qualification du latch reel

Ne pas utiliser `--preparation` ici : cette option fabrique exclusivement
un latch synthetique dans le scratch et ne peut pas accepter de latch externe.
Le lancement cible exige le chemin absolu ET le SHA-256 ci-dessus.

```bash
cd "$RUN"
set +e
env -i HOME="$RUN/home" PATH=/usr/bin:/bin LANG=C.UTF-8 \
  PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1 \
  "$VENV/bin/python" -I -B \
  "$SOURCE/qualification/restored_latch/run_campaign.py" \
  --latch-path "$LATCH" --expected-sha256 "$EXPECTED" \
  --evidence "$PROOF/campaign" --scratch "$RUN/campaign-scratch" \
  2>&1 | tee "$PROOF/pytest.log"
CAMPAIGN_STATUS=${PIPESTATUS[0]}
set -e
export CAMPAIGN_STATUS
printf '%s\n' "$CAMPAIGN_STATUS" > "$PROOF/exit-code.txt"
sha256sum "$LATCH" > "$PROOF/latch-after.sha256"
stat -c 'mode=%a size=%s inode=%i mtime=%y' "$LATCH" > "$PROOF/latch-after.stat"
cmp -- "$PROOF/latch-before.sha256" "$PROOF/latch-after.sha256"
cmp -- "$PROOF/latch-before.stat" "$PROOF/latch-after.stat"

"$PY" -I -B - <<'PY'
import hashlib, os
from pathlib import Path
proof = Path(os.environ["PROOF"]).resolve(strict=True)
files = sorted(p for p in proof.rglob("*") if p.is_file() and p != proof / "SHA256SUMS")
with (proof / "SHA256SUMS").open("x", encoding="ascii", newline="\n") as out:
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

Le sous-repertoire `campaign` est reserve par le lanceur avec `mkdir` sans
`exist_ok`. Le scratch, distinct et neuf, est le seul espace temporaire.
Un audit Python permanent est installe avant pytest et les imports
applicatifs : sockets/DNS, sous-processus, fork, SQLite, SMTP, HTTP externe,
lecture dotenv et ecritures hors preuves/scratch provoquent une erreur.
Toute tentative reste comptabilisee, meme si le code intercepte l'exception.
Les symlinks et chemins de sortie proteges sont refuses. Le harness
interdit aussi vrais threads, moteurs/connexions SQL, clients IA, migrations,
sessions, mails et ouverture de documents.

Les fichiers suivants sont conserves par le lanceur, meme apres un echec
intervenu apres creation des preuves : `environment.json`, inventaire de
sources, JUnit si pytest a termine, `scenarios.json` si disponible,
`pytest-internal.log`, `failure.txt` en cas d'erreur et `SHA256SUMS`.
Les echecs de preflight peuvent preceder ces fichiers : le log externe
`pytest.log` et le code retour restent la preuve du refus, jamais un succes.

## 4. Lire les preuves et decider

Exiger simultanement :

- code retour 0, **9 passed**, aucun skip, xfail ou xpass ;
- JUnit avec neuf cas reussis ; `environment.json` indique
  `preparation_only: false`, `target_runtime: true`, le verdict limite,
  `forbidden_io_events: []`, les deux snapshots identiques au SHA attendu ;
- huit scenarios : standard/Lite, avec/sans en-tetes synthetiques,
  latch restaure/chemin absent ; chaque scenario inventorie **toutes**
  les methodes HTTP enregistrees, plus deux sondes hors routage ;
- `latch_reads` montre une lecture au demarrage du chemin configure, puis
  une lecture par 503 ; les 403 Lite n'atteignent pas la quarantaine ;
- zero appel downstream et zero activite de demarrage metier dans les
  huit scenarios ; ni repertoire documents ni mail en file ;
- inventaires du transfert, des sources, wheels et preuves conformes.

`scenarios.json` et les proprietes JUnit contiennent l'inventaire des
routes/methodes/modules, les reponses, chemins lus et compteurs.
La surface d'administration est recherchee parmi les **vraies routes
enregistrees**. Dans les sources preparees Windows, elle est vide :
`backend.account_admin` est un outil CLI non enregistre ici. Aucun faux
`/admin` ne prouve une couverture HTTP inexistante. La route interne
`/api/v1/internal/upload-admission`, elle, est couverte.

Le neuvieme cas est un controle positif : uniquement le latch temporaire
du harness devient `ready`. Les compteurs de workers/mails/cleanup
synthetiques s'activent et la sentinelle devant le vrai routeur est atteinte
(HTTP 500 converti par SecurityAudit). Le latch restaure ne change jamais.

L'application cible est une instance de `backend.main.create_app` avec ses
six middlewares reels, leur ordre conserve, son vrai routeur et toutes
ses routes. Seule une sentinelle est **ajoutee devant** le routeur ; aucune
route factice ne le remplace. L'application globale de `backend.main`
est creee sous l'isolation du harness original, avec son latch temporaire,
avant construction de l'instance cible explicitement configuree.
Son lifespan n'est pas demarre.

La branche `sandbox` est configuree et ne doit pas effectuer son check
externe en quarantaine ; le profil standard active l'IA pour que les
conditions workers/jobs soient significatives. Le profil Lite impose
l'IA desactivee par sa vraie validation. Les traitements reels, la
disponibilite du sandbox, les transactions et les mails ne sont pas qualifies.

Un echec, une empreinte differente, un skip ou une E/S interdite interdit
le GO limite. Conserver les preuves, ne pas modifier le middleware ni
les sources pour contourner un resultat Debian defavorable.
