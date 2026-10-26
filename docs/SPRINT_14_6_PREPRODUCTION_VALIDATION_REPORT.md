# Sprint 14.6 — Recette préproduction et préparation opérationnelle

25 octobre 2026. Travail local sur `preparation/sprint-14-5-ux-email-abuse`, sans
retour à `main`. Base `8243e0511c5505a9cc70f76ad02392f7a816590d`, schéma `0007`.
Les cinq rapports 14.1–14.5 ont été relus ; les travaux non commités sont conservés.
**Aucune publication, ouverture, opération VPS/B2, modification de secret ou activation IA.**

## 1. Inventaire et cohérence du lot

Avant modification : 47 fichiers modifiés ou nouveaux, relevés par SHA-256.
L'annexe donne leur inventaire exact, y compris les fichiers non suivis.
Au contrôle final, 45 sont strictement identiques ; seuls les deux helpers de test
SMTP/navigateur sont étendus comme indiqué ci-dessous. Onze fichiers sont ajoutés
pour 14.6, soit 58 chemins modifiés/non suivis au total, aucun indexé automatiquement.

| Phase | Cohérence confirmée depuis les sources et tests |
| --- | --- |
| 14.2 | `approve_public_beta` booléen, faux par défaut dans `deploy.yml`, flag CLI distinct des migrations. Politique commune préparation/Compose résolu/sonde image. Public exige cinq, IA/demo/legacy false et verrou SQL fermé, révision 0007 déjà installée. |
| 14.3 | Garde avant connexion/validation de clé, clients de génération/embedding et dispatch des workers ; BYOK ne réactive pas l'IA. Lecture locale/historique et déconnexion conservées. |
| 14.4 | Cinq admissions cumulatives, SQL atomique non négatif, blocage administratif distinct de l'attente, inventaire quota v2 et fermeture des copies restaurées. |
| 14.5 | UX sans promesse de livraison, états agrégés, consentement explicite, paramètres anti-abus réels et signal de saturation du reset. |

Le bundle CI contient `release.json`, `compose.production.yaml`, `deploy_production.py`,
`backup_local.py`, `release_manifest.py`, **`public_beta_policy.py`**. Ce dernier est
indispensable aux imports des nouveaux scripts ; il est bien copié par le workflow.
Les builds API copient backend, moteur, migrations et moteur d'extraction ; le build
frontend copie serveur et sources. Les nouveaux tests utilisent les fixtures SMTP
présentes dans le dépôt. Aucun fichier runtime nécessaire identifié comme oublié.
Un futur commit doit inclure les fichiers non suivis pertinents, pas `var/`.

Pas de nouvelle migration ; `schema_head()` et les bases de recette sont en `0007`.
Les scripts, workflows et fichiers applicatifs des phases précédentes ne sont pas
modifiés par 14.6. Deux helpers de test 14.5 sont étendus avec des valeurs par défaut
compatibles : adresse/port SMTP de recette et email/résolution locale du navigateur.

## 2. Environnement réellement utilisé

Windows 11, Docker Desktop local explicitement ciblé par le pipe
`npipe:////./pipe/dockerDesktopLinuxEngine`. Noyau Docker Linux
`6.18.54.1-microsoft-standard-WSL2`, amd64, **Landlock ABI 7 mesurée** ; ce n'est pas
le noyau de production Linux 6.12 / ABI 6 annoncé par l'opératrice.

Projets neufs `documind-s14-6-recipe-a85c`, puis `documind-s14-6-recipe-b17c` :

- PostgreSQL 17/pgvector local, stockage neuf sur tmpfs, base applicative neuve ;
  autre base neuve distincte pour les tests SQL natifs, jamais une base existante.
- API et BFF réels, React construit, un processus API/BFF. API en **sandbox**,
  Landlock/seccomp obligatoires, readonly, `no-new-privileges`, capacités supprimées,
  limites CPU/mémoire/PID et tmpfs. Aucune adaptation ABI 2 ni repli development.
