# Docnelo Public Beta — Tests de préparation à dix admissions

31 octobre 2026. **NO-GO ouverture**, malgré les succès du quota SQL. Aucune requête de création/suppression, aucun SMTP ni connexion de test vers le VPS.

## Contextes isolés

| Contexte | Provenance | Usage |
| --- | --- | --- |
| Référence Git R2 | b046e5d8256d45b65bf575a8a006351616b69fc9 ; 345 sources suivies copiées, .env exclus | Test diagnostique du backend Git, pas attestation API active |
| Hypothèse API candidate | Backend Python de exports/public-beta-candidate-20261030T234818Z superposé dans une autre copie synthétique ; 65 fichiers, 17 différences avec R2 | Diagnostic du code Beta Lite supplémentaire ; pas une image VPS vérifiée |
| BFF réel R2 local | Image ebdbc7fba1c61c03349088ca093470c78eec9dd91c5e2aa92ab1d8c0db5be362, fichiers server identiques montés en lecture seule avec leurs tests | Non-régression des contrats Web/BFF, sans API réelle |

Chaque exécution PostgreSQL utilise un réseau Docker **interne neuf**, une base PostgreSQL 17/vector vide en tmpfs, aucun port publié ni volume persistant, un conteneur de tests en lecture seule avec /tmp temporaire. Les containers et réseaux créés par chaque exécution sont ensuite arrêtés/retirés par leurs IDs capturés ; aucun volume existant n’est supprimé. Les bases synthétiques sont migrées à l’entrée des fixtures et nettoyées à leur sortie, exclusivement dans ce laboratoire. Ne jamais reprendre le cleanup tests/conftest.py sur VPS : il remet le quota fictif à zéro pour démonter la base de test.

Image de dépendances : documind-s14-6-proofs:local, ID 526917bd27ecc837a7b683c0ca396fcdf315dde81c879100bffda874a3abeb1d, Python 3.13. La grammaire des nouveaux scripts/probes est contrôlée avec Python 3.11 ; le runtime exact de l’API VPS n’est pas attesté par ces essais. L’image DB locale d2e0a72a9da2… n’est pas celle d’un service VPS. Aucun téléchargement d’image ni mise à jour de dépendance n’a été nécessaire.

## Résultats finaux par contexte

| Groupe | Réussis | Échecs d’assertion | Erreurs de fixture/nettoyage | Ignorés |
| --- | ---: | ---: | ---: | ---: |
| API Git R2, PostgreSQL 17, 9 modules pytest | 188 | 0 | 0 | 0 |
| API export candidat, mêmes modules | 188 phases de test | 0 | **10** | 0 |
| Nouveau processus API Git R2, dix admissions persistantes | 1 | 0 | 0 | 0 |
| Nouveau processus API export candidat, même contrôle | 1 | 0 | 0 | 0 |
| BFF R2, Node réel | 50 | 0 | 0 | 0 |

Les tests entre références se recouvrent ; ces nombres ne sont pas présentés comme des scénarios uniques additionnables ni comme une qualification du mode durable à dix. La suite candidate retourne un **code d’échec 1**, même si pytest affiche 188 passed pour les appels de tests, car dix teardowns sont en erreur. Les tests de refus lifecycle réussis prouvent précisément un blocage, pas une ouverture réussie.

Durées des suites principales : Git R2 219,85 s ; candidat 206,31 s. Redémarrage par nouveau processus : 5,18 s / 4,74 s. BFF : 50 passed, 0 failed, 0 skipped, environ 0,78 s. Avertissements : dépréciation Starlette/httpx ; un avertissement Pydantic additionnel dans le candidat. Ils restent consignés sans modifier les dépendances.

## Matrice des exigences

| Exigence | Test exécuté / résultat | Limite de preuve |
| --- | --- | --- |
| Premier puis dixième compte | test_first_tenth_eleventh_no_recycling_and_no_numeric_public_count | Dix comptes/admissions SQL non vérifiés, profil legacy de test, lifecycle durable désactivé par la fixture historique |
| Refus onzième | Même test, 202 générique, aucun mail/compte supplémentaire, options full | Aucun faux testeur créé sur VPS |
| Concurrence | test_two_independent_http_instances_race_for_tenth : neuf vrais comptes synthétiques puis deux APIs et connexions PG synchronisées sur UPDATE | Une seule admission restante attribuée ; deux PID PostgreSQL différents ; garde RAM non partagée |
| Restart API, compteur conservé | Nouvelle instance dans suite ; test_ten_users_process_restart lance aussi un **nouveau processus Python**, cycle complet create_app/TestClient | Compteur dix relu dans le nouveau processus, aucune création de ligne de quota au démarrage |
| Connexion après fermeture | Même nouveau processus, registration_mode=disabled, login compte synthétique vérifié HTTP 200, disponibilité closed | Profil legacy de test ; aucune session VPS testée |
| Compte abandonné | Dix admissions non vérifiées ; suppression synthétique d’un compte ne libère pas le compteur | La purge réelle n’est pas exécutée |
| Échec transaction et réessai | test_rollback_after_reservation_does_not_leave_orphans_or_consume_a_place et suite publique | Rollback SQL sans témoin durable ; commit incertain durable reste une recette bloquante future |
| Échec SMTP/file pleine et renvoi | test_public_beta_email_abuse, SMTP TLS local fictif, queue/erreurs et renvoi protégés | Délivrabilité externe et prestataire VPS non testés |
| Vérification, expiration et rejeu | test_public_beta + state : bon/mauvais mot de passe, token expiré/corrompu, usage unique, renvoi et concurrence verify/resend | Jetons uniquement synthétiques |
| Reset, sessions et documents | test_accounts_saas, documents, public_beta_authorization, upload_admission | Assertions passées ; erreurs teardown candidate détaillées ci-dessous |
| Consentements | Mauvaise version/refus non accepté ; version et timestamp de dix comptes contrôlés | Ne constitue ni approbation juridique ni registre complet de réacceptations |
| Anti-abus | Tests existants challenge/preuve/IP/expiration/429, SMTP et comptes ; seuils inchangés | Les tests séquentiels de dix simulent des demandes espacées >60s uniquement dans l’horloge du rate limiter ; aucun seuil applicatif n’est changé |
| Lifecycle strict | Refus HTTP 503 sans opt-in synthétique, configured_admissions refuse dix, témoin refuse séquence 6, admin/politique refusent dix | **Capacité durable dix non disponible et non qualifiée** |
| BFF | 50 tests de routes, sécurité, cookies/CSRF et upload ; image R2 hors réseau externe | API active non jointe, contrats du BFF conservés |

