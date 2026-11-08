# Docnelo V5.1 — P4 / B1 — Rapport consolidé de revue technique

**Date :** 5 novembre 2026  
**Classification :** revue hors ligne, preuves historiques en lecture seule  
**Décision générale :** `REVIEW_ONLY_BLOCKED`  
**Clôture formelle B1 :** `false`  
**B2 à B7 :** ouverts  
**P4 Build / Create / Start / Run / Pull / Import / Production :** **NO-GO**  
**C5, runtime, provenance :** non accordés

> Ce document consolide les sorties terminal Debian fournies par l'opératrice et les références documentaires des livraisons. Il n'est ni un certificat signé, ni une revue de provenance indépendante, ni un nouveau rejeu sur la VM. Les empreintes des preuves sont rapportées à partir des sorties Debian ; les dossiers historiques de la VM ne sont pas incorporés au présent fichier.

## 1. Synthèse de décision

| Périmètre | Constat | Décision |
|---|---|---|
| **A — Contenus réguliers de la couche P3** | 9 771 chemins réguliers et SHA-256 identiques aux inventaires authentifiés ; aucune divergence de contenu | `REGULAR_LAYER_CONTENTS_IDENTICAL_ONLY`, `scope_returncode=0`, `measurement_complete=true` |
| **B — Conformité stricte de l'archive Docker entière** | Blob `eec772...` présent, auto-cohérent, mais non rattaché au graphe OCI principal | `ERROR`, `returncode=20`, `conformity_granted=false` |
| **C — Qualification de la base P4 et provenance** | Non démontrées par la mesure A | `qualification_granted=false`, `provenance_granted=false` |
| **Décision générale** | Le CLI limité préserve délibérément l'anomalie B | `REVIEW_ONLY_BLOCKED`, code général `20`, tous GO `false` |

**Point cardinal :** le code général `20` et le code de périmètre A `0` ne sont pas contradictoires. Le premier interdit de conclure à la conformité de l'archive entière ; le second autorise uniquement le constat d'identité des contenus réguliers inventoriés.

## 2. Environnement et chaîne de contrôle

- VM : Debian GNU/Linux 13.7 (`trixie`), Linux amd64.
- Python approuvé : **3.11.18** via `recovery-directory-p1-j5QntXdb/venv-p1/bin/python`, options `-I -B`.
- Mode : analyse hors ligne, archive P3 et inventaires en lecture seule, sans Docker ni extraction de couche.
- Livraison **OCI Comparator v2** : 35 tests synthétiques réussis ; refus historique de l'archive complète `20`.
- Livraison **P3 Layer Regular Contents v1** : 46 tests synthétiques réussis, zéro échec et zéro test ignoré ; comparaison réelle exécutée séparément.
- Livraison v1 transférée par **SCP depuis Windows vers la VM Hyper-V**, en dérogation au protocole prescrivant un support physique ; transfert et provenance ne sont pas qualifiés par ce fait. Les copies ont été contrôlées par SHA-256 sur Debian.

### Ancres des livraisons

| Objet | SHA-256 |
|---|---|
| OCI Comparator v2 — `SHA256SUMS` | `77db188638f19b4b33777b97b5cfe054ef62d38ea9a4525b6f0338fba5cef5df` |
| Noyau strict `comparator.py` v2 et copie v1 | `63225aec80a257a246ca492acbaf1dcc73c66a0c49123ffaffc9ad73ee6c383a` |
| P3 Layer Contents v1 — `SHA256SUMS` | `4c99f2ff46fbfa6854982078018a5f9364eda77e1ba74a2a0b8e3aa29fa1b5d1` |
| Nouveau `layer_contents.py` | `0dca2348e9b8de9ca105e41fa05ed463d01da69ed7b92b8fb4c0e8e0884a4b66` |

Les 13 fichiers de la livraison v1 ont été vérifiés avec `sha256sum --check --strict` après transfert. Le fichier adjacent `.anchors.json` renseigne l'ancre, mais ne constitue pas une signature ; l'indépendance du canal de remise doit rester documentée.

## 3. Entrées historiques et rattachement OCI

**Base VM** : `/home/adeline/docnelo-lab/development/v5.1-hardening`

- Archive : `quarantine-debian-evidence/p4-b1-p3-source-1d8b8a7266fb42e6878d6b70f404ad2e/p3-image-export.tar`.
- Inventaires : `docnelo-p3-python311-fixed-37d04ec892f7464a809d2fdfe69d57b3/ROOTFS-SHA256SUMS` et `ROOTFS-METADATA.txt`.

