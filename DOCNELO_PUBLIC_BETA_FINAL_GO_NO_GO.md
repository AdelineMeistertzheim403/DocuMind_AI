# Docnelo - decision finale de preparation de la beta publique

Date : 2026-11-06. Reference historique : `docs\docnelo\PUBLIC_BETA_READINESS_2026-11-06.md`.

**Verdict : NO-GO pour l'ouverture.** Le candidat de livraison selectionne est qualifie localement, mais aucun chemin d'effacement physique standard, autorise et operationnel, n'a ete trouve. La procedure ci-dessous assure une reception administrative tracable ; elle ne remplace pas l'effacement et ne leve donc pas ce blocage. SMTP/HTTPS reels, inventaire VPS, validation juridique et CI distante restent aussi a confirmer.

Les inscriptions restent fermees : `REGISTRATION_MODE=disabled`, porte SQL `closed=true`. Aucun acces VPS, changement de production, push, publication d'image ou lancement de workflow distant n'a ete effectue. Aucun fichier de preuve hors depot n'a ete modifie. Aucun chantier VSS A/B n'a ete repris.

## 1. Blocages resolus et subsistants

| Point | Resultat |
|---|---|
| Dix admissions publiques cumulatives | Qualifie sur PostgreSQL reel : pending, refus et suppressions consomment leur place ; legacy/invite exclus ; course au dernier emplacement et fermeture serialisees en SQL. |
| Verification et approbation | E-mail puis revue administrative obligatoires ; refus des connexions et sessions non approuvees ; reset du mot de passe sans contournement. |
| Migration des donnees existantes | 0008 additive, aucune approbation automatique, compteur jamais abaisse et porte fermee ; historiques superieurs a dix conserves, sans nouvelle admission. |
| Selection Git | Nouveau worktree isole, sans fusion, imports Lite retires et changements historiques de sauvegarde exclus du delta. |
| Textes et effets UI | Aucune annonce d'effacement sur 503 ; suppression du parcours Lite du candidat. Nouveau brouillon de CGU sans alteration des deux versions archivees. |
| Effacement physique documents/comptes | **BLOQUANT** : protections fail-closed conservees. Reception administrative possible, execution finale non disponible. |
| Systeme de suivi administratif reel et delais | A faire approuver/provisionner ; les tests ne prouvent pas l'existence d'une permanence ou d'un registre externe sur le VPS. |
| Production existante | Non inspectee : projet, volumes, images, schema, compteurs, latch et autorites restent inconnus. |
| SMTP/HTTPS reels et documents juridiques | Non attestes ; les preuves locales utilisent uniquement certificats et adresses fictifs. |
| Integration Git, CI, images attestees et confiance independante | Preparees, non executees a distance ; la branche n'est pas automatiquement publiable ou deployable. |

### Cause des 503

- `backend\services\documents.py::delete_document` appelle `require_synthetic_mutation` avant toute suppression SQL ou fichier.
- `backend\account_api.py::deletion` appelle la meme garde avant le recu, la ligne `DeletionRequest`, la desactivation et la revocation des sessions. Un 503 ne signifie donc **pas** que la demande est enregistree.
- Avec `LIFECYCLE_DURABLE_RECEIPTS_REQUIRED=true` et `LIFECYCLE_SYNTHETIC_MUTATIONS_ENABLED=false`, ce refus est intentionnel. `purge_account`, `_purge_account` et l'execution de purge des comptes en attente refusent egalement le traitement strict. Les effacements derives restent proteges.
- La confirmation HMAC locale existante utilise des transitions synthetiques ; sa presence ne constitue pas une autorite operationnelle de production.
- Le chemin administratif operationnel experimental `lite_deletions` exige un autre profil, sur invitation, a cinq admissions, avec ses propres autorites. Le reutiliser directement violerait le profil public/10. Il n'est pas embarque.

**Aucun DELETE/unlink administratif brut, changement de flag de durabilite, activation synthetique ou passage en Lite n'est propose.** Un simple ticket, une commande `reject` ou une desactivation ne prouvent pas l'effacement. Resoudre l'execution exige une autorite administrative non synthetique et une qualification ciblee supplementaire ; ce rapport ne pretend pas les avoir implementees.

