# Traçabilité de l'audit de préparation bêta dix

## 1. Objet audité et méthode

Dossier de référence demandé : **2026-11-05**. Cette date est un identifiant
de dossier, pas une preuve d'heure de déploiement ou un horodatage signé.

Répertoire local : dépôt `DocuMind_AI`, Windows.
Git HEAD lu directement :
`1bc1a4a5bb49395acabdce5e7604d1a6b97dea61`.
**Le worktree est modifié et contient de nombreux fichiers non suivis**,
notamment des livraisons et rapports. HEAD seul ne reproduit pas ces octets.
Le diff préexistant backend/frontend/tools porte notamment sur auth,
admissions, documents, lifecycle, BFF, juridique, backup et restore.
Aucun de ces changements préexistants n'a été corrigé, intégré ou annulé.

Trois objets sont séparés dans toutes les conclusions :

1. Workspace local : code lu dans son état courant, pas release autorisée.
2. Candidate fermée Lifecycle 10 : commit
   `8b11d4daf47bd7c3c6766b9f5231ea8a84fdbf71`, référence composite
   `a323afc5c9d63a8a9f59ac10c365710b58d1c868`, image candidate selon preuve
   locale `sha256:32a1516206d9e648e3741b54dc0543c0b455f22cdf676e7d69d9a971e1f4213d`.
3. VPS : état courant **non inspecté** ; production fermée, compteur zéro,
   schéma 0007 et ancienne limite cinq sont des informations historiques
   communiquées par l'opératrice, non de nouvelles observations.

Lecture statique de fichiers et rapports, recherche ciblée de noms/symboles,
lecture de journaux et JSON, hashes de fichiers, vérification de manifestes
et inspection en mémoire de l'archive de preuves B1. Aucun import de module
applicatif ou exécution de script de qualification/application.

## 2. Contrôles d'intégrité directement réalisés

### Ancres B1 fournies par l'opératrice

| Fichier local | SHA-256 recalculé | Résultat |
|---|---|---|
| `qualification\b1-review-20261105\b1-evidence.tar` | `49418c8f928de66e82b49c5b9834ae1ce0254245a4092898ca0e5b3d28f971cd` | Conforme à l'ancre fournie |
| `qualification\b1-review-20261105\B1_INDEPENDENT_REVIEW.md` | `edc2309dbef2d302f45767806d5b870489584a9c02591868a23b73344e3d88e0` | Conforme à l'ancre fournie ; formulaire non signé |

L'archive a été parcourue avec `tarfile.open(..., 'r|*')`, lecture des
fichiers en mémoire, **sans extraction sur disque et sans exécution**.
Les quatre manifestes ont été recalculés, puis leurs entrées vérifiées :

| Jeu interne | SHA-256 de SHA256SUMS | Entrées vérifiées |
|---|---|---:|
| OCI v2 / unit-tests | `80f0435b6d5eddfd724660359c1cfd7ec0ef76aa13ea01484855c370188067ea` | 4 |
| OCI v2 / comparison | `da22ccae43b1eb4df9906993015fc666bb454e7bdb0cdcc41ea1ba65d780cd0c` | 5 |
| P3 Layer v1 / unit-tests | `d44877191c7f0d0043887f9b11a5387685a62aa305ada83dc7bf1adce54bee91` | 4 |
| P3 Layer v1 / comparison | `832d2272b76f38583fcf060cfb34e43e309cf677ddeadb64d1f143d1a5615ef8` | 5 |

Préfixes des membres :
`p4-b1-oci-v2-6e3e9a30bf4e452780fc79f0cd6a53c7` et
`p4-b1-p3-layer-v1-1f1304c0ce3246b9b64ebd851dbeb442`.
Les JSON `comparison/report.json` ont été lus directement : strict v2
`status=ERROR`, décision `REVIEW_ONLY_BLOCKED` ; scope A du contrôle séparé
`REGULAR_LAYER_CONTENTS_IDENTICAL_ONLY`, égalité true, code de scope zéro.
Les résultats complets et leurs limites sont détaillés dans le rapport
consolidé et la fiche indépendante, non convertis en nouvelle exécution Debian.

Les **35 et 46 tests** restent des exécutions historiques Debian
13.7/Python 3.11.18 documentées par ces jeux de preuves, pas des tests
réexécutés ici. L'original de l'archive P3, ses inventaires et le rootfs
vivant n'ont pas été relus sur la VM par cet audit.

