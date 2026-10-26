# Sprint 14.7.6 — Préparation finale de la Pull Request

26 octobre 2026. Audit, recette fictive et documentation locaux uniquement.
Références : [supply chain](SPRINT_14_7_5_SUPPLY_CHAIN_REPORT.md),
[intégrité](SPRINT_14_7_4_DOCUMENT_INTEGRITY_REPORT.md),
[revue RC](SPRINT_14_7_1_RELEASE_CANDIDATE_REVIEW.md) et
[runbook](SPRINT_14_7_PUBLIC_BETA_OPENING_RUNBOOK.md).

**Verdict : Go technique pour présenter le travail en PR en brouillon après les
autorisations de commit, push et création de PR. No-Go fusion, publication d'une
RC utilisable, déploiement et ouverture publique.** Cette préparation n'est pas
une release candidate validée. Aucun risque résiduel accepté au nom de l'exploitante.

## 1. État Git, périmètre et préservation

Branche actuelle : `preparation/sprint-14-5-ux-email-abuse`.
HEAD : `8243e0511c5505a9cc70f76ad02392f7a816590d`.
Ce SHA est la base actuelle, **pas** celui d'un futur commit contenant le Sprint 14.
Les changements de ce sprint restent non commités.

Inventaire initial : **78 chemins = 35 suivis modifiés + 43 non suivis**, développé
fichier par fichier, notamment les quatre fixtures de tests. Comparaison avec le
périmètre 14.7.5 : aucun chemin manquant ou inattendu. Les cinq fichiers de 14.7.5
sont présents : lock, CI, outil de matériaux, tests et rapport.

Le seul nouveau candidat de cette mission est ce rapport :
**79 chemins à indexer après validation, 35 suivis modifiés + 44 non suivis**.
Comparaison SHA-256 de clôture : les 78 chemins initiaux restent identiques.
Index vide ; aucune branche, commit, indexation ou opération distante effectués.

### Liste explicite des 79 fichiers à indexer, proposée seulement

Cette liste est une whitelist de revue, **pas une commande déjà exécutée**.
Elle comprend les phases 14.1–14.7.5 et le présent rapport. Aucun fichier non suivi
n'est inclus simplement parce qu'il est non suivi : chaque chemin a un rôle source,
test, configuration ou documentation identifié.

