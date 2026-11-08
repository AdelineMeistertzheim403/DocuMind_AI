# Matrice de préparation — A à J

**Décision : NO-GO.** Chaque ligne reçoit un seul statut. `VALIDÉ` signifie
uniquement que le contrôle **délimité dans la ligne** dispose d'une preuve
pertinente ; cela ne valide pas son déploiement. Les dates sont celles des
preuves ou du dossier d'audit, jamais des dates de déploiement déduites.

## Lecture des références

Les chemins courts ci-dessous sont relatifs à la racine du dépôt.
`C\` désigne exactement
`deliveries\docnelo-lifecycle-10-api\source\`.
`R2\` désigne exactement
`deliveries\docnelo-web-branding-r2\payload\`.
Ces préfixes ne désignent pas le workspace courant.

| Preuve | Fichier et périmètre | Date |
|---|---|---|
| P01 | `DOCNELO_PUBLIC_BETA_10_USERS_LIFECYCLE_TEST_REPORT.md:1-71` ; logs candidats `pytest.log:82`, `bff-tests.log:364-371`, `operator-tests.log:1-4` sous `deliveries\docnelo-lifecycle-10-api` ; 227 + 50 + 11, non rejoués | 31/10/2026 |
| P02 | `deliveries\docnelo-lifecycle-10-api\roundtrip-result.json:1-19`, `deliveries\docnelo-lifecycle-10-api\source-release.json:1-67`, `deliveries\docnelo-lifecycle-10-api\image-proof.json:1-75`, `deliveries\docnelo-lifecycle-10-api\test-runtime-parity.json:1-13` ; copies synthétiques et identité de candidate | 31/10/2026 |
| P03 | `R2\DOCNELO_PUBLIC_BETA_BRANDING_R2_TEST_REPORT.md:1-76` ; 134 tests rapportés, navigateur avec API simulée, 404 téléchargement constaté | 31/10/2026 |
| P04 | `DOCNELO_SIGNUP_E2E_LAB_TEST_REPORT.md` et `deliveries\docnelo-signup-e2e-lab\test-results.json:1-110` ; contrôles de refus, verdict BLOCKED, pas de signup réussi | 31/10/2026 |
| P05 | `DOCNELO_API_DEPLOYMENT_PROVENANCE_20261031_REPORT.md:1-75,112-162,199-240` et `DOCNELO_API_CONTROLLED_RECONCILIATION_PLAN.md:1-91` ; H0 non authentifié, R1 non créée | 01/11/2026 |
| P06 | `DOCNELO_V51_BACKUP_RESTORE_HARDENING_REPORT.md:1-208` ; développement, 167 réussites/13 ignorés sous Windows, pas de GO Linux/S2 | 01/11/2026 |
| P07 | `DOCNELO_V51_QUARANTINE_FUNCTIONAL_TEST_REPORT.md:1-100`, `DOCNELO_V51_RESTORED_LATCH_FASTAPI_QUALIFICATION.md:1-163`, `DOCNELO_V51_RECOVERY_DIRECTORY_R3_REPORT.md:1-71` ; scopes in-process/préparation séparés | 01–02/11/2026 et r3 sans date explicite |
| P08 | `DOCNELO_PUBLIC_BETA_10_USERS_LEGAL_READINESS.md:1-51` ; inventaire documentaire, NON APPROUVÉ | 31/10/2026 |
| P09 | `DOCNELO_PUBLIC_BETA_10_USERS_OPENING_RUNBOOK.md:1-135` ; procédure préparatoire, pas un journal exécuté | 31/10/2026 |
| P10 | `qualification\b1-review-20261105\b1-evidence.tar`, quatre manifestes internes vérifiés ; `qualification\b1-review-20261105\B1_INDEPENDENT_REVIEW.md:1-109` ; rapport consolidé `DOCNELO_V51_P4_B1_CONSOLIDATED_REVIEW_2026-11-05.md:1-120` | 05/11/2026 |
| P11 | `docs\PHASE_15_4_LOT_2_19_FULL_RECOVERY_TEST_RESULTS.md:1-38`, `docs\PHASE_15_4_LOT_2_18_S2_RECOVERY_RUNBOOK.md:1-69` ; tests synthétiques et plan non autorisé | Date non explicitée |
| P12 | `docs\sprint-8-monitoring.md:1-145`, `tests\test_monitoring.py:25-356`, `tests\test_security_audit.py:39-236` ; outillage/tests existants, installation bêta actuelle non attestée | Date non explicitée |

**I/T/E/Q/V** sont cinq niveaux distincts : implémentation, test existant,
exécution réussie rapportée, qualification formelle, état VPS observé.
P01/P02 établissent I/T/E sur la candidate et un avis technique local fermé,
pas Q d'ouverture ou V. Les tests seulement lus établissent T, pas E.
Les contrôles locaux SHA de cet audit sont décrits dans `AUDIT_TRACEABILITY.md`.

## A — Architecture et déploiement

| ID | Contrôle | Statut | Criticité | Source et lignes | Rapport/test | Date preuve | Validité pour la cible | Manque | Action minimale |
|---|---|---|---|---|---|---|---|---|---|
| A01 | Frontend BFF/API/PostgreSQL/volumes | PARTIEL | élevé | `compose.public-beta.vps.yaml:9-31,227-362` | P05/P09 | 31/10–01/11/2026 | Topologie locale ; pas runtime VPS | Relevé réel et capacité mesurée | Attester services/réseaux/volumes et marge pour dix |
| A02 | Images, dépendances et version de release | PARTIEL | élevé | `Dockerfile:1-34`, `frontend\Dockerfile:1-19`, `pyproject.toml:5-18`, `C\backend\lifecycle_capacity.py:11-12` | P02 ; manifeste API release | 31/10/2026 | Candidate figée ; workspace divergent | Identité du déploiement et sélection des deltas | Figer une release exacte, conserver locks/hashes et inventaire runtime |
| A03 | Provenance de création et chaîne Compose | BLOQUANT | élevé | `DOCNELO_API_DEPLOYMENT_PROVENANCE_20261031_REPORT.md:5-46,199-230` | P05 | 01/11/2026 | H0 historique uniquement | Chaîne authentifiée et voie autorisée malgré refus du garde | Collecte fraîche puis revue de politique ; aucun skip/allowlist |
| A04 | Variables et paramètres sûrs | PARTIEL | élevé | `backend\config.py:15-39,131-153`, `compose.public-beta.vps.yaml:227-257` | P01/P09 ; tests d'autorisation | 31/10/2026 | Config déclarative ; pas paramètres servis | Profil standard, flag opérationnel candidat, namespace, overrides effectifs | Vérifier allowlist expurgée et cohérence sans appliquer public/10 |
| A05 | Reverse proxy, HTTPS, cookies et accès directs | NON VÉRIFIÉ | critique | `compose.public-beta.vps.yaml:283-334`, `frontend\server\app.mjs:140-153,184-207`, `backend\gateway.py:6-24` | P03 ; `frontend\server\app.test.mjs:273-283,416-437` | 31/10/2026 | Tests locaux seulement | Certificat, proxy de confiance, ports/API/DB non exposés sur cible | Contrôle opérateur réseau/TLS sans insecure |
| A06 | Isolation, secrets, persistance | PARTIEL | élevé | `compose.public-beta.vps.yaml:16-20,258-281,335-362`, `Dockerfile:21-32` | P05/P09 | 31/10–01/11/2026 | Conception ; secrets non lus | Droits effectifs, sauvegarde des clés, absence de fuite et mounts réels | Relevé privé de droits/montages sans valeurs secrètes |
| A07 | Santé, ressources et déploiement/rollback | PARTIEL | élevé | `compose.public-beta.vps.yaml:21-31,263-281,335-350`, `P09` | P02/P09 | 31/10/2026 | Limites source, pas charge qualifiée | RAM/disque/inodes, marge capture, repli compatible 6..10 | Mesure ciblée et exercice de repli fermé ; aucune mutation ici |

## B — Authentification et comptes

| ID | Contrôle | Statut | Criticité | Source et lignes | Rapport/test | Date preuve | Validité pour la cible | Manque | Action minimale |
|---|---|---|---|---|---|---|---|---|---|
| B01 | Hachage/connexion et rejet compte non vérifié | VALIDÉ | élevé | `backend\auth.py:40-75`, `backend\ai\settings_api.py:47-68`, `backend\authentication.py:10-29` | P01 ; `C\tests\test_public_beta_capacity_ten.py:77-99`, `tests\test_accounts_saas.py:48-80` | 31/10/2026 | Contrat candidat testé ; pas validation VPS | Rattachement à release déployable | Réutiliser tests puis preuve d'intégration cible |
| B02 | Sessions, expiration, logout et révocation | VALIDÉ | élevé | `backend\auth.py:92-152`, `backend\account_api.py:274-308`, `backend\ai\settings_api.py:71-75` | P01 ; `tests\test_accounts_saas.py:81-98` | 31/10/2026 | Mono-processus ; sessions RAM assumées | Restart/proxy réels | Recette ciblée expiration/logout/reset sur assemblage retenu |
| B03 | Reset, jetons à usage unique et non-énumération | PARTIEL | élevé | `backend\account_api.py:73-89,229-266` | P01/P04 ; `tests\test_accounts_saas.py:61-80` | 31/10/2026 | API testée ; e-mail réel non prouvé | Chaîne BFF/SMTP/boîte et récupération complète | E2E isolé puis délivrabilité autorisée |
| B04 | Approbation administrative préalable | BLOQUANT | élevé | `backend\public_registration.py:111-119,165-186`, `backend\account_admin.py:60-77`, `frontend\src\pages\Account.tsx:40-59,73-74` | P01 : vérification e-mail ; `tests\test_public_beta_state.py:121-156` : block/release, pas approbation obligatoire | 31/10/2026 | Standard public ; Beta Lite distinct à cinq | État/verrou d'approbation standard et preuve impossible d'accès avant accord | Décision explicite de règle ; si exigence maintenue, delta code/tests dédié |
| B05 | Autorisations API et séparation opérateur/utilisateur | PARTIEL | critique | `backend\authentication.py:10-43`, `backend\account_api.py:92-98`, `backend\account_admin.py:197-205` | P01/P07 ; aucune route admin enregistrée dans P07 | 31/10–02/11/2026 | Owner et CLI, pas modèle de rôles admin web inventé | Frontière opérateur réelle et tests cible | Vérifier privilèges hôte/CLI et impossibilité d'administration utilisateur |
| B06 | Limitation d'abus et CSRF | PARTIEL | élevé | `backend\public_registration.py:24-53,86-96`, `backend\auth.py:141-152`, `frontend\server\app.mjs:194-207` | P01/P03 ; `tests\test_public_beta.py:131-173,327-350` | 31/10/2026 | Limiteurs/challenges RAM et un worker | IP effectives, NAT commun, restart et charge réaliste | Recette ciblée sans retirer les limites ; ne pas prétendre anti-abus distribué |
| B07 | Audit des événements sensibles | PARTIEL | élevé | `backend\security_audit.py:14-32,126-127`, `frontend\server\app.mjs:99-132` | P11/P12 ; `tests\test_security_audit.py:39-236` | Date non explicitée | Implémentation/tests ; déploiement inconnu | Collecte effective, rétention, alertes sans PII | Vérifier réception et accès privés aux journaux |

## C — Dix admissions et fermeture

| ID | Contrôle | Statut | Criticité | Source et lignes | Rapport/test | Date preuve | Validité pour la cible | Manque | Action minimale |
|---|---|---|---|---|---|---|---|---|---|
| C01 | Schéma SQL et cumul non recyclé | VALIDÉ | élevé | `migrations\versions\0007_public_beta.py:10-29`, `backend\public_registration.py:59-65` | P01 ; `tests\test_public_beta.py:319-385` | 31/10/2026 | SQL additif ; état 0007 VPS rapporté, non relu | Constat SQL frais | Lire schéma/quota sans relancer migration ni reset |
| C02 | Capacité durable dix et refus onzième | VALIDÉ | critique | `C\backend\lifecycle_capacity.py:11-12,47-59`, `C\tests\test_public_beta_capacity_ten.py:77-99` | P01/P02, source scellée vérifiée | 31/10/2026 | Candidate 8b11 uniquement | Applicabilité au futur déploiement | Conserver recette ; contrôler identité/paramètres à l'intégration |
| C03 | Concurrence dernière place | VALIDÉ | critique | `C\tests\test_public_beta_capacity_ten.py:102-117`, `backend\public_registration.py:59-65` | P01 ; deux connexions PG distinctes | 31/10/2026 | Deux APIs candidates, pas le seul sémaphore RAM | Assemblage final inchangé ou delta contrôlé | Réutiliser preuve ; rejouer si protocole/concurrence modifié |
| C04 | Échec SQL, commit incertain et refus pending | VALIDÉ | critique | `C\tests\test_public_beta_capacity_ten.py:120-138` | P01, deux cas avant/après commit | 31/10/2026 | Candidate durable ; SQL peut rester à 0 ou 1 | Procédure humaine de réconciliation/fraîcheur | Ne pas relancer admission ni recycler pending ; qualifier procédure |
| C05 | Migration des témoins et administration dix | VALIDÉ | élevé | `C\backend\lifecycle_capacity.py:62-135`, `C\backend\account_admin.py:23-70` | P01 ; `C\tests\test_public_beta_capacity_failures.py:26-63` | 31/10/2026 | Migration SQLite dédiée ; pas migration Alembic supplémentaire | Autorisation/état réel et outillage compatible | Réutiliser paquet scellé ; préparation fermée distincte, pas ici |
| C06 | Fermeture, reopen explicite et compteur conservé | VALIDÉ | critique | `C\backend\account_admin.py:23-70`, `C\tests\test_public_beta_capacity_ten.py:88-99,120-138` | P01 ; `tests\test_public_beta_postgresql_concurrency.py:212-299` | 31/10/2026 | Dix nominal testé ; courses fermeture historiques à cinq | Course fermeture à la borne dix et exercice opérateur | Recette ciblée dix ; full n'est pas closed=true automatique |
| C07 | Workspace / ancienne release bornés cinq | BLOQUANT | élevé | `backend\lifecycle_durability.py:61,83-111,221-225`, `backend\lifecycle_admissions.py:167-172`, `backend\account_admin.py:32-39`, `tools\public_beta_policy.py:20` | P01/P05 ; comparaison avec C02/C05 | 05/11/2026, lecture statique | Ne vaut pas défaut de la candidate déjà corrigée | Release choisie et promotion sûre | Ne pas ouvrir root/ancienne API par simple public/10 ; réutiliser candidate |
| C08 | Cohorte dix personnes vs dix admissions publiques | PARTIEL | élevé | `backend\account_api.py:162-195`, `backend\public_registration.py:111-125` | P09 ; `tests\test_public_beta_state.py:55-88` | 31/10/2026 | Invités/historiques hors compteur public | Inventaire agrégé et règle des comptes existants | Fixer cohorte et accès autorisés ; COUNT(users) ne remplace pas issued_count |
| C09 | UI/backend/flags et e-mail bout en bout | BLOQUANT | élevé | `frontend\src\pages\Account.tsx:29-59,72-78`, `backend\config.py:131-153` | P03/P04/P09 | 31/10/2026 | UI cinq ; candidate strict non synthétique distincte | E2E réussi du même assemblage et textes dix | Qualifier parcours complet, sans activer synthétique ou désactiver durabilité |

## D — Documents et confidentialité

| ID | Contrôle | Statut | Criticité | Source et lignes | Rapport/test | Date preuve | Validité pour la cible | Manque | Action minimale |
|---|---|---|---|---|---|---|---|---|---|
| D01 | Upload PDF/TXT, taille, extraction confinée | PARTIEL | critique | `backend\services\documents.py:148-198`, `backend\services\extraction.py:25-30,85-115`, `backend\api.py:49-65` | P01 ; `tests\test_documents.py:58-105` et tests upload/extraction | 31/10/2026 | Tests candidat ; sandbox effectif VPS inconnu | Confinement Linux et garde de startup sur image finale | Recette d'extraction bornée sur image exacte, échec fermé obligatoire |
| D02 | Chemins opaques et source intègre | VALIDÉ | élevé | `backend\services\documents.py:35-61,149-181` | P01 ; `tests\test_documents.py:122-177` | 31/10/2026 | Code documents identique entre workspace et candidate | Montage/droits cible | Conserver protections et vérifier volumes non servis publiquement |
| D03 | Isolation des comptes sur toutes les routes | PARTIEL | critique | `backend\services\documents.py:20-32`, `backend\api.py:69-90,110-132`, `backend\authentication.py:10-29` | P01 ; `tests\test_documents.py:108-120`, `tests\test_accounts_saas.py:99-111` | 31/10/2026 | API testée ; ensemble BFF/stockage cible non qualifié | Deux comptes via HTTPS, IDs étrangers, accès direct statique | Recette positive/négative sur assemblage exact ; tout accès étranger bloque |
| D04 | Téléchargement authentifié de bout en bout | BLOQUANT | élevé | `backend\api.py:88-107`, `frontend\server\app.mjs:297-323` | P03: section contrats, 404 référence/R2 ; `frontend\server\app.test.mjs:213-257` existe dans workspace | 31/10/2026 + lecture 05/11 | Backend existe ; Web R2 livré défaillant ; correctif local non assimilé à R2 | Delta Web scellé et E2E réussi | Qualifier correctif existant, session/propriétaire/octet/headers et négatifs |
| D05 | Suppression documentaire en profil durable réel | BLOQUANT | élevé | `backend\services\documents.py:261-274`, `C\backend\lifecycle_durability.py:255-259` | P01 inclut des régressions sous autres fixtures ; preuve statique du refus strict | 05/11/2026 | Même garde dans candidate ; operational admissions ne lève pas ce refus | Protocole opérationnel autorisé, confirmation et anti-résurrection | Lot minimal d'effacement revu/testé ou périmètre restreint explicitement approuvé avec recours éprouvé |
| D06 | Demande/suppression compte et recours RGPD | BLOQUANT | élevé | `backend\account_api.py:311-355`, `backend\account_admin.py:80-86,135-169`, `C\backend\account_admin.py:153-155,185-187` | P08/P11 ; `tests\test_accounts_saas.py:112-129` n'établit pas le profil strict | 05/11/2026 | Standard strict : refus, pas purge autorisée | Canal effectif, reçu, délais, traitement et restauration sans résurrection | Qualifier traitement des droits ; aucun flag synthétique ni purge improvisée |
| D07 | Erreurs, commit incertain et conservation privée | PARTIEL | élevé | `backend\services\documents.py:214-259`, `backend\api.py:93-107` | `tests\test_document_integrity.py:72-159,194-230,262-315` ; P11 | Date non explicitée | T présent ; pas toute cette suite prouvée pour la release finale | Fault cases sur delta retenu et confidentialité des erreurs | Recette ciblée et préservation des sources incertaines |

## E — Sauvegarde et restauration

| ID | Contrôle | Statut | Criticité | Source et lignes | Rapport/test | Date preuve | Validité pour la cible | Manque | Action minimale |
|---|---|---|---|---|---|---|---|---|---|
| E01 | Dump PostgreSQL restauré et persistance dix | VALIDÉ | élevé | `C\tests\capacity_roundtrip.py:75-123` | P02 : vrai pg_dump/restore, trois processus, stale=0/restored=10 | 31/10/2026 | Synthétique ; pas sauvegarde complète de la bêta active | Lien snapshot/release/chaîne réelle | Réutiliser ce round-trip ; ne pas le présenter comme restauration VPS |
| E02 | Capture cohérente DB/documents/cinq SQLite/deux clés | PARTIEL | critique | `DOCNELO_PUBLIC_BETA_BACKUP_RESTORE_COMPATIBILITY_AUDIT.md:227-271`, `ops\public_beta\VPS_BACKUP_RESTORE_RUNBOOK.md:1-34` | P06/P11 ; P02 ne couvre pas toute l'orchestration réelle | 01/11/2026 | Quiescence prévue, frontière opérateur explicite | Preuve intégrée de tous les éléments et overrides, intégrité avant/après | Un exercice complet isolé avec manifeste et ID exact |
| E03 | Fermeture du quota restauré, échecs et quarantaine | PARTIEL | critique | `tools\validate_restore.py:35-74,284-307,344-370,447-458` | P06 ; tests `test_restore_hardening.py`, P07 | 01–02/11/2026 | Corrigé en développement, pas ancien bundle V5.1 | Validation Linux/PG effective du parcours retenu | Qualifier correctif déjà écrit ; ne pas re-signaler « sealer jamais appelé » pour le workspace |
| E04 | HMAC, fraîcheur externe et non-résurrection | BLOQUANT | critique | `docs\PHASE_15_4_LOT_2_18_S2_RECOVERY_RUNBOOK.md:7-15,37-61`, `tools\validate_restore.py:427-456` | P01/P02/P11 | 31/10/2026 ; runbook sans date | Stale test réussi, pas autorité survivante réelle | Preuve indépendante au domaine restauré et réconciliation | Établir source de fraîcheur/receipts/holds et revue indépendante |
| E05 | Restic distant et récupération de l'ID exact | NON VÉRIFIÉ | élevé | `ops\public_beta\VPS_BACKUP_RESTORE_RUNBOOK.md:24-34`, `DOCNELO_PUBLIC_BETA_BACKUP_RESTORE_COMPATIBILITY_AUDIT.md:199-209` | P09/P12 ; constats anciens communiqués | 31/10–01/11/2026 | Présence remote_verified ≠ restore ; ancien /srv ≠ bêta /opt | Backup bêta frais récupéré et vérifié hors VPS | Exercice distinct autorisé ; aucun accès réseau ici |
| E06 | Outillage compatible dix et rollback fermé | PARTIEL | critique | `C\tests\test_public_beta_capacity_backup.py:28-70`, `DOCNELO_PUBLIC_BETA_10_USERS_API_RELEASE_MANIFEST.md:26-46` | P01/P02/P09 | 31/10/2026 | tooling5.2 structure testé ; V5.1 refuse l'extension | Chaîne complète et repli final à compteur 6..10 | Qualifier ensemble choisi ; aucun retour automatique à image cinq |
| E07 | Échec backup, durée, reprise et rétention | PARTIEL | élevé | `ops\public_beta\VPS_BACKUP_RESTORE_RUNBOOK.md:24-44`, `tools\retention_production.py:1,72-80` | P06/P12 ; tests backups/retention existants | Date non explicitée | Outils/procédures ; rétention réelle non attestée | Exercice interruption/disque/SMTP et politique exécutée | Mesurer temps/arrêts, garder preuves, vérifier rétention sans purger |

## F — S2 et P4

| ID | Contrôle | Statut | Criticité | Source et lignes | Rapport/test | Date preuve | Validité pour la cible | Manque | Action minimale |
|---|---|---|---|---|---|---|---|---|---|
| F01 | Cahier S2, garde applicative et autorisation | PARTIEL | critique | `docs\PHASE_15_4_LOT_2_18_S2_RECOVERY_RUNBOOK.md:1-69`, `docs\PHASE_15_4_LOT_2_19_S2_APPLICATION_GUARDS.md:1-31` | P07/P11 ; plans non autorisés | 01–02/11/2026 et documents sans date | Tests locaux bornés, pas validation formelle globale | Reprise complète, fraîcheur, acteurs et approbation | Recette E02–E06 puis revue S2 applicable à la filière choisie |
| F02 | Identité des 9 771 contenus P3 (A seulement) | VALIDÉ | moyen | `DOCNELO_V51_P4_B1_CONSOLIDATED_REVIEW_2026-11-05.md:13-29,85-120` | P10, SHA externes et 18 entrées internes vérifiées ici | 05/11/2026 | Couche/inventaires historiques, pas rootfs vivant ou runtime | Revue humaine de son emploi, pas nouveau comptage | Conserver cette mesure et ses limites |
| F03 | Archive OCI entière, métadonnées et C5 | BLOQUANT | élevé | `qualification\b1-review-20261105\B1_INDEPENDENT_REVIEW.md:39-109` | P10 ; ERROR/20, UID/GID 10 334, racine absente, fiche non signée | 05/11/2026 | P4/B1 uniquement | Rattachement/provenance du blob, revue métadonnées, C5 autorisé | Maintenir refus ; aucun PASS déduit de A |
| F04 | Barrières P4 B2–B7 | BLOQUANT | critique | `qualification\p4_base_runtime_v3\P4_BASE_RUNTIME_REPORT.md:56-119` | Rapport P4 et P10 | Date non explicitée ; état consolidé 05/11 | Obligatoires si déploiement P4 retenu | Fournisseurs exacts, Python, ABI, exécution, équivalence et approbations | Qualification propre à chaque barrière ; aucun build autorisé ici |
| F05 | Dépendance bêta ↔ P4 et filière existante distincte | PARTIEL | élevé | `Dockerfile:1,16`, `DOCNELO_PUBLIC_BETA_10_USERS_API_RELEASE_MANIFEST.md:7-30`, `qualification\p4_base_runtime_v3\P4_BASE_RUNTIME_REPORT.md:56-66` | P02/P05/P09 | 31/10–05/11/2026 | Deux filières techniques identifiables, aucune ouverture autorisée | Décision écrite de périmètre et applicabilité des gardes | Choisir distinctement ; jamais déclarer P4 validé/non applicable globalement |

## G — Parcours disponibles

Les qualificatifs de parcours ne remplacent pas le statut unique de contrôle.

| ID | Contrôle / état du parcours | Statut | Criticité | Source et lignes | Rapport/test | Date preuve | Validité pour la cible | Manque | Action minimale |
|---|---|---|---|---|---|---|---|---|---|
| G01 | Inscription/vérification/connexion : implémenté, API testée, E2E partiel | PARTIEL | élevé | `backend\public_registration.py:68-186`, `frontend\src\pages\Account.tsx:20-66` | P01/P04 | 31/10/2026 | Candidate vs ancienne image E2E en refus | Assemblage navigateur/SMTP candidat réussi | Recette TG01 du document de lacunes |
| G02 | Approbation : non démontrée en standard | BLOQUANT | élevé | B04, mêmes sources | P01/P04 ; pas de test d'accord préalable standard retrouvé | 05/11/2026 | Beta Lite ne qualifie pas standard dix | Règle et mécanisme | Traiter B04, sans créer deux blocages indépendants |
| G03 | Tableau de bord/liste/consultation : implémenté, tests UI simulés/API | PARTIEL | moyen | `frontend\src\pages\Dashboard.tsx:9-30`, `frontend\src\pages\Documents.tsx:9-29`, `backend\api.py:69-85` | P01/P03 | 31/10/2026 | Pas navigation réelle avec comptes sur assemblage final | Preuve navigateur authentifiée | Recette ciblée deux comptes et pagination |
| G04 | Import : implémenté et testé API | PARTIEL | élevé | `backend\api.py:41-65`, `backend\services\documents.py:148-198` | P01 et D01 | 31/10/2026 | Confinement final non vérifié | Intégration de l'upload au Web cible | Recette positive/négative PDF/TXT et refus sans session |
| G05 | Téléchargement/suppression : défaillant sur périmètres D04/D05 | BLOQUANT | élevé | D04–D06, mêmes sources | P03/P01, garde statique | 31/10–05/11/2026 | API download existe, BFF R2 404 ; suppression stricte refusée | Deltas qualifiés | Traiter D04–D06, sans recompter leur priorité |
| G06 | Recherche/organisation locale : partiellement testée | PARTIEL | faible | `frontend\src\pages\Documents.tsx:10-28`, `backend\api.py:69-80` | P03 : vues Documents | 31/10/2026 | Recherche nom/format sur page chargée seulement | Recette et information du périmètre | Vérifier pagination/texte ; ne pas promettre recherche globale ou dossiers |
| G07 | Recherche sémantique et IA | NON APPLICABLE | faible | `backend\config.py:81`, `compose.public-beta.vps.yaml:240-242`, `frontend\src\pages\Account.tsx:75` | P09 cible IA=false | 31/10/2026 | Exclusion de la bêta initiale, pas absence de code | Preuve effective des flags | Vérifier refus propre et absence d'appel fournisseur |
| G08 | Profil/mot de passe/sessions/demande compte : partiellement testé | PARTIEL | élevé | `backend\account_api.py:269-355`, `tests\test_accounts_saas.py:81-129` | P01/P03 ; D06 limite l'effacement | 31/10/2026 | Pas édition arbitraire identité/email prévue par ces routes | Recette et canal d'exercice des droits | Tester uniquement champs permis ; traiter D06 |
| G09 | Renommage/dossiers/tags non établis | NON APPLICABLE | faible | `backend\api.py:69-85,110-132`, `frontend\src\pages\Documents.tsx:9-29` | Inventaire statique de ces parcours | 05/11/2026 | Non requis comme nouveaux développements | Aucune preuve de ces fonctions | Ne pas les annoncer ni les ajouter pour ouvrir cette bêta |
| G10 | Erreurs et indisponibilité : implémenté, partiellement testé | PARTIEL | moyen | `frontend\server\app.mjs:44-59,287-295`, `frontend\src\pages\Documents.tsx:25-28` | P01/P03 ; `tests\test_documents.py:189-194` | 31/10/2026 | Cas locaux, pas incident de cible | E2E 401/403/413/429/503 et reprise | Recette ciblée sans exposer de détails internes |

## H — Information et conformité

| ID | Contrôle | Statut | Criticité | Source et lignes | Rapport/test | Date preuve | Validité pour la cible | Manque | Action minimale |
|---|---|---|---|---|---|---|---|---|---|
| H01 | Mentions, CGU et confidentialité approuvées | BLOQUANT | élevé | `frontend\src\pages\Legal.tsx:4-25`, `frontend\src\legal\documents.ts:2-8,43-52` | P08 ; `frontend\src\pages\Legal.test.tsx:21-70` | 31/10/2026 + lecture 05/11 | Workspace a déjà Docnelo sous ancien identifiant ; pas texte approuvé | Nouvelle version dix, date/fin de bêta actualisées, avis juridique | Conserver anciens octets/URLs ; préparer et faire approuver nouveaux textes |
| H02 | Sous-traitants, flux, finalités, droits et support | PARTIEL | élevé | `DOCNELO_PUBLIC_BETA_10_USERS_LEGAL_READINESS.md:7-35` | P08 ; documents présents, coordonnées non reproduites ici | 31/10/2026 | Information existante ; exactitude non attestée | Entités/régions/contrats/transferts/canal et responsable effectifs | Revue exploitante et avis juridique compétent ; pas de déduction par marque |
| H03 | Conservation effectivement appliquée | BLOQUANT | élevé | `frontend\src\legal\documents.ts:574-594`, `tools\retention_production.py:1,72-80`, `backend\account_admin.py:80-86,135-169` | P08 ; `tests\test_retention.py:240-249` refuse l'exécution | 31/10/2026 + lecture 05/11 | 7 j/90 j/3 mois/3 ans annoncés, exécution non prouvée | Politique justifiée et tâches/processus réellement qualifiés | Aligner promesses sur fonctionnement approuvé ; pas de purge pendant audit |
| H04 | Acceptation versionnée et archives | PARTIEL | élevé | `backend\public_registration.py:73-76,117-119`, `frontend\src\legal\documents.ts:1-8`, `frontend\src\pages\Legal.tsx:11-25` | P01/P03/P08 | 31/10/2026 | terms_version/timestamp, pas registre complet des réacceptations | Immutabilité des versions et archive confidentialité/notice | Nouvelles entrées/hashes/URLs ; aucun changement rétroactif d'acceptation |
| H05 | Cookies/traceurs et information stockage | PARTIEL | moyen | `frontend\server\app.mjs:194-202,332-337`, `frontend\src\pages\Dashboard.tsx:16` | P03/P08 ; `frontend\src\pages\Legal.test.tsx:70` | 31/10/2026 + lecture 05/11 | Cookies essentiels visibles ; inventaire déployé inconnu | Inventaire réel et cohérence de « restent chez vous » avec hébergement serveur | Vérifier cookies/requêtes et corriger information dans nouvelle release ; bandeau non présumé requis |

## I — Exploitation et observabilité

| ID | Contrôle | Statut | Criticité | Source et lignes | Rapport/test | Date preuve | Validité pour la cible | Manque | Action minimale |
|---|---|---|---|---|---|---|---|---|---|
| I01 | Logs API/BFF, erreurs, accès et rotation | PARTIEL | élevé | `compose.public-beta.vps.yaml:29-31,271,281,350`, `backend\security_audit.py:14-32,126-127` | P11/P12 ; accès uvicorn désactivé explicitement | Date non explicitée | Audit structuré prévu ; logs proxy/runtime non observés | Collecte, droits, durée, absence PII et requêtes corrélées | Confirmer journaux utiles sans corps/secrets, ne pas réactiver logs bruts par défaut |
| I02 | Disponibilité API/DB et ressources | NON VÉRIFIÉ | élevé | `compose.public-beta.vps.yaml:23-28,275-280,345-349`, `tools\monitor_production.py:51-68` | P09/P12 | 31/10/2026 ; guide sans date | Healthchecks et outil /srv ne prouvent pas supervision bêta /opt | Latence/5xx/OOM/restarts, PG connexions/verrous, disque/inodes | Contrôle opérateur ciblé et seuils adaptés |
| I03 | Backup, alertes et réception | NON VÉRIFIÉ | élevé | `tools\monitor_production.py:87-162`, `docs\sprint-8-monitoring.md:9-24,104-139` | P12 ; `tests\test_monitoring.py:120-145,242-262` | Date non explicitée | Moniteur existant, pas installation ni arrivée boîte bêta | Timers/identités corrects et alerte reçue | Vérification autorisée de bout en bout, sans conclure sur seul SMTP accepté |
| I04 | Incident, maintenance et fermeture urgente | PARTIEL | élevé | `DOCNELO_PUBLIC_BETA_10_USERS_OPENING_RUNBOOK.md:106-135`, `ops\public_beta\VPS_BACKUP_RESTORE_RUNBOOK.md:35-44` | P01/P09 | 31/10/2026 | Procédures et close local, pas exercice effectif | Responsable/suppléant, seuils, délais et exercice | Recette fermeture/repli fermé avec compteur conservé |

## J — Décision et ouverture

| ID | Contrôle | Statut | Criticité | Source et lignes | Rapport/test | Date preuve | Validité pour la cible | Manque | Action minimale |
|---|---|---|---|---|---|---|---|---|---|
| J01 | État effectif et fraîcheur du dossier | NON VÉRIFIÉ | critique | `DOCNELO_PUBLIC_BETA_10_USERS_OPENING_RUNBOOK.md:6-22,26-85` | P05/P09 ; disabled/closed/0/0007 communiqués par opératrice | Historique, date du relevé non fournie | Pas observation VPS de cet audit | Dossier frais relié à même release | Collecte distincte autorisée, agrégats sans PII |
| J02 | Sécurité critique et recette finale | BLOQUANT | critique | D03/E02/E04/F01 et leurs sources | P01–P12 : scopes non interchangeables | Dates ci-dessus | Pas qualification finale de l'assemblage | Tous critères critiques satisfaits et aucune garde refusée | Compléter recette minimale et revue indépendante |
| J03 | Autorisation humaine limitée dix | BLOQUANT | critique | P09: conditions ; `qualification\b1-review-20261105\B1_INDEPENDENT_REVIEW.md:93-109` | Aucun acte d'ouverture signé dans les pièces examinées | 05/11/2026 | Formulaires/plans non assimilables à autorisation | Décideur, périmètre, date, signature et réserves levées | Compléter `BETA_10_GO_NO_GO.md` après preuves, pas pendant cet audit |

## Synthèse de portée

Les lignes G02/G05 et J02 agrègent des contrôles déjà identifiés : elles ne
créent pas des blocages supplémentaires à compter. F03/F04 s'appliquent à
P4 ; leur absence de résolution ne peut être « neutralisée » qu'en choisissant
formellement une **autre filière qualifiée**, sans accorder de GO P4.
La confidentialité, la reprise sûre et l'autorisation restent obligatoires
pour toute filière. Tous les contrôles de cible non exécutés portent la limite :
**NON VÉRIFIÉ — CONTRÔLE DYNAMIQUE REQUIS**.