| Source ancrée | SHA-256 attendu |
|---|---|
| Archive complète | `ffec209c1b5eb3a8861e60585266c18069896adf05c8fe8f98c558d682351c2d` |
| Inventaire régulier `ROOTFS-SHA256SUMS` | `a37f1847df7c7212c2d1b004e5ab3b0d654323a8ab2d425e20d89c551279527f` |
| Inventaire `ROOTFS-METADATA.txt` | `64863f4ebc2aaddb717d83147e623e37942716728736afa40f5bd39d1083db36` |
| Configuration OCI, 835 octets | `bbe90dab376fcd41b3495cad1264c017323ed68ed0915c601ea5fd229cbf6abd` |
| Manifeste OCI, 402 octets | `c4c9b897d2e3dea6bbcc3da95b078ce5ffa556f5e4c52020a40da8be784ccc44` |
| Couche TAR brute, 322 534 912 octets | `7b1b9ae269d164c3b88d386714f2def703acb15812a6d6f813c10064f57c766e` |
| Blob auxiliaire non référencé, 829 octets | `eec772146db049680bf51af9758854bd4c210bff907cac5d73a10deec0775653` |

Le graphe explicite observé est `index.json` → manifeste OCI `c4c9...` → configuration `bbe90...` et couche `7b1b...`. Le fichier Docker `manifest.json` confirme configuration et couche, ainsi que `LayerSources`. La SHA-256 du manifeste OCI a également été recalculée directement sur les octets du blob historique via `tar -xOf ... | sha256sum` : sortie conforme, `MANIFEST_HASH_EXIT=0`. **Le blob `eec772...` n'est pas justifié par une référence de ce graphe.** Son empreinte correspond à son nom, mais cela n'établit ni son rattachement, ni sa provenance, ni son approbation.

## 4. Exécutions et preuves vérifiées

| Exécution | Résultat | SHA-256 du `SHA256SUMS` des preuves |
|---|---|---|
| Tests OCI Comparator v2 | 35/35, `returncode=0`, `complete=true` | `80f0435b6d5eddfd724660359c1cfd7ec0ef76aa13ea01484855c370188067ea` |
| Contrôle strict OCI v2 sur archive P3 | `returncode=20`, `status=ERROR`, `complete=true`, blob non rattaché | `da22ccae43b1eb4df9906993015fc666bb454e7bdb0cdcc41ea1ba65d780cd0c` |
| Tests P3 Layer Contents v1 | 46/46, `returncode=0`, `complete=true`, zéro ignore | `d44877191c7f0d0043887f9b11a5387685a62aa305ada83dc7bf1adce54bee91` |
| Mesure P3 Layer Contents v1 | `returncode général=20`, `complete=true` ; périmètre A réussi | `832d2272b76f38583fcf060cfb34e43e309cf677ddeadb64d1f143d1a5615ef8` |

**Dossier de preuves de la dernière mesure** :

`quarantine-debian-evidence/p4-b1-p3-layer-v1-1f1304c0ce3246b9b64ebd851dbeb442/`

- `unit-tests/` : `started.json`, `stdout`, `stderr`, `receipt.json`, `SHA256SUMS`, `evidence-anchor.json`.
- `comparison/` : `started.json`, `report.json`, `stdout`, `stderr`, `receipt.json`, `SHA256SUMS`, `evidence-anchor.json`.
- `scoped-shell-returncode` : `20`.

Les vérifications `sha256sum --check --strict SHA256SUMS` des deux jeux de preuves ont été rapportées comme réussies. Le dernier contrôle de cohérence en terminal a affiché `P3_LAYER_FINAL_REVIEW=PASS`, `A_CONTENTS=IDENTICAL_ONLY`, `B_ARCHIVE=BLOCKED_20`, `C_P4=NOT_GRANTED`, `FORMAL_B1_CLOSED=False`. Le collage de ce dernier script présente des caractères mélangés ; l'appui principal des constats reste le rapport JSON, le récépissé et les contrôles d'intégrité précédents, et non le texte recollé comme source exécutable exacte.

## 5. Résultats détaillés de la mesure réelle P3

### Périmètre A — identité des contenus réguliers

- `measurement_complete=true`
- `expected_regular_paths=9771`
- `regular_contents_equal=true`
- `scope_returncode=0`
- `decision=REGULAR_LAYER_CONTENTS_IDENTICAL_ONLY`
- `complete_metadata_equality_established=false`

### Différences et couverture publiées

| Indicateur `comparison.difference_counts` | Valeur |
|---|---:|
| `content` | 0 |
| `missing_regular` | 0 |
| `extra_entries` | 0 |
| `type` | 0 |
| `permissions` | 0 |
| `links` | 0 |
| `missing_nonroot_directories` | 0 |
| `uid_gid` | **10 334** |