## 2. Livraison Git selectionnee

Branche : `release/docnelo-public-beta-10-20261106`.

Worktree : `deliveries\docnelo-public-beta-release-20261106\source`.

Base exacte : `1bc1a4a5bb49395acabdce5e7604d1a6b97dea61`. Le commit local de livraison est celui contenant le present rapport, identifiable par :

```powershell
git rev-parse release/docnelo-public-beta-10-20261106
git diff --name-status 1bc1a4a5bb49395acabdce5e7604d1a6b97dea61 release/docnelo-public-beta-10-20261106
```

Le worktree original reste sur `branding/docnelo`, au meme HEAD, avec ses 59 fichiers suivis modifies et son index non stage. Ses fichiers non suivis sont conserves ; le present rapport y est egalement copie pour consultation. Les quatre anciens worktrees sont conserves. Les references observees precedemment montrent une divergence avec `origin/main` : aucune fusion/rebase automatique n'a ete tentee.

### Inventaire exact du delta de livraison

Les sources et dependances deja suivies dans la base restent presentes. Les chemins ajoutes ou modifies pour cette livraison sont :

```text
.dockerignore
.env.production.example
.github\workflows\ci.yml
.github\workflows\deploy.yml
.gitignore
DOCNELO_PUBLIC_BETA_FINAL_GO_NO_GO.md
backend\account_admin.py
backend\account_api.py
backend\ai\settings_api.py
backend\auth.py
backend\authentication.py
backend\config.py
backend\main.py
backend\public_registration.py
compose.production.yaml
docs\docnelo\PUBLIC_BETA_READINESS_2026-11-06.md
frontend\index.html
frontend\public\brand\docnelo\docnelo-business-dark-transparent.png
frontend\public\brand\docnelo\docnelo-business-transparent.png
frontend\public\brand\docnelo\docnelo-horizontal-dark-transparent.png
frontend\public\brand\docnelo\docnelo-horizontal-transparent.png
frontend\public\brand\docnelo\docnelo-icon-192.png
frontend\public\brand\docnelo\docnelo-icon-32.png
frontend\public\brand\docnelo\docnelo-icon-512.png
frontend\public\brand\docnelo\docnelo-icon-64.png
frontend\public\brand\docnelo\docnelo-icon-transparent.png
frontend\public\brand\docnelo\docnelo-tokens.css
frontend\public\brand\docnelo\favicon.ico
frontend\public\manifest.webmanifest
frontend\server\app.mjs
frontend\server\app.test.mjs
frontend\src\components\Assistant.tsx
frontend\src\components\Brand.tsx
frontend\src\components\Layout.tsx
frontend\src\components\Workspace.tsx
frontend\src\legal\documents.ts
frontend\src\pages\AISettings.tsx
frontend\src\pages\Account.tsx
frontend\src\pages\Legal.test.tsx
frontend\src\pages\PublicBeta.test.tsx
frontend\src\services\account.ts
frontend\src\services\api.ts
frontend\src\styles.css
frontend\src\test\app.test.tsx
frontend\src\types\api.ts
migrations\versions\0008_public_account_approval.py
tests\fixtures\public_beta_browser.mjs
tests\test_lifecycle.py
tests\test_public_beta.py
tests\test_public_beta_approval.py
tests\test_public_beta_authorization.py
tests\test_public_beta_email_e2e.py
tests\test_public_beta_postgresql_concurrency.py
tests\test_release_security.py
tools\deploy_production.py
tools\public_beta_policy.py
tools\release_manifest.py
tools\release_security.py
```

Le branding existant et ses assets sont repris pour conserver une interface Docnelo compilable. Le point BFF `ui-config`, necessaire au libelle d'environnement existant, passe par les gardes Host/origine et ne publie que ce libelle. Aucune nouvelle fonction documentaire ou IA.

**Exclus du delta :** modules/outils/tests `lite_*`, modifications locales de `backup_local`, `verify_snapshot`, `validate_restore`, `restore_pgvector`, `lifecycle_key_policy`, recettes VSS, anciens exports, qualifications, logs, captures, archives et autres livrables/worktrees. Les outils de sauvegarde deja suivis dans la base ne sont ni redeveloppes ni retires ; l'inventaire du bundle reste celui de cette base. Les manifests et attestations sont uniquement adaptes au schema 0008. Le profil de securite existant, les digests, l'identite CI et la confiance independante restent obligatoires.

