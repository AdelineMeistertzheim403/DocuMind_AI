# Scénarios existants et lacunes de recette

**Aucun test applicatif n'a été exécuté pendant cet audit.** Les résultats
ci-dessous sont lus dans les preuves existantes, dont l'intégrité locale a
été contrôlée. Toute recette future avec écritures doit être autorisée et
isolée des bases, comptes, données et preuves historiques.

Préfixe `C\` =
`deliveries\docnelo-lifecycle-10-api\source\`.
Preuves `P01` à `P12` : registre dans `BETA_10_READINESS_MATRIX.md`.
Les tests simplement présents dans le workspace ne sont pas déclarés réussis.

## Ce qui est déjà prouvé, sans extrapolation cinq → dix

La suite consolidée candidate contient douze modules selon
`deliveries\docnelo-lifecycle-10-api\result.json`. Son journal final est
`pytest.log:82` : 227 réussites, 17 avertissements, aucune ligne finale
d'échec/skip. Les 50 tests BFF et 11 contrôles opérateur donnent un total
de **288**, sans addition des reprises focused/intermédiaires. Le rapport
lifecycle écrit une fois « 287 » : incohérence rédactionnelle, pas preuve
d'un test manquant ; les trois journaux finaux établissent 227+50+11.

| Scénario attendu | Test existant et preuve | Résultat applicable | Lacune restante |
|---|---|---|---|
| Attribuer chacune des dix admissions | `C\tests\test_public_beta_capacity_ten.py:77-87`, `test_operational_one_five_six_nine_ten_and_eleventh` ; P01 | Boucle 1..10, assertions durables aux bornes 1/5/6/9/10, vérification e-mail/rejeu | Rattachement de la candidate à l'assemblage cible ; pas nouveau développement capacity10 |
| Refuser la onzième sans compte/mail | Même test `:88-93` ; P01 | Réponse générique 202, aucun mail, total utilisateurs dix, options full | Vérifier aussi DB/workspace/jetons/receipts et corps générique dans l'E2E final ; ne pas sonder une onzième personne en production |
| Deux demandes sur la dixième place | `C\tests\test_public_beta_capacity_ten.py:102-117`, `test_independent_apis_compete_for_last_durable_admission` ; P01 | Deux PIDs PG, un seul gagnant durable, compteur dix | Rejouer seulement si protocole/pool/assemblage change |
| Échec avant commit et résultat incertain après commit | Même fichier `:120-138`, `test_rollback_or_uncertain_commit_leaves_pending_and_blocks_retry`, deux paramètres ; P01 | pending conservé, SQL 0/1, nouvelles admissions et reopen refusés | Exercice de procédure humaine de réconciliation/fraîcheur, pas retry automatique |
| Atomicité SQL sans sémaphore partagé | `tests\test_public_beta_postgresql_concurrency.py:153-170` ; P01 inclut le module candidat | Course PostgreSQL réellement testée ; cas historique borné cinq | La preuve dédiée dix ci-dessus est celle de la nouvelle limite |
| Fermer sans recycler les admissions et conserver le login | `C\tests\test_public_beta_capacity_ten.py:88-99` ; P01 | Close à dix, compteur conservé, reopen plein refusé, login vérifié accessible | Course close/admission au passage 9→10 et exercice CLI/retour d'état |
| Réouverture explicitement autorisée | Fixture candidate `:27-57`, pending/full refusés `:93-96,133-138` ; `C\backend\account_admin.py:23-70` ; P01 | Dry-run puis confirmation spécifique ; vérifications de témoins | Manipulation opérateur de la release finale, sans SQL de contournement |
| Migration legacy des témoins | `C\tests\test_public_beta_capacity_ten.py:169` et suite ; `C\tests\test_public_beta_capacity_failures.py:26-60` ; P01 | Idempotence, conservation lignes/inodes/tags, rollback SQLite et WAL refusé | État réel admissible, autorisation et chaîne d'outillage ; ne pas relancer 0007 |
| Restore dix / ancien compteur cinq | `C\tests\test_public_beta_capacity_ten.py:141-166` ; P01 | Copies SQLite via backup API, dix cohérent, cinq en réconciliation, tag falsifié refusé | Une source indépendante survivante réelle n'est pas remplacée par ce scénario synthétique |
| Dump initial zéro vs restore dix après redémarrage | `C\tests\capacity_roundtrip.py:75-123` ; P02 `roundtrip-result.json` | Vrais dumps/restores PostgreSQL, cinq stores, trois processus, stale=0 refusé | Capture complète réelle, documents/clés/latch, récupération distante et revue S2 |
| Format de backup étendu compatible dix | `C\tests\test_public_beta_capacity_backup.py:28-70` ; P01 | tooling5.2 accepte la structure ; V5.1 refuse l'extension | Manifeste/payloads synthétiques ; pas preuve de capture quiescente réelle |
| Reprise de challenge, e-mail, quotas, comptes existants | `tests\test_public_beta.py:116-175,219-245,289-317`, `tests\test_public_beta_state.py:55-156` ; P01 inclut modules candidats | Régressions présentes dans suite réussie | Beaucoup de fixtures historiques ont durabilité réduite ; ne pas qualifier par elles les mutations opérationnelles strictes |

`full` signifie capacité épuisée avec `closed` éventuellement encore false.
Le refus de la onzième doit rester vrai indépendamment d'une fermeture
administrative ultérieure. Le compteur est cumulatif : abandon, absence de
vérification, effacement ou redémarrage ne rendent pas de place.

## Recettes ciblées manquantes ou insuffisantes

Chaque résultat ci-dessous est **NON VÉRIFIÉ — CONTRÔLE DYNAMIQUE REQUIS**
sur l'assemblage final. Les observations statiques établies ne sont pas
elles-mêmes en attente d'un test pour être reconnues.

| ID | Scénario et critères de réussite | Preuve déjà disponible / insuffisance | Intervention minimale | Nature |
|---|---|---|---|---|
| TG01 | Navigateur → HTTPS/BFF → challenge/CGU → admission durable → SMTP → vérification → connexion ; dix puis refus onzième, identités et versions cohérentes | P01 teste API et BFF séparément ; P04 conclut BLOCKED/503. Ses 26 contrôles PASS incluent des refus ; mail envoyé par appel direct ne prouve pas l'admission | Recette neuve avec comptes fictifs, SMTP captif et profil standard durable non synthétique, sur mêmes images/outils | Intégration/preuve, après deltas |
| TG02 | Approbation administrative : vérification e-mail seule ne permet ni login ni document ; accord/rejet/rejeu/concurrence contrôlés | `backend\public_registration.py:165-186` active après e-mail+mot de passe ; block/release `backend\account_admin.py:60-77` n'est pas un préalable obligatoire | Décider la règle ; si maintenue, nouveau verrou et quelques tests ciblés avant E2E | Code conditionnel à exigence, non redéveloppement général auth |
| TG03 | Urgence à quota 9 et demandes concurrentes : aucun compteur >10, close persistant, anciens comptes accessibles, aucun reopen implicite | Tests de close/concurrence historiques à cinq ; close nominal dix déjà réussi | Paramétrage/scénario dix de la course, puis procédure CLI/observation en lab | Test ciblé/preuve |
| TG04 | Isolation entre deux comptes via BFF : liste, détail, texte, original, analyse et suppression ; UUID étranger/inconnu, sans session, session expirée/révoquée ; aucun accès direct volume/API | `tests\test_documents.py:108-159`, `tests\test_accounts_saas.py:99-111`, P01 : API testée ; réseau de cible inconnu | Recette positive/négative sur images et proxy exacts, comparaison des octets et absence de détails sensibles | Preuve critique d'intégration |
| TG05 | Download positif PDF/TXT : mêmes octets/hash, filename/headers bornés, pas de chemin interne ; négatifs corruption, propriétaire, 401/404/409, réponse upstream invalide | Backend testé ; R2 404 établi P03. Correctif local `frontend\server\app.mjs:297-323` et tests `frontend\server\app.test.mjs:213-257` déjà écrits | Qualifier le delta existant et l'embarquer uniquement dans une nouvelle release autorisée | Delta déjà implémenté + qualification |
| TG06 | Effacement documentaire strict : confirmation avant effet, holds, commit avant/après, crash/pending, aucun accès après décision ; pas de résurrection après restore | `backend\services\documents.py:261-274` et `C\backend\lifecycle_durability.py:255-259` refusent le profil durable non synthétique ; tests historiques de suppression ne suffisent pas | Lot opérationnel minimal revu ; sinon procédure alternative réellement qualifiée et périmètre explicitement approuvé, sans fausse réponse de succès | Code/protocole requis pour fonction promise |
| TG07 | Demande compte, révocation, traitement d'effacement et conservation justifiée ; délai/recours, preuves survivantes et données de backup rapprochées | `backend\account_api.py:311-355`, `backend\account_admin.py:135-169` : refus/limitations strictes ; P08 sans preuve du traitement réel | Qualifier le canal utilisateur et le traitement autorisé, avec reçus et incidents ; vérifier les délais annoncés | Protocole, juridique et éventuellement code |
| TG08 | Capture cohérente et restore complet : SQL, documents, cinq stores, deux clés, latch, inventaire exhaustif et SHA, quota clos sans diminution | P02 prouve un round-trip borné ; P06 corrige des composants ; aucun des deux ne qualifie toute l'orchestration active | Un exercice isolé avec release choisie, mêmes paths/overrides/droits, aucun writer et preuve avant/après | Preuve critique intégrée |
| TG09 | Ancien backup, witness survivant plus récent, clés absentes/incorrectes, hold/effacement postérieurs, état pending et divergence ; rester fermé | Stale zéro/cinq contre dix et HMAC altéré déjà testés ; source indépendante réelle absente | Établir chaîne de fraîcheur hors domaine restauré ; cas de perte simultanée explicitement indécidable et fermé | Preuve + politique de reprise S2 |
| TG10 | Restore : quota initial ouvert, échec pg_restore/commit/disque, crash, cible partielle non réutilisable ; aucune API attachée | P06 : 167 tests Windows, 13 ignorés ; `tools\validate_restore.py:344-370` appelle bien le sealer ; Linux/PG opt-in non exécutés dans ce rapport | Qualification Linux/PG du correctif exact, cible neuve à chaque échec, états incomplete/failed conservés | Preuve, pas re-correction d'un sealer absent |
| TG11 | Retour fermé après compteurs 6..10 et schémas SQLite étendus ; pas de reset/restore ancien et pas de perte de textes acceptés | P01 admin/compatibilité ; P09 interdit rollback cinq ; pas exercice final de repli complet | Éprouver image/outillage de fermeture compatibles dix et erreur/interruption en lab | Preuve critique opératoire |
| TG12 | Récupération distante du snapshot complet exact, hashes et restore neuf ; perte locale simulée dans périmètre autorisé | remote_verified/inventaire Restic ou anciens constats Sprint 8 ne prouvent pas cette récupération bêta | Exercice distinct explicitement autorisé, sans forget/prune ni source réécrite | Preuve externe |
| TG13 | Mot de passe oublié/reset : TLS SMTP, boîte reçue, expiration/usage unique, révocation de toutes sessions ; renvoi après fermeture sans nouvelle admission | P01 API et SMTP fictif ; P04 appel direct de mail, pas le parcours complet | E2E isolé, puis délivrabilité externe autorisée avec boîte de recette ; aucun vrai compte créé par audit | Preuve ciblée |
| TG14 | Charge raisonnable : dix comptes, uploads bornés et échecs propres, proxy/IP partagés, PG/verrous, espace/inodes et marge d'une capture | Limites source CPU/RAM/disque logiques ; aucune mesure actuelle de VPS | Recette synthétique bornée sur machine représentative puis relevé readonly autorisé ; pas de benchmark massif sur production | Mesure/preuve, pas dimensionnement théorique imposé |
| TG15 | Alertes disponibilité/API/PG/disque/backup, mail réellement reçu, incident et fermeture avec responsable/suppléant | Moniteur/tests P12, chemins historiques /srv ; installation et destinataire bêta inconnus | Exercice de notification et de procédure sur périmètre autorisé ; sortie expurgée et accusé de réception | Preuve opératoire |
| TG16 | Conservation : non-vérifiés, logs, backups, demandes RGPD ; expiration/gel justifié et traitement après restore | P08 ; `tools\retention_production.py:1,72-80` est planificateur/refuse formats hors périmètre ; purge pending strict refusée | Vérifier processus effectivement déployés ou qualifier un processus borné ; avis juridique sur promesses, sans purge pendant audit | Politique/preuve, code seulement si nécessaire |
| TG17 | Nouvelles pages dix, archives anciennes inchangées, CGU API/UI/hash/acceptation cohérentes, dates et stockage serveur correctement expliqués | P03 protège archives R2 ; workspace change déjà la marque sous `beta-2026-10-v1` ; `frontend\src\pages\Legal.tsx:19` avertit toujours brouillon | Nouvelle version, approbation puis recette UI ; conserver les octets R2 historiques comme référence | Contenu/UI + preuve |
| TG18 | HTTP erreurs/auth et fonctions exclues : IA/demo/legacy refusés, pas d'appel fournisseur, pas de stack/PII, comptes existants accessibles pendant fermeture | P01/P03 tests locaux ; cible non observée | Scénarios bornés sur release finale, contrôle allowlist des flags et journaux | Non-régression ciblée |

## Parcours ne justifiant pas de nouveaux chantiers

Le tableau de bord, les listes paginées, la consultation et l'import disposent
déjà de code et de tests. Leur lacune est l'intégration finale authentifiée,
pas leur absence. La recherche locale est limitée à la page chargée dans
`frontend\src\pages\Documents.tsx:16-28` ; recherche sémantique/IA, dossiers,
tags et renommage ne doivent pas être inventés comme exigences nouvelles.
Tester le périmètre annoncé, non ajouter des fonctionnalités.

## Dossier attendu pour chaque campagne future

Nouvelle cible et nouveau dossier, autorisation et périmètre ; révisions/images/
outils/configuration et hashes ; données uniquement synthétiques en laboratoire ;
commandes, paramètres expurgés, environnement, stdout/stderr/RC ; résultats par
scénario, échecs/ignorés explicites, manifestes et ancre indépendante.
Un skip n'est jamais un PASS. Un résultat uncertain reste uncertain.
Un succès technique n'est ni une qualification formelle ni une autorisation.
