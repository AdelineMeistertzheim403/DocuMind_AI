# Sprint 13 — Préparation de la bêta publique contrôlée

Étude et implémentation locales du 25 octobre 2026. **Aucune ouverture publique autorisée.**
Branche : `preparation/sprint-13-public-beta`, base `15483068657cf5a3efb3a3aadfafcebbc201745f`.

## État initial vérifié

Le dépôt était propre sur `main`. La lecture des références GitHub par `git ls-remote origin`
a confirmé `main=1548306…` et `security/sec10-04-audit-logging=eb2ee2b4…` ; ce dernier est
ancêtre du premier, issu de la fusion SEC10-04. L'outil `gh` n'était pas disponible dans
le PATH ; aucune information de déploiement, de configuration privée ou de CI nouvelle
n'en est déduite. Aucun fetch, commit, push, workflow ou changement GitHub effectué.

| Domaine | Avant ce sprint | Intervention |
| --- | --- | --- |
| Comptes | Connexion, invitations, sessions serveur, CSRF, reset TLS | Conserver ; ajouter l'admission publique explicite |
| E-mail | Reset avec jeton haché, file RAM bornée | Ajouter vérification expirante à usage unique et renvoi |
| Abus | Limiteurs API/BFF et uploads | Ajouter plafond cumulatif SQL, preuve de travail et honeypot |
| Isolation | Owner UUID, espace personnel, SEC10-02/03 | Conserver, interdire aussi les identités legacy aux nouveaux comptes publics |
| IA | BYOK, budgets et réservations, mode démonstration | Refuser OWNER_DEMO aux comptes publics, même après fermeture |
| Suppression | Désactivation/révocation immédiates ; purge administrateur | Conserver ; simulation de nettoyage des inscriptions en attente |
| Exploitation | Sauvegardes, supervision, conservation et rollback existants | Aucun changement aux Sprints 7–12 ni installation de collecteur/alerte |
| Légal | Informations techniques, durées/exploitant à approuver | Page publique d'information et liens configurables ; approbation réelle indispensable |

Les succès historiques de restauration et l'état du VPS communiqués par l'exploitante ne
constituent pas une inspection actuelle. La capacité réelle disponible, le SMTP et les
documents juridiques de production ne sont pas vérifiés pendant ce travail.

## Admission implémentée

`REGISTRATION_MODE=disabled` reste la valeur par défaut ; `invite` conserve son invitation
individuelle et sa réponse 201. Le nouveau mode `public` utilise une réponse 202 générique
pour adresse existante, capacité épuisée, honeypot ou preuve incorrecte. Les refus de
format/conditions, de passerelle, de CSRF et de limitation gardent leurs codes dédiés.
Ce choix limite l'énumération par réponse ; il ne garantit pas un temps constant réseau/SQL.

Le navigateur obtient un défi aléatoire lié à l'IP validée par la passerelle, valable cinq
minutes, consommé une seule fois. Il calcule une preuve SHA-256, sans CAPTCHA tiers.
La recherche côté navigateur est bornée et rend régulièrement la main à l'interface.
Le stock RAM de défis est borné à 1 024. Cette protection ralentit l'automatisation : elle
ne prouve pas qu'un utilisateur est humain et n'arrête pas une attaque distribuée.

Après conditions versionnées acceptées, limites et preuve, une seule transaction réserve
une place par `UPDATE ... WHERE issued_count < limite AND NOT closed RETURNING`, puis
crée User, Workspace, Membership et budget BYOK avec un owner UUID généré côté serveur.
Une erreur SQL annule l'ensemble. Le compteur **cumulatif** inclut comptes en attente et
comptes ultérieurement supprimés ; il n'est jamais libéré par la purge. Ce plafond n'est
ni un quota quotidien ni un compteur d'utilisateurs actifs. Ne pas le remettre à zéro.

