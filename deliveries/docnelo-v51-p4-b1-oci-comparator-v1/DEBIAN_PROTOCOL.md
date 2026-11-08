# Verification Debian hors ligne - arrets obligatoires

Utiliser Bash sur la VM Debian 13, sans reseau et sans Docker. Ne jamais
executer le Python ou les binaires du rootfs P3. Python 3.11 doit etre **deja**
approuve et installe ; Debian 13 peut proposer une autre version par defaut.
Si absent, ARRET sans apt/pip/installation dans ce protocole.

Chaque bloc est a executer dans le meme shell, dans l'ordre. Toute erreur
impose l'arret avant le bloc suivant. Les chemins ci-dessous sont des
parametres operatrice ; le chemin d'archive existante n'est pas connu ici.

## 1. Preparer sans toucher aux entrees historiques

```bash
set -eu
umask 077
export LC_ALL=C
PY="/chemin/approuve/python3.11"
DELIVERY="/chemin/nouveau/docnelo-v51-p4-b1-oci-comparator-v1"
P3_FIXED="/home/adeline/docnelo-lab/development/v5.1-hardening/docnelo-p3-python311-fixed-37d04ec892f7464a809d2fdfe69d57b3"
ARCHIVE="/chemin/existant/archive-docker-save-P3.tar"
BASE="/chemin/nouveau-parent-preuves-p4-oci"
ANCHOR="REMPLACER_PAR_ANCRE_SHA256SUMS_RECUE_INDEPENDAMMENT"
test -x "$PY" || exit 1
"$PY" -I -B -c 'import sys; assert sys.version_info[:2] == (3,11)' || exit 1
test -d "$DELIVERY" || exit 1
test -f "$ARCHIVE" || exit 1
test -f "$P3_FIXED/ROOTFS-SHA256SUMS" || exit 1
test -f "$P3_FIXED/ROOTFS-METADATA.txt" || exit 1
test ! -e "$BASE" && test ! -L "$BASE" || exit 1
mkdir -m 700 -- "$BASE" || exit 1
```

**ARRET** si un chemin est douteux, inaccessible ou deja utilise. Ne pas
changer ses permissions, ne pas chercher dans un dossier historique refuse,
ne pas pretendre une recherche exhaustive. Ne jamais ecrire dans P3/B1.

## 2. Verifier le code avant execution

SHA256SUMS est ancre hors livraison. Ne pas croire une ancre simplement
contenue dans le meme dossier non verifie. Utiliser sha256sum Debian deja
approuve ; enregistrer le controle dans le nouveau parent de preuves.

```bash
printf '%s  %s\n' "$ANCHOR" "$DELIVERY/SHA256SUMS" \
  | sha256sum --check --strict - > "$BASE/bootstrap.stdout" \
      2> "$BASE/bootstrap.stderr" || exit 1
(
  cd "$DELIVERY" || exit 1
  sha256sum --check --strict SHA256SUMS
) > "$BASE/payload.stdout" 2> "$BASE/payload.stderr" || exit 1
```

**ARRET** si le manifeste ou un fichier differe. Ne pas corriger/re-sceller
sur la VM. L'outil verifiera aussi la couverture exacte des fichiers livres
(un fichier supplementaire, un symlink ou des fichiers absents est refuse).
Ne pas creer de bytecode, logs ou preuves dans DELIVERY.

## 3. Tests controles et traces

```bash
"$PY" -I -B "$DELIVERY/record_tests.py" \
  --release-anchor "$ANCHOR" --timeout 120 --out "$BASE/unit-tests" || exit 1
(
  cd "$BASE/unit-tests" || exit 1
  sha256sum --check --strict SHA256SUMS
) || exit 1
```

**ARRET** si le code retour n'est pas 0, si un test est ignore, ou si le
recepisse est absent/incomplet. Les tests ne lisent aucune preuve historique.
Ils remplacent les ancres uniquement dans des fichiers de fixtures
temporaires neufs ; le comparateur livre n'est jamais modifie.

## 4. Comparaison des octets historiques

Les cinq ancres sont constantes dans comparator.py. Les chemins `./` des
inventaires ne sont modifies qu'en memoire. Les fichiers ne sont ni recopies
ni regeneres. Pas de nouvel export Docker.

```bash
set +e
"$PY" -I -B "$DELIVERY/comparator.py" \
  --release-anchor "$ANCHOR" --archive "$ARCHIVE" \
  --sums "$P3_FIXED/ROOTFS-SHA256SUMS" \
  --metadata "$P3_FIXED/ROOTFS-METADATA.txt" \
  --out "$BASE/comparison"
RC=$?
set -e
printf '%s\n' "$RC" > "$BASE/comparator-shell-returncode"
case "$RC" in
  0|10) ;;
  *) printf 'ARRET: comparaison refusee ou incomplete, code %s\n' "$RC"; exit 1 ;;
esac
```

Le comparateur enregistre argv, parametres, interpreteur, cwd, code mesure,
stdout/stderr exacts, hashes d'entrees observes et attendus, hash du code,
rapport, recepisse et manifeste de preuves. `started.json` conserve la
tentative si elle est interrompue. En cas d'erreur, conserver ce dossier ;
ne jamais reutiliser `--out`.

## 5. Integrite du recepisse et revue du resultat

```bash
(
  cd "$BASE/comparison" || exit 1
  sha256sum --check --strict SHA256SUMS
) || exit 1
"$PY" -I -B -c '
import hashlib,json,pathlib,sys
p=pathlib.Path(sys.argv[1]); shell=int(sys.argv[2])
r=json.loads((p/"receipt.json").read_bytes())
q=json.loads((p/"report.json").read_bytes())
assert r["complete"] is True and r["returncode"] == q["returncode"] == shell
assert q["decision"] == "REVIEW_ONLY_BLOCKED"
assert q["formal_b1_contents_closed"] is False and not any(q["go"].values())
assert q["complete_metadata_equality_established"] is False
for n,h in r["sha256"].items():
    assert hashlib.sha256((p/n).read_bytes()).hexdigest() == h
a=json.loads((p/"evidence-anchor.json").read_bytes())
assert hashlib.sha256((p/"SHA256SUMS").read_bytes()).hexdigest() == a["sha256sums"]
print(json.dumps({k:q[k] for k in ("status","returncode","counts","difference_counts",
                                 "root_directory","regular_contents_equal")},indent=2))
' "$BASE/comparison" "$RC" || exit 1
```

**ARRET de qualification automatique dans tous les cas** : meme code 0,
pas de GO et pas de cloture. Au code 10, examiner toutes les listes de
differences, pas seulement le contenu. Le profil historique indique une
racine absente et 10 334 divergences UID/GID ; ne pas imposer ces valeurs
au nouvel outil. Tout ecart doit rester visible et etre analyse en C2-C4.

Archiver physiquement le nouveau BASE et remettre separement l'empreinte de
`comparison/SHA256SUMS` et celle de `unit-tests/SHA256SUMS`. Leurs fichiers
evidence-anchor.json sont des supports de transmission, pas des signatures.
C5 exige une autorisation distincte ; ne jamais modifier les flags GO.
