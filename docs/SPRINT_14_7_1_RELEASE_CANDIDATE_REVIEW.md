# Sprint 14.7.1 — Revue Git et préparation de la release candidate

26 octobre 2026. Revue exclusivement locale, branche
`preparation/sprint-14-5-ux-email-abuse`, HEAD
`8243e0511c5505a9cc70f76ad02392f7a816590d`. La production Sprint 13/0007,
inscriptions fermées et IA désactivée, est un état annoncé par l'opératrice,
non observé à distance pendant cette mission.

**Verdict : No-Go pour une release candidate validée et sa publication CI.**
La revue Git est préparée, mais un échec SQLAlchemy 503 dans la suite complète WSL
reste inexpliqué et RF10-03 nécessite une nouvelle décision pour cette publication.
Les répétitions réussies ne corrigent pas cet échec. Une PR en brouillon pourrait
porter la revue après autorisation ; elle ne constituerait pas un Go de livraison.
Aucune publication ni ouverture n'est autorisée par ce document.

## 1. Inventaire Git et préservation

Les rapports 14.1, 14.2, 14.3, 14.4, 14.5, 14.6, 14.6.1 et le runbook 14.7
ont servi de références. Leurs constats historiques restent datés : le bundle à six
fichiers décrit en 14.2/14.6 est remplacé par les neuf fichiers de 14.6.1, et le
défaut B14-10 décrit en 14.6 est traité par les nouveaux contrôles 14.6.1.

Inventaire initial développé fichier par fichier, y compris `tests/fixtures/` :
**64 chemins = 32 fichiers suivis modifiés + 32 fichiers non suivis**. Index vide.
Un relevé SHA-256 initial puis une comparaison confirment **64/64 identiques**
après la revue et les tests. Aucun correctif applicatif, workflow ou migration
n'a été appliqué dans ce lot. Le présent rapport est le seul nouveau candidat Git :
**65 chemins à revoir avant une éventuelle indexation explicite**.

### Fichiers suivis modifiés à inclure, sous réserve de validation

```text
.github/workflows/ci.yml
.github/workflows/deploy.yml
backend/account_admin.py
backend/account_api.py
backend/ai/api.py
backend/ai/providers.py
backend/ai/settings_api.py
backend/public_registration.py
backend/rag/indexing.py
backend/rag/providers.py
frontend/server/app.mjs
frontend/server/app.test.mjs
frontend/src/components/Assistant.tsx
frontend/src/pages/AISettings.tsx
frontend/src/pages/Account.tsx
frontend/src/pages/CompareDocuments.tsx
frontend/src/pages/IntelligentLibrary.tsx
frontend/src/pages/PublicBeta.test.tsx
frontend/src/pages/Rag.test.tsx
frontend/src/services/account.ts
tests/test_byok.py
tests/test_deployment.py
tests/test_openai_provider.py
tests/test_production_backups.py
tests/test_public_beta.py
tools/backup_local.py
tools/backup_production.py
tools/deploy_production.py
tools/prepare_production.py
tools/release_manifest.py
tools/validate_restore.py
tools/verify_snapshot.py
```

### Fichiers non suivis à inclure, sous réserve de validation

```text
compose.public-beta-test.yaml
docs/SPRINT_14_1_PUBLIC_BETA_AUDIT.md
docs/SPRINT_14_2_PUBLIC_BETA_AUTHORIZATION_REPORT.md
docs/SPRINT_14_3_AI_DISABLED_ENFORCEMENT_REPORT.md
docs/SPRINT_14_4_PUBLIC_BETA_QUOTA_CONCURRENCY_REPORT.md
docs/SPRINT_14_5_PUBLIC_BETA_UX_EMAIL_ABUSE_REPORT.md
docs/SPRINT_14_6_1_SECURE_ROLLBACK_REPORT.md
docs/SPRINT_14_6_PREPRODUCTION_VALIDATION_REPORT.md
docs/SPRINT_14_7_PUBLIC_BETA_OPENING_RUNBOOK.md
frontend/src/pages/AISettings.test.tsx
frontend/src/services/registration.test.ts
ops/testing/Dockerfile.beta-recipe
ops/testing/Dockerfile.beta-recipe.dockerignore
ops/testing/cleanup_beta_recipe.py
ops/testing/prepare_beta_recipe.py
ops/testing/traefik-public-beta-test.yaml
ops/testing/validate_beta_recipe.py
tests/fake_smtp.py
tests/fixtures/public_beta_browser.mjs
tests/fixtures/public_beta_gateway.mjs
tests/fixtures/public_beta_smtp.py
tests/fixtures/public_beta_tcp_relay.py
tests/test_ai_disabled_enforcement.py
tests/test_public_beta_authorization.py
tests/test_public_beta_email_abuse.py
tests/test_public_beta_email_e2e.py
tests/test_public_beta_postgresql_concurrency.py
tests/test_public_beta_snapshot.py
tests/test_public_beta_state.py
tests/test_release_security.py
tools/public_beta_policy.py
tools/release_security.py
```