### Candidate Lifecycle 10

Les quinze fichiers de `source-release.json` ont été lus sous
`deliveries\docnelo-lifecycle-10-api\source` et comparés à leurs hashes :
**15/15 conformes**.

Le fichier `payload-manifest.sha256` ancre le `payload\SHA256SUMS` :
`9d077ca43a8995429e6a471f30e9cd12d7724292a56dd6a74332c4f0954497c5`.
Ses **37 entrées** ont été recalculées conformes, y compris les octets des
fichiers privés du payload, sans les charger/exécuter ni en publier le contenu.
Ce contrôle d'intégrité ne reconstitue pas la provenance CI historique et
ne prouve pas un déploiement sur VPS.

| Preuve sous `deliveries\docnelo-lifecycle-10-api` | SHA-256 recalculé | Observation |
|---|---|---|
| `pytest.log` | `09f164fdc22304e680b6e135fa709f48eee253bf139cbbc3d48698d316b4de93` | Ligne 82 : 227 passed, 17 warnings |
| `bff-tests.log` | `5fd0d9638897a907ddf0070f6c50be6b69de495822bdbf6adce9d946760cbb3c` | Lignes 364–371 : 50 tests, pass 50, fail 0, skipped 0 |
| `operator-tests.log` | `1924959ce040083e05354531625a7bd9b33c0fedea286b6c9283d9d5923fffa4` | Lignes 2–4 : 11 tests, OK |
| `roundtrip-result.json` | `8b7c2155222853db6445bd982d24468b0900777af2621103b1d383ff1dd6bfc0` | passed=true, PG17, trois processus, restored=10, stale=0 refusé |
| `image-proof.json` | `9af7272238ccad876a88a050b34140d4ff917f72bcfd1929d8c0a2b1e396e051` | Déclaration d'image/source/runtime, pas inspection Docker de cet audit |
| `source-release.json` | `e8db5c63c203957b7ec35994062f4c251eff452777d6cbe7e1fdd1bb6d489d95` | Commit candidat et quinze sources |

`result.json` déclare exit_code=0 et les douze modules de la suite
consolidée. **Ne pas utiliser `focused-result.json` comme verdict final** :
il garde un autre scope et `strict_lifecycle_ten_qualified=false`.
Les essais intermédiaires ne sont pas additionnés ni effacés.

Comparaison directe workspace/candidate : `backend\auth.py`,
`backend\authentication.py`, `backend\api.py` et
`backend\services\documents.py` sont identiques octet pour octet.
`backend\account_api.py` diffère. L'étude de la garde de suppression a
donc aussi porté explicitement sur la candidate :
`deliveries\docnelo-lifecycle-10-api\source\backend\lifecycle_durability.py:255-259`.

### Empreintes de repérage du workspace audité

Ces hashes fixent les principales sources citées ; ce tableau n'est pas
un manifeste complet de release.

| Chemin | SHA-256 |
|---|---|
| `backend\config.py` | `d56c3c664a3416836dbcf34b90aff4a4fc19c645b5ba329049f571aa0ee6a90e` |
| `backend\public_registration.py` | `9031ce147084dfcefd65958a5538ff078c7e83844686c78334e1264db78f052b` |
| `backend\account_admin.py` | `a78e9deff2062951adcd054e9fb408f446f9b588f0b9a486cad6ce262c73d136` |
| `backend\api.py` | `667f69a169e3aa2921987ede5a6e16c539e9106a3a05f2b547d47c52980b3fdf` |
| `frontend\server\app.mjs` | `d34d1ce551f15d9ee24649804bcf53555740de0fcefe35aa282de2ffad33553a` |
| `frontend\src\legal\documents.ts` | `a74ea65bbbb14b339cc1de0d865f4c70a64e380fb9759a5ddbbcaed2c8b74992` |
| `compose.public-beta.vps.yaml` | `f46571b71b7a3174c96b15b2848f2b31cdae60339621116eb14be03393dc4ff2` |
| `tools\validate_restore.py` | `92edaabbf1ca48f62687156c9f7e4c6d31629546be20ea1d26107a18d15357ff` |

Une égalité de SHA identifie des octets relativement à une ancre.
Elle n'est ni une signature, ni une preuve de fraîcheur indépendante,
ni une autorisation.