- Volume documentaire propre au projet, sans aucun volume ou réseau de production.
  API sur réseaux internes, aucun port PostgreSQL/API/BFF/SMTP publié.
- Traefik **v3.3 local disponible**, fournisseur fichier, pas de socket Docker ni
  ACME/Let's Encrypt. TLS local avec certificat de recette éphémère approuvé/pinné.
  Production : v3.0 et fournisseur Docker ; cette différence reste à valider.
- Faux SMTP STARTTLS interne, certificat vérifié par l'API, messages fictifs capturés
  dans `var/` uniquement. Aucun relais ni fournisseur SMTP réel.
- Trois relais TCP transparents donnent à Traefik trois pairs réseau réellement
  distincts. Ils servent uniquement à séparer la recette quota de la limite NAT.
  Pas de confiance dans un X-Forwarded-For fourni par le navigateur. Seuls les ports
  **127.0.0.1:19443–19445** sont publiés ; TLS reste terminé par Traefik.

Les limites restent difficulté 12, trois demandes/heure/IP/email, dix/minute global,
challenge cinq/minute/IP. Elles ne sont pas augmentées pour atteindre cinq admissions.
API sans réseau sortant ; BFF ne relaie que vers l'API interne. Aucun appel IA réel.

### Limite des images candidates

La construction **exacte** du Dockerfile API avec `--network none` échoue : résolution
Debian indisponible et dépendances de build `setuptools>=75` introuvables hors ligne.
Ce n'est ni un test applicatif réussi ni un défaut métier démontré. Aucun accès à
la Registry privée ni installation réseau n'est utilisé pour contourner cet échec.

Des overlays hors ligne réutilisent les runtimes locaux Sprint 13, avec les sources
actuelles et le build React actuel. `requirements.lock`, `pyproject.toml` et les
lockfiles frontend sont inchangés ; aucune dépendance nouvelle. Ces images portent
`org.opencontainers.image.revision=uncommitted-sprint-14-6`, **pas** un faux SHA de release.

| Image locale | ID |
| --- | --- |
| API | `sha256:391142d07e18b4ab3a78b239d6bb56e7ae195d5ac29247097c1c2dcddc11d9be` |
| BFF/frontend | `sha256:f15855942fb4382375648841bbcdc486fd39d252e80e8fdf8eb42999d6590019` |
| Preuves/SMTP/relais | `sha256:dd91e56395bfc4f174e5317abe2d745ae8d2f4a12a18924820ba04d4d1cbb79e` |

Ces IDs locaux ne sont pas des références Registry par digest. **Les builds CI exacts,
leurs trois digests amd64 et une recette des images effectivement publiées restent
obligatoires avant ouverture.** Aucun overlay de recette ne doit être déployé.

## 3. Parcours fonctionnels et sécurité

| Scénario | Preuve locale |
| --- | --- |
| HTTPS et connexion | Traefik sert React et `/login`, BFF/API healthy. Certificat local vérifié côté Python et SPKI spécifique approuvé dans Chromium, sans bypass TLS global. |
| Host, Origin, CSRF | Mauvais Host : 404 Traefik ; Origin hostile : 403 BFF ; écriture sans CSRF : 403. |
| Inscription par formulaire | Chromium ordinateur puis iPhone 13 émulé, consentement non précoché, PoW réelle 12, email reçu par faux SMTP TLS. |
| Vérification et connexion | Jeton extrait du mail capturé, formulaire avec mot de passe, puis login et cookie Secure/HttpOnly/Strict ; aucun localStorage/sessionStorage. |
| Workspace et documents | Création réelle, imports TXT et PDF fictifs, consultation autorisée, analyses locales HTTP 201, extraction PDF sous sandbox. |
| Isolation | Un second compte reçoit 404 pour les documents TXT et PDF du premier. |
| IA fermée | Statut `enabled=false`, connexion de clé et validation BYOK refusées 403, fonctions documentaires utilisables. |
| Quota | Cinq comptes publics admis ; sixième 202 générique sans compte ni incrément ; pas de place recyclée. |
| Fermeture | CLI exécuté explicitement, compteur conservé, nouvelles demandes sans admission ; comptes existants utilisables. |
| Réouverture | Simulation sans mutation puis action explicite sous le plafond ; à cinq, réouverture refusée. |
| Redémarrage | API/BFF seuls redémarrés, même conteneur PostgreSQL, compteur cinq et verrou fermé conservés ; session RAM perdue, reconnexion possible. |
| Processus de démarrage invalide | Nouveau processus isolé avec valeur de mode invalide : refus fermé, application saine et verrou conservés. |
| Journaux | Sentinelles email/mot de passe/clé et jetons capturés absents des logs API/BFF/Traefik/SMTP de recette. |