Le compte reste désactivé jusqu'à présentation du jeton reçu **et du mot de passe choisi**.
Un simple clic d'un destinataire non demandeur n'active donc pas un compte précréé par
un tiers. Le token est stocké uniquement sous forme de condensat ; le secret transite
par la file de courrier et le fragment du lien HTTPS, jamais dans la query string.
L'interface retire le fragment, le garde en mémoire et attend une action explicite.
L'activation ne crée pas automatiquement de session. Les sessions fabriquées pour un
compte en attente sont refusées, y compris avant lecture d'un upload.

Le renvoi exige mot de passe et nouvelle preuve, invalide les anciens liens et demeure
possible après fermeture des nouvelles admissions. Le reset permet au propriétaire de
la boîte de reprendre une préinscription non demandée ; il ne l'active pas. Une vérification
distincte reste obligatoire. La suppression demandée interdit renvoi/récupération/activation.
Les comptes historiques désactivés ne sont pas réactivés par ce parcours.

La file de courrier n'est pas durable. Échec SMTP, redémarrage ou file pleine peuvent
laisser un compte en attente ; le renvoi est le recours prévu, sans révéler son existence.
Pas d'envoi de courrier réel pendant les tests. Délivrabilité, SPF/DKIM/DMARC et surveillance
des échecs doivent être validés par l'exploitante avant admission réelle.

## Configuration nécessaire, sans activation implicite

Les exemples `.env.example` et `.env.production.example` restent fermés :

```dotenv
REGISTRATION_MODE=disabled
PUBLIC_REGISTRATION_LIMIT=0
PUBLIC_REGISTRATION_PER_HOUR=3
PUBLIC_VERIFICATION_TTL_SECONDS=3600
PUBLIC_CHALLENGE_DIFFICULTY=12
PUBLIC_AI_MAX_BUDGET_USD=1
PUBLIC_LEGAL_READY=false
PUBLIC_OPERATOR_NAME=
PUBLIC_CONTACT_EMAIL=
PUBLIC_LEGAL_NOTICE_URL=
PUBLIC_PRIVACY_URL=
PUBLIC_TERMS_URL=
PUBLIC_TERMS_VERSION=
```

Le démarrage en mode public refuse : BFF_SERVICE_KEY vide, legacy actif, OWNER_DEMO actif,
SMTP absent, identité/contact/version manquants, attestation légale non donnée ou liens
non HTTPS/avec identifiants/fragment. Le contrôle syntaxique ne valide ni le contenu légal
ni la disponibilité du SMTP. Renseigner les vraies coordonnées et faire approuver les
conditions, confidentialité, durées de conservation, traitement IA et gestion des demandes.
`PUBLIC_LEGAL_READY=true` est une attestation explicite de l'exploitante, pas une certification.
`ACCOUNT_BASE_URL` doit être l'origine HTTPS effectivement utilisée pour les liens.

Le Compose de production existant transmet déjà son env_file et le mode explicite ; il
n'est pas modifié. BFF_SERVICE_KEY, authentification, cookies Secure/HttpOnly/SameSite,
CSRF, confiance du proxy, allowlist et admission avant corps sont conservés. Un seul
processus API/BFF reste nécessaire aux sessions, défis et limiteurs RAM.

**Garde de livraison conservée :** `tools/prepare_production.py` et les contrôles
`check_config()`/prévalidation Settings de `tools/deploy_production.py` n'autorisent encore
que `disabled` et `invite`. Cette préparation permet donc une future livraison **fermée**,
mais l'ouverture publique via la chaîne existante demeure volontairement bloquée. Ne pas
contourner ces gardes en lançant directement Compose ou en modifiant la configuration à
chaud. Leur extension conditionnelle au mode public, avec tests et nouvelle revue des
prérequis, sera nécessaire après décision Go. Les étapes d'ouverture ci-dessous décrivent
le protocole cible, pas une commande aujourd'hui autorisée ni une chaîne déjà prête à ouvrir.

## Ressources et argent

