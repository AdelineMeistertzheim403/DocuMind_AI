# Docnelo V5.1 — P4 / B1 — Fiche de revue indépendante

**Version de la fiche :** 1.0 — 5 novembre 2026  
**Statut initial :** `REVIEW_ONLY_BLOCKED`  
**Objet :** examen contradictoire des preuves B1, **sans clôture ni autorisation implicite**.  
**Relecteur habilité :** _à renseigner_  
**Organisation / rôle :** _à renseigner_  
**Date et heure de revue (avec fuseau) :** _à renseigner_  
**Référence de décision / ticket :** _à renseigner_

> Cette fiche est un formulaire préparatoire, non une décision signée. Aucun relecteur indépendant n'a été identifié dans les éléments fournis. Tous les champs de décision demeurent « À instruire ». Ne pas interpréter la préparation ou la copie de cette fiche comme une clôture B1, une approbation C5 ou un GO P4.

## 1. Pièces soumises à la revue

| Pièce | Emplacement / référence | Contrôle connu |
|---|---|---|
| Archive de preuves `b1-evidence.tar` | `qualification/b1-review-20261105/b1-evidence.tar` sur Windows | SHA-256 `49418c8f928de66e82b49c5b9834ae1ce0254245a4092898ca0e5b3d28f971cd` ; transfert SCP et vérification Windows `PASS` |
| Rapport technique consolidé | `DOCNELO_V51_P4_B1_CONSOLIDATED_REVIEW_2026-11-05.md` ; à joindre séparément | Rapport documentaire, non signé ; ne fait pas partie des 33 entrées de l'archive |
| Livraisons exécutables scellées | OCI Comparator v2 ; P3 Layer Contents v1, chacune conservée séparément | Les programmes sources ne sont pas inclus par défaut dans `b1-evidence.tar` ; les rendre accessibles en lecture seule au relecteur si une revue du code est requise |
| Archive P3 et inventaires historiques | Restent sur la VM Debian, aux chemins historiques | Non inclus dans `b1-evidence.tar` ; ne pas altérer ni transférer sans procédure autorisée |

**Archive de transmission :** 33 entrées TAR observées ; SHA-256 vérifié sur Debian et sur Windows. Les 33 entrées sont un total comprenant répertoires et fichiers, pas 33 jeux de preuves. L'archive contient les dossiers OCI v2 et P3 Layer v1, chacun avec `unit-tests/` et `comparison/`.