Une première recette a rencontré un 429 mobile légitime : plusieurs entrypoints
ne suffisaient pas à créer des IP distinctes, Traefik ajoutant son pair réel dans
X-Forwarded-For. Les en-têtes simulés ont été retirés au profit de relais TCP. Reprise
explicite du seul état local reconnu (un compte déjà admis), sans reset du compteur.
Une seconde recette part ensuite de données entièrement neuves pour confirmer le
parcours final. Les preuves initiales sont conservées dans `var/`, non publiables.

Le premier générateur lancé sous sandbox produisait un fichier fictif inaccessible
à l'identité locale Docker ; un nouveau répertoire a été généré avec cette identité,
sans changement des ACL globales ou des secrets. Les helpers SMTP/relais ont `init`
pour terminer proprement leurs processus Python ; les protections API ne changent pas.

## 4. Livraison contrôlée et blocage rollback

Les tests du déployeur et de la politique couvrent `disabled` sans approbation,
public refusé sans flag, limite autre que cinq/IA/demo/legacy actifs refusés, verrou
absent/ouvert/incohérent refusé, absence de réouverture, échec de démarrage et repli
applicatif avec verrou conservé. Ce sont des **simulations du déployeur**, pas une
connexion Registry/SSH ni une exécution du workflow de livraison.

**B14-10 — blocage de sécurité avant ouverture :** `can_rollback()` ne vérifie que
`supported_schema_revisions`. L'appel réel avec un ancien candidat déclarant `0007`
retourne `true`. La branche d'échec de `execute()` peut redémarrer `previous` si son
schéma est compatible ; vérifier un quota fermé ne certifie pas le code ancien.
Un ancien vérificateur d'email peut notamment réintroduire B14-08 même sans nouvelle
admission. Un candidat Sprint 13 n'est donc pas un rollback sûr pour cette bêta.

Nuance : le workflow refuse un ancien bundle incomplet lorsqu'il exige le nouveau
fichier de politique. Cela ne prouve pas que l'image visée conserve tous les correctifs,
ni ne protège à lui seul le redémarrage automatique de la release précédente.
**Le refus automatique de tout ancien binaire vulnérable n'est pas validé.**

Correction proposée, non appliquée dans ce lot : attestation/version de profil de
sécurité liée au SHA et aux digests de CI, vérifiée avant rollback **et** avant tout
redémarrage automatique de previous. Ajouter les tests négatifs sur anciens candidats
0007, y compris en mode disabled avec comptes publics existants. Garder la base et
le quota fermés si aucun candidat sûr n'est attesté. Une simple étiquette autodéclarée
ou une compatibilité de schéma ne suffit pas. Une liste opératrice de SHA corrigés
peut servir de contrôle complémentaire, pas masquer ce chemin automatique.

Aucune modification applicative ou du déployeur n'est faite pour cacher ce blocage.
Le runbook 14.7 impose son traitement avant l'étape de livraison publique.

## 5. Sauvegarde et restauration indépendantes