Le rapport historique de reference est conserve comme historique : ses resultats, chemins d'exemples et dependances du candidat melange ne remplacent pas la presente selection. `.env.public-beta.example` et `compose.public-beta.vps.yaml` experimentaux ne sont pas repris ; cette livraison vise l'installation geree existante via `compose.production.yaml` et son `env_file`.

Nettoyage realise : isolation par copie selective et exclusions du contexte Docker. **Aucune suppression** de branche, worktree, fichier non suivi ou ancien livrable. Les preuves locales dans `var` et les images de qualification sont conservees, hors commit.

## 3. Qualification du candidat selectionne

| Groupe | Resultat final |
|---|---|
| PostgreSQL : approbation, quotas, vraies connexions concurrentes, comptes, gateway, audit, abus et autorisation de release | **201 passes, aucun saut** |
| Regressions portables : livraison, sauvegarde existante, lifecycle, durabilite et quarantaine | **340 passes, 21 sauts attendus** PostgreSQL/POSIX/root dans cette execution Windows ; ne vaut pas suite complete Linux. |
| Groupe natif obligatoire PostgreSQL de la CI : protocole existant, temoin concurrent, inventaire readonly, commit incertain et historique de release | **27 passes, aucun saut** |
| Extraction et protocole natifs Linux sur les sources selectionnees | **73 passes, aucun saut** |
| Autorite et permissions root / refus d'autorite non-root | **2 + 1 passes, aucun saut** |
| Navigateur Chromium desktop/mobile, HTTPS reel local, BFF reel, SMTP STARTTLS reel local ; plus six cas HTTP d'abus/reprise SMTP | **8 passes, aucun saut** |
| Reception administrative d'effacement idempotente, sans effet SQL et sans autorisation de purge | **1 passe, aucun saut** |
| Interface / BFF | **65 / 53 passes** |
| TypeScript/Vite, images Docker backend et frontend, compilation Python, whitespace et resolution Compose fermee | Reussis |
| Smoke de l'image backend non-root/read-only/cap-drop ALL, sandbox et PostgreSQL jetable | Migration **0008**, sante **ok/database ok**, compteur **0**, porte **fermee**, approbation active, durabilite active et synthetique inactif |

Le parcours navigateur prouve : inscription -> SMTP/TLS -> verification -> connexion refusee avant approbation -> approbation administrative SQL verrouillee -> connexion -> import TXT -> analyse classique -> refus IA -> demande de suppression documentaire **503** -> demande de compte **503** -> compte et document encore accessibles. C'est une preuve de preservation des protections, **pas** une preuve d'effacement reussi. Le test API controle aussi la conservation exacte du fichier et l'absence de `DeletionRequest` apres le refus.

Images locales uniquement :

- Backend `docnelo-release10-local:20261106` : `sha256:5f5656004ca999063b9820af922374fc1be5bc72a135bceb2618c4825e61bf61`.
- Frontend `docnelo-release10-web-local:20261106` : `sha256:7529fa56c1bbf40c3b6b97557205c12b7e780b24c07d11ca30a992a0fd5c2771`.

Ces IDs ne sont pas des digests publies, des attestations ou une approbation de deploiement. Le conteneur PostgreSQL jetable et le smoke ont ete arretes/retirees automatiquement, sans volume persistant. Aucun autre conteneur n'a ete arrete.

Les premieres executions ont revele des preconditions de test manquantes : repertoire temporaire Windows, fermeture SQL introduite par 0008 dans la fixture HTTPS, dependance cryptography de l'image de preuves et identite PostgreSQL isolee imposee par le protocole CI. Les relances ci-dessus passent apres preparation correcte, sans affaiblissement des gardes de production. Avertissement httpx/Starlette non bloquant. La suite exhaustive du depot et la CI distante n'ont pas ete executees.

### CI preparee, non declenchee

