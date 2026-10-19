# Sprint 6 — Registry privée, Traefik existant et déploiement approuvé

## État et audit

Infrastructure confirmée par l’administratrice : Traefik **v3.0**, fournisseur Docker,
réseau externe **web**, entrypoint **websecure**, resolver **letsencrypt** ; Registry
**registry.adelinemeistertzheim.fr**, conteneur existant
`design-pattern-playground-registry-registry-1`. Domaine applicatif :
**documind.adelinemeistertzheim.fr**. Environ 41 Go libres déclarés sur le VPS.

Audit du dépôt : backend non-root sur 8000, BFF Express non-root sur **3000**, PostgreSQL 17
avec pgvector 0.8.7 sur 5432. Les healthchecks existants sont conservés. Le worker des résumés,
les sessions et les clés BYOK partagent la mémoire du processus API ; une seule instance API/BFF.
Les migrations atteignent actuellement `0006`. Aucun changement de schéma n’est introduit ici.

Le Compose du Sprint 5 construisait sur place et créait un Traefik séparé. Il est adapté,
pas dupliqué : trois images privées, aucun port hôte publié, aucun nouveau proxy, et uniquement
le BFF connecté au réseau `web`. Les réseaux `data` et `application` restent internes.
Le backend conserve un réseau de sortie dédié pour joindre OpenAI/SMTP ; cela ne publie aucun port.
API et DB portent `traefik.enable=false`, même si le proxy expose par défaut les autres conteneurs.

Le nom du projet reste `documind-prod`. Les volumes restent
`documind-prod_production_database` et `documind-prod_production_documents`. Aucun
`container_name` global, aucune commande de nettoyage global, aucun retrait de volumes.
Le conteneur Registry et les autres applications ne sont ni reconfigurés ni redémarrés.

## Images et versions

La CI publie ces dépôts avec `sha-<SHA Git complet de 40 caractères>` :

- `registry.adelinemeistertzheim.fr/documind-ai/backend` ;
- `registry.adelinemeistertzheim.fr/documind-ai/frontend` ;
- `registry.adelinemeistertzheim.fr/documind-ai/postgres`.

Le troisième dépôt distribue le **Dockerfile.db existant**, nécessaire à pgvector. Il ne
remplace pas la Registry. Images AMD64 et ARM64 ; le VPS télécharge sa propre plateforme.
Chaque image porte `org.opencontainers.image.revision` et sa valeur est vérifiée au déploiement.

Un artefact `documind-release-<SHA>` contient `release.json`, le Compose et les scripts exacts
de cette version. Les images déployées sont épinglées par **digest SHA-256**, jamais par `latest`.
Le manifeste inclut la révision de base testée et celle supportée pour un retour arrière.

Le workflow refuse de réutiliser un tag SHA déjà publié. Une Registry Docker ordinaire peut
cependant permettre à un autre client autorisé de modifier un tag : sans politique serveur,
le nom du tag n’est pas une garantie d’immutabilité. Le digest du manifeste rend la sélection
déployée immuable. Ne pas supprimer les digests des versions encore nécessaires au rollback.
Une publication partielle ou une relance sur un SHA déjà publié est refusée : utiliser l’artefact
existant s’il est complet, sinon préparer un nouveau commit après diagnostic. Pas de suppression
automatique d’images dans la Registry.

## Secrets GitHub à configurer

Dans **Settings → Secrets and variables → Actions**, au niveau du dépôt pour la CI :

| Secret | Usage |
|---|---|
| `REGISTRY_PUSH_USERNAME` | compte de publication des trois dépôts DocuMind |
| `REGISTRY_PUSH_PASSWORD` | mot de passe/token de ce compte |

Dans **Settings → Environments → production**, uniquement pour le déploiement approuvé :

| Secret | Usage |
|---|---|
| `REGISTRY_PULL_USERNAME` | compte de téléchargement, lecture seule si l’autorisation existante le permet |
| `REGISTRY_PULL_PASSWORD` | mot de passe/token de téléchargement |
| `VPS_HOST` | véritable adresse SSH, IP v4 ou nom DNS ; ne pas déduire cette valeur du domaine web |
| `VPS_PORT` | véritable port SSH, obligatoire, sans valeur supposée |
| `VPS_USER` | compte de déploiement autorisé sur le VPS |
| `VPS_SSH_KEY` | clé privée dédiée à ce déploiement |
| `VPS_KNOWN_HOSTS` | ligne OpenSSH du VPS, empreinte vérifiée par un canal indépendant |

Ajouter aussi la **variable d’environnement GitHub** `VPS_DEPLOY_PATH` : répertoire absolu
choisi pour DocuMind, sans espaces ni `..`, par exemple `/srv/documind-ai`. Cet exemple n’est
pas un chemin observé sur le VPS. La clé SSH publique correspondante doit être autorisée sur
le compte choisi. Restreindre cette clé (pas de redirection de ports/agent/X11, pas de PTY).
L’accès Docker donne des privilèges importants sur le serveur ; protéger ce compte comme un
compte administrateur et ne pas partager sa clé avec les autres applications.

