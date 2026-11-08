# Docnelo V5.1 - Recovery Control Directory r3

**Revision proposee pour examen uniquement. Aucun remplacement de v1/r2,
aucun GO P3 operationnel, Docker, S2, Lifecycle 10, Public Beta ou production.**

Rapport technique detaille :
`candidates/recovery-control-directory-v1-r3/REPORT_R3.md`.
Protocole offline : `DEBIAN_OFFLINE_PROTOCOL.md` dans ce nouveau candidat.

## Correction verifiee

Le chemin `validate_documents -> _validate_source -> _validate_rendered`
confirme le diagnostic : r2 comparait mem_limit a un entier, donc la
chaine native `"134217728"` n'etait pas normalisee vers `'128m'`.
R3 accepte seulement `"128m"` et `"134217728"` de type str, ou
`134217728` de type int exact. Floats, booleens, valeurs voisines,
variantes d'unites/espaces/zeros initiaux et champ absent sont refuses.
Le rendu brut reste intact. Le seul autre changement du module est
le tag de preuve `v1-r3`.

Le YAML source `128m` et les `create_host_path: false` explicites
restent obligatoires. Source + rendu + parametres + P2 + hote restent
conjoints ; `bind: {}` seul est insuffisant.

## Tests et conservation

**Windows / CPython3.13.7 : 209 tests reussis, aucun echec, skip,
xfail ou evenement d'E/S interdite.**

| Suite | Cas |
|---|---:|
| P1 configuration/contrat inchange | 77 |
| P1 vraie FastAPI ASGI inchange | 42 |
| Source/rendu/P2/hote r2 inchange | 51 |
| Nouveaux cas de normalisation r3 | 39 |

Les 39 cas couvrent trois representations approuvees, 24 variantes
negatives, l'absence de limite, deux notations exponentielles, trois
alterations de source refusees, quatre controles conjoints, le CLI
avec conservation du JSON brut et la preservation SHA.
Preuves finales :
`qualification/recovery_directory_r3/windows-preparation-final-002`,
avec JUnit, cas, resultat, inventaire d'entree, dependances et SHA256SUMS.
La campagne 001 reste conservee. Le delta a passe git apply --check
sur une copie isolee de r2, sans jamais etre applique.

Verification de conservation : **248 fichiers v1, 257 fichiers r2
et 70 artefacts historiques** ; **248 fichiers r2 non concernes
byte-identiques dans r3**. Compose, publishers, middleware et P2 inchanges.

## Fichiers et transfert

Dans r3, quatre fichiers modifies par rapport a la copie r2 :
`source/tools/preflight_recovery_compose.py`, `run_local.py`,
`README.md`, `DEBIAN_OFFLINE_PROTOCOL.md`.
Quatre ajouts : `tests/test_compose_memory_normalization.py`,
`BASELINE_R3.json`, `build_r3_inventory.py`, `REPORT_R3.md`.
Cinq metadonnees regenerees : `REVISION_CHANGES.json`, `revision.patch`,
`PRESERVATION_VERIFIED.json`, `INPUTS.json`, `SHA256SUMS`.
Le delta et ses SHA avant/apres sont dans REVISION_CHANGES.json.

Transfert independant :
`deliveries/docnelo-v51-recovery-directory-candidate-v1-r3/`.
Le guide, l'archive, PACKAGE-SHA256SUMS et le manifeste externe
permettent les controles offline ; les SHA ne sont pas des signatures.
Ancre du SHA256SUMS candidat r3 :
`5f3cc1598423107c5616d630d63d31b849b939cbd9f3ce9ce25fc0bf3440f8d4`.

## Limites

Le constat Debian r2 est fourni par l'operateur ; aucune execution
Docker locale ni reproduction native r3. Debian13/CPython3.11.18,
Compose2.26.1-4, D11, identites effectives, RO/DAC, Engine et propagation
restent a qualifier apres autorisation distincte. Aucune nouvelle image
ou fermeture de dependances offline n'est fournie.
Aucun conteneur, nouveau namespace synthetique, chmod, changement du
latch P2 ou operation de production. **Examen uniquement.**
