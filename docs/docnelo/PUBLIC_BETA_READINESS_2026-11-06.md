# Docnelo : preparation de la beta publique a 10 comptes

Date : 2026-11-06. **Verdict : candidat local qualifie sur les parcours cibles ; ouverture de production NON autorisee et NON encore prete.**

Les obstacles restants sont explicites ci-dessous. Aucune connexion au VPS, modification de base de production, ouverture des inscriptions, publication d'image, fusion ou creation de commit n'a ete effectuee.

## 1. Decisions et limites du travail

- Decision confirmee : **10 admissions publiques cumulatives**, comptes publics existants inclus. Les comptes `legacy` et `invite` sont exclus.
- Un compte en attente, refuse, desactive ou supprime ne rend jamais sa place.
- Verification de l'e-mail **et** approbation administrative requises avant connexion.
- Admissions simples transactionnelles PostgreSQL, sans extension des preuves de sauvegarde. Les protections existantes de quarantaine, d'effacement et de reprise sont conservees.
- Aucun travail VSS A/B repris. Aucun fichier de preuve hors depot consulte ou modifie. Les sorties de commande et fichiers temporaires de tests ne constituent pas une consultation de ces preuves.
- Docker Desktop a ete autorise explicitement pour une base locale jetable. Aucun conteneur tiers n'a ete modifie.

## 2. Etat Git observe avant intervention

Racine : `C:\Users\Adeline\Documents\DocuMind_AI`.

Branche active : `branding/docnelo`, HEAD `1bc1a4a5bb49395acabdce5e7604d1a6b97dea61`.
Index vide ; **44 fichiers suivis modifies** et **4 209 fichiers non suivis** lors de l'inventaire detaille initial. Les nombreux fichiers sous les livraisons ne sont pas assimilables a des fichiers jetables.

Les references distantes ont ete verifiees par `git ls-remote`, sans fetch/prune :

- `origin/main` et distant `main` : `9b26006a2f8cfa3185580de66c671d419ad24dd6`.
- `origin/preparation/sprint-14-review` et distant correspondant : HEAD local ci-dessus.
- La branche active diverge de `origin/main` : 1 commit distant absent et 2 commits locaux absents du distant. Ne pas fusionner automatiquement dans ce worktree sale.
- La branche locale `main` est en retard de 8 commits sur `origin/main`.

### Branches : divergence par rapport a origin/main

Les colonnes indiquent respectivement les commits presents seulement sur `origin/main` et seulement sur la branche.

| Branche | Distant seul | Branche seule |
|---|---:|---:|
| branding/docnelo | 1 | 2 |
| preparation/sprint-14-review | 1 | 2 |
| branding/docnelo-public-beta-web-r1 | 7 | 1 |
| branding/docnelo-public-beta-web-r2 | 1 | 4 |
| preparation/docnelo-public-beta-lifecycle-10 | 27 | 8 |
| fix/long-summary-windows-ci | 9 | 1 |
| main | 8 | 0 |
| preparation/sprint-13-public-beta | 9 | 0 |
| preparation/sprint-14-2-public-beta-authorization | 8 | 0 |
| preparation/sprint-14-3-ai-disabled-enforcement | 8 | 0 |
| preparation/sprint-14-4-quota-concurrency | 8 | 0 |
| preparation/sprint-14-5-ux-email-abuse | 8 | 0 |
| preparation/sprints-7-10 | 16 | 0 |
| security/sec10-03-gateway-auth | 13 | 0 |
| security/sec10-04-audit-logging | 12 | 0 |

Commits locaux propres a la branche active : `d9ce98f` et `1bc1a4a`. Commit distant absent de celle-ci : `9b26006`.
Autres travaux non fusionnes identifies : `c1a3de9` (CI Windows), `22b6428` (Web R1), `fa02986` et `b046e5d` (Web R2), et les huit commits jusqu'a `8b11d4d` sur la branche lifecycle. Leur presence n'autorise ni cherry-pick ni suppression.

### Worktrees

Les quatre worktrees de livraison etaient propres, y compris les fichiers non suivis :

| Chemin relatif | Reference | HEAD |
|---|---|---|
| `deliveries\docnelo-lifecycle-10-api\source` | preparation/docnelo-public-beta-lifecycle-10 | 8b11d4d |
| `deliveries\docnelo-signup-e2e-lab\source` | HEAD detache | b046e5d |
| `deliveries\docnelo-web-branding-r1\source` | branding/docnelo-public-beta-web-r1 | 22b6428 |
| `deliveries\docnelo-web-branding-r2\source` | branding/docnelo-public-beta-web-r2 | b046e5d |