- `comparison.root_directory.absent_from_layer=true` : l'en-tête de répertoire racine `.` manque dans la couche ; il ne s'agit pas d'un fichier régulier manquant.
- `comparison.root_directory.metadata_comparison_complete=false`.
- `outer_coverage.all_bytes_accounted=true`, neuf entrées logiques/physiques externes, `trailer_bytes=1024`.
- `layer_coverage.all_bytes_accounted=true`, **10 334** entrées logiques/physiques de couche, `trailer_bytes=1024`.
- Aucune extension TAR indiquée par les deux objets `extension_headers` du rapport.

**Limites** : les inventaires sources ne démontrent pas l'identité des tailles source, timestamps, xattrs, ACL, capabilities, topologie des liens physiques, ni l'identité des métadonnées de la racine absente. Le rootfs vivant n'a pas été relu. Les 10 334 divergences de propriétaire UID/GID restent explicites ; l'égalité des contenus ne les neutralise pas.

### Périmètre B — archive complète

- `decision=BLOCKED`, `status=ERROR`, `returncode=20`, `conformity_granted=false`.
- Blob `blobs/sha256/eec772146db049680bf51af9758854bd4c210bff907cac5d73a10deec0775653` : `OUTSIDE_EXPECTED_PINNED_PRINCIPAL_GRAPH`, `approved=false`, `used_to_identify_layer=false`, `digest_matches_blob_name=true`.
- Le contrôle sur l'inventaire externe complet réutilise le noyau strict v2 et reproduit le refus `Unclaimed outer regular entries`, **sans constituer un nouveau récépissé CLI historique v2**.

### Périmètre C — base P4 et provenance

- `qualification_granted=false`.
- `provenance_granted=false`.
- `formal_b1_contents_closed=false`.
- `go.c5`, `go.p4`, `go.production`, `go.runtime` : tous `false`.

## 6. Réserves et points ouverts

1. **Blob auxiliaire non rattaché** : aucune levée du refus strict, aucune règle générique autorisant des blobs supplémentaires. Sa nature Docker-compatible n'établit pas la conformité de l'archive.
2. **Écarts UID/GID** : 10 334 différences doivent rester évaluées au regard des exigences de sécurité du futur environnement ; aucune équivalence de métadonnées ne peut être déclarée.
3. **Racine `.` absente** : métadonnées de ce répertoire non mesurées dans la couche.
4. **Provenance et approbation** : pas de signature cryptographique de livraison ni de décision indépendante C5 ; les ancres externes doivent être vérifiées par un canal de confiance distinct. Le transfert SCP constitue une dérogation au protocole physique prescrit.
5. **Portée des preuves** : les SHA-256 prouvent l'intégrité relative aux ancres, pas à elles seules l'origine ou la sûreté du code ; les tests synthétiques ne qualifient pas P4 en exploitation.
6. **Autres barrières P4** : B2–B7 ouverts ; aucune conclusion sur les qualifications runtime, ABI, hardening complet, déploiement ou production.

## 7. Conditions proposées pour la revue indépendante — sans GO implicite

- Conserver **sans remplacement** l'archive P3, les inventaires, les livraisons v2 et v1, les dossiers de preuves et leurs fichiers d'ancres.
- Archiver les nouvelles preuves hors VM selon une procédure autorisée, avec remise indépendante des empreintes de `unit-tests/SHA256SUMS` et `comparison/SHA256SUMS` ; ne pas déclarer l'archivage accompli avant retour vérifié.
- Faire relire par un responsable autorisé le rapport JSON intégral, les compteurs, la chaîne d'ancres, les restrictions des outils et la dérogation SCP.
- Traiter explicitement le statut du blob auxiliaire et les différences de métadonnées sans transformer la conclusion A en conformité B.
- Préparer une décision C5 séparée et explicite seulement lorsque les exigences formelles de B1 sont satisfaites ; poursuivre B2–B7 selon leurs propres critères et autorisations.

## 8. Décision finale du présent rapport

```json
{
  "decision": "REVIEW_ONLY_BLOCKED",
  "A_regular_layer_contents": "REGULAR_LAYER_CONTENTS_IDENTICAL_ONLY",
  "A_scope_returncode": 0,
  "A_measurement_complete": true,
  "B_strict_whole_archive": "ERROR",
  "B_returncode": 20,
  "C_p4_and_provenance": "NOT_GRANTED",
  "general_returncode": 20,
  "formal_b1_contents_closed": false,
  "go": {
    "c5": false,
    "p4": false,
    "runtime": false,
    "production": false
  }
}
```

**Conclusion :** le contrôle indépendant et reproductible atteste l'identité des **9 771 contenus réguliers** de la couche historique P3 par rapport aux inventaires ancrés. Il **n'atteste pas** l'identité complète des métadonnées, la conformité stricte de l'archive Docker entière, la provenance ni l'autorisation de P4. Le dossier reste **REVIEW_ONLY_BLOCKED**.