Ajouter à cet inventaire le présent fichier :
`docs/SPRINT_14_7_1_RELEASE_CANDIDATE_REVIEW.md`.
Les fichiers de recette et fixtures sont des sources nécessaires aux preuves ;
ils ne sont pas des captures de données ou certificats générés.

### Exclusions explicites

`var/` entier, `.env`, `.env.production`, `compose.upload-test.windows.yaml`,
`.venv/`, caches Python/pytest, `*.egg-info`, `frontend/node_modules/`,
`frontend/dist/`, `frontend/test-results/`, rapports Playwright et `*.tsbuildinfo`.
Les règles d'exclusion sont vérifiées avec `git check-ignore` et
`git ls-files --others --ignored --exclude-standard --directory`.
La présence locale de `.env.production` n'est pas supposée et son contenu n'est pas lu.

Les relevés, journaux, certificats/clés éphémères, messages SMTP fictifs, archives,
PDF fictif et harnais supplémentaires de cette revue restent dans `var/`, ignoré.
Aucun chemin candidat n'est un secret, dump, document utilisateur, certificat privé,
base SQLite ou lien symbolique. Contrôle des extensions, marqueurs de clés privées
et formats courants de credentials, puis lecture selon le rôle du fichier : aucun
secret réel identifié dans les candidats. Ce contrôle n'est pas une preuve absolue
d'absence de tout secret ; vérifier encore l'index exact avant commit.

Une tentative de liste récursive des ignorés a rencontré des refus d'accès sur
d'anciens dossiers privés sous `var/`. Aucun droit n'a été changé et leur contenu
n'a pas été inspecté ; la liste par répertoires et les règles Git suffisent à les exclure.

## 2. Revue des changements et invariants

| Domaine | Résultat confirmé dans le dépôt et les tests ciblés |
| --- | --- |
| 14.2, autorisation | Politique partagée préparation/Compose/paramètres effectifs ; `approve_public_beta` ne vaut ni migration ni réouverture SQL. Public exige 0007, cinq admissions, IA/demo/legacy false et verrou fermé avant livraison. |
| 14.3, IA | Refus avant connexion/validation BYOK, constructeurs SDK et appels génération/embedding ; workers et retry revérifient le drapeau courant. Suppression de clé, annulation, historique et analyse classique restent disponibles. |
| 14.4, identité | Attente email distincte du blocage administratif ; vérification, renvoi et reset ne lèvent pas le blocage. Anciens comptes publics ambigus conservés bloqués, sans backfill automatique. |
| 14.4, quota | Incrément SQL conditionnel atomique avec borne non négative ; cinq admissions cumulatives, comptes en attente inclus ; aucune place rendue par suppression, fermeture ou restauration. |
| 14.4, sauvegardes | Inventaire v2 des 23 tables avec compteur/verrou ; v1 lisible mais quota non certifié. Fidélité de restauration vérifiée avant fermeture explicite de la copie indépendante. |
| 14.5, UX/email | Consentement explicite, message 202 sans promesse de livraison, disponibilité fermée par défaut, renvoi et erreurs génériques ; événement expurgé de saturation reset. |
| 14.6, recette | Harnais local isolé, faux SMTP STARTTLS, vrais navigateurs, PDF/TXT, quota, backup/restauration ; aucun fournisseur réel. |
| 14.6.1, livraison | Autorisation distincte de la compatibilité de schéma, registre root, contrôleur indépendant et garde de reprise backup ; refus fermé du précédent non approuvé. |

Syntaxe AST des Python candidats, YAML candidats, Python embarqué dans les workflows,
syntaxe des fixtures Node, TOML et lockfile JSON contrôlés. Les imports plats des six
modules Python du bundle réussissent ; `prepare_production.py --help` fonctionne.
La suite collecte 823 tests sans erreur d'import. `pip check` ne trouve aucune
dépendance installée incompatible ; cela ne vérifie ni provenance ni CVE.

Schéma unique `0007`, profil exact `public-beta-2026-10-v1` dans manifeste,
attestation, politique et labels CI ; aucun profil ABI 2 ou mode development ajouté.
La version de paquet `0.1.0` préexistante est inchangée : la release est identifiée
par SHA Git complet et digests, pas par ce numéro de paquet.

Compose de production, Dockerfiles, migrations, moteurs Landlock/seccomp, locks de
dépendances et unités systemd sont inchangés par rapport à HEAD. SEC10-02/03/04,
sessions, CSRF et isolation ne sont pas supprimés. Les scripts de monitoring et de
conservation sont préservés ; la rétention reste `--simulate`. Le verrou commun
est **`/srv/documind-ai/deployment.lock`**, pas un fichier sous `var/`.