Le worktree principal contient des modifications preexistantes entremelant branding, profils Lite, cycle de vie, restauration, dependances et recettes de test. Elles ont ete conservees, pas attribuees a cette intervention.

Etat final local : meme branche et meme HEAD, index toujours vide, **59 fichiers suivis modifies et 4 212 fichiers non suivis**. Les trois nouveaux fichiers non suivis crees pour cette intervention sont la migration `0008`, `tests\test_public_beta_approval.py` et ce rapport ; les autres existaient deja. Les corrections s'ajoutent aux modifications preexistantes, sans les annuler.

## 3. Nettoyage propose et operations realisees

**Aucune suppression, aucun deplacement, aucun nettoyage Git destructif, aucun retrait de branche ou worktree.**

| Chemins | Classification et proposition, soumises a validation avant retrait |
|---|---|
| `.tmp-docnelo.patch`, `.tmp_patch_backup_local.py`, `.tmp_patch_backup_local_v4_v5.py`, `.tmp_patch_validate_restore.py`, `.tmp_patch_verify_snapshot.py`, `.tmp_rework_backup_local_keys_flag.py` | Candidats temporaires ; verifier d'abord que leur contenu est repris dans les sources. Conserver en attendant validation. |
| `.gitconfig.codex` | Configuration locale a examiner avant toute decision ; ne pas publier ou retirer aveuglement. |
| `deliveries\` | 1 620 fichiers non suivis a l'inventaire, plus les worktrees enregistres ; historique de livraisons a conserver. |
| `exports\` | 1 177 fichiers non suivis ; anciens exports et archives avec sommes de controle. Proposer archivage hors chemin de build seulement apres validation. |
| `candidates\` | 766 fichiers non suivis ; ne pas assimiler a un cache sans selection du candidat officiel. |
| `qualification\` | 510 fichiers non suivis ; preuves de qualification a conserver jusqu'a decision explicite. |
| `docnelo-lab-wheels\`, `pgvector-bundle.zip`, `pgvector.sig` | Materiaux hors ligne/signatures potentiellement necessaires a une reproduction ; pas de retrait sans verification des usages. |
| `DOCNELO_*.md`, `DOCUMIND_*.md`, `PHASE_15_*.md`, `P4_B1_*.md`, `docs\docnelo\` | Rapports/runbooks historiques ; deduplication documentaire proposee, pas de suppression automatique. |
| `var\`, `.pytest_cache\`, `__pycache__\`, `frontend\test-results\` | Melange possible de caches, logs, donnees et preuves. Certains sous-repertoires var/cache refusent l'acces ; pas de changement de permissions ni d'effacement. |
| `frontend\dist\`, `frontend\tsconfig.tsbuildinfo`, `build\`, `documind_ai.egg-info\` | Sorties regenerables, deja ignorees. Conservees ; le build frontend les regenere normalement. |
| `.venv\`, `frontend\node_modules\` | Necessaires aux commandes locales ; ne pas supprimer pendant la qualification. |

Operations reversibles realisees :

- `.gitignore` protege desormais le futur fichier secret `.env.public-beta`.
- `.dockerignore` exclut les livraisons, exports, candidats, qualifications, roues de laboratoire, archives et rapports historiques du contexte backend. Sources, migrations, tests, locks, `build-materials\pgvector.json` et outils de build restent disponibles.
- Les fichiers existants, y compris les sources non suivies `backend\lite_*.py`, `backend\lifecycle_bootstrap.py`, `tools\lifecycle_key_policy.py`, `tools\restore_pgvector.py`, et les assets de marque, sont conserves : certaines sont des dependances reelles du candidat courant, pas du rebut.
- Aucun `git add`, commit, push, merge, checkout, clean, reset ou prune.

## 4. Audit et corrections

### Inscription et quota

`backend\public_registration.py` conserve une transaction unique : increment conditionnel du compteur SQL, creation utilisateur/espace/appartenance/budget/jeton, puis commit. Les erreurs transactionnelles annulent aussi la reservation. L'UPDATE de la meme ligne serialise les instances concurrentes et la fermeture administrative.

Le plafond serveur est maintenant **10**, meme si une valeur plus grande est injectee apres construction des settings ; une configuration publique superieure a 10 est rejetee au chargement. Les options publiques annoncent la limite effective. Les reponses generiques restent identiques pour adresse deja connue, quota plein ou porte SQL fermee ; HTTP 202 n'est pas une confirmation de creation.

Le semaphore et les limites anti-abus peuvent refuser temporairement une demande avec 429/503. Ils ne constituent pas la garantie de quota : celle-ci vient de PostgreSQL, testee avec des connexions et instances independantes.

### Approbation et authentification

- `users.approved_at`, ajoute par migration `0008`, reste NULL pour tous les comptes existants : aucune approbation automatique.
- `PUBLIC_REGISTRATION_REQUIRES_APPROVAL=true` par defaut.
- Approbation locale uniquement : `python -m backend.account_admin public-account approve UUID`. Simulation sans `--execute`.
- L'approbation exige un compte public deja verifie, non bloque et sans demande de suppression. Elle ne modifie ni identite, ni espace, ni compteur.
- `reject --execute` bloque le compte, retire l'approbation et invalide ses jetons. Les sessions deviennent inutilisables lors du controle serveur suivant.
- Connexion et chaque authentification de session verifient la meme condition e-mail/approbation. Un jeton fabrique avant approbation ne permet pas de recevoir un upload.
- Une recuperation de mot de passe n'accorde pas l'approbation.
- Les comptes historiques et sur invitation gardent leur fonctionnement existant.

Les messages UI ne promettent plus une connexion immediate apres verification d'e-mail ; le quota et les textes juridiques locaux indiquent dix admissions publiques.

### API et sessions

Conservation des gardes existantes : cle de service BFF distincte, transport HTTPS atteste par le BFF, cookie `__Host-` Secure/HttpOnly/SameSite, protection CSRF/origine/hote, jetons de session conserves cote serveur, controles d'appartenance documentaire et admission avant reception d'upload. Les tests de sessions, reset, logout, isolation des proprietaires, journalisation sans secrets et refus des API historiques passent.

Les sessions sont en memoire : **une instance API/un worker et une instance BFF** pour cette beta. Un redemarrage impose une reconnexion. La preuve multi-instance concerne le quota, pas une architecture de sessions distribuees.

### Reprise, effacement et IA

`PUBLIC_REGISTRATION_USE_LIFECYCLE_RECEIPTS=false` est une selection explicite du parcours d'admission SQL. Sa valeur par defaut reste true. Ce parametre ne desactive PAS `LIFECYCLE_DURABLE_RECEIPTS_REQUIRED`, la quarantaine ou les gardes d'effacement.

**Blocage conserve et verifie :** avec les gardes strictes actuelles et les mutations synthetiques desactivees, la suppression d'un document ou d'un compte peut rester indisponible (503). Ne pas contourner en desactivant globalement la durabilite ou en activant les mutations synthetiques. Prevoir une prise en charge administrative qualifiee et une information juridique exacte avant ouverture.

Aucun mode demo, API legacy ou fonction IA reactive. L'arret du worker IA est maintenant lie a son demarrage effectif, pas a un flag mutable : correction de 14 erreurs de fermeture de tests, sans demarrer de worker supplementaire.

### Messages

Le parcours existant envoie verification et reinitialisation par SMTP TLS ; les jetons sont a usage unique, hashes en base, avec mot de passe requis pour verifier l'e-mail. Les messages passent par une file en memoire bornee : un echec SMTP apres commit ne rend pas la place et exige un renvoi de verification. Le SMTP reel et sa delivrabilite restent a verifier sur l'environnement cible.

Pas de nouveau message automatique d'approbation. L'administrateur doit informer manuellement le testeur apres approbation.

### Livraison

Les politiques et attestations acceptent maintenant le schema `0008`, avec exactement 10 admissions, approbation explicite et profil SQL. Le schema `0007` reste limite au profil historique a 5.

Les digests, SHA, sommes de controle et approbation independante de la release restent requis. Les applications `0007` ne peuvent pas etre utilisees comme rollback sur une base `0008`.

Deux dependances deja presentes mais non suivies (`tools\lifecycle_key_policy.py`, `tools\restore_pgvector.py`) sont maintenant incluses dans le bundle de livraison ; le controleur embarque egalement son helper necessaire. Cela corrige l'import plat qui echouait avant cette intervention, sans modifier la logique de sauvegarde. Les anciens inventaires attestes restent acceptables uniquement en retour arriere, sous leurs controles existants.

L'import CSS de la palette a ete corrige pour que le build de production Windows resolve les assets de marque.

## 5. Migration 0007 vers 0008

- Ajout nullable de `approved_at`, sans changement de mots de passe, UUID, proprietaires, e-mails, dates historiques ou etats de desactivation.
- Compteur porte a `max(compteur historique, nombre de comptes publics presents)` ; jamais diminue. Les comptes historiques et sur invitation n'y sont pas ajoutes.
- Inscriptions fermees par la migration. Les comptes publics precedemment verifies attendent une approbation individuelle apres activation de la nouvelle politique.
- Une base ayant deja plus de dix admissions est preservee mais ne peut pas etre rouverte. Ne pas supprimer de comptes pour simuler de nouvelles places.
- Le downgrade est refuse apres des admissions publiques. Le retour arriere est applicatif, avec schema `0008` conserve.
- PostgreSQL reel : scenarios compteur sous-estime, compteur superieur au nombre de comptes restants, et historique deja superieur a dix verifies. L'upgrade repete est inoffensif.
- Des comptes publics deja supprimes alors que le compteur aurait ete perdu ne peuvent pas etre reconstruits a partir des seuls comptes presents : reconciliation administrative obligatoire.

## 6. Resultats des verifications

| Groupe | Resultat |
|---|---|
| Parcours comptes/API/beta, migrations et concurrence sous PostgreSQL 17.11, `--require-no-skips` | **201 passes, aucun saut ni echec** |
| Historique PostgreSQL / garde des comptes desactives | **1 passe, aucun saut** |
| Tests portables d'attestation et de deploiement | **164 passes, 4 sauts attendus** : PostgreSQL et privileges Linux, executes separement |
| Confinement natif Linux et protocole d'extraction, code courant monte en lecture seule dans une image de preuves locale | **73 passes** ; les 2 tests root selectionnes avec ce groupe ont ete sautes puis reexecutes comme root |
| Preuves Linux root : permissions et approbation independante | **2 passes, aucun saut** |
| Preuve Linux non-root : un registre non privilegie ne fait pas autorite | **1 passe, aucun saut** |
| Tests UI complets | **68 passes** |
| Tests BFF complets | **55 passes** |
| TypeScript et build Vite | Reussis |
| Build Docker backend, cible production | Reussi, image locale `docnelo-beta10-local:20261106` |
| Smoke de cette nouvelle image, utilisateur non-root, filesystem read-only, cap-drop ALL, sandbox Linux, PostgreSQL jetable | Migration `0008`, `health={"status":"ok","database":"ok"}`, porte SQL fermee, arret propre |
| Resolution Compose public beta avec valeurs de test | Reussie ; aucune creation de stack |
| Compilation Python et controle whitespace adapte aux CRLF | Reussis |

Image backend locale : `sha256:f4438f9719cdde76088bda1d17cd91aacc1cdca2d4e4b4dc2c0f874bd1854b2c`. Ce n'est ni un digest de registre ni une release approuvee.

Le seul conteneur PostgreSQL cree pour cette session (`docnelo-beta10-20261106-fd598d90`) a ete arrete puis retire automatiquement, sans volume persistant. Les conteneurs de qualification ponctuels ont aussi ete retires. L'image backend locale est conservee, sans push. Les sorties de tests restent dans les sous-repertoires ignores `var\beta10-*` ; aucun ancien livrable n'a ete efface.

Les premieres executions ont revele le build CSS, l'arret d'un worker jamais demarre et l'absence de helpers dans le bundle ; ces problemes ont ete corriges et revalides. L'avertissement de deprecation httpx/TestClient reste non bloquant. La suite complete du depot et le navigateur E2E HTTPS avec le SMTP reel n'ont pas ete executes ; aucune CI distante n'a ete declenchee.

Les tests couvrent : inscription valide, attente, refus, approbation simulee/executee, connexion apres approbation, refus d'acces avant approbation, recuperation sans contournement, dix admissions, absence de recyclage, deux vraies inscriptions concurrentes pres du plafond, rollback transactionnel, fermeture/reouverture et course fermeture/inscription.

## 7. Configuration exacte du profil a 10

Source : `.env.public-beta.example`. Les exemples restent **fermes par defaut**, sans identite juridique declaree valide et sans ancienne image preselectionnee.

```dotenv
APPLICATION_PROFILE=standard
REGISTRATION_MODE=disabled
PUBLIC_REGISTRATION_LIMIT=10
PUBLIC_REGISTRATION_REQUIRES_APPROVAL=true
PUBLIC_REGISTRATION_USE_LIFECYCLE_RECEIPTS=false
PUBLIC_REGISTRATION_PER_HOUR=10
PUBLIC_CHALLENGE_DIFFICULTY=12
PUBLIC_VERIFICATION_TTL_SECONDS=3600
AI_ENABLED=false
OWNER_DEMO_ENABLED=false
LEGACY_API_ENABLED=false
API_KEYS={}
LIFECYCLE_DURABLE_RECEIPTS_REQUIRED=true
LIFECYCLE_SYNTHETIC_MUTATIONS_ENABLED=false
```

Le changement ulterieur en `REGISTRATION_MODE=public` est une autorisation distincte, insuffisante a elle seule pour ouvrir la porte SQL.

A renseigner et verifier : images backend/frontend/PostgreSQL par digest de release, `POSTGRES_PASSWORD`, `BFF_SERVICE_KEY` independante d'au moins 32 caracteres, `APP_HOST`, `ACCOUNT_BASE_URL=https://APP_HOST`, IP effective du proxy BFF, SMTP TLS et expediteur, identite/contact exploitant, URLs HTTPS des documents et version des CGU. `PUBLIC_LEGAL_READY` reste false jusqu'a validation humaine.