## 3. Corpus examiné

Les lectures ont porté sur les sections utiles et les résultats de recherche,
pas systématiquement sur chaque ligne de chaque fichier.

| Groupe | Documents / sources examinés | Usage et limite |
|---|---|---|
| Architecture | `Dockerfile`, `frontend\Dockerfile`, `pyproject.toml`, `compose.public-beta.vps.yaml`, inventaire de migrations jusqu'à `0007_public_beta.py` | Configuration Git/worktree, pas configuration servie |
| Auth/comptes | `backend\auth.py`, `authentication.py`, `gateway.py`, `config.py`, `public_registration.py`, `account_api.py`, `account_admin.py`, `ai\settings_api.py`, `main.py`, recherches `security_audit.py` | Validation e-mail distincte d'approbation ; CLI distincte d'admin HTTP |
| Documents | `backend\api.py`, `services\documents.py`, `services\extraction.py` ; tests documents/intégrité/SaaS/upload | Autorisations/chemins/confinement et refus strict d'effacement |
| Lifecycle | `backend\lifecycle_admissions.py`, `lifecycle_durability.py` ; candidate `lifecycle_capacity.py`, `account_admin.py`, tests `test_public_beta_capacity_ten.py`, `test_public_beta_capacity_failures.py`, `test_public_beta_capacity_backup.py`, recherches `capacity_roundtrip.py` | Root cinq vs candidate dix ; scopes opérationnel/synthétique séparés |
| Tests comptes/quota | `tests\test_public_beta.py`, `test_public_beta_state.py`, `test_public_beta_postgresql_concurrency.py`, `test_public_beta_authorization.py`, `test_accounts_saas.py` | Définitions et assertions ; exécution créditée seulement aux modules du dossier candidat |
| Frontend | `frontend\server\app.mjs`, `app.test.mjs`, `src\pages\Account.tsx`, `Dashboard.tsx`, `Documents.tsx`, `Legal.tsx`, `src\legal\documents.ts`, recherches `Account.test.tsx`, `Legal.test.tsx` | Workspace non assimilé à Web R2 ; nouveau BFF download distinct |
| Historique dix | `DOCNELO_PUBLIC_BETA_10_USERS_AUDIT.md`, `..._TEST_REPORT.md`, `..._LIFECYCLE_TEST_REPORT.md`, `..._API_PROVENANCE.md`, `..._API_RELEASE_MANIFEST.md`, `..._OPENING_RUNBOOK.md` | Anciennes anomalies comparées à corrections/candidate ultérieures |
| Preuves candidate | `deliveries\docnelo-lifecycle-10-api\result.json`, `focused-result.json`, `source-release.json`, `image-proof.json`, `roundtrip-result.json`, `test-runtime-parity.json`, trois logs et manifestes | Intégrité directe et résultats historiques ; aucune réexécution |
| Web R2 et signup | `deliveries\docnelo-web-branding-r2\payload\DOCNELO_PUBLIC_BETA_BRANDING_R2_TEST_REPORT.md`, `DOCNELO_SIGNUP_E2E_LAB_TEST_REPORT.md`, `deliveries\docnelo-signup-e2e-lab\test-results.json` | UI/API simulée ≠ E2E réussi ; R2 download 404 confirmé historiquement |
| Provenance/dérive | `DOCNELO_API_DEPLOYMENT_PROVENANCE_20261031_REPORT.md`, `DOCNELO_API_CONTROLLED_RECONCILIATION_PLAN.md`, `DOCNELO_LIFECYCLE10_COMPOSE_GUARD_TEST_REPORT.md` | Provenance locale de contenu distincte de création H0 ; tests du garde ne le font pas passer sur VPS |
| Backup/reprise | `DOCNELO_PUBLIC_BETA_BACKUP_RESTORE_COMPATIBILITY_AUDIT.md:1-300`, `DOCNELO_V51_BACKUP_RESTORE_HARDENING_REPORT.md:1-208`, `tools\validate_restore.py:35-74,284-458`, `ops\public_beta\VPS_BACKUP_RESTORE_RUNBOOK.md` | Ancien sealer non invoqué corrigé dans développement ; pas bundle ancien promu |
| S2/quarantaine | `docs\DOCUMIND_S2_OPERATIONAL_CHECKLIST.md`, `docs\PHASE_15_4_LOT_2_18_S2_RECOVERY_RUNBOOK.md`, `docs\PHASE_15_4_LOT_2_19_S2_APPLICATION_GUARDS.md`, `docs\PHASE_15_4_LOT_2_19_FULL_RECOVERY_TEST_RESULTS.md`, `DOCNELO_V51_QUARANTINE_FUNCTIONAL_TEST_REPORT.md`, `DOCNELO_V51_RESTORED_LATCH_FASTAPI_QUALIFICATION.md`, `DOCNELO_V51_RECOVERY_DIRECTORY_R3_REPORT.md` | Recettes locales bornées et préparations ; pas d'autorisation S2 globale retrouvée dans ces pièces |
| Préparations de preuves | Recherches ciblées `qualification\docnelo_v51_hardening`, `restored_latch`, `quarantine_debian`, `recovery_directory_r3` | Résultats Windows/préparation ne sont pas des succès Debian déduits |
| P4/B1 | `qualification\p4_base_runtime_v3\P4_BASE_RUNTIME_REPORT.md`, `DOCNELO_V51_P4_B1_CONSOLIDATED_REVIEW_2026-11-05.md`, archive/fiche B1, référence `P4_B1_OCI_AUXILIARY_BLOB_ROOT_CAUSE_REVIEW.md` | A/B/C séparés ; B1/C5/B2–B7 non validés |
| Juridique | `DOCNELO_PUBLIC_BETA_10_USERS_LEGAL_READINESS.md` et sources Legal ci-dessus | Inventaire documentaire, pas avis juridique ; aucune coordonnée personnelle recopiée |
| Exploitation | `tools\monitor_production.py:1-180`, `tools\retention_production.py:1-150`, `docs\sprint-8-monitoring.md:1-145`, recherches `tests\test_monitoring.py`, `test_retention.py`, `test_security_audit.py`, inventaire unités systemd | Outils historiques /srv et tests, pas preuve d'installation sur bêta /opt |