```text
.github/workflows/ci.yml
.github/workflows/deploy.yml
backend/account_admin.py
backend/account_api.py
backend/ai/api.py
backend/ai/providers.py
backend/ai/settings_api.py
backend/config.py
backend/public_registration.py
backend/rag/indexing.py
backend/rag/providers.py
backend/services/document_integrity.py
backend/services/documents.py
compose.public-beta-test.yaml
docs/SPRINT_14_1_PUBLIC_BETA_AUDIT.md
docs/SPRINT_14_2_PUBLIC_BETA_AUTHORIZATION_REPORT.md
docs/SPRINT_14_3_AI_DISABLED_ENFORCEMENT_REPORT.md
docs/SPRINT_14_4_PUBLIC_BETA_QUOTA_CONCURRENCY_REPORT.md
docs/SPRINT_14_5_PUBLIC_BETA_UX_EMAIL_ABUSE_REPORT.md
docs/SPRINT_14_6_1_SECURE_ROLLBACK_REPORT.md
docs/SPRINT_14_6_PREPRODUCTION_VALIDATION_REPORT.md
docs/SPRINT_14_7_1_RELEASE_CANDIDATE_REVIEW.md
docs/SPRINT_14_7_2_SQLALCHEMY_INTERMITTENT_FAILURE_REPORT.md
docs/SPRINT_14_7_3_RELEASE_RISK_QUALIFICATION_REPORT.md
docs/SPRINT_14_7_4_DOCUMENT_INTEGRITY_REPORT.md
docs/SPRINT_14_7_5_SUPPLY_CHAIN_REPORT.md
docs/SPRINT_14_7_6_PR_PREPARATION_REPORT.md
docs/SPRINT_14_7_PUBLIC_BETA_OPENING_RUNBOOK.md
frontend/server/app.mjs
frontend/server/app.test.mjs
frontend/src/components/Assistant.tsx
frontend/src/pages/AISettings.test.tsx
frontend/src/pages/AISettings.tsx
frontend/src/pages/Account.tsx
frontend/src/pages/CompareDocuments.tsx
frontend/src/pages/IntelligentLibrary.tsx
frontend/src/pages/PublicBeta.test.tsx
frontend/src/pages/Rag.test.tsx
frontend/src/services/account.ts
frontend/src/services/registration.test.ts
ops/testing/Dockerfile.beta-recipe
ops/testing/Dockerfile.beta-recipe.dockerignore
ops/testing/cleanup_beta_recipe.py
ops/testing/prepare_beta_recipe.py
ops/testing/traefik-public-beta-test.yaml
ops/testing/validate_beta_recipe.py
requirements.lock
tests/document_integrity_crash_child.py
tests/fake_smtp.py
tests/fixtures/public_beta_browser.mjs
tests/fixtures/public_beta_gateway.mjs
tests/fixtures/public_beta_smtp.py
tests/fixtures/public_beta_tcp_relay.py
tests/test_ai_disabled_enforcement.py
tests/test_build_materials.py
tests/test_byok.py
tests/test_deployment.py
tests/test_document_integrity.py
tests/test_openai_provider.py
tests/test_production_backups.py
tests/test_public_beta.py
tests/test_public_beta_authorization.py
tests/test_public_beta_email_abuse.py
tests/test_public_beta_email_e2e.py
tests/test_public_beta_postgresql_concurrency.py
tests/test_public_beta_snapshot.py
tests/test_public_beta_state.py
tests/test_release_security.py
tools/backup_local.py
tools/backup_production.py
tools/build_materials.py
tools/check_document_integrity.py
tools/deploy_production.py
tools/prepare_production.py
tools/public_beta_policy.py
tools/release_manifest.py
tools/release_security.py
tools/validate_restore.py
tools/verify_snapshot.py
```

### Exclusions

`var/` entier, journaux, wheelhouses, archives, bases SQLite, dumps, PDF/documents
personnels, certificats/clés, fichiers SMTP fictifs générés, venvs, node_modules,
dist, caches, test-results et fichiers privés `.env*`. Les fixtures de cette liste
sont des **scripts sources**, pas des données réelles ou captures de sessions.
Les sorties de build frontend restent ignorées. Aucun fichier privé n'est indexé.

Les candidats sont réguliers/non symlinks, sans extension de donnée/archive privée.
Scan limité aux candidats : aucun en-tête de clé privée ni motif de credential
courant détecté. Aucun contenu de `.env.production` ou stockage privé n'est lu.
Cela complète la revue humaine sans constituer une preuve absolue d'absence de secret.
Avant le commit, vérifier de nouveau **l'index réel**, pas seulement cette liste.

## 2. Contrôles de cohérence effectués

- 44 Python candidats analysés par AST ; 4 YAML parsés ; TOML et lock npm lisibles.
- Trois blocs Python embarqués des workflows analysés ; huit actions uniques
  référencées par SHA complet de 40 caractères. Origine distante non revérifiée.
- Six modules de bundle importés à plat depuis tools, sans exécuter leurs main.
- Collecte complète de **860 cas pytest**, sans erreur d'import ; ce n'est pas
  une exécution de ces 860 cas.
- Nouvel inventaire des dépendances exécuté avec `--require-pins` : couverture
  des 50 distributions runtime/test Windows ; lock npm examiné séparément.
- Fichiers et références CI locaux présents ; tests React/BFF et build TypeScript
  vérifient les imports frontend. Aucun téléchargement ni installation.