Les fixtures interdisent les vrais clients OpenAI. Certains tests historiques de non-régression SaaS activent un fournisseur **mock dans leur seule application fictive** ; cela ne change aucun paramètre Public Beta et ne produit aucun appel IA réel. Les scénarios dix gardent AI_ENABLED=false.

## Erreurs candidate à conserver dans le verdict

Dix tests de test_accounts_saas.py utilisent la fixture accounts de test_byok.py, qui passe ai_enabled à true **après** le démarrage de l’application. Dans l’API candidate, main.py ne démarre le thread summary_worker que si l’IA était déjà active au startup ; au shutdown il teste la valeur actuelle du flag. Le fixture fait donc appeler stop() sur un thread jamais démarré, avec RuntimeError: cannot join thread before it is started. Les assertions métier ont réussi, mais le cycle de vie de cette suite n’est pas propre.

Ce résultat démontre une incompatibilité entre cette fixture historique et le cycle de vie du worker candidat ; il **ne démontre pas** que l’API réelle arrêtée avec AI_ENABLED=false constant rencontre ce défaut. Ne pas activer l’IA sur le VPS pour faire passer les tests. Préparer une correction distincte : tester le démarrage/arrêt à partir de l’état effectivement démarré du worker, ou construire les fixtures avec leurs paramètres définitifs avant le lifespan, puis rejouer la suite sur les sources de l’API attestée. Aucun changement applicatif n’a été appliqué pour masquer ces erreurs.

Le nouveau test de processus a lui-même demandé deux corrections de harnais : fixture beta non importée (1 erreur de préparation), puis clé fictive SecretStr masquée à la sérialisation (1 échec). Ces tentatives sont conservées dans restart-attempt1.log et restart-attempt2.log. Le test final réinjecte uniquement la constante BFF fictive connue dans le processus enfant ; il passe sur les deux références, sans modification de code applicatif ni lecture de secret réel.

## Reproduction et preuves

```powershell
# Scripts locaux : ne ciblent que Docker Desktop, jamais le VPS.
.venv/Scripts/python.exe -B deliveries/docnelo-10-users/run_lab.py
.venv/Scripts/python.exe -B deliveries/docnelo-10-users/run_lab.py --candidate
.venv/Scripts/python.exe -B deliveries/docnelo-10-users/run_lab.py --restart-only
.venv/Scripts/python.exe -B deliveries/docnelo-10-users/run_lab.py --candidate --restart-only
```

La suite principale conserve explicitement les neuf modules prévus ; elle ne collecte pas automatiquement le module de restart ajouté ensuite, exécuté séparément. prepare_lab.py / prepare_candidate.py refusent d’écraser une copie existante ; ne pas les relancer sur ces dossiers. Les sources applicatives des copies sont identiques aux inventaires, seuls les deux nouveaux fichiers de tests sont ajoutés.

Preuves dans deliveries/docnelo-10-users : pytest.log, candidate-pytest.log, restart-pytest.log, candidate-restart-pytest.log, bff-tests.log, result.json et résultats homologues, source-inventory.json, candidate-api-inventory.json. SHA256SUMS et qualification-summary.json recensent les preuves et les nouveaux outils. Les sources/copies/logs sont des artefacts locaux de qualification, pas un bundle de déploiement. Ne pas les transférer en bloc sur VPS.

## Ce qui reste obligatoirement à qualifier

API active par provenance et paramètres réels ; dix admissions avec lifecycle strict et réconciliation indépendante ; migrations de témoins existants et backups à six/dix ; crash/commit incertain ; nouvelle réouverture administrative et fermeture sur le protocole corrigé ; emails réels autorisés, textes approuvés, capacité et rétention effectives. La recette de création/suppression contre le VPS n’est pas un substitut autorisé.

**Verdict : NO-GO ouverture.** SQL et BFF diagnostiqués, refus stricts confirmés, erreurs candidate conservées et contrôle opérateur encore nécessaire.