## 3. Bundle, attestation et chaîne de livraison

Le bundle immuable attendu contient exactement :

```text
release.json
compose.production.yaml
deploy_production.py
backup_local.py
backup_production.py
release_manifest.py
public_beta_policy.py
release_security.py
security-attestation.json
```

Le statement lie profil, 0007, SHA complet, les trois références Registry par digest,
repository/workflow/run/attempt et SHA-256 des huit autres fichiers. `images.env`
et `deployment-report.json` sont des sorties séparées, non des pièces à modifier pour
fabriquer une approbation. Les labels OCI des trois images sont contrôlés après pull.

Un bundle fictif à neuf fichiers est généré localement ; création/validation du
statement et imports plats réussissent. Son autorisation sans registre indépendant
est refusée. Les tests exécutent aussi le vrai Python du step de validation du
workflow sur un bundle généré, et couvrent ancien bundle, faux profil, incohérence
SHA/digest/checksum/producteur, révocation, permissions root et symlinks.

`release_security.check` valide l'intégrité, **pas l'origine ni l'approbation**.
L'ancre fixe `/etc/documind-ai/release-security-trust.json` doit être root, régulière,
non symlink, non inscriptible groupe/autres ; son répertoire doit aussi être root et
non inscriptible groupe/autres. Le service debian doit pouvoir la lire. Une proposition
`propose-trust` n'est jamais une autorisation automatique. Il n'existe pas de signature
CI indépendante : l'administratrice doit vérifier l'origine réelle GitHub, le code
revu et le run/attempt avant d'approuver l'empreinte exacte.

Le workflow valide la source CI réussie sur main et son repository/SHA, puis utilise
un contrôleur du checkout courant dans `deploy-controls/...`, avec `--bundle TARGET`.
Il n'exécute pas le déployeur d'un ancien candidat. Autorisation et garde ops sont
revérifiées avant arrêt/démarrage/activation et avant reprise du précédent.
Les rapports antérieurs ne sont pas écrasés.

Un push sur la seule branche de préparation n'active pas `publish` ; l'ouverture ou
mise à jour d'une PR exécute les tests. Une fusion sur main déclenche la CI, puis
la publication séquentielle backend/frontend/postgres **linux/amd64**, uniquement si
`python`, `windows`, `frontend` réussissent. `workflow_dispatch` sur main peut également
publier : il ne doit pas servir à contourner un échec. `deploy.yml` reste manuel et
exige l'environnement production avec approbateurs. Les règles GitHub effectives
et secrets disponibles ne sont pas vérifiés à distance dans cette revue.

**RF10-04 :** publication non atomique. Si une image est poussée puis une étape échoue,
arrêter la livraison ; conserver run, étape, SHA, sorties digest et éventuel artefact.
Pas d'approbation root, déploiement, suppression, retagging ou relance automatique.
`check_registry_tags.py` refuse de réutiliser un tag SHA existant ; une réparation ou
nouvelle version nécessite une décision explicite. Trois images présentes sans
bundle final valide ne constituent pas une release utilisable.

## 4. Bootstrap contrôlé proposé — jamais exécuté sur le VPS

Cette procédure complète le runbook 14.7. **Commencer par une livraison profilée en
mode disabled**, puis examiner séparément une future préparation `public/5`, verrou
SQL fermé. Aucun changement de configuration de production n'est réalisé ici.

### A. Préparer les preuves avant toute fenêtre

1. Obtenir les autorisations distinctes commit/PR, fusion et publication privée,
   traiter les blocages de cette revue et RF10-03. Vérifier le run réel, ses trois
   digests amd64, les neuf fichiers et leurs empreintes ; refaire la recette sur
   les images CI exactes. Les overlays de tests ne sont pas des releases.
2. Identifier séparément le contrôleur revu, le candidat, ses scripts ops et la
   proposition de registre. Revoir l'origine par un canal authentifié indépendant
   du bundle. Ne jamais certifier Sprint 13 en ajoutant un profil ou en réécrivant
   son rapport. Préparer la procédure de correction en avant et une fenêtre dont
   l'indisponibilité maximale et la perte temporaire de sauvegarde sont acceptées.
3. Après autorisation VPS ultérieure : vérifier current réel Sprint 13/0007, santé,
   deux volumes connus, aucune maintenance pendante, capacité disque et sauvegarde
   B2 récente confirmée/restauration indépendante. Relever uniquement compteur,
   verrou et existence agrégée d'identités publiques, sans lister les comptes.
   En cas d'histoire publique inconnue ou positive, ne pas utiliser la compatibilité
   historique décrite ci-dessous : arrêter le bootstrap pour revue.
4. Garder le mode disabled et IA/demo/legacy false. Fermer et relire le verrou SQL
   via le CLI de la release active autorisée, sans reset ni changement du compteur.
   Aucun `reopen` pendant cette transition.