La CI exige les tests PostgreSQL d'approbation/concurrence et ajoute un groupe navigateur/SMTP avec `--require-no-skips`, Chromium et build frontend. Son execution ne dispose d'aucun SMTP reel ni de cle IA.

Commandes locales a executer **seulement apres validation de publication** :

```powershell
git push -u origin release/docnelo-public-beta-10-20261106
gh workflow run ci.yml --ref release/docnelo-public-beta-10-20261106
gh run list --workflow ci.yml --branch release/docnelo-public-beta-10-20261106 --limit 5 --json databaseId,headSha,status,conclusion,url
```

Verifier `headSha` contre le commit de livraison. Cette execution de branche ne publie pas d'images. Publication/deploiement exigent ensuite une integration **relue et autorisee** sur `main`, une nouvelle CI verte sur le SHA exact de `main`, les trois images par digest, le bundle atteste et son approbation independante. Ne pas reutiliser une ancienne CI verte d'un autre commit.

## 4. Procedure temporaire pour les demandes d'effacement

**Portee : reception et suivi fiables, pas execution physique. Tant qu'aucun executeur standard autorise n'est qualifie, l'ouverture reste interdite.** Aucun de ces gestes n'a ete execute sur des donnees reelles.

1. Designer un responsable et un suppleant, une boite de contact effectivement surveillee et un registre de suivi a acces restreint, independant de la base applicative et de ses restaurations. Approuver les delais de reponse et la retention avant ouverture. L'existence et la disponibilite de ce dispositif reel restent a verifier.
2. A reception, verifier l'identite de facon proportionnee via un canal connu. Ne jamais demander le mot de passe, un jeton de session ou le contenu du document par e-mail. Consigner une reference opaque, horodatage UTC, identifiants internes, perimetre document/compte, responsable, echeance et etat `recu - execution bloquee`. Ne pas mettre ces informations dans Git, les logs publics ou le present rapport.
3. Envoyer un accuse de reception manuel avec reference, etat exact et prochaine echeance. Expliquer qu'un 503 n'a pas enregistre automatiquement la demande, ni retire l'acces, ni efface les donnees. Ne jamais clore un ticket parce qu'une commande a simplement retourne sans erreur.
4. Pour une demande de compte, un operateur peut, **apres autorisation et verification des chemins existants**, utiliser le registre lifecycle deja provisionne afin d'obtenir un recu deduplique. Depuis un checkout administratif verifie des sources de cette release, avec Python et acces aux chemins canoniques prives :

   ```text
   python3 -m tools.lifecycle_admin --registry "$REGISTRY" --backup-lock "$LOCK" receive erasure --user-id "$USER_ID" --owner-id "$OWNER_ID"
   ```

   Cette commande ecrit seulement un recu `received`, pas une autorisation, une desactivation, une ligne SQL de demande ou un effacement. Sa sortie et sa relecture doivent etre conservees dans le dossier prive ; les retries rendent la meme reference. Ne jamais lancer `init` sur un chemin de production suppose. Si le registre, le verrou ou leurs permissions sont inconnus/invalides, rester sur le dossier administratif externe et escalader.

   Le bundle plat et l'image API n'embarquent pas `tools.lifecycle_admin` : ne pas inventer une commande `docker exec ... -m tools.lifecycle_admin`. Pour un document seul, garder son perimetre dans le dossier prive ; un recu d'effacement de compte ne doit pas etre utilise pour autoriser une purge de compte a la place.
5. Faire un inventaire **en lecture seule** du perimetre, de l'etat des traitements et des gels de conservation. Ne pas lever un hold, fabriquer une confirmation, ecrire `ready`, utiliser `public-account reject` comme substitut a la suppression, ni executer les purges legacy. Un recu non rapproche peut maintenir une reprise en quarantaine : il ne faut pas l'effacer pour rendre le service vert.
6. Affecter l'execution a l'administrateur responsable. **Point d'arret actuel : aucun executeur standard non synthetique disponible.** Maintenir le ticket ouvert, informer le demandeur de l'etat reel et traiter l'escalade suivant les obligations approuvees. Une reception bien tracee ne garantit pas a elle seule le respect du delai legal d'effacement.
7. La cloture future exigera une execution autorisee et des controles independants : absence des lignes et dependances du perimetre, absence des fichiers canoniques et residus temporaires, impossibilite d'acces, maintien du compteur cumulatif, verification des holds et recus/resultats rapproches. Traiter separement les sauvegardes, logs et retenues justifiees, avec delais approuves et prevention de reintroduction apres restauration. Ne pas annoncer un effacement de toutes les copies sans preuve.