| Protection effective | Valeur initiale | Portée / réserve |
| --- | --- | --- |
| Admission totale publique | 0 par défaut | SQL atomique, à fixer très bas après recette de capacité |
| Inscriptions | 10/min global ; 3/h/IP et adresse | Avant hachage ; une seule création/hachage public concurrente |
| Défis | 60/min global, 5/min/IP | Risque de refus partagé derrière NAT |
| Vérification | 10/min/IP | Token expirant et usage unique atomique |
| Documents | 100 par owner, 10 Mio/fichier | Limites existantes, pas une promesse de capacité VPS |
| Stockage | 500 Mio/owner, 5 Gio global | Contrôles existants ; espace disque réel à mesurer |
| Uploads | 2 globaux, 1/owner, 8 prévalidations | Budget temporaire 64 Mio ; garde libre 32 Mio |
| Délais upload | Auth 3 s, inactivité 5 s, réception 30 s | Total BFF 75 s ; revue Traefik réelle encore nécessaire |
| Extraction | 200 pages, 1 M caractères, 30 s, 512 Mio, 2 workers | Landlock ABI ≥ 3 + seccomp obligatoires en sandbox |
| IA publique | BYOK seulement, limite estimative initiale maximale 1 USD | Aucun financement OWNER_DEMO pour ce rôle ; pas de clé commune via legacy |

Le plafond IA applicatif est estimatif, cumulatif selon le suivi existant et n'est pas
une garantie de facturation fournisseur. L'IA reste désactivée dans cette préparation.
`PUBLIC_AI_MAX_BUDGET_USD` borne le budget initial et les modifications de préférences ;
abaisser cette valeur ne réécrit pas les budgets déjà enregistrés. Une réduction des
budgets existants exige une procédure contrôlée distincte ; ne pas la présenter comme
un coupe-circuit immédiat des travaux déjà réservés.
Les réservations/quotas et expirations BYOK existants restent en place. Les limites
de documents, stockage, concurrence et budget doivent être abaissées si les mesures
de capacité le justifient ; aucune charge de production n'a été exécutée.
Les quotas documentaires comptent les fichiers importés, pas toute la croissance PostgreSQL,
les archives, index, journaux ou tmpfs : ils ne remplacent pas une garde disque et une
mesure de capacité. Le plafond d'admission ne garantit pas à lui seul la disponibilité.

## Migration et données existantes