L’empreinte doit être vérifiée depuis la console de confiance du fournisseur VPS. Ne pas
remplacer cette vérification par un `ssh-keyscan` accepté aveuglément. `StrictHostKeyChecking=yes`
reste actif dans tous les appels SSH/SCP.

Configurer des comptes Registry distincts et vérifier leurs droits **réels**. Un simple fichier
htpasswd n’établit pas nécessairement des droits lecture/écriture par dépôt. Ne pas supposer
qu’un compte nommé « pull » est en lecture seule. Vérifier l’autorisation existante sans modifier
le conteneur Registry durant ce sprint. Aucun identifiant ne doit apparaître dans une URL.

Les identifiants de téléchargement passent par stdin sur SSH et `docker login --password-stdin`.
Le VPS utilise un `DOCKER_CONFIG` temporaire privé, effacé à la fin du processus. Aucun mot de
passe Registry n’est passé dans la ligne de commande ou conservé dans le bundle de release.
Le client et le daemon doivent valider TLS ; le déploiement refuse un réglage de Registry
insecure explicite ou un CIDR insecure correspondant à son adresse.

## Approbation GitHub obligatoire

Créer **production**, ajouter au moins un **Required reviewer**, limiter les déploiements à
`main` et désactiver le contournement administrateur si disponible. Protéger aussi la branche
`main` et les modifications de workflows par revue. L’option empêchant sa propre approbation
nécessite une autre personne habilitée ; l’activer si votre organisation le permet.

Le workflow vérifie via l’API que des reviewers obligatoires sont effectivement configurés.
Un simple nom `environment: production` ne suffit pas. La disponibilité de ces protections
dépend du plan et de la visibilité du dépôt : si elles sont indisponibles, ce workflow refuse
le déploiement ; ne pas supprimer le contrôle pour contourner ce prérequis.
[Documentation GitHub des environnements](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments).

## Préparation du VPS, sans démarrer DocuMind

Conditions : Docker/Compose existants, Python **3.11+**, compte de déploiement configuré,
accès en lecture à la Registry, réseau `web` existant. Le nom du conteneur Traefik confirmé
est `traefik`. Vérifier CPU/RAM/disque avec les autres applications avant
la première ouverture. Les plafonds conservés sont API 1,5 GiB/2 CPU, DB 1 GiB/1 CPU et BFF
512 MiB/1 CPU. Ce sont des maxima, pas des réservations ni une garantie de capacité du serveur.

Choisir le répertoire ; les commandes ci-dessous emploient un exemple à adapter :

```bash
install -d -m 700 /srv/documind-ai
# Transférer .env.production.example depuis le dépôt puis créer le fichier réel localement.
# Le répertoire doit appartenir au compte de déploiement.
chmod 600 /srv/documind-ai/.env.production
python3 --version
docker compose version
docker network inspect web --format '{{.Name}}'
free -h
df -h
docker stats --no-stream
```

Dans `.env.production`, renseigner sur le VPS : `POSTGRES_PASSWORD` aléatoire compatible
avec une URL (base64url conseillé), `BFF_SERVICE_KEY` distinct de 32 caractères minimum,
`TRAEFIK_CONTAINER=traefik`, `ACCOUNT_BASE_URL=https://documind.adelinemeistertzheim.fr`,
SMTP si nécessaire. Garder `LEGACY_API_ENABLED=false`, `REGISTRATION_MODE=disabled` ou `invite`,
`OWNER_DEMO_ENABLED=false` et `AI_ENABLED=false` pour le premier démarrage. Aucune inscription libre.

`DEPLOY_MIN_FREE_GIB=8` impose une marge avant téléchargement ; un second contrôle demande
aussi la place de la base et des documents avant sauvegarde. Docker ne fournit pas de quota
portable sur ses volumes nommés : conserver les quotas documentaires de l’application, prévoir
un quota/une alerte du système de fichiers et surveiller les WAL PostgreSQL et sauvegardes.
Les journaux Docker restent limités à trois fichiers de 10 MiB par service. Rien n’est purgé
automatiquement pour gagner de l’espace.

Les secrets applicatifs restent sur le VPS, **pas dans GitHub ni dans l’artefact**, sauf
identifiants Registry/SSH explicitement listés. Sauvegarder séparément `.env.production` et
les clés SSH de façon chiffrée. Ne pas modifier les secrets `.env` de l’installation locale.

## DNS, TLS et BFF

Créer l’enregistrement DNS A du sous-domaine vers la véritable IP v4 du VPS. Ajouter AAAA
uniquement si IPv6 fonctionne réellement pour Traefik et les challenges TLS. Conserver les
ports/règles firewall et resolver de votre Traefik actuel ; aucune seconde instance, aucun
nouveau certificat local, aucune modification de sa configuration globale.