- L'image locale de preuves correspond aux 41 Python candidats backend/tests/tools
  concernés, vérifiés par SHA-256. Ce contrôle permet sa réutilisation en recette,
  sans prétendre qu'elle est une image publiée ou un build complet de production.

### Bundle sécurisé, exactement neuf fichiers

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

Les sept sources statiques et le manifeste/statement générés sont cohérents avec
les copies CI et les sets du validateur. `release.json` et le statement ne sont
**pas** des candidats Git : la CI les génère pour ses SHA/digests réellement publiés.
Les tests fabriquent des bundles fictifs pour exercer génération/validation/refus ;
aucune attestation ou approbation de release réelle n'est créée ici.

Les inventaires runner de 14.7.5 sont des artefacts séparés ; ils ne deviennent
pas un dixième fichier du bundle. `images.env` et `deployment-report.json`
restent des sorties distinctes. Profil `public-beta-2026-10-v1`, schéma 0007,
contrôleur actuel, registre root indépendant, guards ops, marqueurs et verrou
partagé `deployment.lock` préservés. Un hash de statement n'est pas une signature
et ne donne pas automatiquement l'approbation de l'administratrice.

## 3. Vérifications locales et résultats

Toutes les campagnes ci-dessous sont terminées et leurs sorties ont été relues ;
les journaux restent dans `var/s14-7-6-*`, exclus de Git.

| Campagne 14.7.6 | Réussis | Ignorés | Échecs / état |
| --- | --- | --- | --- |
| Python Windows 3.13.7, sélection essentielle | 433 | 12 | 0, 347,96 s |
| PostgreSQL 17.11/pgvector 0.8.7 neuf, intégrité/concurrence/guards | 124 | 2 | 0, 119,98 s |
| Docker non-root, Landlock/seccomp/protocole | 72 | 0 | 0, 10,42 s |
| Docker root, autorité du registre/approbation/guard ops | 2 | 0 | 0, 0,80 s |
| React/Vitest | 52 | 0 | 0, 10 fichiers |
| Node/BFF | 50 | 0 | 0 |
| TypeScript/Vite | Build | — | Réussi, Vite 4,98 s |
| Inventaire dépendances Windows | 50 distributions | — | Aucune contrainte manquante/divergente |
| Collecte Python | 860 collectés | — | Aucune erreur d'import |

La sélection Windows comprend intégrité, PDF/TXT, transactions, public/quota/email,
IA off, comptes/sessions/propriétaires, BYOK, gateway, admission upload, matériaux,
registre/rollback/déploiement et sauvegardes/inventaires/restauration simulée.
La sélection PostgreSQL comprend les 22 cas d'intégrité, neuf entrelacements
d'inscription, identité/quota, refus IA et sécurité du registre/déploiement.

Les 12 skips Windows sont six snapshots Docker opt-in, deux preuves root Linux,
une preuve d'autorité non-root Linux, une preuve Unix de symlink/droits et deux
cas PostgreSQL (barrière documentaire et historique public). Les deux skips PG
sont les preuves root, exécutées séparément ci-dessus. Aucun de ces skips n'est
un test rendu vert ou retiré pour faciliter la PR. L'avertissement préexistant
Starlette/TestClient-httpx n'est pas masqué. Les tests de restauration simulée
ne remplacent pas les six snapshots opt-in ni une restauration réelle B2.

Aucune suite complète Windows/WSL n'est annoncée comme exécutée dans cette phase :
leurs résultats 14.7.4 (775/817 réussis) restent historiques. Les campagnes se
recouvrent, ne pas additionner leurs totaux comme des cas uniques. Les tests ignorés
ne deviennent pas des validations. Les snapshots/E2E opt-in non exécutés et la
restauration B2 réelle restent explicitement hors preuve de cette préparation.

