# Protocole Debian - mesure A avec refus general 20 maintenu

Bash, hors ligne, Python 3.11 **deja** approuve et installe. Ne jamais utiliser
l'interpreteur/binaire du rootfs P3. Aucune commande Docker, aucun export,
reseau, apt/pip ou extraction. Toute erreur impose l'arret avant l'etape
suivante. Ne pas executer comparator.py pour cette mesure limitee.

## 1. Chemins independants et interpreteur

```bash
set -euC
umask 077
export LC_ALL=C
PY="/chemin/approuve/python3.11"
DELIVERY="/chemin/nouveau/docnelo-v51-p4-b1-p3-layer-contents-v1"
P3_FIXED="/home/adeline/docnelo-lab/development/v5.1-hardening/docnelo-p3-python311-fixed-37d04ec892f7464a809d2fdfe69d57b3"
ARCHIVE="/chemin/existant/p3-image-export.tar"
BASE="/chemin/nouveau-parent-preuves-p3-layer-contents"
ANCHOR="REMPLACER_PAR_ANCRE_SHA256SUMS_RECUE_INDEPENDAMMENT"
test -x "$PY" || exit 1
"$PY" -I -B -c 'import sys; assert sys.version_info[:2] == (3,11)' || exit 1
test -f "$ARCHIVE" || exit 1
test -f "$P3_FIXED/ROOTFS-SHA256SUMS" || exit 1
test -f "$P3_FIXED/ROOTFS-METADATA.txt" || exit 1
test -d "$DELIVERY" || exit 1
test ! -e "$BASE" && test ! -L "$BASE" || exit 1
mkdir -m 700 -- "$BASE" || exit 1
```

ARRET si chemin douteux, symlink, permission refusee, interpreteur absent
ou destination existante. Aucun chmod sur les preuves historiques. Ne
pretendre aucune recherche exhaustive dans un dossier inaccessible.
Le nouveau BASE doit etre hors P3, hors livraisons et hors preuves B1.
`set -C` interdit les ecrasements par redirection dans ce shell.

## 2. Verifier les octets livres avant execution

```bash
printf '%s  %s\n' "$ANCHOR" "$DELIVERY/SHA256SUMS" \
  | sha256sum --check --strict - \
      > "$BASE/bootstrap.stdout" 2> "$BASE/bootstrap.stderr" || exit 1
(
  cd "$DELIVERY" || exit 1
  sha256sum --check --strict SHA256SUMS
) > "$BASE/payload.stdout" 2> "$BASE/payload.stderr" || exit 1
```

ARRET si une empreinte differe. Pas de re-scellement pour rendre conforme
une copie. Les outils verifient aussi la couverture exacte des fichiers
livres, y compris code limite, copie du noyau strict et tests.

## 3. Tests sans aucun ignore

```bash
"$PY" -I -B "$DELIVERY/record_tests.py" \
  --release-anchor "$ANCHOR" --timeout 120 --out "$BASE/unit-tests" || exit 1
(
  cd "$BASE/unit-tests" || exit 1
  sha256sum --check --strict SHA256SUMS
) || exit 1
"$PY" -I -B -c '
import json,pathlib,sys
p=pathlib.Path(sys.argv[1])
r=json.loads((p/"receipt.json").read_bytes())
t=(p/"stderr").read_text()
assert r["complete"] is True and r["returncode"] == 0
assert r["python"].startswith("3.11.")
assert t.rstrip().endswith("OK") and "skipped" not in t
' "$BASE/unit-tests" || exit 1
```

ARRET si un test echoue ou est ignore. Fixtures synthetiques uniquement :
elles ne lisent aucun inventaire/archive historique.

## 4. Mesurer la couche sans lever le refus general

```bash
set +e
"$PY" -I -B "$DELIVERY/layer_contents.py" \
  --release-anchor "$ANCHOR" --archive "$ARCHIVE" \
  --sums "$P3_FIXED/ROOTFS-SHA256SUMS" \
  --metadata "$P3_FIXED/ROOTFS-METADATA.txt" \
  --out "$BASE/comparison"
RC=$?
set -e
printf '%s\n' "$RC" > "$BASE/scoped-shell-returncode"
test "$RC" -eq 20 || exit 1
```

Le 20 est intentionnel : B reste bloque. Il ne prouve pas la completion de A.
Verifier le recepisse et la mesure avec l'etape suivante. L'outil produit
started.json, rapport deterministe, stdout/stderr exacts, recepisse,
SHA256SUMS et evidence-anchor.json. Toutes les entrees restent en lecture
seule, sans copie/extraction de la couche. Toute tentative interrompue doit
etre conservee ; nouveau --out obligatoire pour une nouvelle tentative.

## 5. Verifier la completion, les portees et les empreintes

```bash
(
  cd "$BASE/comparison" || exit 1
  sha256sum --check --strict SHA256SUMS
) || exit 1
"$PY" -I -B -c '
import hashlib,json,pathlib,sys
p=pathlib.Path(sys.argv[1])
r=json.loads((p/"receipt.json").read_bytes())
q=json.loads((p/"report.json").read_bytes())
assert r["complete"] is True and r["returncode"] == q["returncode"] == 20
assert q["decision"] == "REVIEW_ONLY_BLOCKED"
assert q["formal_b1_contents_closed"] is False and not any(q["go"].values())
assert q["B_strict_whole_archive"]["returncode"] == 20
assert q["B_strict_whole_archive"]["status"] == "ERROR"
assert q["historical_v2_refusal"]["returncode"] == 20
assert q["B_strict_whole_archive"]["anomalies"]
assert all(x["approved"] is False for x in q["B_strict_whole_archive"]["anomalies"])
assert q["C_p4_and_provenance"]["qualification_granted"] is False
assert q["C_p4_and_provenance"]["provenance_granted"] is False
assert q["A_regular_layer_contents"]["measurement_complete"] is True
assert q["A_regular_layer_contents"]["scope_returncode"] in (0,10)
assert q["A_regular_layer_contents"]["expected_regular_paths"] == 9771
assert q["outer_coverage"]["all_bytes_accounted"] is True
assert q["layer_coverage"]["all_bytes_accounted"] is True
assert q["comparison"]["complete_metadata_equality_established"] is False
for n,h in r["sha256"].items():
    assert hashlib.sha256((p/n).read_bytes()).hexdigest() == h
a=json.loads((p/"evidence-anchor.json").read_bytes())
assert hashlib.sha256((p/"SHA256SUMS").read_bytes()).hexdigest() == a["sha256sums"]
print(json.dumps({k:q[k] for k in ("A_regular_layer_contents","B_strict_whole_archive",
                                  "C_p4_and_provenance")},indent=2))
print(json.dumps({k:q["comparison"][k] for k in ("counts","difference_counts",
                      "root_directory","directory_comparison")},indent=2))
' "$BASE/comparison" || exit 1
```

ARRET si A n'est pas mesuree completement : le 20 seul n'est jamais un PASS.
Si A.scope_returncode=10, examiner tous les chemins/contenus divergents.
Si A.scope_returncode=0, conclure uniquement REGULAR_LAYER_CONTENTS_IDENTICAL_ONLY.
Dans les deux cas, conserver toutes les differences metadata/repertoires,
l'absence de `.` et l'anomalie eec772146... dans B.

ARRET de toute qualification automatique : pas de GO P4, pas de provenance
accordee, pas de cloture C5. Archiver le nouveau BASE sur support physique et
remettre separement les empreintes de comparison/SHA256SUMS et
unit-tests/SHA256SUMS. Ne jamais remplacer les preuves ou recepisses v2.
