# Inventaire Git - 2026-11-05

Diagnostic uniquement. Aucun nettoyage, ajout a l'index ou changement de source.
Reference commune : `AUDIT_TRACEABILITY.md`.

## Instantane initial

Capture UTC : `2026-11-05T13:00:03.247747+00:00`, avant les dix livrables de cet audit.
Branche : `branding/docnelo`. HEAD : `1bc1a4a5bb49395acabdce5e7604d1a6b97dea61`.
Dernier commit : `2026-10-29T19:19:09+01:00`.

| Mesure | Nombre |
|---|---:|
| Chemins suivis, index et HEAD | 338 |
| Fichiers suivis modifies | 44 |
| Modifications indexees | 0 |
| Modifications suivies non indexees | 44 |
| Entrees non suivies | 4 192 |
| Total des entrees en attente | 4 236 |
| Suppressions / renommages / conflits | 0 / 0 / 0 |
| Chemins suivis correspondant aux exclusions actuelles | 0 |
| Gitlinks / sous-modules declares | 0 |
| Entrees ignorees retournees | 138 276 |

**Precision importante : 4 236 entrees Git ne sont pas 4 236 fichiers ordinaires.**
Les 4 192 entrees non suivies comprennent 4 190 fichiers ordinaires et deux racines
de worktrees imbriques, que Git represente chacune par un repertoire `source/`.
Le total strict est donc **4 234 fichiers ordinaires en attente**, plus deux racines.
L'index ne contient aucune modification, mais contient bien les 338 chemins suivis.
Les 44 statuts sont tous ` M`. Le diff donne 3 179 insertions et 2 034 suppressions;
ce ne sont pas 4 000 modifications applicatives.

## Repartition des entrees en attente

Octets : somme des tailles logiques des fichiers ordinaires seulement, sans occupation
physique, deduplication des copies ou comptage recursif des worktrees imbriques.

| Repertoire | Entrees Git | Octets |
|---|---:|---:|
| deliveries | 1 620 | 735 380 648 |
| exports | 1 177 | 21 703 780 |
| candidates | 766 | 11 254 082 |
| qualification | 493 | 56 584 134 |
| Racine, hors repertoires | 75 | 994 947 |
| frontend | 28 | 1 828 787 |
| backend | 20 | 336 739 |
| tests | 20 | 276 187 |
| ops | 11 | 78 699 |
| tools | 11 | 177 765 |
| docs | 9 | 589 817 |
| docnelo-lab-wheels | 6 | 5 109 004 |
| **Total** | **4 236** | **834 314 589** |

`deliveries`, `exports`, `candidates`, `qualification` expliquent **4 056 entrees,
soit 95,75 %** du statut. Ce sont essentiellement des instantanes, livraisons,
outillages de qualification et preuves, pas des dechets a ignorer globalement.

Principaux sous-ensembles : `deliveries\docnelo-10-users` 720 entrees;
`deliveries\docnelo-web-branding-r1` 703, dont 596 dans `npm-cache`;
exports `234818Z` 357, `234658Z` 356, `234303Z` 354;
candidates recovery v1-r3 261, v1-r2 257, v1 248;
qualification build materials v2 139 et base runtime v3 106.

## Classification disjointe

| Classe | Entrees | Octets des fichiers ordinaires |
|---|---:|---:|
| Code source, scripts et styles, hors tests/generation | 1 730 | 14 470 546 |
| Tests et fixtures classees par chemin | 538 | 4 923 834 |
| Documentation | 279 | 2 940 203 |
| Configuration, verrous, empreintes et modeles | 314 | 2 776 030 |
| Artefacts, archives, rapports et bases candidates | 451 | 746 638 988 |
| Assets | 114 | 16 090 471 |
| Generes identifies par motifs | 623 | 46 241 617 |
| Autres, dont les deux racines de worktree | 187 | 232 900 |
| **Total** | **4 236** | **834 314 589** |

Hors des quatre familles d'instantanes/preuves : **54 fichiers de code et 25 tests**.
Les 1 676 autres chemins de code et 513 autres tests sont dans ces familles.
Sur les 2 268 fichiers classes code/tests en attente, il existe **465 contenus
SHA-256 distincts** et 346 groupes de copies identiques : 1 803 occurrences au-dela
de la premiere copie. Cela ne permet pas de supprimer les copies scellees.

Les **623 generes** se decomposent en 596 fichiers du cache npm R1 et 27 fichiers
de distributions : image-context R1 13, reference-runtime R1 7, export `234213Z`
7. Ces 27 distributions peuvent etre des preuves de livraison : conservation.
Aucun genere n'est classe dans les 180 entrees hors des quatre familles.
Les cinq scripts racine `.tmp_*.py` sont du code temporaire candidat, pas des
fichiers automatiquement reproductibles; ils restent comptes comme code.

## Repartition exhaustive par extension des entrees en attente

Les deux racines de worktree sont dans « sans extension ». La classification
semantique precedente a priorite : un `.py` peut etre un test ou une copie, un
`.md` peut appartenir au cache. Une extension n'est pas une decision de conservation.