Docker Desktop local, images cached et `--pull never`, PostgreSQL neuf en tmpfs,
réseau interne propre, aucun port/bind/volume existant ; tests de confinement sans
réseau ni volume. Readonly, cap-drop ALL, no-new-privileges et ressources bornées.
Noyau local WSL/ABI local, pas une nouvelle recette du noyau/Traefik du VPS.
Les fonctions IA ne sont exercées que par mocks et par les tests de refus.

**Aucun test réel SMTP/B2/VPS réalisé dans cette préparation.** Aucun fournisseur
payant, inscription réelle, accès Registry ou donnée de production. L'état de la
production et des protections GitHub n'est pas relu à distance.

Commandes principales de cette phase, logs et basetemp neufs :

```text
python -m pytest tests/test_document_integrity.py tests/test_documents.py tests/test_transactions.py tests/test_public_beta.py tests/test_public_beta_state.py tests/test_public_beta_email_abuse.py tests/test_ai_disabled_enforcement.py tests/test_accounts_saas.py tests/test_byok.py tests/test_gateway_security.py tests/test_upload_admission.py tests/test_build_materials.py tests/test_release_security.py tests/test_deployment.py tests/test_production_backups.py tests/test_public_beta_snapshot.py -q -p no:cacheprovider --basetemp=var/pytest-14-7-6-essential --tb=short
python -m pytest --collect-only -q -p no:cacheprovider
python tools/build_materials.py --require-pins --npm-lock frontend/package-lock.json
npm.cmd run test:ui
npm.cmd run test:bff
npm.cmd run build
git diff --check
```

Le Python Windows est celui de `.venv/Scripts/python.exe`, déjà installé.
Aucune commande d'installation ou de téléchargement de dépendance n'est exécutée.

## 4. Proposition de PR prête à copier

Source dédiée recommandée, **non créée** : `preparation/sprint-14-review`.
Cible : `main`. La branche locale actuelle est conservée. Ce nom dédié évite de
mettre à jour sans vérification une éventuelle PR ancienne liée au nom Sprint 14.5 ;
l'existence distante de l'un ou l'autre nom n'est pas vérifiée ici.

Titre :

```text
Sprint 14 : bêta contrôlée, intégrité documentaire et livraison sécurisée — revue en brouillon
```

### Description de PR

Le bloc suivant est la description finale proposée ; aucune PR n'a été créée.

<!-- PR_BODY_START -->
## Objet

Préparer la revue du Sprint 14 avant toute décision de livraison. **PR en brouillon :
ce travail n'est pas une release candidate validée et n'autorise aucune fusion,
publication de RC utilisable, intervention VPS ou ouverture publique.**

## Changements majeurs

- Autorisation explicite de la préparation public/5, cinq admissions cumulatives,
  quota SQL atomique et fermeture/réouverture opératrice distinctes du déploiement.
- Vérification email et identité séparées du blocage administratif ; UX, consentement,
  renvoi et protections anti-abus sans promesse de livraison d'email.
- Désactivation serveur stricte des nouvelles générations/embeddings/connexions BYOK
  lorsque l'IA est fermée ; l'analyse classique reste utilisable.
- Rollback et reprise sûrs : bundle neuf fichiers, trois digests, statement lié aux
  artefacts, approbation root indépendante, contrôleur actuel et guards de sauvegarde.
- R14-SQL-02 : source conservée après commit incertain, connexion suspecte invalidée,
  vérification durable indépendante/barrière du writer ; suppression SQL avant
  nettoyage, bornes de stockage retenu et inventaire en lecture seule.
- Quatre transitifs observés désormais contraints, inventaire des matériaux en CI
  avec refus des dépendances runtime/test non contraintes ou divergentes.
- Recette locale, tests et rapports 14.1–14.7.6. Pas de nouvelle migration :
  schéma 0007 conservé, images de production toujours limitées à linux/amd64.

## Validations locales