Migration additive `0007` après `0006` : quatre colonnes User (origine d'inscription,
date de vérification, version/date d'acceptation) et table singleton du compteur/fermeture.
Les identifiants, propriétaires, hachages, e-mails et états de désactivation existants
restent inchangés ; leur origine devient `legacy`, sans prétendre leur e-mail vérifié.
Les nouvelles invitations deviennent `invite`. Aucun fichier documentaire n'est déplacé.

Le downgrade refuse après toute admission publique, même si les utilisateurs ont été
supprimés. Ne pas effacer le compteur pour contourner cette garde. Le teardown des tests
réinitialise uniquement les bases fictives vérifiées vides à l'entrée ; ce n'est jamais
une procédure d'exploitation. Les manifests futurs doivent indiquer `schema_revision=0007`.
Les anciennes reprises de premières installations au schéma 0006 restent historiques.

## Validation locale

Les comptes, mots de passe, clés et documents de test sont fictifs. Les clients OpenAI
réels sont interdits par fixture. Aucune base existante ni secret réel utilisé.

| Campagne exécutée | Résultat |
| --- | --- |
| Python Windows 3.13.7, suite complète | **605 réussis, 40 ignorés, 0 échec** ; 699,66 s |
| WSL Python 3.12.3 / SQLite, suite complète | **644 réussis, 0 ignoré, 1 échec** ; 717,44 s ; détail ci-dessous |
| Docker Python 3.13 / PostgreSQL 17.11, pgvector 0.8.7, suite complète | **645 réussis, 0 ignoré, 0 échec** ; 532,84 s |
| WSL, cas de résumé 200 pages rejoué isolément | **1 réussi**, 6,75 s, aucune erreur SQL capturée ; n'efface pas l'échec global |
| API ciblée public/byok/accounts/audit, avant deux dernières assertions | 56 réussis, 0 échec |
| Nouveaux formulaires React seuls | 5 réussis |
| Suite React complète | 42 réussis, 0 échec |
| Suite BFF complète | 49 réussis, 0 échec |
| TypeScript + Vite production | Succès, 2 247 modules |
| Images locales API, isolation-tests et frontend | Trois constructions réussies, aucune publication |
| Docker isolation sans réseau/volume | 72 réussis, 0 ignoré, 0 échec |
| Recette HTTPS avec certificat fictif vérifié | 49 contrôles réussis |
| Contrôles API directs de passerelle/admission | 7 réussis |
| Chromium réel : mobile 390 px et desktop 1 280 px | 14 contrôles réussis |
| Journalisation API/BFF et PostgreSQL de recette | 28 événements structurés, 8 types requis, sentinelles privées absentes |

La suite publique nouvelle couvre 21 cas : défaut fermé/prérequis, activation différée,
jetons expirés/corrompus/utilisés, mot de passe incorrect sans consommation, réponse
générique et non-écrasement, honeypot/preuve/consentement, défi lié à l'IP expirant/borné,
inscriptions concurrentes, réservation SQL indépendante du sémaphore, fermeture/réouverture,
reset d'une préinscription non demandée, rôle public/BYOK/legacy, parcours documentaire,
isolation et effacement, nettoyage en simulation et compteur conservé, downgrade refusé,
absence de données sensibles dans l'audit et préservation 0006→0007→0006 sans admission.

Commandes principales (environnements factices neutralisés, basetemp uniques sous `var/`) :

```powershell
python -m pytest tests/test_public_beta.py tests/test_byok.py tests/test_accounts_saas.py tests/test_security_audit.py -q -p no:cacheprovider --tb=short --basetemp <temporaire-local-neuf>
python -m pytest -q -p no:cacheprovider --tb=short --basetemp <autre-temporaire-local-neuf>
npm --prefix frontend run test:ui
npm --prefix frontend run test:bff
npm --prefix frontend run build
```

Sous Windows, `python` désigne en pratique `.venv/Scripts/python.exe` (Python 3.13.7).
La copie WSL exclut `.env`, `.git`, `var` et dépendances locales ; nouveau répertoire
`/var/tmp/documind-s13-a7b75801`, venv Python 3.12.3 et contraintes `requirements.lock`.
Commande exécutée : `wsl -d Ubuntu --exec bash <script-local-ignoré>/linux-test.sh`, puis
la même suite pytest complète sur SQLite fictif. Aucun fichier Windows privé copié.

La recette réutilise `compose.upload-test.yaml`, sa surcharge Windows locale ignorée
(nécessaire à l'exposition HTTPS Docker Desktop) et une surcharge privée propre au
nouveau projet **s13-a7b75801** : sous-réseau 172.30.250.0/24, port local 55782,
nouveau certificat, nouvelles bases `upload_test` et `beta_tests`, aucun volume nommé.
Les quatre services étaient opérationnels, API/BFF/PostgreSQL healthy, Traefik HTTPS.
L'application fictive a été migrée à **0007** ; les tests PostgreSQL utilisent exclusivement
la seconde base vide, jamais celle du parcours interactif. PostgreSQL reste 17/pgvector.
Les versions relevées sont PostgreSQL **17.11**, pgvector **0.8.7** ; résultats ci-dessus.

Les commandes Compose emploient `--env-file var/s13-a7b75801/recipe.env`, `-p s13-a7b75801`,
les deux fichiers existants et la surcharge `var/s13-a7b75801/compose.local.yaml` ; aucune
lecture du `.env.production` réel. Le démarrage utilise `up --no-build --wait db`, création
de `beta_tests`, `run --rm --no-deps api alembic upgrade head`, puis `up --no-build --wait
api web traefik`. DB et documents sont tmpfs, les images ont des noms uniques.

La suite pgvector utilise l'image isolation-tests avec source expurgée montée read-only
sur `/suite`, workdir `/suite`, seul réseau interne `s13-a7b75801_data`, base beta_tests,
rootfs read-only, cap-drop ALL, no-new-privileges, 1 536 Mio/2 CPU/PID 64 et tmpfs /tmp.
La preuve parseur séparée emploie les mêmes bornes avec **`--network none` sans volume**.
La surcharge Windows rend le réseau proxy non interne pour joindre le port depuis
Docker Desktop ; cela ne prouve pas l'absence d'egress du BFF. Les réseaux données et
application restent internes et le parseur est testé sans réseau.
Le noyau local observé est 6.18.54.1 WSL, Landlock ABI 7 ; ce n'est pas une attestation
du noyau/configuration actuellement déployés. Aucun assouplissement du sandbox.

Le courrier est intercepté en mémoire par un module **uniquement de recette**, monté
read-only depuis `var`, avec lecture interne protégée par la seule clé fictive ; ce module
n'est ni dans les images publiables ni dans le code applicatif ni dans l'inventaire Git.
Il ne valide pas le SMTP réel. Les contrôles HTTPS Python vérifient SNI et certificat en
utilisant ce seul certificat comme ancre, sans installer de CA système. Chromium conserve
son sandbox et accepte uniquement l'empreinte SPKI du certificat fictif ; aucun
`ignoreHTTPSErrors` global. Pas de token, mot de passe ou cookie dans les comptes rendus.

Le navigateur a réellement calculé la preuve WebCrypto, retiré le fragment, vérifié puis
connecté un compte fictif, ouvert le menu mobile, testé focus et absence de débordement
horizontal, cookie sécurisé et absence de secrets dans local/sessionStorage. Ce n'est
pas un audit WCAG complet ni un test de tous les navigateurs ou appareils.
Les premiers essais du script privé ont rencontré un encodage UTF-16 PowerShell de
l'empreinte, un sélecteur accentué altéré et un menu mobile encore fermé ; seuls les
scripts de recette ont été corrigés, sans assouplir l'application. Le passage final
à 14 contrôles est conservé séparément ; aucun échec initial n'est effacé du bilan.
La recette utilise une difficulté de preuve **10**, contre 12 par défaut : mesurer cette
valeur par défaut sur des appareils mobiles représentatifs avant ouverture. Changer la
taille du viewport Chromium ne simule ni leur CPU ni leur technologie d'assistance.

Le parcours HTTPS couvre création, attente, vérification à usage unique, première
connexion, TXT fictif/sandbox/analyse, logout/login, reset et révocation, second owner
refusé 404, fermeture SQL sans perte de session, réouverture, demande d'effacement et
purge administrative fictive. Aucun `.part` résiduel. La purge conserve le compteur
d'admissions et les registres pseudonymes prévus ; les sauvegardes réelles ne sont pas touchées.

La collecte locale des journaux compare les valeurs sentinelles sans imprimer les logs.
L'événement de purge est émis dans stdout de la commande administrative, pas dans le
journal du processus API : le contrôle Docker attend donc la **demande** d'effacement
dans ce dernier. Aucun collecteur ni alerte supplémentaire installé. Le log PostgreSQL
de cette campagne ne contient pas de STATEMENT/DETAIL ; cela ne garantit pas l'absence
générale de données SQL dans d'autres circonstances. La rotation VPS reste à vérifier.

### Réserve de test Linux/SQLite

La campagne complète WSL échoue dans
`test_large_pdfs_multilevel_complete_with_page_provenance[200-400]` : le polling du job
attend 200 et reçoit 503 `Base de données indisponible`, avec l'événement expurgé
`system.database.unavailable`. Ce sont les faits confirmés. Aucun paramètre fournisseur
réel n'est utilisé. Une contention SQLite sous exécution parallèle de campagnes est
une **hypothèse**, pas une cause démontrée ; l'exception SQL originale n'est pas conservée
dans le journal sécurisé. Une réserve similaire était déjà documentée au Sprint 12.

Le même cas, rejoué via `python -m pytest` avec un plugin de diagnostic temporaire
ne collectant que type/code d'erreur, passe (1/1) sans erreur SQL capturée. Le plugin
n'altère aucun timeout, statut attendu ou mécanisme d'accès. Une première tentative
de diagnostic par `pytest.main()` non gardé avait réexécuté le harnais dans les workers
multiprocessing, causant un upload 422 et une erreur de teardown : résultat de harnais
invalide, distinct du 503 initial. Elle a été remplacée par l'invocation CLI correcte.
Pas de correction appliquée au moteur de résumé ou aux politiques du sandbox.

Les 40 preuves natives Linux passent dans la campagne WSL et dans la suite PostgreSQL ;
les 21 nouveaux cas publics passent sur les trois plateformes. Cela ne transforme pas
la suite WSL complète en succès : une confirmation globale Linux stable reste requise
avant validation de livraison. L'avertissement Starlette/httpx existant est également
conservé, sans changement de dépendance pour le masquer. Les charges complètes, SMTP
réel, audit WCAG, restauration récente et configuration Traefik du VPS ne sont pas validés.

### Inventaire local

25 fichiers candidats, sans indexation ni commit :

- Exemples fermés : `.env.example`, `.env.production.example`.
- Admission et comptes : `backend/public_registration.py` (nouveau), `backend/account_api.py`,
  `backend/account_admin.py`, `backend/account_models.py`, `backend/auth.py`,
  `backend/authentication.py`, `backend/config.py`, `backend/main.py`.
- Restriction du financement public : `backend/ai/settings_api.py`.
- Audit expurgé : `backend/security_audit.py`, `backend/audit_middleware.py`.
- BFF : `frontend/server/app.mjs`, `frontend/server/app.test.mjs`.
- Interface : `frontend/src/App.tsx`, `frontend/src/pages/Account.tsx`,
  `frontend/src/pages/PublicBeta.test.tsx` (nouveau), `frontend/src/services/account.ts`,
  `frontend/src/services/registration.ts` (nouveau).
- Migration : `migrations/versions/0007_public_beta.py` (nouveau).
- Tests : `tests/test_public_beta.py` (nouveau), `tests/conftest.py`, `tests/test_deployment.py`
  (le contrôle de tête réelle est dynamique ; les scénarios historiques 0006 restent tels quels).
- Présent rapport : `docs/sprint-13-public-beta.md` (nouveau).

Aucun script `tools/`, fichier systemd `ops/`, workflow, Dockerfile, Compose de production,
politique Landlock/seccomp ou procédure historique n'est modifié. Les six nouveaux fichiers
ont aussi été vérifiés pour syntaxe Python/espaces finaux/fin de fichier ; `git diff --check`
ne suffit pas seul à inspecter des fichiers non suivis. Les traces, certificats, harnais
et surcharges de recette sous `var/` sont ignorés ; aucun fichier de secrets n'est candidat.

Après vérification des labels, noms et absence de montage de type volume, les **quatre
seuls conteneurs et trois réseaux nouveaux** du projet s13 ont été retirés par `compose
down --timeout 30`, sans `-v` ni prune. La liste des réseaux préexistants est inchangée ;
aucun conteneur ne reste démarré par cette campagne. Images et traces privées de test
restent locales pour revue. Aucun service, volume, timer ou donnée de production touché.

## Ouverture progressive proposée — non exécutée

1. Revue Git puis autorisations distinctes pour commit/PR, publication et livraison.
   La CI main publie après python/windows/frontend ; elle ne déploie pas automatiquement.
2. Valider les documents légaux et l'exploitant, le SMTP TLS de bout en bout, le traitement
   des demandes d'effacement et les responsables de suivi. Choisir la conservation réelle.
3. Mesurer CPU/RAM/disque/temporaire sous charge locale représentative. Vérifier sauvegarde
   récente Restic confirmée, restauration indépendante et place avant migration via procédures
   existantes et verrou partagé. Aucun timer, collecteur ou alerte supplémentaire installé ici.
4. Après autorisation de livraison : sauvegarde cohérente, migration contrôlée 0007,
   déploiement initial fermé (`disabled`, legacy=false, owner_demo=false, AI=false), healthchecks,
   test d'un compte fictif existant, isolation et admission upload. Ne pas utiliser `--initialize`
   ou `--recover-from` pour une mise à jour normale déjà installée.
5. Lever la réserve transport ci-dessous ou obtenir une décision de risque publique explicite
   étayée par un test du proxy réel. Revoir aussi la minimisation des journaux SQL/Traefik.
6. Seulement après accord d'ouverture : mode public, plafond initial proposé de **5 admissions
   cumulatives**, documents approuvés et paramètres validés. Contrôler le singleton avant/après.
   Ne pas augmenter automatiquement le plafond ; revue manuelle après observation.

## Fermeture d'urgence et nettoyage — commandes préparées uniquement

Dans une release déjà autorisée, depuis `/srv/documind-ai/current`, avec le Compose et
l'env_file habituels, adapter le préfixe aux procédures Sprint 6. Ces commandes ne sont
pas exécutées par ce sprint :

```bash
cd /srv/documind-ai/current
PRODUCTION_ENV_FILE=/srv/documind-ai/.env.production docker compose --env-file /srv/documind-ai/.env.production --env-file /srv/documind-ai/current/images.env -p documind-prod -f compose.production.yaml exec -T api python -m backend.account_admin public-registration status
PRODUCTION_ENV_FILE=/srv/documind-ai/.env.production docker compose --env-file /srv/documind-ai/.env.production --env-file /srv/documind-ai/current/images.env -p documind-prod -f compose.production.yaml exec -T api python -m backend.account_admin public-registration close --execute
PRODUCTION_ENV_FILE=/srv/documind-ai/.env.production docker compose --env-file /srv/documind-ai/.env.production --env-file /srv/documind-ai/current/images.env -p documind-prod -f compose.production.yaml exec -T api python -m backend.account_admin public-registration status
```

Le drapeau SQL ferme les admissions immédiatement après commit, sans redémarrer ni révoquer
les comptes existants. Une admission déjà engagée peut terminer avant cette fermeture.
Le compteur n'est jamais réduit ; vérification des admis, connexion, reset et renvoi restent
disponibles. Vérifier l'interface et une inscription fictive sans nouvelle place réservée.
En défense supplémentaire, planifier `REGISTRATION_MODE=disabled` par la procédure normale,
sans recréation improvisée ni arrêt PostgreSQL. Une réouverture exige accord explicite,
mode public, capacité restante et `public-registration reopen --execute` ; sans `--execute`
close/reopen sont des simulations. Aucun bouton administratif public n'existe.

`python -m backend.account_admin purge-pending --older-than-hours 48` est une simulation
locale administrative. L'exécution explicite `--execute`, après sauvegarde/revue, traite
seulement les comptes publics non vérifiés anciens, sans lien encore valide, document,
réservation ou consommation IA ; elle réutilise la purge existante et garde le compteur.
Pas de tâche automatique ajoutée. Les demandes de suppression actives suivent la purge
administrative Sprint 5, en respectant les workers/réservations ; la restauration ne doit
pas remettre en service un compte supprimé sans réappliquer les demandes concernées.

## Suivi quotidien et seuils proposés

Pendant les premiers jours : vérifier health API/BFF et HTTPS, admissions vs plafond,
comptes en attente, file/échecs SMTP, refus/429/503, latence, CPU, mémoire, espace disque,
taille `/app/var`, `.part` résiduels, dernier snapshot Restic confirmé et état des timers
existants. Consulter localement des fenêtres bornées `docker compose ... logs --since 24h
--tail 200 api web` ; ne pas publier les journaux bruts ou activer des logs de corps/SQL/SMTP.
Rechercher uniquement types d'événements et request IDs autorisés SEC10-04 ; expurger tout
diagnostic avant partage. Contrôler rotation et permissions avec l'exploitante.

Seuils de départ à confirmer par capacité : fermer les admissions si moins de 8 Gio libres,
disque/mémoire conteneur > 80 %, CPU > 80 % soutenu cinq minutes, healthcheck non sain,
échecs SMTP persistants ou sauvegarde quotidienne absente depuis plus de 26 h. À 90 % mémoire
ou disque < 4 Gio, incident prioritaire selon runbook ; aucun nettoyage de volume automatique.
Ce sont des seuils d'intervention proposés, pas des mesures effectuées ni de nouvelles alertes.
La journalisation best effort peut perdre des événements : l'absence de log n'atteste pas
l'absence d'incident. Aucun collecteur/alerte avancée installé.

## Retour arrière et restauration

Fermer d'abord l'admission, sauvegarder via les procédures existantes, garder les preuves
et une seule version de chaque service. Un retour applicatif à 0006 ne doit pas tenter
de downgrade SQL 0007 après admission ; garder le schéma additif et faire valider sa
compatibilité par la procédure de rollback existante. Le déployeur refuse normalement
une incompatibilité de manifestes : ne pas éditer ceux-ci pour passer la garde. Une
release de retour compatible 0007, fermée, est préférable à une rétrogradation forcée.
Si l'on revient à une application sans contrôles du rôle public, imposer disabled,
legacy=false, owner_demo=false et AI=false ; les comptes en attente restent désactivés.
Les sessions et clés BYOK RAM sont perdues au redémarrage, pas les documents ni comptes.

Une restauration complète reste une intervention séparée, sauvegardée et approuvée :
Restic vers emplacement indépendant, vérification du manifeste/empreintes, PostgreSQL
compatible et test isolé avant décision de restauration. Jamais `down -v`, reset, suppression
de snapshot ou manipulation du compteur pour contourner les protections. Aucun exercice
de restauration de production n'est réalisé ici.

## Réserve Expect et verdict

La réserve HTTPS `Expect: 100-continue`, corps annoncé non envoyé, connexion persistante
devant Traefik reste **ouverte**. Les refus BFF/ASGI avant lecture sont testés mais ne
prouvent pas une réponse finale immédiate à la frontière proxy. Le scénario avec
`Connection: close` n'est pas équivalent. Sprint 13 ne modifie pas la politique du proxy
pour masquer cette réserve ; la configuration réellement déployée n'a pas été inspectée.
Une sonde locale unique, bornée à trois secondes, connexion persistante et corps jamais
envoyé, n'a reçu aucune réponse finale dans cette fenêtre. Elle confirme une absence de
preuve de rejet immédiat ; elle ne démontre ni une attente infinie ni une saturation.

**No-Go pour activer publiquement aujourd'hui.** Il manque l'approbation des documents
légaux/identité/conservation, la délivrabilité SMTP réelle, la capacité et les contrôles
opérationnels récents, ainsi qu'une résolution ou acceptation publique explicite de la
réserve transport et l'extension revue des gardes de livraison fermées. L'ancienne
acceptation de publication privée RF10 ne couvre pas cette
ouverture. La préparation locale pourra être proposée en revue après les validations
et réserves explicites de ce rapport, dont le 503 WSL encore sans cause démontrée ; elle
n'autorise ni commit, ni publication, ni admission publique réelle. La suite Linux globale
n'est pas entièrement verte et une livraison ne doit pas être validée sur le seul rejeu isolé.