`create_backup()` réel, API/BFF arrêtés, PostgreSQL laissé en marche : dump complet,
archives documentaires, SHA-256, inventaire v2 de 23 tables incluant compteur/verrou.
Restauration par `pg_restore` dans une **autre base neuve**, jamais la source.
`verify_snapshot()` relit les empreintes ; trois documents sont extraits et comparés
aux tailles et SHA-256 stockés en base. Le compteur cinq et le verrou sont vérifiés.

Dans la campagne finale, une copie synthétique v1 est créée dans un nouveau répertoire,
sans toucher au snapshot v2 : lecture compatible, mais **quota non certifié**.
Après preuve de fidélité, le verrou est ouvert uniquement sur la copie hors service
pour injecter un défaut ; `seal_restored_registration()` existant doit le fermer
sans changer le compteur. La source reste fermée à cinq. Aucune API n'utilise cette copie.

Les nouveaux helpers réutilisent les fonctions métier de backup/vérification/seal.
Ils ne lancent ni downgrade, restauration de production, Restic distant ni purge.
L'orchestrateur quotidien charge dynamiquement **le `backup_local.py` de current** :
une fois un nouveau bundle réellement actif, il utilisera ce helper v2, sans besoin
de remplacer aveuglément le script systemd. Vérifier les versions installées et un
snapshot réel après livraison ; aucune propriété du VPS n'est supposée observée.

## 6. Supervision adaptée aux cinq admissions

Audit local des unités : backup à 03:00, monitoring à 08:00, rétention à 09:00,
Europe/Paris, timers persistants. Leur activation effective n'est pas vérifiable ici.
`documind-retention.service` appelle **`--simulate`**, suppression désactivée.
Le verrou `deployment.lock` reste commun ; sauvegarde exclusive, monitoring/rétention
lisent avec les contrôles de concurrence existants. Aucun timer n'est modifié.

Le monitoring existant surveille disque, fraîcheur B2, timer/horloge et alertes
d'exploitation ; il n'est pas un collecteur automatique de tous les événements
d'inscription ou de mail. Les événements SEC10-04 sont disponibles mais aucune
alerte Gmail SMTP applicative nouvelle n'est installée par cette recette.

Proposition opératrice pendant les premières admissions :

- Avant ouverture, santé `db/api/web`, `/bff/health`, disque et dernier backup/restauration.
  Seuils locaux existants : avertissement sous 20 Gio, critique sous 10, urgence sous 8.
- Première heure : contrôle manuel toutes les deux à cinq minutes, opératrice joignable,
  compteur/verrou via CLI et décompte expurgé des événements. Pas de nouveaux comptes
  réels pour sonder le quota ; une demande de test peut consommer une place.
- Surveiller `system.mail.failed`, `system.database.unavailable`, `system.audit.dropped`,
  `rate_limit.exceeded`, inscriptions et vérifications. Un pic de 429 peut être un NAT,
  pas une preuve d'attaque. HTTP 202 n'est ni admission ni livraison SMTP.
- Échec mail répété, compteur incohérent ou alerte disque : fermer explicitement les
  admissions, conserver compteur et comptes, diagnostiquer puis décider ; pas de reset.
- Santé API/BFF ne prouve pas la santé SMTP. La profondeur de file n'est pas exposée ;
  un CLI séparé ne peut pas lire la file RAM du processus vivant. Ne pas annoncer
  une profondeur zéro en construisant une nouvelle application.
- Revue privée des logs Traefik, PostgreSQL et SMTP réels : pas d'en-têtes credentials,
  corps, paramètres SQL sensibles ou URLs de tokens dans des collecteurs publics.

## 7. Décision proposée sur la file email

Fréquence de perte non quantifiable sans observations réelles : risque à chaque
redémarrage/crash avec file non vide, indisponibilité SMTP ou saturation. Une admission
touchée représente 20 % de la cohorte de cinq. Le compte reste en attente, sa place
reste consommée ; le renvoi peut réparer la livraison sans créer de nouvelle admission.