Résultats de cette préparation : Windows 433 réussis/12 ignorés, PostgreSQL
124 réussis/2 ignorés, 72 preuves Linux natives et deux preuves root réussies,
52 tests React et 50 tests BFF réussis, build TypeScript/Vite réussi ; aucun échec.
Les ignorés et les limites sont détaillés dans
docs/SPRINT_14_7_6_PR_PREPARATION_REPORT.md. Collecte de 860 tests sans erreur d'import,
sans prétendre les avoir tous exécutés dans cette phase.

Les précédentes réinstallations hachées, comparaisons d'overlays et suites complètes
restent des preuves historiques datées. Les overlays locaux ne sont pas les trois
images de production reconstruites et certifiées.

## Risques ouverts

- **R14-SQL-01** : cause historique du GET 503 non identifiée ; non-reproductions
  ultérieures ne valent pas correction.
- **R14-SQL-02** : corrigé localement, testé sous fautes synthétiques et PostgreSQL ;
  ne répare pas automatiquement une incohérence ancienne.
- **R14-SQL-03** : inscription potentiellement commitée malgré 503 et mail absent ;
  compteur conservé, renvoi protégé, décision opératrice nécessaire.
- **RF10-03** : supply chain partiellement verrouillée ; 11 wheels Linux 3.13,
  outils PEP 517, bases, paquets système, commit pgvector et provenance à qualifier.
- File mail RAM, limites d'abus/NAT, restauration/alertes/exploitation et conformité
  des textes restent soumis aux validations prévues par le runbook.

**Aucun test réel SMTP/B2/VPS réalisé dans cette préparation.** Aucun téléchargement,
secret réel, activation IA, inscription publique réelle ou publication exécutés.

## Gates et interdictions de fusion

- python : inventaire contraint, suites Linux/SQLite/PostgreSQL/pgvector et
  Landlock/seccomp hôte/Docker ; aucun repli de sécurité.
- windows : Python 3.13, inventaire contraint et suite portable.
- frontend : React, BFF et TypeScript/build.
- Tous sur la dernière révision de PR et une base main à jour ; relever les SHA
  source, base et checkout réellement testé, qui peuvent être distincts.
- publish ne doit pas être requis sur une PR et doit rester ignoré par sa condition.
- Pas de fusion avec test en échec, manque de preuve obligatoire, fuite, dérive de
  source, rollback non sûr, RF10-03 non qualifié/non traité ou décisions de risques
  manquantes. Une CI verte ne lève pas ces conditions.

## Après une publication ultérieure autorisée

La CI de PR ne publie pas d'image. Une future fusion sur main peut lancer
automatiquement les trois publications amd64 ; elle exige donc une autorisation
distincte couvrant cet effet. Contrôler le run/attempt, digests, provenance/inventaires,
neuf fichiers et statement ; RF10-04 : arrêt en cas de publication partielle,
sans relance, suppression ni retagging automatiques. Recetter les images exactes,
puis seulement examiner approbation indépendante et livraison fermée autorisée.
Déploiement et ouverture sont encore deux décisions séparées ; IA toujours off.
<!-- PR_BODY_END -->

## 5. Autorisations et commandes futures

**Aucune commande de cette section n'est exécutée par cette mission.**

1. Autorisation commit : valider les 79 chemins, le nom de branche dédié et un commit
   cohérent. Tous les fichiers partagés de livraison/compte/tests doivent être présents
   ensemble ; ne pas découper les modules référencés arbitrairement. Vérifier l'état,
   absence de secret et baselines, créer la branche locale approuvée depuis ce travail
   conservé, indexer seulement les chemins explicites, lire le diff indexé et lancer
   `git diff --cached --check` avant commit.
2. Message proposé :
   `feat(security): préparer la revue de la bêta contrôlée et sécuriser la livraison`.
   Le titre ne présente pas une ouverture effective ou une RC déjà certifiée.
3. Autorisation push distincte : actualiser les refs **à ce moment seulement**,
   vérifier main ancêtre, les nouveaux commits attendus et l'absence de branche
   distante divergente. Si la base a évolué, arrêter avant toute réécriture/rebase/
   fusion automatique. Aucun force push, aucun push main.