Le test ajoute couvre l'etape de reception et son absence d'effets ; il ne valide ni une purge en production ni un futur executeur. La levee de ce blocage demande une decision et une qualification supplementaires, pas une desactivation des protections.

## 5. Configuration et deploiement prepares

### Configuration exacte, encore fermee

Le fichier `.env.production.example` de la release est un modele sans secrets. Completer **l'environnement existant**, sans remplacer ses chemins, credentials ou volumes :

```dotenv
APPLICATION_PROFILE=standard
REGISTRATION_MODE=disabled
PUBLIC_REGISTRATION_LIMIT=10
PUBLIC_REGISTRATION_REQUIRES_APPROVAL=true
PUBLIC_REGISTRATION_USE_LIFECYCLE_RECEIPTS=false
PUBLIC_REGISTRATION_PER_HOUR=3
PUBLIC_CHALLENGE_DIFFICULTY=12
PUBLIC_VERIFICATION_TTL_SECONDS=3600
AI_ENABLED=false
OWNER_DEMO_ENABLED=false
LEGACY_API_ENABLED=false
API_KEYS={}
LIFECYCLE_DURABLE_RECEIPTS_REQUIRED=true
LIFECYCLE_SYNTHETIC_MUTATIONS_ENABLED=false
PUBLIC_LEGAL_READY=false
PUBLIC_TERMS_VERSION=beta-2026-11-06-draft-1
```

La version ci-dessus est un **brouillon**, non une approbation juridique. Adapter la version seulement a des textes effectivement approuves et publies, en conservant leurs archives. Les anciens comptes doivent etre revus individuellement ; aucun script d'approbation de masse.

Renseigner les trois images **de cette release publiee** par digest dans le manifest, `APP_HOST`, `ACCOUNT_BASE_URL=https://APP_HOST`, `POSTGRES_PASSWORD`, `BFF_SERVICE_KEY` independante, IP reelle du proxy, noms/contact/URLs HTTPS des documents et les parametres SMTP. Preserver le fichier de reprise gere par l'operateur et les chemins/cles/permissions lifecycle existants. Un seul worker/replica API et un seul BFF : les sessions sont locales en memoire.

SMTP : port 465 avec `SMTP_STARTTLS=false` pour TLS implicite, ou port 587 avec `SMTP_STARTTLS=true` pour STARTTLS obligatoire ; fournir `SMTP_HOST`, `SMTP_FROM`, `SMTP_USERNAME`/`SMTP_PASSWORD` selon le fournisseur. Pas de repli plaintext ni de certificat invalide accepte. Verifier expediteur autorise, SPF/DKIM/DMARC, acces sortant et reception sur la boite reelle. La file mail est en memoire ; un 202 ne garantit pas la livraison. Le renvoi protege doit etre teste. L'approbation administrative n'envoie pas de mail automatique : notification manuelle.

### A. Inventaire VPS en lecture seule - autorisation prealable obligatoire

**Toutes les commandes VPS ci-dessous sont preparees, NON executees.** Elles sont destinees au shell Linux du VPS, pas au PowerShell local. Identifier d'abord sans inspecter les secrets :

```sh
docker compose ls --format json
docker ps --format '{{.ID}} {{.Names}} {{.Image}} {{.Status}} {{.Ports}}'
docker inspect --format '{{index .Config.Labels "com.docker.compose.project"}} {{index .Config.Labels "com.docker.compose.project.config_files"}} {{.Image}} {{.State.Status}}' "$API_CONTAINER"
docker inspect --format '{{range .Mounts}}{{println .Type .Name .Source .Destination .RW}}{{end}}' "$API_CONTAINER"
docker inspect --format '{{range .Mounts}}{{println .Type .Name .Source .Destination .RW}}{{end}}' "$DB_CONTAINER"
docker exec "$DB_CONTAINER" psql -X -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$DB_NAME" -c "BEGIN READ ONLY; SELECT version_num FROM alembic_version; SELECT id,issued_count,closed FROM public_registration_quota; SELECT registration_kind,count(*) FROM users GROUP BY registration_kind; SELECT count(*) FROM account_deletion_requests; SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='users' AND column_name='approved_at'; COMMIT;"
```