### B. Mettre les outils ops à niveau sans course avec systemd

1. Relever l'état enabled/active du seul `documind-backup.timer`. Après autorisation,
   arrêter **le timer seulement**, sans désactiver sa configuration et sans tuer
   `documind-backup.service`. Attendre qu'une éventuelle exécution existante, y compris
   `ExecStopPost`, soit terminée. `Persistent=true` peut déclencher un rattrapage
   dès réactivation : ne pas remettre le timer avant les contrôles ci-dessous.
2. Vérifier l'absence de `var/backup-maintenance.json` et de
   `var/security-maintenance.json`. S'ils existent, conserver les preuves et arrêter ;
   aucune suppression, édition, déplacement ou fabrication de pointeur ne débloque
   cette procédure. Un backup normal interrompu relève du `--resume` validé ; une
   maintenance de sécurité exige une correction approuvée, pas cet ancien resume.
3. Prendre le **même verrou existant** `deployment.lock` en exclusif/non bloquant,
   avec le compte d'exploitation, pour toute l'installation. Vérifier encore que
   le service n'est pas actif ; sinon relâcher et attendre. Ne jamais remplacer ce
   fichier pour « libérer » le verrou ni en créer un nouveau appartenant à root.
4. Vérifier le répertoire `/srv/documind-ai/ops` root/non inscriptible groupe-autres,
   sans chown récursif. Installer sous contrôle root les **deux seuls fichiers**
   `backup_production.py` et `release_security.py`, depuis les octets exacts du
   bundle approuvé, root:root 0644. Utiliser des fichiers temporaires root nouveaux
   puis renommages atomiques, sous verrou et timer arrêté : aucune exécution ne
   doit observer une paire partiellement mise à jour. Conserver les anciennes
   versions dans le dossier privé de transition, sans effacer de preuve.
5. Faire approuver la première entrée du registre par l'administratrice. Répertoire
   `/etc/documind-ai` root:root 0755, registre root:root 0644, non symlinks. Fusionner
   les entrées existantes revues ; ne pas écraser aveuglément le registre avec la
   proposition d'un bundle. Installation atomique après validation JSON stricte,
   permissions et origine. Aucun secret nouveau n'est nécessaire dans ce registre.
6. Sous identité debian, contrôler lisibilité/imports et empreintes des deux scripts,
   puis `check_backup_guard(root, candidate)` et `security.authorize(candidate, release)`
   avec les outils revus. Ne pas exécuter `backup_production.py` sans argument en
   croyant lancer un simple contrôle : cela déclenche une vraie sauvegarde/B2.
7. Sous le même verrou, appeler explicitement
   `backup_production.ActiveRelease(root).preflight()` sur le current Sprint 13,
   sans arrêt ni upload. Puis libérer le verrou. Tout refus interdit le déploiement.

### C. Compatibilité backup pendant la transition

Confirmé : en 0007, mode disabled, sans profil, sans identité publique et compteur zéro,
le nouveau `authorize_restart()` lit le SQL et n'exige pas l'attestation inexistante
de Sprint 13. Deux tests couvrent verrou ouvert/fermé ; aucune requête UPDATE ni
chargement du module de politique n'est autorisé dans ces scénarios.
Le préflight historique complet de montages/images/projet reste testé séparément.
Ce sont des simulations locales, pas une observation du current réel du VPS.

Le helper de backup est toujours chargé depuis **current** : avec Sprint 13 actif,
son ancien inventaire peut rester v1, quota non certifié. Installer le nouvel
orchestrateur ne réécrit pas ce helper ni les anciens snapshots. Le contrôleur neuf
utilise son propre `backup_local.py` v2 pour la sauvegarde précédant le déploiement ;
après activation du nouveau current, la sauvegarde quotidienne prend son helper v2.

Ne pas interrompre les sauvegardes pendant plusieurs jours en attendant une CI ou
une approbation : effectuer d'abord la préparation hors fenêtre. Si les préflights
ci-dessus réussissent, le timer peut être remis dans son état actif antérieur **avant**
le déploiement ; le verrou partagé exclut les exécutions simultanées. Surveiller le
rattrapage éventuel et son rapport. Une vraie sauvegarde de vérification/B2 demande
une autorisation propre, conserve les secrets VPS et ne recrée jamais PostgreSQL.
Si le garde refuse Sprint 13, ne pas réactiver en boucle : No-Go de transition,
diagnostic et procédure corrigée à tester avant intervention.

### D. Première livraison corrigée, toujours fermée

Après succès des étapes précédentes et autorisation de livraison : nouveau répertoire
de tentative, contrôleur revu indépendant, candidat attesté/approuvé, ops identiques,
mode disabled, IA fermée, schéma 0007. Workflow manuel avec `operation=deploy`,
`initialize=false`, `allow_migration=false`, `approve_public_beta=false` pour cette
première étape disabled. Ne pas réutiliser un répertoire portant déjà un rapport.