4. Autorisation PR distincte : vérifier source/cible et éventuelle PR existante,
   utiliser `--draft`, sans auto-merge. L'ouverture déclenchera les tests déclarés
   par `pull_request` ; ne pas lancer manuellement publish/deploy.
5. Consulter la CI après autorisation : résultats complets, ignorés et artefacts,
   SHA source/base/checkout réel. Un simple numéro de run ou un ancien résultat
   vert ne suffit pas. Les protections effectives et permissions GitHub sont à
   relire alors, jamais supposées certifiées depuis ce dépôt local.

Exemple futur, après les autorisations et seulement avec la branche approuvée :

```text
git switch -c preparation/sprint-14-review
git add -- <les 79 chemins explicitement validés ci-dessus>
git diff --cached --name-only
git diff --cached --check
git commit -m "feat(security): préparer la revue de la bêta contrôlée et sécuriser la livraison"
```

Le placeholder de git add n'est pas une commande prête à lancer. Il doit être
remplacé par la whitelist exacte, sans glob, var, ajout global ou fichier non revu.
Push/PR ne sont pas inclus dans l'autorisation de commit. Après autorisations
séparées et contrôles de références :

```text
git push --set-upstream origin preparation/sprint-14-review
gh pr create --draft --base main --head preparation/sprint-14-review --title "Sprint 14 : bêta contrôlée, intégrité documentaire et livraison sécurisée — revue en brouillon" --body-file var/s14-7-6-pr-body.md
```

Le body-file privé proposé contient la même description que ce rapport ; il reste
exclu du futur commit. Aucun fetch, push, appel GitHub ou création de branche ici.

## 6. Conditions de CI et points bloquant toute fusion

Selon ci.yml local, une PR déclenche python/windows/frontend. Le job publish porte
`github.event_name != 'pull_request' && github.ref == 'refs/heads/main'` : il ne publie
pas pour cet événement, même si la cible de PR est main. deploy.yml reste manuel,
sur main, avec environnement production et contrôle d'approbateurs.

La politique GitHub réelle, ses restrictions de fork, éventuels workflows additionnels
côté organisation et ses checks imposés ne sont pas vérifiables hors ligne.
Exiger les trois checks obligatoires issus de GitHub Actions, branche à jour,
conversations résolues et aucune divergence/conflict avant toute décision de fusion.
Ne pas demander publish comme check obligatoire sur une PR où il est volontairement
ignoré. Refaire la revue si de nouveaux commits ou une nouvelle base apparaissent.

Interdictions de fusion : échec non expliqué, fuite/artefact dans l'index, invariants
documentaires/quotas/sessions/IA/guards altérés, source ou digests incohérents,
preuves RF10-03 incomplètes sans décision explicite compatible avec le périmètre,
SQL-01/SQL-03 non statués, ou absence d'autorisation. La future fusion déclenche
potentiellement une publication privée **automatique** ; elle ne peut donc pas
servir simplement à poursuivre une enquête sans accepter explicitement cet effet.

## 7. Qualification future RF10-03, indépendante de la PR

**Non exécutée. Aucune acquisition ni publication dans cette préparation.**

1. Ouvrir un lot séparé, avec autorisation explicite réseau et périmètre des origines,
   versions, plateformes, caches neufs et stockage privé des preuves. Réviser ce plan
   selon le code de la PR ; ne pas assimiler la revue humaine à son exécution.
2. Cible CPython 3.13 Linux amd64 : récupérer les onze wheels listés ci-dessous, puis
   compléter/vérifier la fermeture runtime/test entière. Refuser les sdists implicites,
   les tags incompatibles et une résolution de version non approuvée.
3. Pour chaque archive, enregistrer nom officiel, version, tags, taille, SHA-256 calculé,
   origine HTTPS sans credentials et preuves d'origine disponibles. Confronter aux
   métadonnées de l'index approuvé et aux attestations disponibles, sans inventer
   leur existence ; pas de hash de RECORD ni de copie d'un hash de wheel Windows.
   Les archives déjà en cache restent d'origine non certifiée jusqu'à cette revue.