Conserver exactement le projet Compose, les volumes, la version majeure PostgreSQL, les chemins lifecycle et le fichier de quarantaine de l'installation existante. Ne pas copier un exemple pour recreer silencieusement une base neuve. Ne jamais positionner automatiquement un fichier de reprise a `ready`.

## 8. Procedure de deploiement et verification (preparee, NON executee)

### Conditions prealables

1. Selectionner et relire le delta de release parmi les modifications existantes. Inclure les sources non suivies reellement importees, les assets, les helpers, la migration et ce rapport ; pas les anciens exports. Faire relire puis committer sur une branche de livraison propre, sans fusion aveugle des autres worktrees.
2. Executer la CI Linux/Windows/PostgreSQL et frontend sur le SHA exact, publier les trois images par digest et produire un bundle atteste. L'approbation independante du registre de confiance reste obligatoire, jamais auto-accordee.
3. Identifier la stack VPS reelle, ses volumes, son schema, ses digests actifs et ses gardes existantes. Cette identification distante n'a pas ete faite ici.
4. Valider les documents juridiques, la retention et le traitement administratif des demandes d'effacement actuellement bloquees. Tester le SMTP cible, les domaines/DNS/TLS et le parcours navigateur complet en environnement isole.
5. Fermer explicitement les inscriptions et relever les effectifs/compteurs avant migration. Utiliser uniquement la sauvegarde operationnelle existante si elle est deja qualifiee ; aucune nouvelle architecture VSS demandee. Si une protection existante refuse une operation, s'arreter et signaler ce refus.

