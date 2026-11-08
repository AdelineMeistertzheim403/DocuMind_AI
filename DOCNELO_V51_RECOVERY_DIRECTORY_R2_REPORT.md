# Docnelo V5.1 - Rapport de revision Recovery Control Directory r2

**Revision proposee pour examen uniquement ; aucun remplacement du
candidat v1, aucun GO P3 ou production.**

Rapport complet : `candidates/recovery-control-directory-v1-r2/REPORT_R2.md`.
Protocole Debian hors ligne : `DEBIAN_OFFLINE_PROTOCOL.md` dans cette revision.

La garde historique reste stricte. Le nouveau preflight exige ensemble
le YAML source avec `create_host_path: false` explicite, un rendu Compose
concordant et les controles hote/P2. `bind: {}` seul ne suffit jamais.
Le YAML, les publishers, les 119 tests P1 et les controles P2 restent
byte-identiques a v1 ; aucune modification de middleware.

**Windows, CPython 3.13.7 : 170 tests reussis (119 P1 + 51 r2),
aucun skip/xfail et aucune E/S interdite enregistree.**
Preuves finales : `qualification/recovery_directory/windows-r2-preparation-final-003`.
La campagne intermediaire 002 reste conservee. Le patch a ete verifie
avec `git apply --check` sur une copie isolee, sans application.
La conservation des 248 fichiers v1 et de 45 artefacts historiques est
verifiee par le generateur d'inventaire r2.

Inventaires : `REVISION_CHANGES.json`, `PRESERVATION_VERIFIED.json`,
`INPUTS.json`, `SHA256SUMS` ; correctif non applique : `revision.patch`.

Le constat Compose 2.26.1-4 est fourni par l'operateur, non reproduit
nativement ici. Debian13/CPython3.11.18, inspections Engine, D11,
permissions reelles et propagation Docker restent a qualifier.
Aucun conteneur ni service n'a ete demarre, aucun namespace synthetique
ou latch restaure modifie. Aucun GO Docker operationnel, S2, Lifecycle 10,
Public Beta ou production.

Transfert neuf : `deliveries/docnelo-v51-recovery-directory-candidate-v1-r2/`.
Son `SHA256SUMS` couvre l'archive et le guide de transfert ; l'archive
contient egalement un inventaire `PACKAGE-SHA256SUMS`.