Le profil seul impose la politique renforcée, même en mode disabled. Le déployeur
crée sa maintenance de sécurité, arrête seulement API/BFF pour le snapshot v2, puis
réalise la livraison. Le chemin ordinaire peut recréer le PostgreSQL **DocuMind** si
son digest change et exécute `upgrade head` ; à schéma constant c'est un no-op SQL,
pas une garantie d'absence d'interruption PostgreSQL. Prévoir cette interruption,
jamais `down -v` ni changement des autres projets.

Après healthchecks, HTTPS/CSRF/refus anonyme et réautorisation, current est activé
et le contrôleur retire son propre marqueur. Vérifier mode disabled, IA off, quota
inchangé/fermé, schéma, trois digests, rapport et sauvegarde quotidienne v2. Un second
déploiement explicitement approuvé pourra préparer `public/5` avec
`approve_public_beta=true` ; la réouverture SQL restera une troisième décision.

## 5. Risques de transition et récupération

**Il peut n'exister aucun précédent sûr pour le premier déploiement profilé.**
Sprint 13 n'est pas admissible au fallback renforcé. En cas d'échec après arrêt,
API/BFF restent arrêtés, PostgreSQL et volumes sont conservés, current peut encore
pointer vers Sprint 13 et le marqueur de sécurité reste présent. Le backup quotidien,
son `--resume` et `ExecStopPost` refusent alors de relancer l'ancienne application.
Ce refus volontaire protège les données mais suspend les sauvegardes automatiques.

Correction en avant : diagnostic, nouveau candidat corrigé/CI réussi, mêmes garanties,
0007 supporté, attestation et approbation indépendante, scripts ops compatibles,
nouveau dossier de tentative et contrôleur actuel `--bundle` explicite. Le contrôleur
peut adopter son marqueur de sécurité existant valide et ne le retire qu'après succès.
Une simulation déroule réellement échec du premier candidat, refus du précédent,
refus backup, puis succès du candidat approuvé suivant sans édition du marqueur.
Une maintenance backup préexistante interdit en revanche tout changement de services ;
ce refus est testé et ne possède pas de bypass dans cette procédure.

Ne pas révoquer le current ou remplacer les guards pendant un backup : si l'approbation
disparaît entre arrêt et reprise, le refus est fermé et une maintenance backup peut
rester pendante. Le déployeur la refuse aussi. **Ce cas exige une procédure d'incident
spécifique revue, et reste No-Go pour une transition automatique.** Ne jamais effacer
le marqueur, réautoriser artificiellement un ancien binaire ni utiliser un vieux
script pour forcer une reprise. Préparer les secours et coordonner les révocations.

Un secours futur doit être approuvé et conserver les mêmes helpers ops exacts ;
des helpers différents bloquent le retour par conception. Aucun secours CI réel,
registre root installé ou état de timer n'est certifié depuis le dépôt local.
Sans disponibilité opératrice, borne d'arrêt acceptée, capacité de correction en
avant et contrôle des sauvegardes, le bootstrap VPS est **No-Go**.

Aucun blocage intrinsèque du chemin privé Sprint 13 sans histoire publique n'est
démontré par les tests : la correction proposée est l'ordre opératoire coordonné
et la première livraison disabled, pas un retrait des guards. Les scénarios de
compatibilité, refus et correction en avant sont testés ; les opérations systemd,
copies root et disponibilité effective sur le VPS ne le sont pas. L'absence de
directive `restart` dans le Compose n'introduit pas de reprise Docker automatique ;
un éventuel autoheal/service hôte externe reste à exclure lors de la revue VPS autorisée.

## 6. Dépendances, provenance et risques ouverts

**RF10-03 reste ouvert.** L'acceptation historique d'une seule publication privée
ne couvre pas cette nouvelle livraison et ne couvre jamais l'ouverture publique.
Aucun changement de dépendance n'est justifié/appliqué par cette revue.

- `requirements.lock` fixe des versions runtime/test mais sans hashes. Il ne couvre
  pas toute la chaîne : `argon2-cffi-bindings`, `cffi`, `pycparser` ne sont pas épinglés,
  ni `setuptools>=75` de l'environnement de build isolé. Les versions installées ne
  constituent pas un verrou reproductible de la future construction.
- Les Dockerfiles utilisent `python:3.13-slim`, `node:22-alpine`, `postgres:17-alpine`,
  sans digest de base. APT/APK et le tag pgvector `v0.8.7` peuvent fournir des entrées
  différentes ; le tag Git n'est pas une révision source verrouillée.
- Les actions GitHub sont épinglées par SHA, checkout sans credentials persistants ;
  npm utilise `npm ci` et les intégrités du lockfile. Cela ne certifie pas les scripts
  d'installation ou toutes les vulnérabilités transitives.