Relever aussi les noms exacts des volumes, version majeure PostgreSQL/extension vector, digests actifs, release courante, espace disque, sauvegarde operationnelle existante, chemin/etat du latch, autorites/holds et compteurs historiques externes. Utiliser uniquement des inspections allowlistees : pas de `docker inspect` integral ni `compose config` integral dans un rapport public, car ils exposent les secrets. Ne pas reparer un schema inconnu ou un compteur incoherent en meme temps que l'inventaire.

Le controleur gere **`documind-prod`** et une installation deja adoptee (`current`, bundles attestes, confiance independante). Si le VPS utilise un autre projet, des volumes differents, un outillage plus recent ou une installation non adoptee, **STOP** : ne pas recreer/renommer une stack ni remplacer ses outils historiques. Faire valider une adoption/adaptation distincte. Aucune commande automatique de ce rapport ne resout cette inconnue.

### B. Migration fermee 0007 -> 0008

Apres inventaire valide, sauvegarde operationnelle existante verifiee et confirmation explicite :

1. Choisir le bundle CI du SHA exact et ses digests/attestation ; faire approuver la confiance par l'autorite independante. Prevoir a l'avance une application de repli compatible 0008, ou accepter la maintenance fermee faute de repli.
2. Dans la stack courante identifiee, confirmer puis fermer la porte SQL avec `python -m backend.account_admin public-registration close --execute` dans l'API. Relever les compteurs avant arret. Mettre l'environnement existant en `REGISTRATION_MODE=disabled`.
3. Pour une installation geree compatible, declencher **apres nouvelle validation**, depuis `main` :

   ```text
   gh workflow run deploy.yml --ref main -f release_sha=SHA_MAIN -f ci_run_id=CI_RUN_ID -f operation=deploy -f initialize=false -f allow_migration=true -f approve_public_beta=false
   ```

   Les variables/secrets de l'environnement GitHub `production`, dont `VPS_DEPLOY_PATH`, les hotes SSH verifies et les reviewers obligatoires doivent correspondre a l'inventaire. Le controleur arrete les ecrivains, utilise la protection operationnelle existante et execute dans l'image candidate la migration `alembic upgrade head`. Ne pas cumuler une migration manuelle avec ce workflow.
4. La commande de migration sous-jacente, donnee pour verification du plan et **non a lancer en parallele**, est :

   ```sh
   docker compose --env-file "$ROOT/.env.production" -f "$BUNDLE/compose.production.yaml" -p documind-prod run --rm --no-deps -T --entrypoint alembic api upgrade head
   ```

   Elle suppose les images/digests et les variables deja resolus par le controleur ; la copier seule ne suffit pas a deployer une release.
5. Controler en readonly : schema `0008`, `closed=true`, `issued_count >= compteur_avant` et `>= comptes_publics_presents`, donnees existantes conservees et `approved_at` initialement NULL pour les comptes a revoir. Si l'historique atteint/depasse dix, ne pas l'abaisser : aucune nouvelle place.
6. Verifier les services `db/api/web`, les images exactes, le rapport de deploiement, etat du latch autorise et absence d'API/DB exposees publiquement. Ne jamais ecrire automatiquement `ready`.

### C. Sante, SMTP et HTTPS sur le VPS

```sh
curl --fail --silent --show-error "https://$APP_HOST/bff/health"
curl --fail --silent --show-error "https://$APP_HOST/bff/auth/options"
curl --silent --show-error --output /dev/null --write-out '%{http_code}\n' "https://$APP_HOST/bff/documents"
openssl s_client -connect "$APP_HOST:443" -servername "$APP_HOST" -verify_hostname "$APP_HOST" -verify_return_error </dev/null
```