File RAM 100, envoi après commit, timeout réseau 10 s par opération, join 12 s sans
drainage garanti. Le reset partage la file, limite IP/adresse mais pas de plafond
global dédié. Les anciens comptes éligibles comptent aussi dans ce risque ; leur
nombre actuel et les performances SMTP ne sont pas déduits du dépôt.

**Proposition : conserver la file RAM pour cette cohorte uniquement si l'exploitante
accepte explicitement le risque**, SMTP réel validé, surveillance rapprochée, renvoi
testé et fermeture prête. Ce rapport ne donne pas cette acceptation à sa place.
En cas de refus ou de saturation observée, exiger un lot ciblé de limite globale du
reset/priorisation avant ouverture, avec mesures et tests ; aucune nouvelle file
durable, migration ou infrastructure n'est introduite ici.

## 8. Campagnes et limites de preuve

| Campagne | Réussis | Ignorés | Échoués / état |
| --- | --- | --- | --- |
| Docker, Linux natif extraction/protocole, réseau none | 72 | 0 | 0 |
| Docker, PostgreSQL natif + concurrence + politiques + IA/SMTP | 223 | 6 | 0 |
| React/Vitest | 52 | 0 | 0 |
| Node/BFF | 50 | 0 | 0 |
| Windows, compatibilité SMTP/anti-abus après extension du helper | 15 | 0 | 0 |
| TypeScript/Vite | — | — | Build réussi |
| Docker intégré final | 9 jalons | 0 | 0, dont deux vrais parcours Chromium |
| WSL Python 3.12.3, suite Python complète | 750 | 24 | 0 |
| Dockerfile API exact hors ligne | — | — | Échec d'installation des dépendances, décrit ci-dessus |
| CI distante, images publiées, SMTP/B2 réels, production | — | — | Non exécutés, interdits dans cette phase |

Les six ignorés PG sont les quatre restaurations et deux altérations Docker du
harnais 14.4 exigeant son `TEST_SNAPSHOT_COMPOSE`. Ils ne sont pas comptés comme
réussis ; la recette intégrée apporte sa propre restauration réelle. Les neuf cas
de concurrence PG et le verrou natif 14.2 sont réellement exécutés. Les deux recettes
utilisent des états neufs ou une reprise explicite, pas des résultats cumulés fictifs.
Windows complet n'est pas relancé : résultat 14.5 **710 réussis/64 ignorés** conservé
comme antérieur. Les tests E2E 14.5 ne sont pas attribués à cette nouvelle stack ;
les navigateurs réellement exécutés ici utilisent Traefik et le sandbox Linux.

Commandes principales exécutées :

```powershell
npm.cmd run test:ui
npm.cmd run test:bff
npm.cmd run build
docker --host npipe:////./pipe/dockerDesktopLinuxEngine build --pull=false --network none -f ops/testing/Dockerfile.beta-recipe --target api -t documind-s14-6-api:local .
# Même Dockerfile, targets web et proofs, tags locaux correspondants.
.\.venv\Scripts\python.exe ops/testing/prepare_beta_recipe.py s14-6-recipe-b17c
# Compose utilisé exclusivement avec --env-file var/s14-6-recipe-b17c/fictitious.env
# et -p documind-s14-6-recipe-b17c : base neuve, upgrade head, close --execute, up --wait.
.\.venv\Scripts\python.exe ops/testing/validate_beta_recipe.py var/s14-6-recipe-b17c --execute-local-recipe
```

Les campagnes PG et confinement utilisent `documind-s14-6-proofs:local`, readonly,
`no-new-privileges`, capacités supprimées, mémoire 1536 Mio, deux CPU, 64 PID, tmpfs
256 Mio. Native : `--network none`, fichiers `test_extraction_linux.py` et
`test_extraction_protocol.py`. PG : uniquement réseau data du projet, base neuve
`documind_s14_6_tests`, sélection public/concurrence/state/autorisation/IA/déploiement/
snapshot/email. Les tests ne disposent d'aucun secret ou client IA réel.