4. Choisir/verrouiller séparément pip, setuptools, wheel et transitifs de build, avec
   artefacts/hashes réellement disponibles. Vérifier le support des options par le pip
   choisi, conserver PEP 517 isolé ou un builder dédié entièrement verrouillé.
   Construire/hacher la wheel projet issue du SHA revu. Aucun --require-hashes sur
   un ensemble incomplet ni application aveugle de --no-build-isolation.
5. Vérifier sur leurs origines les trois bases Python/Node/PostgreSQL, plateformes
   et digests de manifeste ; distinguer index, manifeste amd64 et Image ID local.
   Ne pas transformer un Image ID de preuve en digest de FROM. Figer/revoir aussi
   APT/APK, transitifs et toolchain ; une base par digest ne fige pas apt/apk update.
6. Identifier le commit complet du tag pgvector v0.8.7 sur l'origine officielle,
   vérifier son contenu et l'archive source, calculer son empreinte et contrôler la
   compilation PostgreSQL 17. Ne pas confondre pgvector Python 0.5.1, extension
   serveur 0.8.7 et SHA-256 de vector.so.
7. Construire les trois Dockerfiles complets, deux fois dans des builders propres
   à entrées identifiées, sans réutiliser un overlay comme preuve de recompilation.
   Comparer versions, hashes, paquets natifs, contenus et métadonnées/couches.
   Distinguer répétabilité des matériaux, équivalence fonctionnelle et bit à bit ;
   chaque écart doit être expliqué ou explicitement maintenu comme limite.
8. Exécuter CI requise et recette locale jetable sur ces images : PDF/TXT,
   SQL-02, auth/propriétaires, quota 5/6 et concurrence, email fictif, IA off,
   backup/restauration isolée, rollback/registre et confinement. Aucun appel payant.
9. Examiner inventaires des runners **et** des images, matériaux et provenance
   réellement émis, attestations disponibles et lien au SHA/run/attempt/digests.
   Ne pas activer un générateur SBOM non verrouillé ou déclarer le JSON interne
   conforme SPDX/CycloneDX sans preuve. Aucun audit CVE actualisé réalisé ici :
   prévoir son périmètre et ses limites séparément.
10. Après décision humaine sur les risques et autorisation de publication privée,
    vérifier les trois sorties amd64, neuf fichiers/statement et origine de CI.
    RF10-04 : si partiel, arrêter et conserver les preuves ; aucun retagging,
    suppression, relance ou approbation automatique.
11. Refaire la recette avec les **digests réellement publiés**, pas uniquement
    les images locales préalables. Écarter tout digest divergent ; ne pas déployer.
    Après seulement, examiner les préconditions du bootstrap/backup/registre root,
    secours corrigé ou correction en avant et autorisation distincte de livraison
    fermée. SMTP/B2/VPS réels et ouverture exigent leurs propres autorisations.

Archives manquantes identifiées en 14.7.5 :

```text
cffi==2.1.1
greenlet==3.5.6
httptools==0.9.0
jiter==0.17.0
MarkupSafe==3.0.4
psycopg-binary==3.3.6
pydantic_core==2.50.1
PyYAML==6.0.3
SQLAlchemy==2.0.55
uvloop==0.23.0
websockets==17.2
```

Les versions d'outils de build, bases Python/Node et commit pgvector inconnus
ne sont pas remplacés par des valeurs supposées correctes dans ce plan.

## 8. Risques distincts et conditions d'arrêt