Exiger health `ok`, options `registration_mode=disabled`, limite dix/approbation true, et refus 401 des documents sans session. Verifier aussi DNS A/AAAA, chaine/nom/expiration du certificat, redirection HTTP->HTTPS, Host/origine/CSRF, cookies `__Host-documind` Secure/HttpOnly/SameSite Strict, absence de tokens dans URL apres verification et refus IA/demo/legacy. Pas de `curl -k`.

Le parcours reel avec SMTP cible doit d'abord etre rejoue sur un environnement isole avec des donnees fictives et une autorisation distincte. Ne pas creer dix faux comptes de production pour verifier le plafond : les admissions ne se recyclent pas. Une sante verte ne leve ni les blocages d'effacement ni la validation juridique.

### D. Preparation publique et ouverture - encore interdites

Apres resolution de **tous** les NO-GO et autorisation distincte, preparer `REGISTRATION_MODE=public`, les textes approuves et `PUBLIC_LEGAL_READY=true` ; garder la porte SQL fermee. Le deploiement de preparation utilise `initialize=false`, `allow_migration=false`, `approve_public_beta=true` sur une installation deja en 0008. Il n'ouvre pas les admissions.

Une nouvelle decision explicite autorisera ensuite, dans la vraie API :

```text
python -m backend.account_admin public-registration status
python -m backend.account_admin public-registration reopen
python -m backend.account_admin public-registration reopen --execute
```

Apres chaque verification d'e-mail, revue individuelle :

```text
python -m backend.account_admin public-account status UUID
python -m backend.account_admin public-account approve UUID
python -m backend.account_admin public-account approve UUID --execute
```

Notifier manuellement le testeur, verifier connexion/import/utilisation/isolation et possibilite d'exercer les droits. Les commandes sans `--execute` d'approbation/ouverture sont des simulations, pas une autorisation implicite.

### E. Retour arriere compatible 0008

Fermer la porte SQL avec la commande administrative qualifiee, remettre le mode disabled et conserver PostgreSQL, volumes, chemins lifecycle et compteur. Revenir uniquement a un bundle **atteste et independamment approuve, declarant une compatibilite exacte 0008**, via `operation=rollback`, `initialize=false`, `allow_migration=false`, `approve_public_beta=false`. Le controleur courant verifie le candidat : ne pas executer un ancien script de deploiement a sa place.

**Interdit :** downgrade vers 0007 apres admissions, image 0007 ignorant `approved_at`, baisse/remise a zero du compteur, restauration automatique d'une ancienne base, ou effacement des recus pour permettre un redemarrage. Sans repli 0008 approuve, maintenir le service ferme/maintenance et livrer un correctif. Toute restauration indispensable reste une operation distincte sous quarantaine existante, avec rapprochement des admissions/effacements avant reouverture ; aucun nouveau chantier de sauvegarde n'est requis ici.

## 6. Checklist GO / NO-GO

- [x] Candidat isole, selection explicite, anciens travaux conserves, aucun merge automatique.
- [x] Quota dix, concurrence serveur, approbation, sessions et migration qualifies sur PostgreSQL.
- [x] Parcours navigateur HTTPS/SMTP local et refus d'effacement observes sans contournement.
- [x] Configuration et porte fermees, builds et smoke de release locaux reussis.
- [x] Reception administrative testee sans fausse annonce d'effacement.
- [ ] Executeur d'effacement standard non synthetique qualifie, avec preuves de resultat et gestion des copies.
- [ ] Dispositif humain de reception/suivi et delais effectivement valides.
- [ ] Inventaire VPS autorise et conforme ; compteurs historiques reconcilies.
- [ ] Textes juridiques, contact, SMTP reel et HTTPS de production valides.
- [ ] Integration Git revue ; CI verte sur le SHA exact publie ; digests/attestations et approbation independante.
- [ ] Application de repli 0008 approuvee ou maintien ferme explicitement accepte.
- [ ] Autorisations explicites de migration, deploiement, preparation publique puis ouverture.

**Decision finale : preparation locale livree, ouverture de production NON AUTORISEE et NON PRETE. Le blocage prioritaire d'effacement physique reste reel ; la procedure de reception n'est pas un substitut a sa resolution.**