Labels DocuMind : réseau `web`, routeur/service `documind-ai`, Host exact, TLS sur `websecure`,
resolver `letsencrypt`, service interne **3000**. Les noms sont propres à DocuMind. Vérifier
avant ouverture qu’aucune autre application n’utilise déjà ce Host ou ces noms de routeur.
[Référence Traefik v3.0 Docker](https://doc.traefik.io/traefik/v3.0/routing/providers/docker/).

Le middleware impose `X-Forwarded-Proto=https` sur ce seul routeur HTTPS. Le BFF conserve
Host/Origin, cookies HttpOnly Secure SameSite=Strict et jetons CSRF. Il n’active pas un
`trust proxy=true` global. Le déployeur lit l’IP **réelle du conteneur Traefik sur web** et
la fournit via `BFF_TRUSTED_PROXY_IPS`. Les en-têtes seuls d’un client non fiable sont refusés.
Aucun secret n’est inscrit dans les labels Docker. Le mécanisme secret de Caddy local reste
compatible et inchangé ; le Compose de production ne dépend pas de Caddy.

L’IP n’est pas supposée stable : si Traefik est recréé avec une autre adresse, le BFF refuse
les accès HTTPS privilégiés jusqu’au rafraîchissement de sa configuration. Relancer un
déploiement approuvé de la même release pour relever l’adresse actuelle. Un autre conteneur
partageant `web` n’est pas automatiquement reconnu comme proxy. Vérifier les paramètres
`forwardedHeaders` du Traefik existant, notamment si un CDN le précède ; ne pas activer
`insecure=true`. Les adresses IP servent à limiter les abus, pas à identifier un utilisateur.

## CI et publication

`.github/workflows/ci.yml` teste les PR, les push sur `main` et les lancements manuels :
tests Python/SQLite, puis suite complète PostgreSQL/pgvector construite avec `Dockerfile.db`,
React, BFF, TypeScript et build frontend. Les constructeurs OpenAI réels sont interdits dans
les tests par une fixture globale. Aucun secret de déploiement n’est donné aux tests.

La publication dépend des deux jobs de tests et n’a lieu que depuis `main`, jamais sur une PR.
Les actions sont figées par leur SHA officiel. Le runner GitHub construit les images, le VPS
ne compile rien. Un artefact n’est livré qu’après publication des trois digests.

Avant le premier push, examiner les changements locaux : des fichiers du Sprint 5 peuvent
encore ne pas être commités. Inclure les fichiers applicatifs nécessaires ; exclure `.env`,
`.env.production`, `var/`, documents et clés. Aucun commit ni push n’a été effectué par l’agent.
Configurer les secrets de publication avant le lancement réel. Les builds locaux ne prouvent
pas une publication authentifiée dans votre Registry.

## Déploiement manuel

1. Choisir un run **CI and registry release** terminé avec succès sur `main`.
2. Noter le SHA complet et l’ID numérique du run. Télécharger/archiver son artefact et examiner
   `release.json` : trois digests et révision de schéma, sans secret.
3. Actions → **Approved VPS deployment** → Run workflow depuis `main`.
4. Fournir `release_sha`, `ci_run_id`, `operation=deploy`. Cocher `initialize` **seulement**
   pour la première installation lorsque les deux volumes sont absents. Les volumes existants
   ou partiellement présents entraînent un refus, jamais un remplacement.
5. Lors d’une mise à niveau, cocher `allow_migration` uniquement après revue du changement
   de schéma et de sa procédure de retour arrière. Une installation neuve explicitement
   initialisée crée le schéma initial. Une mise à jour au même schéma exécute un upgrade sans effet.
6. Examiner la version, les risques et l’interruption prévue, puis approuver `production`.

Le workflow vérifie identité/conclusion du run CI, branche, SHA et artefact. Il transfère le
bundle dans `releases/<SHA>-<run>-<tentative>` par SSH avec clé hôte épinglée. Un verrou VPS et
la concurrence GitHub interdisent deux déploiements simultanés.

Ordre : préflight TLS/Registry, disque et volumes ; résolution du vrai proxy ; pull des
digests et vérification des labels Git ; validation des paramètres ; arrêt gracieux API/BFF ;
sauvegarde complète ; éventuelle mise à jour de l’image PostgreSQL **17** ; migration explicite ;
démarrage d’une seule API/BFF ; healthchecks ; sondes HTTPS, cookie CSRF et refus des documents
anonymes ; activation du pointeur `current`. Les sessions et clés BYOK RAM sont perdues au
redémarrage et doivent être reconnectées. Les étapes persistées restent conservées ; aucun
appel IA n’est lancé par ce processus.

L’installation existante sans pointeur `current` est refusée par le déploiement ordinaire.
Une première installation échouée en phase `start` peut être reprise uniquement par la
procédure explicite `--recover-from` ci-dessous, sans utiliser `initialize` pour contourner
les contrôles. Aucun transfert automatique des documents de votre ordinateur vers
le VPS n’est prévu. Une migration de données locales exige une restauration indépendante
testée et une opération distincte approuvée.

Le rapport `deployment-report.json` contient SHA, digests, révisions, chemin de sauvegarde,
phase finale et résultat de reprise éventuelle. Pas de secrets, prompts ou documents. Il reste
dans le bundle VPS et est récupéré comme artefact GitHub, même après un échec du déploiement.
Les sondes HTTPS n’effectuent ni connexion à un vrai compte ni appel IA : compléter la checklist.

## Correctif du healthcheck BFF et reprise d’une première installation partielle

Cas constaté : release `2de68362d2fe0f4dece2d01da34dc5a06f00d4c8`, schéma `0006`,
projet `documind-prod`, deux volumes présents, PostgreSQL sain, échec `start`, aucun `current`.
Ce constat fourni par l’administratrice n’est pas une inspection distante effectuée par l’agent.

L’ancien healthcheck utilisait `fetch` sur `127.0.0.1:3000` avec une surcharge `headers.host`.
La reproduction locale avec Node **22.12.0** et dans l’image **22.23.3 Alpine** montre que le
serveur reçoit néanmoins `Host: 127.0.0.1:<port>`. L’allowlist de production contient uniquement
`documind.adelinemeistertzheim.fr` : le middleware rejette donc correctement cette requête.
Il ne s’agit pas d’une erreur de parsing du domaine ni d’un besoin d’autoriser tous les hôtes.
Le Host reçu sur le VPS n’a pas été observé directement depuis cette session.

Le Dockerfile et le Compose exécutent désormais **la même commande** :
`node server/healthcheck.mjs`. Elle utilise `node:http.request`, l’adresse TCP de boucle locale,
le port `BFF_PORT` (3000 en production) et un Host explicite provenant du premier hôte autorisé.
Le timeout est de trois secondes. Seul HTTP 200 donne un code de sortie 0.
`GET /bff/health` possède un handler dédié, après validation Host/Origin : il vérifie la santé
de FastAPI, renvoie seulement `{"status":"ok"}` ou HTTP 503, sans session ni données privées.
Les documents, cookies Secure, CSRF, allowlist d’hôtes et confiance dans Traefik restent protégés.

### Conditions impératives de reprise

La reprise manuelle exige un **nouveau bundle issu d’une CI réussie contenant ce correctif**,
avec ses images publiées et figées par digest. Ne pas réutiliser le SHA de la release défectueuse,
retaguer ses images ou modifier son manifeste/rapport pour lui attribuer du nouveau code.
Le workflow GitHub existant ne possède pas d’entrée de reprise : cette procédure s’exécute
manuellement par l’administratrice, après approbation de la nouvelle version. Ne pas lancer
un déploiement ordinaire avec `initialize=true` tant que les volumes existent.

Le déployeur, sous verrou exclusif, exige :

- deux volumes existants, aucun pointeur `current` **ni** `previous`, même invalide ;
- un bundle source distinct, directement dans `/srv/documind-ai/releases/`, avec manifeste valide
  et rapport `status=failed`, `phase=start`, SHA/images concordants, `schema_before=null`,
  `schema_after=0006`, sans release précédente ;
- exactement trois conteneurs du projet, services `db`, `api`, `web`, associés au fichier Compose
  du bundle source par leurs labels Docker, avec les images exactes de son manifeste ;
- PostgreSQL déjà démarré et healthy, les deux montages nommés attendus, une seule révision
  Alembic réelle, identique à la source et au schéma pris en charge par la nouvelle release ;
- les contrôles habituels : TLS Registry, digests/labels des nouvelles images, configuration,
  espace disque et adresse réelle de Traefik sur `web`.

Toute différence impose un diagnostic manuel ; le déployeur n’adopte pas une installation ambiguë.

Les destinations de montage sont celles du Compose :
`documind-prod_production_database` sur `/var/lib/postgresql/data` dans PostgreSQL et
`documind-prod_production_documents` sur **`/app/var`** dans l’API. Le chemin
`STORAGE_DIR=/app/var/documents` désigne un sous-répertoire du volume, pas sa destination Docker.
Le BFF n’a aucun montage persistant. Les contrôles refusent les mauvais noms, chemins,
bind mounts et montages persistants supplémentaires ; les tmpfs éphémères restent autorisés.
L’ancien contrôle de reprise attendait à tort `/app/var/documents` : utiliser un bundle
contenant ce correctif du déployeur, sans déplacer ni remonter les volumes pour satisfaire
l’ancienne attente. Le rapport source et son manifeste doivent rester intacts.

`--recover-from` ne se combine pas avec `--initialize`, `--rollback` ou `--allow-migration`.
Une reprise avec changement de schéma est refusée : rétablir d’abord l’application au schéma
actuel, puis réaliser une mise à niveau séparée avec sauvegarde et approbation.

### Commandes à exécuter manuellement, après revue

1. Faire publier **par votre CI** une nouvelle release contenant le correctif ; relever son SHA
   complet et son run réussi. Télécharger l’artefact `documind-release-<nouveau-SHA>` depuis ce run.
   Examiner ses cinq fichiers, les trois digests et `schema_revision=0006` ; transférer les fichiers
   à plat dans un **nouveau répertoire privé** sous `/srv/documind-ai/releases/` par votre accès SSH
   habituel, avec vérification de clé hôte. Préserver intégralement le bundle source et son rapport.
   Ne pas créer `current` à cette étape. Aucun build ne doit être lancé sur le VPS.
2. Sur le VPS, saisir les **deux chemins complets réellement présents** (les suffixes des
   répertoires dépendent des runs et ne sont pas supposés) :

```bash
cd /srv/documind-ai
umask 077
find /srv/documind-ai/releases -mindepth 1 -maxdepth 1 -type d -print
read -r -p 'Chemin complet du bundle échoué 2de68362... : ' SOURCE
read -r -p 'Chemin complet du nouveau bundle corrigé : ' CANDIDATE
export SOURCE CANDIDATE
python3 - <<'PY'
import json, os
from pathlib import Path
root = Path('/srv/documind-ai')
source, candidate = (Path(os.environ[name]).resolve() for name in ('SOURCE', 'CANDIDATE'))
assert source.parent == candidate.parent == root / 'releases' and source != candidate
assert not os.path.lexists(root / 'current') and not os.path.lexists(root / 'previous')
original = json.loads((source / 'release.json').read_text())
report = json.loads((source / 'deployment-report.json').read_text())
target = json.loads((candidate / 'release.json').read_text())
assert original['git_sha'] == '2de68362d2fe0f4dece2d01da34dc5a06f00d4c8'
assert report['status'] == 'failed' and report['phase'] == 'start'
assert original['schema_revision'] == target['schema_revision'] == report['schema_after'] == '0006'
assert target['git_sha'] != original['git_sha']
print('Source :', original['git_sha'], '\nCible :', target['git_sha'], '\nSchéma : 0006')
PY
```

3. Arrêter ici si une assertion échoue. Vérifier l’identité de la cible contre le run CI choisi.
   Vérifier `.env.production` (mode 0600, `TRAEFIK_CONTAINER=traefik`, secrets déjà en place,
   inscriptions `disabled` ou `invite`). La commande suivante nécessite l’authentification
   Docker existante avec un compte Registry en lecture, via `docker login` interactif si nécessaire,
   en conservant TLS. Ne pas passer de mot de passe en argument. Puis lancer **une seule** reprise :

```bash
python3 "$CANDIDATE/deploy_production.py" \
  --root /srv/documind-ai \
  --recover-from "$SOURCE"
```

Le déployeur télécharge/vérifie les images, arrête gracieusement API/BFF, revérifie l’état source
et le schéma, contrôle la capacité disque, puis crée une sauvegarde cohérente sous
`var/backups/deploy-<date>/` : dump PostgreSQL, documents, empreintes et manifeste SHA-256.
Un échec de sauvegarde interdit tout démarrage de la cible. La reprise **ne lance aucune migration,
aucun `up db`, aucune restauration** : PostgreSQL et son image existante restent en place,
même si le manifeste cible contient un nouveau digest PostgreSQL. Ce digest conservé est
consigné dans `retained_database_image` ; la prochaine mise à jour ordinaire pourra appliquer
l’image PostgreSQL 17 de la release après sa propre sauvegarde.

Seuls API/BFF sont ensuite mis à jour. `current` est créé par le déployeur **après** les trois
healthchecks et les sondes HTTPS/CSRF/refus anonyme. Aucun pointeur `previous` n’est inventé.
En cas d’échec, API/BFF restent arrêtés, PostgreSQL et les données sont conservés ; le rapport
source n’est pas écrasé. Examiner le nouveau rapport avant une nouvelle tentative, sans créer
de lien à la main. Une panne survenue après remplacement des conteneurs peut rendre leurs
images différentes de celles du bundle source : une nouvelle reprise automatique sera alors
refusée par `--recover-from`. Utiliser alors uniquement la procédure distincte
`--recover-after-https` ci-dessous si toutes ses preuves sont disponibles ; ne pas changer
artificiellement le rapport source.

4. Après succès, contrôler :

```bash
readlink -f /srv/documind-ai/current
python3 -m json.tool "$CANDIDATE/deployment-report.json"
curl --fail --show-error https://documind.adelinemeistertzheim.fr/bff/health
```

Le rapport doit indiquer `status=success`, `phase=complete`, schéma avant/après `0006`, source
correcte, digest PostgreSQL conservé et chemin de sauvegarde. Vérifier ensuite connexion utilisateur,
import/analyse classique et isolation. Reconnecter les sessions et clés BYOK perdues au redémarrage.
Ne pas déclencher d’appel IA payant pour cette vérification. Archiver la sauvegarde hors VPS
selon la procédure habituelle ; aucun `down -v`, suppression de volume ou reset PostgreSQL.

## Diagnostic HTTPS et reprise après remplacement des conteneurs

Cas fourni par l’administratrice : release `334a40ec76c69c582a4f25c8a6237351f3c2357d`,
échec `phase=https`, API/BFF remplacés puis arrêtés, PostgreSQL d’origine healthy au schéma
`0006`, aucun `current` ni `previous`, sauvegarde `var/backups/deploy-20261019-181649`.
La validité du certificat et le 404 observé après arrêt ne prouvent pas la cause de l’échec
initial : une route Traefik absente après arrêt ne décrit pas son état pendant les sondes.
L’ancien `URLError` ne conservait pas de cause ; aucun accès au VPS n’a été effectué ici.

### Sondes HTTPS et diagnostics conservés

Le déployeur vérifie toujours, sans session ni cookies réutilisés :

| URL | Résultat exigé |
|---|---|
| `https://documind.adelinemeistertzheim.fr/login` | 200 |
| `https://documind.adelinemeistertzheim.fr/bff/health` | 200 |
| `https://documind.adelinemeistertzheim.fr/bff/auth/csrf` | 200 et cookie `__Host-documind-csrf` valide |
| `https://documind.adelinemeistertzheim.fr/bff/documents` | 401 anonyme |

Le cookie doit avoir `Secure`, `HttpOnly`, `SameSite=Strict`, `Path=/` et aucun Domain.
La validation TLS chaîne/nom reste active. Les redirections sont refusées, même vers un autre
chemin du domaine. Aucun corps de réponse, cookie, identifiant, URL de redirection, texte
d’exception ou en-tête fournisseur n’est enregistré.

`deployment-report.json` contient `https_probes` : URL fixe, numéro de tentative, statut attendu,
statut HTTP observé ou catégorie réseau/TLS, éventuel errno/code numérique de validation TLS,
et caractère réessayable. Les diagnostics sont enregistrés **avant** l’arrêt des services
en cas d’échec et restent dans le nouveau rapport. `error_category=HTTPSProbeError` accompagne
une erreur finale explicite avec URL et cause, sans détails bruts potentiellement sensibles.

L’attente dispose d’un budget de **60 secondes**, d’un timeout de socket d’au plus **5 secondes**
par sonde et d’une pause d’au plus **2 secondes** entre tentatives. Le délai de résolution DNS
reste soumis au résolveur système. Les statuts 404/408/425/429/502/503/504, les timeouts,
les connexions refusées/réinitialisées et le DNS temporaire peuvent être réessayés jusqu’à
épuisement du budget ; toute la séquence doit ensuite réussir. Un 404 persistant finit en échec.
Les erreurs de certificat/TLS, le DNS permanent, les redirections, 400/401/403 inattendus,
un 500, un cookie non sécurisé ou l’accès anonyme autorisé échouent immédiatement.
Le 401 des documents est naturellement un succès. Cette attente ne modifie pas Traefik.

### Preuves exigées pour `--recover-after-https`

Cette option est distincte de `--recover-from`, qui conserve son contrôle strict de la première
installation échouée à `start`. Elle nécessite une **nouvelle release CI corrigée**, placée
dans un nouveau bundle, sans écraser les bundles, manifests ou rapports précédents.
Le workflow GitHub de déploiement ordinaire ne possède pas cette entrée de reprise.
Un bundle qui possède déjà `deployment-report.json` est refusé avant toute opération :
chaque tentative utilise un nouveau répertoire et le déployeur n’écrase aucun ancien rapport.

Sous le verrou de déploiement, la nouvelle procédure exige :

- aucun pointeur `current` ou `previous`, exactement les deux volumes attendus et les trois
  conteneurs du projet `documind-prod`, sans montage persistant supplémentaire ;
- un rapport source `failed/https` de la release `334a40ec…`, dont SHA et images correspondent
  au manifeste et dont schémas avant/après sont identiques au schéma cible `0006` ;
- sa chaîne `recovered_from`/`source_sha` complète jusqu’au rapport de première installation
  `failed/start`, `schema_before=null`, sans release précédente ; aucune sortie de `releases/`,
  aucun cycle, au maximum huit bundles ;
- pour chaque reprise HTTPS échouée : la sauvegarde indiquée, son manifeste PostgreSQL 17 au
  bon schéma, les deux archives et leurs empreintes SHA-256 correctes sous `var/backups/` ;
- API/BFF avec les images exactes et les labels de fichier Compose du bundle échoué à HTTPS ;
  PostgreSQL avec l’image exacte et les labels du **bundle initial**, conservés pendant les reprises ;
- la concordance de `retained_database_image` avec ce bundle initial sur toute la chaîne,
  PostgreSQL healthy et une seule révision réelle `0006`, compatible avec la nouvelle cible.

Les paramètres d’identité, montages, TLS/Registry, espace disque et proxy restent vérifiés.
Un ancien rapport perdu, une archive manquante, un checksum erroné, un schéma différent ou une
image inattendue entraîne un refus. Ne pas reconstruire une preuve en modifiant les rapports.
Ne pas combiner cette option avec `--recover-from`, `--initialize`, `--rollback` ou `--allow-migration`.

### Commandes manuelles pour le cas `334a40ec…`

1. Faire publier par la CI une nouvelle release contenant ce correctif, vérifier son run réussi,
   son SHA, ses digests et son schéma `0006`. Transférer ses cinq fichiers d’artefact à plat dans
   un **nouveau** répertoire privé `/srv/documind-ai/releases/<nouvelle-release>` avec votre accès
   SSH vérifié. Ne pas lancer le workflow de déploiement ordinaire pour contourner l’absence de
   `current`. Ne pas écraser le répertoire `334a40ec…` ni celui de la première installation.
2. Sur le VPS, choisir les chemins réels, sans supposer les suffixes des bundles :

```bash
cd /srv/documind-ai
umask 077
find /srv/documind-ai/releases -mindepth 1 -maxdepth 1 -type d -print
read -r -p 'Bundle échoué à HTTPS (334a40ec...) : ' HTTPS_SOURCE
read -r -p 'Nouveau bundle corrigé : ' CANDIDATE
export HTTPS_SOURCE CANDIDATE
python3 - <<'PY'
import json, os
from pathlib import Path
root = Path('/srv/documind-ai')
source, target = (Path(os.environ[key]).resolve() for key in ('HTTPS_SOURCE', 'CANDIDATE'))
assert source.parent == target.parent == root / 'releases' and source != target
assert not os.path.lexists(root / 'current') and not os.path.lexists(root / 'previous')
original = json.loads((source / 'release.json').read_text())
report = json.loads((source / 'deployment-report.json').read_text())
candidate = json.loads((target / 'release.json').read_text())
assert original['git_sha'] == '334a40ec76c69c582a4f25c8a6237351f3c2357d'
assert report['status'] == 'failed' and report['phase'] == 'https'
assert report['git_sha'] == original['git_sha'] and report['images'] == original['images']
assert report['schema_before'] == report['schema_after'] == candidate['schema_revision'] == '0006'
assert report['backup'] == 'var/backups/deploy-20261019-181649'
assert candidate['git_sha'] != original['git_sha']
assert (root / report['backup'] / 'manifest.json').is_file()
print('Source :', original['git_sha'], '\nCible :', candidate['git_sha'], '\nSchéma : 0006')
PY
```

3. Arrêter si une assertion échoue ; comparer la cible au run CI approuvé. Vérifier la présence
   de la chaîne de bundles source et de la sauvegarde originale. Le déployeur vérifiera leurs
   identités et empreintes sans modifier les anciens rapports. Conserver `.env.production`
   en mode 0600, `TRAEFIK_CONTAINER=traefik`, inscriptions fermées/sur invitation et votre
   authentification Docker Registry en lecture (login interactif, TLS actif).
   Après revue, lancer explicitement :

```bash
python3 "$CANDIDATE/deploy_production.py" \
  --root /srv/documind-ai \
  --recover-after-https "$HTTPS_SOURCE"
```

Le déployeur revérifie l’état puis produit **une nouvelle sauvegarde cohérente**, après arrêt
gracieux API/BFF. Il ne lance ni migration, ni `up db`, ni restauration ou suppression de volume.
L’image PostgreSQL initiale reste en place. Seuls API/BFF sont démarrés avec la nouvelle release.
Les sondes attendent la disponibilité HTTPS dans la limite prévue. `current` n’est créé qu’après
réussite des healthchecks et de toute la séquence HTTPS. En cas d’échec, API/BFF sont arrêtés,
les données et les anciennes preuves restent conservées ; lire le **nouveau** rapport :

```bash
python3 -m json.tool "$CANDIDATE/deployment-report.json"
```

Si une nouvelle tentative a échoué à HTTPS après remplacement, son bundle devient la source
explicite de la tentative suivante, dans un nouveau répertoire. Sa chaîne conserve les rapports
précédents. Ne pas reprendre depuis le premier bundle si les conteneurs ne lui correspondent plus.
Après succès seulement :

```bash
readlink -f /srv/documind-ai/current
curl --fail --show-error https://documind.adelinemeistertzheim.fr/bff/health
```

Contrôler ensuite les comptes et l’analyse classique, sans appel IA payant. Ne pas créer un
pointeur manuellement et ne pas réinitialiser PostgreSQL pour débloquer la reprise.

## Sauvegarde et retour arrière

Les sauvegardes réutilisent `tools/backup_local.py` : API/BFF arrêtés, `pg_dump -Fc`, archive
des documents, empreintes des tables/colonnes historiques, révision Alembic et SHA-256 des
archives. L’archive PostgreSQL est contrôlée par `pg_restore --list` avant migration.
Les sauvegardes restent sous `var/backups/` dans le répertoire privé. Elles ne sont jamais
téléversées dans un artefact GitHub. Elles ne sont pas chiffrées automatiquement : prévoir
chiffrement, copie hors VPS et rotation avant la bêta. Les deux volumes ne sont jamais supprimés.

Sauvegarde manuelle d’une release active, depuis la racine choisie :

```bash
docker compose --project-directory "$PWD" -p documind-prod \
  --env-file .env.production --env-file current/images.env \
  -f current/compose.production.yaml stop --timeout 150 web api
python3 current/backup_local.py --production \
  --compose-file current/compose.production.yaml --release-env current/images.env
# Redémarrer ensuite la même release avec les mêmes options Compose, up -d --no-deps api web.
```

Pour un **rollback applicatif**, lancer le même workflow manuel avec l’artefact d’une ancienne
CI réussie et `operation=rollback`, sans `initialize`. La révision actuelle doit appartenir
à `supported_schema_revisions` de l’ancienne version. Une sauvegarde est refaite. Seuls les
conteneurs applicatifs sont remplacés : pas de downgrade Alembic, pas de retour automatique
à une ancienne image PostgreSQL, pas de restauration de volume. Le PostgreSQL courant reste
sur sa version 17 ; le rapport et le schéma sont à vérifier avec l’application rétablie.

Après un échec de mise à jour, l’ancienne application est redémarrée seulement si elle supporte
encore le schéma constaté. Sinon le trafic reste fermé et une intervention est requise.
En particulier, le retour à un ancien code scrypt seul ne permettrait pas de vérifier les mots
de passe Argon2id migrés : ne pas annoncer une compatibilité non testée.

Les artefacts GitHub sont conservés 90 jours. Garder les bundles sur le VPS et archiver les
releases utiles ; ne pas effacer les digests de rollback. Pour une release dont l’artefact a
expiré, utiliser son bundle VPS vérifié lors d’une intervention administrative approuvée.

Pour une **restauration de données**, arrêter l’exploitation et obtenir une confirmation
spécifique. Restaurer d’abord dans une instance indépendante avec l’image PostgreSQL 17
appropriée, comparer les tables/UUID/propriétaires, puis vérifier chaque fichier par SHA-256.
Le script local `tools/validate_restore.py` reste disponible pour une base locale accessible
sur 127.0.0.1 ; il n’est pas présenté comme une restauration automatique du VPS. Une ancienne
sauvegarde perd les écritures ultérieures et peut réintroduire des données effacées : les
demandes de suppression doivent être réappliquées avant réouverture.

## Checklist avant validation de la bêta

- [ ] Nom exact du conteneur Traefik renseigné, réseau et adresse inspectés ; Host/labels sans conflit.
- [ ] DNS A/AAAA et certificat HTTPS valides ; aucune désactivation de TLS Registry/SSH.
- [ ] Droits Registry effectivement vérifiés ; secrets GitHub et reviewers de `production` configurés.
- [ ] Publication des trois images et pull authentifié réussis sur le véritable VPS.
- [ ] RAM/CPU avec les autres applications suffisants ; disque, quotas et alertes configurés.
- [ ] Sauvegarde chiffrée/hors machine et restauration indépendante de la première sauvegarde VPS testées.
- [ ] Compte administrateur créé via CLI ; connexion/déconnexion et récupération SMTP contrôlées.
- [ ] PDF/TXT importés et analysés ; utilisateur B ne voit ni document, recherche ni comparaison de A.
- [ ] Cookies Secure/HttpOnly/SameSite et refus d’une mutation sans CSRF vérifiés dans le navigateur.
- [ ] BYOK connecté puis révoqué sans exposition du secret ; aucune validation fournisseur ni génération automatique.
- [ ] Budget/quotas vérifiés avec les simulations ; tout essai IA réel est autorisé et budgété séparément.
- [ ] Reprise après redémarrage et annulation d’une tâche suspendue vérifiées sans doubler un appel incertain.
- [ ] Retour arrière compatible et rapport de déploiement vérifiés ; conservation/mentions légales validées.
- [ ] Ouverture de la bêta expressément approuvée ; inscriptions libres toujours impossibles.

La liste des fichiers, résultats locaux et vérifications restant à effectuer sur le VPS figure
dans [le rapport Sprint 6](validation-sprint-6.md). Aucun déploiement réel n’a été lancé pendant
la préparation de ces fichiers.