Les extensions `..._` de la ligne « Historique dix » reprennent le préfixe
exact `DOCNELO_PUBLIC_BETA_10_USERS`. Les références sources et tests par
contrôle, avec lignes, sont dans la matrice et les lacunes de tests.

## 4. Opérations locales de consultation

Outils de lecture/recherche : `view`, `glob`, `rg`, plages et motifs ciblés
sur le dépôt et ses descendants. Les appels PowerShell ont effectué :

```powershell
git --no-pager rev-parse HEAD
git --no-pager status --short
git --no-pager diff --stat -- backend frontend tools migrations
git --no-pager status --short -- qualification\beta-10-readiness-audit-20261105
Get-FileHash qualification\b1-review-20261105\b1-evidence.tar,
  qualification\b1-review-20261105\B1_INDEPENDENT_REVIEW.md -Algorithm SHA256
Get-Content deliveries\docnelo-lifecycle-10-api\pytest.log -Tail 6
Get-Content deliveries\docnelo-lifecycle-10-api\bff-tests.log -Tail 9
Get-Content deliveries\docnelo-lifecycle-10-api\operator-tests.log -Tail 5
```

Les commandes présentées sur plusieurs lignes sont un relevé documentaire,
pas un script d'exploitation. Des scripts Python standard sur stdin
(`python -B -`) ont uniquement utilisé `pathlib`, `hashlib`, `json`,
`tarfile` et les lectures de fichiers pour :
recalculer les SHA-256, comparer quinze sources/37 fichiers de payload,
vérifier les quatre manifestes B1, lire les champs A/B/C, compter les lignes
de logs et comparer les quatre sources communes.
Aucun import backend, cache Python, fixture pytest ou accès réseau.

Un premier affichage `Format-Table` a tronqué visuellement les hashes :
ils ont été recalculés/affichés intégralement, sans se contenter du préfixe.
Une lecture de `bff-tests.log` en UTF-8 a échoué (`UnicodeDecodeError`,
commande retour 1) après les premiers contrôles ; reprise avec détection
de BOM UTF-16, retour 0. Aucune preuve n'a été réencodée.
Les quatre vérifications internes B1, quinze sources et 37 payloads ont
ensuite terminé sans divergence. Les recherches qui ne trouvaient pas un
nom/symbole ont été conservées comme recherche négative, pas comme preuve
de succès fonctionnel.