### Commandes de reference, dans la stack existante

Exemple pour la stack geree `documind-prod`, **a adapter uniquement apres identification**, avec un fichier Compose de la nouvelle release approuvee. Pour une installation `documind-public-beta`, conserver ce projet et son fichier/env existants ; ne jamais interchanger leurs volumes.

```text
docker compose --env-file .env.production -f compose.production.yaml -p documind-prod exec -T api python -m backend.account_admin public-registration status
docker compose --env-file .env.production -f compose.production.yaml -p documind-prod exec -T api python -m backend.account_admin public-registration close --execute
docker compose --env-file .env.production -f compose.production.yaml -p documind-prod exec -T db psql -X -v ON_ERROR_STOP=1 -U documind -d documind -c "SELECT registration_kind,count(*) FROM users GROUP BY registration_kind; SELECT id,issued_count,closed FROM public_registration_quota; SELECT version_num FROM alembic_version;"
```

La commande `close --execute` ci-dessus et toutes les commandes mutantes suivantes necessitent une confirmation explicite ; elles ne sont donnees que comme procedure.

Premiere etape : `REGISTRATION_MODE=disabled`, configuration cible a 10 preparee, services ecrivains arretes par le deploiement approuve, sauvegarde existante verifiee. Le workflow gere doit recevoir `initialize=false` et `allow_migration=true` pour passer de `0007` a `0008`. Ne pas demander une preparation publique avant cette migration fermee.