**Dossier Windows :** `C:\Users\Adeline\Documents\DocuMind_AI\qualification\b1-review-20261105\`.

**Dossier de copie Debian :** `/home/adeline/docnelo-lab/development/v5.1-hardening/review-export-b1-061af0a043ec42478faa86b2e80fa7f3/`.

### Ancres de vérification des quatre jeux de preuves

| Preuve | SHA-256 du fichier `SHA256SUMS` |
|---|---|
| OCI Comparator v2 — `unit-tests` | `80f0435b6d5eddfd724660359c1cfd7ec0ef76aa13ea01484855c370188067ea` |
| OCI Comparator v2 — `comparison` | `da22ccae43b1eb4df9906993015fc666bb454e7bdb0cdcc41ea1ba65d780cd0c` |
| P3 Layer Contents v1 — `unit-tests` | `d44877191c7f0d0043887f9b11a5387685a62aa305ada83dc7bf1adce54bee91` |
| P3 Layer Contents v1 — `comparison` | `832d2272b76f38583fcf060cfb34e43e309cf677ddeadb64d1f143d1a5615ef8` |

Les contrôles `sha256sum --check --strict` ont été rapportés `PASS` pour les quatre jeux, avant création de l'archive. Une empreinte SHA-256 n'est pas une signature et ne démontre pas à elle seule l'origine des preuves. **Canal indépendant de remise et de vérification de l'ancre : _à documenter_.**

## 2. Faits techniques à distinguer des décisions

### A — Identité des contenus réguliers de couche P3

- Environnement d'exécution rapporté : Debian 13.7, Python 3.11.18 approuvé (`-I -B`).
- OCI Comparator v2 : **35 tests réussis**, aucun test ignoré ; comparaison stricte : **code retour 20**, `ERROR`.
- P3 Layer Contents v1 : **46 tests réussis**, aucun échec ni test ignoré.
- Mesure réelle limitée : `A_regular_layer_contents.measurement_complete=true`, `scope_returncode=0`, `regular_contents_equal=true`, `decision=REGULAR_LAYER_CONTENTS_IDENTICAL_ONLY`.
- **9 771 chemins réguliers et contenus SHA-256 concordants** avec les inventaires P3 historiques ancrés ; zéro chemin régulier manquant et zéro différence de contenu rapportés.
- Couverture TAR externe et couche : `all_bytes_accounted=true` dans les deux cas, d'après `report.json`.
- La conclusion A ne démontre **pas** l'identité du rootfs vivant, des métadonnées complètes, ni la sécurité d'exécution.

### B — Conformité stricte de l'archive Docker entière

- Résultat strict inchangé : `status=ERROR`, **code retour 20**, `conformity_granted=false`.
- Blob non rattaché au graphe OCI principal : `blobs/sha256/eec772146db049680bf51af9758854bd4c210bff907cac5d73a10deec0775653`, **829 octets**.
- Son SHA-256 correspond au nom ; sa présence n'est **pas** pour autant approuvée. `reason=OUTSIDE_EXPECTED_PINNED_PRINCIPAL_GRAPH`, `approved=false`.
- La mesure limitée A n'efface pas cette anomalie et ne transforme pas le résultat B en PASS.

### Métadonnées et restrictions

- **10 334 divergences UID/GID**, malgré **0 différence de permissions** et **0 différence de type** rapportées.
- Répertoire racine `.` **absent de la couche** : `metadata_comparison_complete=false` pour la racine ; ce n'est pas un fichier régulier manquant.
- `complete_metadata_equality_established=false` : tailles source, timestamps, xattrs, ACL, capabilities et topologie des liens ne sont pas intégralement attestés par les inventaires historiques.

### C — P4, provenance et décisions formelles

- `qualification_granted=false` ; `provenance_granted=false`.
- `formal_b1_contents_closed=false`.
- `go.c5=false`, `go.p4=false`, `go.runtime=false`, `go.production=false`.
- B2 à B7 restent ouverts, indépendamment du résultat A.

## 3. Questions et décisions à documenter par le relecteur

Pour **chaque point**, renseigner : preuves ouvertes personnellement, méthode, résultat `ACCEPTÉ / REFUSÉ / À COMPLÉTER`, justification, action corrective éventuelle, responsable et échéance. Les propositions ci-dessous sont des objets de revue, **pas** des décisions déjà prises.

| ID | Question / critère de revue | Décision | Justification / référence de preuve | Action, responsable, échéance |
|---|---|---|---|---|
| R01 | Les ancres, les quatre manifestes et les récépissés ont-ils été vérifiés indépendamment, y compris le code shell ? | À instruire | _À renseigner_ | _À renseigner_ |
| R02 | Le périmètre A limité aux **9 771 fichiers réguliers** est-il accepté comme preuve suffisante de leur identité, sans extrapolation aux métadonnées ? | À instruire | _À renseigner_ | _À renseigner_ |
| R03 | Le blob auxiliaire OCI non référencé dispose-t-il d'une justification de format et de provenance suffisante ? Si non, le refus strict code 20 est-il maintenu ? | À instruire | _À renseigner_ | _À renseigner_ |
| R04 | Quel est l'impact des **10 334 écarts UID/GID** sur les règles de sécurité et d'exécution envisagées pour P4 ? | À instruire | _À renseigner_ | _À renseigner_ |
| R05 | Comment traiter l'absence de la racine `.` et les attributs non inventoriés ? Une preuve supplémentaire est-elle nécessaire ? | À instruire | _À renseigner_ | _À renseigner_ |
| R06 | Les transferts **SCP**, dérogatoires au protocole de transfert physique, sont-ils acceptables ? Quelles traces et quel canal indépendant d'ancres sont exigés ? | À instruire | _À renseigner_ | _À renseigner_ |
| R07 | La chaîne de provenance des livraisons, du code et des composants historiques est-elle suffisante ? Signatures, auteurs, origine et approbations sont-ils établis ? | À instruire | _À renseigner_ | _À renseigner_ |
| R08 | Les pièces absentes de l'archive de transmission (sources du contrôleur, archive P3, inventaires, rapport consolidé) doivent-elles être examinées séparément ? | À instruire | _À renseigner_ | _À renseigner_ |
| R09 | Les critères formels propres à B1 et à C5 sont-ils tous satisfaits et la décision est-elle explicitement autorisée ? | À instruire | _À renseigner_ | _À renseigner_ |
| R10 | Quels éléments restent nécessaires pour B2–B7, sans préjuger d'un GO runtime ou production ? | À instruire | _À renseigner_ | _À renseigner_ |

## 4. Procédure de revue recommandée (lecture seule)

1. Conserver l'archive d'origine **inchangée** ; calculer son SHA-256 à réception, comparer à `49418c8f...f971cd` transmis via canal distinct et noter le résultat. Ne pas « réparer » une différence d'empreinte en re-scellant la copie.
2. Lister les chemins TAR et vérifier l'absence de chemins dangereux **avant** toute éventuelle extraction dans un environnement isolé de revue ; l'inspection directe en lecture seule est préférable. Ne jamais extraire vers la racine du projet ou vers les dossiers historiques.
3. Vérifier chaque `SHA256SUMS` dans les quatre jeux de preuves ; lire les `receipt.json`, `report.json`, `stdout`, `stderr` et le code shell `scoped-shell-returncode`.
4. Vérifier séparément le résultat **A=0 / B=20 / C non accordé**, les compteurs des 9 771 contenus, la racine absente et les divergences UID/GID ; confronter au rapport consolidé.
5. Demander les pièces complémentaires et les identités de source non contenues dans l'archive, si nécessaires. Les rendre accessibles seulement par un circuit de transmission approuvé.
6. Enregistrer les avis, objections et références exactes sans modifier les preuves. Une décision de B1 ou C5 exige un acte distinct, explicite et attribué à une personne habilitée.

## 5. Décision formelle — **non renseignée**

**Avis technique sur le périmètre A :** ☐ Accepté (limité aux contenus réguliers) ☐ Refusé ☐ Compléments nécessaires  
**Avis sur le blocage de l'archive entière B :** ☐ Maintien du blocage ☐ Compléments nécessaires ☐ Autre (motiver)  
**État de provenance C :** ☐ Non établie ☐ Compléments nécessaires ☐ Établie avec preuves citées  
**Décision formelle B1 :** **NON PRISE** — _champ réservé à une revue indépendante autorisée_  
**Décision C5 :** **NON PRISE** — _champ réservé à une autorisation distincte_  
**Décision P4 :** **NO-GO (état actuel)**

**Conditions préalables ou réserves :** _À renseigner_  
**Preuves supplémentaires exigées :** _À renseigner_  
**Nom et qualité du décideur habilité :** _À renseigner_  
**Date, référence de décision et signature vérifiable :** _À renseigner_

---

**État conservatoire à la rédaction :** `REVIEW_ONLY_BLOCKED`, B1 non clôturé, B2–B7 ouverts ; **aucun build/create/start/run/pull/import Docker P4, aucun GO runtime ou production**. Cette fiche n'attribue aucune approbation et n'autorise aucune modification des archives, livraisons ou preuves historiques.