La suite WSL complète dure 1 084,82 secondes ; ses 24 ignorés sont les dix cas PG,
six snapshots Docker et huit E2E 14.5 opt-in. Les dix cas PG passent dans la campagne
PG dédiée (126,54 s). Les 72 preuves Docker natives passent en 10,48 s. Les six
snapshots du harnais 14.4 ne sont pas réexécutés : la nouvelle recette valide ses
propres archives/restaurations v2 et la compatibilité v1, sans les compter comme
six tests réussis par substitution. Les neuf jalons intégrés ne sont pas des cas
pytest à additionner aux suites. L'avertissement Starlette/httpx antérieur reste visible.

La campagne finale `b17c` atteint les neuf jalons depuis un quota initial zéro fermé,
sans reprise ni remise à zéro intermédiaire : deux navigateurs, cinq admissions,
fermeture/redémarrage, v1/v2, restauration/scellement et logs expurgés. La première
campagne conserve séparément son 429 de harnais et sa reprise après le compte initial.

## 9. Contrôles manuels et critères d'arrêt

La checklist et les commandes futures se trouvent dans le
[runbook 14.7](SPRINT_14_7_PUBLIC_BETA_OPENING_RUNBOOK.md), **non exécuté**.
Il faut encore : correctif/validation du refus de rollback vulnérable, CI exacte,
recette des digests publiés sur Linux 6.12/ABI 6, approbation du risque SMTP RAM,
preuve SMTP réel, textes légaux approuvés, sauvegarde B2 récente/restauration isolée,
contrôle des alertes, flags effectifs et capacité restante réelle.

L'opératrice doit vérifier TLS/authentification SMTP, expéditeur, SPF/DKIM/DMARC,
réception et indésirables d'une boîte autorisée, domaine des liens, renvoi et absence
de tokens dans les logs. Aucun email externe n'est autorisé par ces documents.
Mentions, confidentialité, CGU/version, identité/coordonnées, durées de conservation/
suppression et accessibilité nécessitent validation humaine ; rien n'est inventé.

| Priorité | Point restant | Décision nécessaire |
| --- | --- | --- |
| Bloquant technique | B14-10 : précédent applicatif non certifié sur seule compatibilité 0007. | Corriger et tester les chemins manuel et automatique avant livraison publique. |
| Bloquant avant livraison/ouverture | Builds CI exacts et digests publiés non testés ici ; Linux 6.12/ABI 6 et provider Traefik Docker non reproduits exactement. | CI puis recette de la version réellement destinée à la production. |
| Bloquant opératrice | SMTP réel, textes légaux, sauvegarde B2/restauration et état réel des alertes/flags non vérifiés. | Preuves autorisées et décision humaine, aucune hypothèse de réussite. |
| Sous acceptation explicite | File RAM, perte au restart, reset distribué, limites NAT, place consommée en attente. | Accepter pour cinq admissions sous surveillance ou faire un correctif ciblé avant ouverture. |
| Non bloquant pour la revue locale | Avertissement Starlette/httpx, émulation mobile limitée, overlays uniquement destinés aux tests. | Conserver les limites documentées ; aucune prétention de certification publique. |

RF10-03 (chaîne de build/dépendances) doit aussi être réexaminé pour cette nouvelle
publication ; l'acceptation historique d'une seule exécution privée ne vaut pas
pour une ouverture publique. Aucun audit CVE distant nouveau n'est revendiqué.

## 10. Modifications 14.6 et verdict