La destination était absente avant la première création. Les seules
écritures intentionnelles sont les sept nouveaux fichiers d'audit :
aucun fichier de l'application, de configuration ou de preuve historique
n'est une sortie de cet audit.

La vérification documentaire a contrôlé la liste exacte des sept sorties,
les références de fichiers/plages citées et l'équilibrage des blocs de code.
Les huit empreintes de repérage du workspace ont été recomparées après
rédaction : sources inchangées. Ces contrôles ne sont pas des tests applicatifs.
Les premières passes ont signalé des bornes de citations dépassant les fichiers :
elles ont été corrigées dans ces seuls nouveaux documents. Une assertion du
validateur a aussi nécessité des échappements Unicode pour le transport stdin
PowerShell ; ce n'était pas un échec applicatif ou une altération de preuve.

## 5. Pièces manquantes, hors accès et limites

| Élément | Limite et conséquence |
|---|---|
| VPS/HTTPS/SMTP/B2/Restic actifs | Aucun accès réseau ou distant ; aucun état effectif actuel observé |
| Originaux P3, inventaires et rootfs vivant sur Debian | Non relus directement ; l'archive de preuves locale ne contient pas ces matériaux |
| Dossier historique VM inaccessible signalé antérieurement | Non visité, permissions inchangées ; aucune recherche exhaustive revendiquée |
| Sources historiques exactes de création/assemblage/export P3 | Non établies par la revue documentaire existante ; cause du blob non établie |
| Dossiers locaux à accès refusé signalés dans la recherche antérieure de provenance (`var`, caches de tests) | Aucun contournement ni changement de permissions ; cet audit a utilisé un corpus ciblé accessible, pas un scan intégral de ces arbres |
| Provenance authentifiée de création API H0, journaux opérateur originaux | Non fournis dans les pièces examinées ; récits/labels/empreintes locales ne restituent pas la commande historique |
| Autorisation de transition H0/R1 et ouverture dix signée | Non retrouvée dans les pièces examinées ; plan de réconciliation non exécutoire |
| Approbation formelle S2 globale, C5/B1 et B2–B7 | Non établie ; formulaires, tests locaux et confirmations opératrice restent distincts |
| Recette réelle complète dix avec BFF final/effacement/SMTP et stockage | Non établie ; ancienne recette signup BLOCKED et garde d'effacement strict identifiés |
| Sauvegarde/restauration distante fraîche et repli final compatibles dix | Non prouvés pour l'assemblage cible ; ne pas dévaloriser les round-trips synthétiques existants |
| Approbations juridiques/contrats/régions/rétention effectivement appliquée | Non fournies ; inventaire documentaire seulement, avis juridique nécessaire |
| `frontend\src\pages\Documents.test.tsx` | Chemin recherché absent ; cela ne signifie pas absence de tests Documents ailleurs (P03 en atteste) |

Les déclarations d'absence sont limitées aux sources lues, pas à tous les
supports, sessions ou systèmes possibles. La recherche de fonctions repose
sur sources/routes/tests ciblés ; elle n'est pas une analyse exhaustive de
vulnérabilités ni un certificat de sécurité.

## 6. Contrôles volontairement non exécutés

Ni pytest applicatif, ni npm test/build/install, ni migration SQL, connexion
DB, démarrage/arrêt de service, commande Docker, commande de quota, création
de compte, accès SSH/HTTP/SMTP/Restic, lecture de `.env` réel, import applicatif,
modification de droits ou nettoyage historique.

Ces contrôles exigeraient des mutations ou accès hors périmètre :
**NON VÉRIFIÉ — CONTRÔLE DYNAMIQUE REQUIS**.
Le plan M1–M7 et les scénarios TG01–TG18 constituent les spécifications
distinctes à soumettre à autorisation, pas des opérations déjà accomplies.

## 7. Décision conservatoire et livrables

Sept nouveaux Markdown uniquement : synthèse, matrice, blocages, plan
minimal, lacunes de tests, fiche non signée et présent registre.
Pas de correction silencieuse ; pas de pourcentage d'avancement inventé.
Toutes les décisions sont conditionnées à des preuves applicables à la
release choisie et à l'autorisation humaine distincte.

```text
REVIEW_ONLY_BLOCKED
BETA_10_GO=false
REGISTRATION_OPENING_AUTHORIZED=false
P4_GO=false
P4_FORMAL_B1_CLOSED=false
formal_b1_contents_closed=false
```