Commande de migration utilisee par ce deploiement, uniquement avec l'image API candidate :

```text
docker compose --env-file .env.production -f compose.production.yaml -p documind-prod run --rm --no-deps -T --entrypoint alembic api upgrade head
```

Verifier `alembic_version=0008`, porte `closed=true`, compteur superieur ou egal au releve initial et au nombre de comptes publics presents, `approved_at IS NULL` sur les comptes non encore revus. Ne pas effectuer d'approbation de masse.

Redemarrer uniquement API/BFF dans le deploiement controle, un exemplaire chacun. Exiger les healthchecks db/api/web et verifier :

```text
curl --fail --silent --show-error https://DOMAINE/bff/health
curl --fail --silent --show-error https://DOMAINE/bff/auth/options
```

Verifier aussi : page login disponible, `/bff/documents` sans session refuse, pas de port API/DB public, API legacy/demo/IA refusees. Une sante verte ne prouve ni le SMTP ni l'acceptation juridique ni la disponibilite des effacements.

Deuxieme etape, **sur nouvelle confirmation** : passer en public avec les documents effectivement valides, lancer la preparation publique approuvee sur schema `0008` (`approve_public_beta=true`, `allow_migration=false`, `initialize=false`). Cette preparation exige toujours la porte SQL fermee et ne l'ouvre jamais.