Ajouts de recette : `compose.public-beta-test.yaml`,
`ops/testing/Dockerfile.beta-recipe` et son `.dockerignore`,
`ops/testing/traefik-public-beta-test.yaml`, scripts `prepare_beta_recipe.py`,
`validate_beta_recipe.py`, `cleanup_beta_recipe.py`, fixtures SMTP et relais TCP,
les deux rapports 14.6/14.7. Extensions compatibles de `tests/fake_smtp.py` et
`tests/fixtures/public_beta_browser.mjs`. Aucun code applicatif, workflow, migration,
politique Landlock/seccomp ou unité systemd n'est changé dans ce lot.

Les deux projets ont été nettoyés avec contrôle préalable des labels et identifiants :
huit conteneurs, trois réseaux et le seul volume documentaire propre à chacun.
Les filtres finaux `documind.test=sprint-14-6` ne retournent plus de conteneur, réseau
ou volume. Aucun fichier existant n'est supprimé ; les preuves fictives restent
dans `var/`, ignoré. Les trois images locales de recette sont conservées pour revue,
sans publication. AST Python, syntaxe Node, YAML et `git diff --check` réussissent.

**No-Go pour l'ouverture et pour considérer le dossier de livraison comme clos.**
B14-10 empêche de certifier le refus automatique d'un ancien rollback vulnérable.
La recette locale améliore les preuves, mais ne remplace pas les images CI exactes,
le contexte Linux 6.12/ABI 6 ni les validations opératrice. Les risques de file RAM
nécessitent une décision explicite. Les inscriptions de production et l'IA restent
désactivées ; aucune action du runbook ne doit être exécutée sans nouvelle autorisation.

## Annexe — Inventaire initial exact

- `.github/workflows/ci.yml`
- `.github/workflows/deploy.yml`
- `backend/account_admin.py`
- `backend/account_api.py`
- `backend/ai/api.py`
- `backend/ai/providers.py`
- `backend/ai/settings_api.py`
- `backend/public_registration.py`
- `backend/rag/indexing.py`
- `backend/rag/providers.py`
- `frontend/server/app.mjs`
- `frontend/server/app.test.mjs`
- `frontend/src/components/Assistant.tsx`
- `frontend/src/pages/AISettings.tsx`
- `frontend/src/pages/Account.tsx`
- `frontend/src/pages/CompareDocuments.tsx`
- `frontend/src/pages/IntelligentLibrary.tsx`
- `frontend/src/pages/PublicBeta.test.tsx`
- `frontend/src/pages/Rag.test.tsx`
- `frontend/src/services/account.ts`
- `tests/test_byok.py`
- `tests/test_deployment.py`
- `tests/test_openai_provider.py`
- `tests/test_public_beta.py`
- `tools/backup_local.py`
- `tools/deploy_production.py`
- `tools/prepare_production.py`
- `tools/validate_restore.py`
- `tools/verify_snapshot.py`
- `docs/SPRINT_14_1_PUBLIC_BETA_AUDIT.md`
- `docs/SPRINT_14_2_PUBLIC_BETA_AUTHORIZATION_REPORT.md`
- `docs/SPRINT_14_3_AI_DISABLED_ENFORCEMENT_REPORT.md`
- `docs/SPRINT_14_4_PUBLIC_BETA_QUOTA_CONCURRENCY_REPORT.md`
- `docs/SPRINT_14_5_PUBLIC_BETA_UX_EMAIL_ABUSE_REPORT.md`
- `frontend/src/pages/AISettings.test.tsx`
- `frontend/src/services/registration.test.ts`
- `tests/fake_smtp.py`
- `tests/fixtures/public_beta_browser.mjs`
- `tests/fixtures/public_beta_gateway.mjs`
- `tests/test_ai_disabled_enforcement.py`
- `tests/test_public_beta_authorization.py`
- `tests/test_public_beta_email_abuse.py`
- `tests/test_public_beta_email_e2e.py`
- `tests/test_public_beta_postgresql_concurrency.py`
- `tests/test_public_beta_snapshot.py`
- `tests/test_public_beta_state.py`
- `tools/public_beta_policy.py`