- Les images publiées finales sont figées par digest ; cela ne rend pas leurs entrées
  de construction immuables. Les builds exacts de production ne sont pas rejoués
  hors ligne : leur besoin APT/pip non disponible est documenté en 14.6. Les trois
  overlays locaux réussis ne remplacent pas ces builds CI.

Références officielles consultées pour les mécanismes, **pas un audit CVE actualisé** :
[contraintes de build pip](https://pip.pypa.io/en/latest/user_guide/#build-constraints),
[verrouillage des bases Docker](https://docs.docker.com/build/building/best-practices/#pin-base-image-versions).
Prévoir un lot supply chain ou une nouvelle acceptation privée explicitement bornée
au SHA/run/digests et à une exécution, avec RF10-04. Ne pas étendre cette acceptation
à l'ouverture, au déploiement ou à une relance.

Autres limites : les deux preuves d'autorité root ne tournent pas automatiquement
dans la CI actuelle exécutée non-root ; elles sont réellement exécutées ici dans
un conteneur dédié. Les E2E opt-in et six snapshots dédiés ne sont pas activés par
le simple `pytest` CI. Conserver des preuves séparées ou renforcer ultérieurement
les gates CI ; ne pas les compter comme réussis quand ils sont ignorés.
Le job Linux est borné à 25 minutes pour deux suites et les builds : mesurer le
temps du vrai runner, sans déduire sa durée de WSL sur disque Windows.

File SMTP RAM non durable, reset distribué sans plafond global propre, limites NAT,
cinq places consommables avant réception d'email, textes légaux/accessibilité,
SMTP/B2 et alertes réels restent des décisions ou validations opératrice distinctes.
La recette locale utilise Traefik v3.3 fournisseur fichier et Linux WSL ABI 7,
pas Traefik v3.0 fournisseur Docker ni Linux 6.12/ABI 6 du VPS annoncé.

## 7. Tests réellement exécutés dans cette revue

| Campagne | Réussis | Ignorés | Échoués / état |
| --- | --- | --- | --- |
| Python Windows 3.13.7, suite complète | 755 | 68 | 0, 786,32 s |
| Python WSL Ubuntu 3.12.3, suite complète | 795 | 27 | **1**, 1 174,33 s |
| WSL, fichier résumés longs seul après l'échec | 14 | 0 | 0, 111,17 s |
| WSL, cas défaillant répété, trois bases neuves et logs séparés | 1 × 3 | 0 | 0, 10,61 / 10,43 / 10,26 s |
| Docker Linux 3.13, fichier résumés longs seul | 14 | 0 | 0, 74,76 s |
| PostgreSQL 17 / pgvector, sélection sécurité/concurrence/quotas/IA/déploiement/backup | 330 | 2 | 0, 119,16 s |
| Docker root, sécurité/déploiement/autorisation/backup | 268 | 3 | 0, 8,02 s |
| Docker non-root, Landlock/seccomp et protocole | 72 | 0 | 0, 10,37 s |
| Sauvegardes, monitoring et rétention, Windows | 199 | 0 | 0, 15,12 s |
| Simulations de bootstrap supplémentaires | 4 | 0 | 0, 0,32 s |
| React/Vitest | 52 | 0 | 0 |
| Node/BFF | 50 | 0 | 0 |
| TypeScript/Vite | — | — | Build réussi |
| Recette intégrée Docker/Chromium/SMTP/restauration | 9 jalons | 0 | Tous réussis |
| Bundle fictif neuf fichiers, syntaxe/imports/workflows | — | — | Réussis |

Les sélections se recouvrent et ne s'additionnent pas comme des tests distincts.
Windows ignore 40 cas Linux natifs, 11 cas PostgreSQL, six snapshots Docker, huit E2E
opt-in et trois cas de propriété Linux/root. PG ignore deux preuves root ; la
campagne root ignore le cas non-root et deux cas PostgreSQL. Ils sont testés dans
leurs environnements respectifs. Les huit E2E opt-in 14.5 et les six snapshots du
harnais 14.4 ne sont pas relancés comme tels : la recette intégrée apporte une
validation indépendante, sans les déclarer implicitement passés.

### Échec WSL bloquant : faits et hypothèses

`tests/test_long_summary.py::test_worker_interruption_resume_and_owner_isolation`
échoue à la ligne 159 lors de `wait_job()` après reprise. Le GET de suivi renvoie
HTTP 503 au lieu de 200 ; le gestionnaire `SQLAlchemyError` de `backend/main.py`
émet `system.database.unavailable`, sans texte SQL ou secret. L'échec est donc
confirmé, mais le log expurgé ne distingue pas `SQLITE_BUSY`, épuisement de pool
ou une autre exception SQLAlchemy. Ce n'est pas un simple dépassement démontré du
timeout de suivi, ni la preuve d'une régression PostgreSQL.

La suite Windows et WSL tournaient en parallèle, sur des bases de tests distinctes.
Le code et les bibliothèques WSL sont lus depuis le dépôt monté Windows, mais les
bases de cette campagne sont bien sous `/var/tmp` Linux. Une contention de ressources,
SQLite ou une course du cycle worker/session sont des **hypothèses**, pas une cause
identifiée. Les fichiers `backend/db.py`, `backend/ai/long_summary.py` et leur test
ne sont pas modifiés dans le lot ; cela ne suffit pas à exclure une interaction.

Après la campagne complète, les 14 tests passent isolément sous WSL et sous Docker.
Trois répétitions WSL distinctes du cas fautif passent aussi ; un plugin temporaire
hors suivi Git ne collecte que le type d'exception DBAPI et `sqlite_errorname`,
jamais SQL/paramètres/contenus. Il n'observe aucune erreur lors de ces répétitions.
Cela établit une intermittence dans les conditions testées, **pas une résolution**.
Aucun retry SQL, timeout supplémentaire, test ignoré ou correctif applicatif n'est ajouté.

Action proposée avant validation RC : reproduire avec cette instrumentation dans
une campagne complète, conserver type d'erreur, état transactionnel et terminaison
du worker, puis ajouter une régression déterministe si la cause est établie. Comparer
le même scénario PostgreSQL dédié si une correction transactionnelle est envisagée.
Ne pas attribuer la cause à Windows/SQLite par défaut ou modifier les délais pour
faire passer le test. Cette investigation et toute correction seront un lot ciblé
à faire valider ; le résultat WSL complet rouge est conservé dans le verdict.

Les 27 ignorés WSL sont onze PostgreSQL, six snapshots, huit E2E opt-in et deux
preuves root. Les tests Linux non-root sont exécutés. Les résultats antérieurs des
rapports 14.1–14.6.1 restent historiques et ne remplacent pas cette nouvelle campagne.

Commandes de référence exécutées, sans cache pytest et avec répertoires neufs :

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp=var/pytest-14-7-1-windows --tb=short
.\.venv\Scripts\python.exe -m pytest tests/test_production_backups.py tests/test_monitoring.py tests/test_retention.py -q -p no:cacheprovider --basetemp=var/pytest-14-7-1-ops --tb=short
.\.venv\Scripts\python.exe -m pytest var/test_s14_7_1_bootstrap.py -q -p no:cacheprovider --basetemp=var/pytest-14-7-1-bootstrap --tb=short
npm.cmd run test:ui
npm.cmd run test:bff
npm.cmd run build
```

WSL réutilise le venv local existant, depuis le dépôt monté :

```bash
cd /mnt/c/Users/Adeline/Documents/DocuMind_AI
/var/tmp/documind-s13-a7b75801/.venv/bin/python -m pytest -q -p no:cacheprovider \
  --basetemp=/var/tmp/documind-s14-7-1-linux --tb=short
```

Docker Desktop est explicitement ciblé par
`--host npipe:////./pipe/dockerDesktopLinuxEngine`, moteur 29.8.2. Image de preuves
locale `documind-s14-7-1-proofs:local`, construite hors ligne, non publiable.
Tests natifs sans réseau/volumes, rootfs readonly, cap-drop ALL, no-new-privileges,
1536 Mio, deux CPU, 64 PID, tmpfs 256 Mio. Root est utilisé seulement pour les
preuves de propriété dans ce tmpfs ; le parseur est testé comme utilisateur applicatif.

PostgreSQL neuf `s14-7-1-pg-c6a4`, réseau interne dédié `s14-7-1-review-c6a4`,
sans port publié ni volume persistant, données sur tmpfs et compte fictif. Les fixtures
refusent une base non vide. Aucun SDK fournisseur réel, B2 ou SMTP externe.

La recette réutilise les scripts existants, nouveau projet
`documind-s14-6-recipe-c71e` : huit services, trois réseaux et un volume documentaire
propres. Les images API/BFF reconstruites avec les sources actuelles sont identiques
aux images locales prévues par le Compose. Deux vrais parcours Chromium, quota 5/6,
fermeture/restart, trois documents, inventaire v2/23 tables, v1 signalé non certifié,
restauration dans une autre base neuve puis scellement sans reset : neuf jalons réussis.
Le projet et le PG dédié sont nettoyés après contrôle des labels/montages ; aucun
conteneur, volume ou réseau préexistant n'est modifié. Les fichiers de preuve restent
dans `var/`. Les avertissements Starlette/httpx et `fitz` préexistants ne sont pas masqués.

## 8. Plan Git, PR et vérifications post-CI — proposé seulement

Proposition : une branche de publication dédiée, par exemple
`preparation/sprint-14-release-candidate`, créée uniquement après autorisation depuis
le travail conservé. **Un commit cohérent des 65 fichiers** évite de publier une
chaîne de livraison référençant des modules non encore inclus. Le découpage par
phase reste visible dans les rapports ; les évolutions partagées d'account_admin,
du déployeur, du bundle et des tests ne doivent pas être séparées arbitrairement.

Message proposé :
`feat(security): préparer la bêta publique et sécuriser la livraison`

Titre PR proposé :
`Sprint 14 : release candidate bêta contrôlée et livraison sécurisée`

Description proposée :

> Prépare l'admission publique de cinq comptes cumulés sans ouvrir les inscriptions :
> autorisation distincte de livraison, compteur transactionnel, blocage administratif
> conservé à la vérification, sauvegarde/restauration du quota, UX/email et refus
> strict des appels IA. Sécurise le rollback et les reprises par bundle lié aux
> digests, approbation root indépendante et garde de sauvegarde.
>
> Inclut la recette locale HTTPS/PG/SMTP/navigateurs et les rapports 14.1–14.7.1.
> Les résultats complets et réserves sont dans le rapport RC ; toute défaillance
> non expliquée reste bloquante. Trois images amd64 seulement ; aucune migration
> nouvelle, activation publique, IA ou installation ops implicite.
>
> Avant merge/publication : CI python/windows/frontend verte et risques de build
> réacceptés ou corrigés. Après publication : vérifier les neuf fichiers, trois
> digests et run/attempt. Déploiement fermé, bootstrap root et ouverture SQL exigent
> des autorisations ultérieures distinctes.

Après autorisation future, contrôler branche/base à jour, index explicitement limité
à l'inventaire, absence de secrets et `git diff --cached --check`. Aucun `git add .`
ou `git add -A`. Les commandes de lecture `git status --short --branch`,
`git diff --stat`, `git diff --check`, `git diff --cached --name-only` sont exécutées
localement ; aucune indexation, branche nouvelle, commit ou requête GitHub ici.

Avant merge : contrôles requis **python, windows, frontend**, sans `publish` requis,
source SHA exacte, revue des différences et protections effectives à vérifier sur
GitHub après autorisation. Le job python doit réussir SQLite, PostgreSQL/pgvector et
Docker confinement ; frontend doit réussir React/BFF/build. Un test ignoré n'est pas
une preuve de validation. Ne pas fusionner avec une défaillance locale inexpliquée.

Après une publication autorisée : vérifier succès du run complet/attempt, architecture,
labels de révision/profil, trois références `@sha256`, absence de fichier supplémentaire
dans le bundle, hashes, origine et recette des images réelles. Une approbation root
ou une installation des scripts n'est pas produite par la CI. Pas de VPS avant toutes
ces preuves et les préconditions des sections 4–5.

## 9. Critères Go / No-Go et étapes futures

| Décision | Critères |
| --- | --- |
| Préparation/revue Git locale | Inventaire complet, 64 fichiers préservés, rapport additionnel seul, index vide ; contrôles statiques réussis. |
| PR de validation | Diagnostic WSL terminé et résultat présenté ; une PR en brouillon peut porter la revue mais ne vaut pas validation RC. Commit/push/PR nécessitent autorisation explicite. |
| Fusion et publication CI privée | Aucun échec inexpliqué, trois gates CI verts sur SHA exact, acceptation RF10-03 nouvelle ou correction validée, procédure RF10-04 comprise, autorisation de publication. |
| Bootstrap/déploiement fermé | Bundle CI réellement approuvé, registre/scripts root installés et relus, timer coordonné, backup possible, absence de maintenance pendante, correction en avant disponible et fenêtre acceptée. |
| Ouverture publique | Recette digests sur environnement accepté ABI 6, SMTP/textes/alertes/B2 réels validés, risques RAM/NAT acceptés, quota connu, fermeture prête et nouvelle décision explicite. IA toujours off. |

**Verdict final : préparation Git achevée, mais release candidate non prête en tant
que version validée pour PR de livraison et publication CI.** Une PR en brouillon
de revue reste envisageable sous autorisation, sans fusion. Aucun correctif code
n'est appliqué sans cause démontrée. Les 64 fichiers précédents sont conservés ;
le présent rapport est le seul ajout au périmètre publiable. Aucun fichier indexé,
commit, push, merge, workflow distant, accès VPS/Registry, déploiement ou modification
de configuration de production. Les étapes VPS ci-dessus sont futures et non exécutées.
Contrôle Git final : **32 suivis modifiés + 33 non suivis = 65 fichiers**, index vide,
branche inchangée, 64/64 empreintes initiales conservées. `git diff --stat` porte
sur les 32 suivis seulement : 572 insertions et 90 suppressions ; il n'inclut pas
les fichiers nouveaux. `git diff --check` réussit, de même que le contrôle séparé
des blancs des nouveaux fichiers. Les filtres Docker des ressources propres à
cette mission sont vides après nettoyage.

**L'ouverture publique et l'activation IA restent interdites.**