Apres verification du compteur historique, du traitement des demandes de donnees et du fichier de reprise autorise, nouvelle decision explicite d'ouverture :

```text
docker compose --env-file .env.production -f compose.production.yaml -p documind-prod exec -T api python -m backend.account_admin public-registration reopen
docker compose --env-file .env.production -f compose.production.yaml -p documind-prod exec -T api python -m backend.account_admin public-registration reopen --execute
```

Apres inscription et verification de l'adresse, relever localement l'UUID du compte public (SQL administratif), examiner la demande et executer individuellement :

```text
python -m backend.account_admin public-account status UUID
python -m backend.account_admin public-account approve UUID
python -m backend.account_admin public-account approve UUID --execute
```

Ces trois commandes sont a lancer dans le conteneur API comme les commandes d'administration precedentes. Tester la connexion, l'import TXT/PDF, l'analyse classique et l'isolation d'espace. Informer manuellement le testeur apres approbation.

Ne pas creer dix faux comptes en production pour tester la limite : les places ne se recyclent pas. Les tests de saturation/concurrence ont ete effectues uniquement sur la base jetable.

### Retour arriere

Fermer immediatement la porte SQL avec `close --execute`, puis remettre le mode disabled dans l'environnement controle. Cela ne supprime ni les comptes ni les places.

Conserver PostgreSQL et tous les volumes. Revenir uniquement a une image **explicitement compatible schema 0008**, attestation et approbation independante verifiees, sans downgrade de base. Si aucune image precedente compatible n'existe, maintenir le service ferme/maintenance et livrer un correctif ; ne pas relancer une ancienne application `0007` qui ignore l'approbation.

Une restauration de base, si elle devient necessaire, est une procedure separee sous quarantaine existante. Le compteur SQL seul ne protege pas contre un retour a une ancienne copie : reconcilier les admissions historiques, y compris comptes supprimes, avant toute nouvelle ouverture. Ne jamais remettre le compteur a zero ou abaisser sa valeur.

## 9. Conditions restantes avant GO

| Condition | Etat |
|---|---|
| Quota serveur/concurrence, approbation et migrations | Qualifies localement |
| Configuration fermee, raccord du bundle/schema, builds et sante de l'image | Prepares et testes localement |
| Depot selectionne, propre, commit de release et CI distante verte | A faire ; aucun commit automatique |
| Identification et inventaire reels de l'installation et des comptes existants | Non effectues |
| SMTP reel, DNS/HTTPS, parcours navigateur sur candidat deploye | A verifier |
| Documents juridiques et politique de donnees effectivement approuves | Non attestes par ce travail |
| Prise en charge qualifiee des demandes d'effacement avec les gardes conservees | Bloquante tant qu'absente |
| Confirmation explicite de migration, deploiement et ouverture | Non donnee |

**Conclusion : le candidat local est techniquement avance et les cas critiques demandes passent, mais annoncer la production prete ou ouvrir les inscriptions maintenant serait premature. Aucun besoin de reprendre le chantier VSS A/B pour constater ou traiter ces conditions.**