| Extension | Nombre | Extension | Nombre |
|---|---:|---|---:|
| .py | 1 707 | sans extension | 782 |
| .json | 304 | .md | 280 |
| .tsx | 248 | .ts | 146 |
| .mjs | 108 | .whl | 105 |
| .png | 98 | .yaml | 63 |
| .example | 41 | .lock | 39 |
| .log | 30 | .txt | 24 |
| .css | 20 | .service | 20 |
| .ini | 15 | .timer | 15 |
| .zip | 15 | .html | 13 |
| .js | 12 | .svg | 12 |
| .xml | 12 | .dockerignore | 10 |
| .sh | 10 | .sha256 | 10 |
| .toml | 10 | .yml | 10 |
| .mako | 9 | .ico | 7 |
| .patch | 7 | .webmanifest | 7 |
| .pdf | 6 | .ps1 | 6 |
| .beta-recipe | 5 | .db | 5 |
| .lifecycle-validation | 5 | .sql | 5 |
| .gz | 4 | .tar | 3 |
| .env | 2 | .codex | 1 |
| .crt | 1 | .key | 1 |
| .pins | 1 | .sha256sums | 1 |
| .sig | 1 | | |

## Volume et limites physiques

| Ensemble retourne par Git | Fichiers ordinaires | Octets logiques |
|---|---:|---:|
| Suivis, modifies ou non | 338 | 3 742 791 |
| Non suivis | 4 190 | 833 764 637 |
| Ignores accessibles et enumeres | 138 274 | 10 100 393 172 |
| **Total enumere, hors .git** | **142 802** | **10 937 900 600** |

Principaux volumes en attente : `deliveries\docnelo-signup-e2e-lab\api-untagged.tar`
305 111 040 octets; `deliveries\docnelo-web-branding-r1\payload\web-image.tar`
260 080 640; ZIP runtime v3 20 349 155; ZIP build materials v2 20 252 196;
archive B1 6 830 080. Les deux images representent a elles seules 565 191 680
octets. Ne pas les publier automatiquement.

Dans les tailles ignorees, `var` represente environ 7,13 Go et `deliveries`
environ 2,13 Go. Ce ne sont pas uniquement des caches : sauvegardes, preuves,
candidates et archives privees y sont aussi masquees.

**Inventaire physique non exhaustif** : 117 avertissements lors de l'enumeration
ignoree, dont 115 refus de permission et deux « Function not implemented ».
Aucune permission modifiee, aucun lien suivi pour contourner ces refus.
Les tailles n'incluent ni `.git`, ni les chemins non retournes, ni les contenus
internes des quatre worktrees representes par leur racine.

## Worktrees imbriques, pas sous-modules

| Racine sous deliveries | HEAD | Statut interne retourne |
|---|---|---|
| docnelo-signup-e2e-lab\source | b046e5d8256d45b65bf575a8a006351616b69fc9 | 0 entree |
| docnelo-web-branding-r1\source | 22b6428f961e98c6482a9881579361f53c114934 | 0 entree |
| docnelo-lifecycle-10-api\source | 8b11d4daf47bd7c3c6766b9f5231ea8a84fdbf71 | 0 entree |
| docnelo-web-branding-r2\source | b046e5d8256d45b65bf575a8a006351616b69fc9 | 0 entree |

Cinq worktrees enregistres en comptant la racine; aucun declare prunable ou locked.
Les deux derniers sont ignores localement. Un statut interne sans entree ne prouve
pas l'absence de fichiers ignores. Ne pas additionner leurs fichiers aux comptes
du statut parent ni traiter ces dossiers comme des copies ordinaires deplacables.

## Liste complete des 44 chemins suivis modifies

```text
.env.production.example
backend\account_admin.py
backend\account_api.py
backend\ai\providers.py
backend\ai\settings_api.py
backend\api.py
backend\authentication.py
backend\config.py
backend\lifecycle_backup_lock.py
backend\lifecycle_durability.py
backend\main.py
backend\public_registration.py
backend\recovery_quarantine.py
backend\services\documents.py
compose.public-beta-test.yaml
frontend\index.html
frontend\server\app.mjs
frontend\server\app.test.mjs
frontend\src\components\Assistant.tsx
frontend\src\components\Layout.tsx
frontend\src\components\Workspace.tsx
frontend\src\legal\documents.ts
frontend\src\pages\AISettings.tsx
frontend\src\pages\Account.tsx
frontend\src\services\account.ts
frontend\src\services\api.ts
frontend\src\styles.css
frontend\src\test\app.test.tsx
frontend\src\types\api.ts
ops\testing\combined_restore_lab.py
ops\testing\prepare_beta_recipe.py
ops\testing\validate_beta_recipe.py
pyproject.toml
requirements.runtime.lock
requirements.test.lock
tests\fixtures\public_beta_browser.mjs
tests\test_pinned_builds.py
tests\test_public_beta_snapshot.py
tests\test_snapshot_backup_integrity.py
tools\backup_local.py
tools\backup_production.py
tools\retention_production.py
tools\validate_restore.py
tools\verify_snapshot.py
```

Les dix nouveaux livrables de l'audit ajouteront dix entrees non suivies a cet
instantane, sans augmenter les 44 modifications suivies.