| Risque | État à présenter au reviewer |
| --- | --- |
| R14-SQL-01 | Cause historique non identifiée ; aucune correction revendiquée à partir d'une non-reproduction. |
| R14-SQL-02 | Corrigé localement et testé sous fautes définies ; inspection read-only et conservation privée, sans réparation automatique d'une perte ancienne. |
| R14-SQL-03 | Inscription éventuellement commitée malgré 503/mail absent ; risque résiduel et décisions opératrice, pas de remboursement/reset automatique de quota. |
| RF10-03 | Partiellement verrouillé ; qualification future ci-dessus, aucune acceptation nouvelle. |
| RF10-04 | Publication séquentielle partielle possible ; arrêt/protection des preuves sans relance automatique. |

L'invalidation SQL-02 concerne les opérations documentaires, pas une correction
générale des commits d'inscription ou des pools. Le risque synthétique de transaction
résiduelle sur inscription documenté en 14.7.3 n'est pas déclaré corrigé ici.

Le retour non expliqué du pilote PowerShell de double overlay mentionné en 14.7.5,
les gaps de bit-reproductibilité, les tests opt-in et l'absence de preuves réelles
SMTP/B2/VPS ne sont ni masqués ni transformés en validations. Les snapshots valides
ne garantissent pas à eux seuls qu'une source manquante a été restaurée ; toujours
vérifier la correspondance fichiers/lignes et conserver le compteur cumulatif.
Les marqueurs de maintenance restent intouchés : pas de contournement pour redémarrer.

## 9. Vérifications après publication future

Distinguer deux publications : **branche/PR** et **images RC privées**.

Après branche/PR autorisées : relever URL/numéro, base/source, nouveaux commits,
checks effectifs et SHA réellement testé ; confirmer draft, absence d'auto-merge et
publish ignoré. En cas d'échec, conserver logs expurgés, analyser et demander une
décision avant nouveau commit/push. Les résultats locaux ne remplacent pas GitHub CI.

Après fusion/publication d'images autorisées seulement : relever merge SHA et run/
attempt, trois digests amd64/labels, bundle exact à neuf fichiers, hashes et statement,
inventaires/provenance et politique d'origine. Refaire la recette de ces digests puis
revoir approbation root/guards et bootstrap coordonné. Aucun lien current inventé,
aucun ancien Sprint 13 accepté comme secours corrigeant SQL-02, aucun déploiement
ou activation automatique à la suite d'une publication.

## 10. Verdicts et clôture

| Décision | Verdict de cette préparation |
| --- | --- |
| Présentation en PR en brouillon | Go technique sous transparence des risques et autorisations commit/push/PR distinctes. |
| Fusion | No-Go ; preuves et décisions ci-dessus manquantes, effet automatique de publication à autoriser. |
| Publication d'une RC utilisable | No-Go ; RF10-03 et décisions SQL résiduelles non closes, builds réels non certifiés. |
| Déploiement fermé | No-Go ; aucune approbation VPS/registre/backup/recette des digests réels dans ce lot. |
| Ouverture publique | No-Go ; nouvelle décision opératrice et tous les critères du runbook requis ; IA toujours off. |

Aucun fichier applicatif, workflow, dépendance, migration, quota, secret ou configuration
de production modifié dans cette mission. Seul ce rapport rejoint les candidats Git ;
corps de PR, audits et logs restent sous var, ignoré. Les 78 empreintes initiales
sont conservées ; seul ce nouveau rapport est ajouté au périmètre. `git diff --check`
et le contrôle des blancs du rapport réussissent, index vide et même branche/HEAD.
Le PostgreSQL de mission et son réseau sont nettoyés après vérification des labels
et de l'absence de montages persistants ; aucun volume ni service préexistant touché.
Aucune indexation, commit, push,
PR, merge, workflow distant, téléchargement, Registry ou VPS ; aucune inscription
publique ni IA activée. Les éventuelles commandes et étapes futures restent non exécutées.

**La branche peut être présentée en Pull Request en brouillon pour revue humaine,
après autorisation explicite et publication contrôlée de ses futurs commits. Cette
possibilité n'autorise aucune fusion, RC utilisable, livraison ou ouverture.**
