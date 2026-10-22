# Sprint 11 — SEC10-03 : séparation passerelle / identité utilisateur

Revue locale du 22 octobre 2026, branche `security/sec10-03-gateway-auth`.
Aucun commit, push, accès VPS/Registry, déploiement, modification de secret ou migration SQL.

## Correction et périmètre

La correction déjà présente de `backend/gateway.py::trusted_gateway()` est conservée :
seule une `BFF_SERVICE_KEY` non vide correspondant à l'en-tête `X-API-Key` authentifie
la passerelle. Aucun repli sur `settings.api_keys`. La comparaison reste effectuée
avec `secrets.compare_digest`. Les fins de ligne de ce fichier ont été normalisées
en LF pour obtenir un diff Git sans erreur, sans autre modification fonctionnelle.

`secure_gateway()` exige toujours aussi `X-Documind-Secure: 1`. Ce marqueur seul
ne prouve donc ni une passerelle de confiance ni une session utilisateur.
`client_ip()` accepte l'adresse transmise uniquement avec la clé BFF valide ; la
confiance dans cette adresse est liée au credential de passerelle, pas au marqueur HTTPS.
Les contrôles HTTPS, proxy, origine et CSRF du BFF restent inchangés.

La fixture applicative possède désormais une clé BFF fictive dédiée, distincte des deux
clés historiques. Le client historique reste inchangé ; une fixture `gateway_client`
séparée est utilisée pour les comptes/BYOK. L'utilitaire de connexion transmet cette
clé dédiée puis conserve le Bearer personnel. Le test de désactivation du mode historique
présente explicitement une ancienne clé, indépendamment de l'identité BFF.

Le test existant de prévalidation SEC10-02 utilisait lui aussi une ancienne clé : seul
son credential de passerelle a été adapté. Ses assertions 204 sans lecture du corps,
absence de fuite de session et refus d'une mauvaise clé sont conservées.

## Preuves de sécurité

Les trois tests gateway initiaux sont conservés et complétés pour couvrir :

- clé BFF non configurée, en-tête absent/vide/incorrect, ancienne clé utilisateur ;
- marqueur HTTPS absent ou incorrect, et couple clé BFF/marqueur valide ;
- impossibilité pour une ancienne clé de falsifier l'IP utilisée par l'admission IP ;
- prévalidation exigeant l'identité de passerelle et une session personnelle ;
- sessions absentes, inventées, expirées, révoquées, compte désactivé ou propriétaire modifié ;
- rejet avant tout `receive` ASGI et absence de réservation/fichier résiduel pour ces uploads ;
- absence d'identité utilisateur accordée à la seule clé BFF, quel que soit le mode historique ;
- désactivation effective des anciennes clés avec `legacy_api_enabled=False` ;
- upload avec session valide, isolation lecture/suppression entre propriétaires et révocation par logout.

Les routes documentaires conservent leur politique existante : Bearer utilisateur valide,
ou ancienne clé explicitement autorisée lorsque le mode historique est actif. Cette
correction ne leur ajoute pas une obligation générale de passer par `secure_gateway()`.
La prévalidation interne et les routes comptes/BYOK qui l'exigeaient restent protégées.
La clé BFF dédiée n'appartient pas au registre d'identités utilisateur ; conserver cette
séparation des credentials dans la configuration opérationnelle.

Les sessions serveur ne changent ni de format ni de stockage. Aucune modification de
`authenticate()`, des contrôles de propriétaire, du vault, des quotas, du sandbox
Landlock/seccomp ou des fonctionnalités des Sprints 7–10 n'a été nécessaire.

La lecture du Compose de production confirme que `BFF_SERVICE_KEY` est déjà obligatoire
et transmise aux deux services, avec `LEGACY_API_ENABLED=false` pour l'API. Aucun changement
de configuration de production n'est nécessaire dans le dépôt. Une installation ancienne
qui dépendrait encore du repli sans clé BFF ne pourrait plus utiliser les routes protégées
par `secure_gateway()` : refus fermé intentionnel, à vérifier avant toute future livraison.
Cela ne constitue pas une vérification des valeurs réellement présentes sur le VPS.

## Environnement Windows et répertoires temporaires

L'alias système `python` pointe sur WindowsApps et son exécution est refusée dans cet
environnement. L'interpréteur `.venv\Scripts\python.exe` fonctionne : Python 3.13.7.
Il s'agit d'un problème de lancement distinct des assertions de tests.

Le premier lancement avec cet interpréteur a utilisé le répertoire temporaire Windows
habituel sans reproduire le `PermissionError` signalé pour `pytest-of-Adeline`.
La cause exacte de cet ancien refus d'accès n'est donc pas confirmée par cette session.
Les validations suivantes utilisent un chemin neuf sous `var/` avec `--basetemp`, sans
modifier les ACL Windows ni supprimer de répertoire système. Choisir un répertoire
exclusivement réservé à pytest : pytest peut en nettoyer le contenu lors d'une exécution.

Exemple reproductible PowerShell, depuis la racine du dépôt :

```powershell
$testBase = Join-Path (Get-Location) ('var/pytest-sec10-03-' + [guid]::NewGuid().ToString('N'))
.\.venv\Scripts\python.exe -m pytest tests/test_gateway_security.py tests/test_byok.py tests/test_accounts_saas.py -q -p no:cacheprovider --tb=short --basetemp $testBase
```

`TEST_DATABASE_URL` est absent : les fixtures utilisent exclusivement leurs bases SQLite
jetables. Les clients OpenAI réels sont interdits par la fixture automatique ; les tests
IA utilisent des fournisseurs simulés. La suite complète est lancée avec des variables
de processus neutralisant les credentials et fonctionnalités par défaut, sans modifier
aucun fichier d'environnement.

## Fichiers concernés

- `backend/gateway.py` : correction existante préservée, normalisation LF uniquement pendant ce travail.
- `tests/conftest.py` : clé dédiée et fixture de passerelle ; client historique conservé.
- `tests/test_byok.py` : comptes et connexion via la clé BFF fictive.
- `tests/test_accounts_saas.py` : présentation explicite de la clé historique dans son test de désactivation.
- `tests/test_upload_admission.py` : credential dédié pour la prévalidation existante.
- `tests/test_gateway_security.py` : extension des trois tests initiaux.
- `docs/sprint-11-sec10-03.md` : ce bilan.

## Résultats et décision

| Validation locale | Résultat |
| --- | --- |
| Reproduction initiale : gateway + BYOK + comptes | 3 réussis, 15 échecs réels de fixtures (HTTP 403), aucun WinError reproduit |
| Même sélection après adaptation initiale des fixtures | 49 réussis, aucun échec |
| Gateway, après ajout des derniers cas en-tête absent / admission IP | 38 réussis, aucun échec |
| Régressions documents, admission upload, IA, RAG, résumés longs, configuration | 105 réussis et un échec : ancien credential dans le test de prévalidation SEC10-02 |
| Admission upload après correction de ce credential de test | 35 réussis, aucun échec |
| BFF : `npm.cmd --prefix frontend run test:bff` | 42 réussis, aucun échec |
| Suite Python complète Windows, après toutes les corrections | 562 réussis, 40 ignorés (Linux natif), aucun échec ; 368,95 s |
| `git diff --check` et contrôle des espaces/fins de fichier des nouveaux fichiers | Réussis |

La sélection Python de régression utilise `tests/test_documents.py`,
`tests/test_upload_admission.py`, `tests/test_ai.py`, `tests/test_rag.py`,
`tests/test_long_summary.py` et `tests/test_config_and_schema.py` avec les mêmes
options pytest et un autre `--basetemp` unique. L'échec constaté et corrigé ne
nécessitait aucun assouplissement applicatif.

La suite complète a été exécutée avec `.\.venv\Scripts\python.exe -m pytest -q
-p no:cacheprovider --tb=short --basetemp $testBase`, après création d'un chemin unique
sous `var/`. Les variables de processus `DATABASE_URL=sqlite://`, `API_KEYS={}`,
`BFF_SERVICE_KEY` et `OPENAI_API_KEY` vides, `AI_ENABLED=false` et
`REGISTRATION_MODE=disabled` neutralisent les valeurs par défaut à l'import.
Les fixtures configurent ensuite leurs seules identités fictives dédiées.

Les 53 cas actuels gateway/BYOK/comptes (38 + 5 + 10) font partie de cette suite complète,
ainsi que les 35 cas d'admission upload. Les sélections du tableau se recoupent : ne pas
additionner leurs résultats. Les échecs de fixtures et de prévalidation décrits plus haut
sont tous résolus dans cette exécution finale. Un avertissement de dépréciation historique
Starlette/httpx subsiste ; il ne s'agit pas d'un échec d'authentification.

À l'issue de cette première campagne Windows, les preuves Linux natives, PostgreSQL et
Docker restaient à effectuer. Leur validation supplémentaire est consignée ci-dessous ;
les résultats Windows restent des résultats antérieurs, sans nouvelle exécution complète.

**Verdict de la première campagne : prêt pour une revue Git locale.** Aucune régression détectée dans les suites
exécutées ; les connexions personnelles, l'isolation des propriétaires, la révocation,
les budgets simulés et SEC10-02 sont préservés. L'ancienne capacité à présenter une clé
utilisateur comme passerelle est supprimée volontairement. Aucun commit, push, publication
ou déploiement n'est autorisé par ce bilan.

## Validation finale Linux, PostgreSQL et Docker — 22 octobre 2026

### Environnement et isolation

- Ubuntu WSL, Python 3.12.3, noyau `6.18.54.1-microsoft-standard-WSL2`, Landlock ABI 7.
- Docker Desktop : moteur 29.8.2, Compose 5.5.1, images API/BFF amd64.
- Projet neuf `sec1003-f988dd887e`, distinct des projets et réseaux locaux préexistants.
- Réutilisation du Dockerfile (cibles `isolation-tests` et `production`), de
  `compose.upload-test.yaml`, de la surcharge Windows locale déjà présente et du fichier
  Traefik existant sous `ops/testing/`. Aucun de ces fichiers n'a été modifié.
- Une surcharge sous `var/sec1003-f988dd887e/` fournit les noms d'images uniques, les ports
  éphémères, le sous-réseau distinct `172.30.252.0/24`, le certificat fictif neuf et le
  healthcheck API existant en production. Traefik de recette utilise UID/GID 1000.
- PostgreSQL et les documents sont exclusivement en tmpfs ; aucun volume persistant.
  La base applicative neuve `upload_test` est distincte de la base de tests neuve
  `gateway_tests`. Aucun accès à une base ou à un conteneur préexistant.
- Les sources WSL sont une copie assainie de 228 fichiers, sans `.env`, `var/`, PDF réel,
  base existante ou secret. Leur identité SHA-256 avec le workspace a été vérifiée.
  Le venv est privé à `/var/tmp/documind-sec1003-f988dd887e/`.
- Les preuves Docker isolées ont utilisé `--network none`, aucun volume, racine read-only,
  `--cap-drop ALL`, `no-new-privileges`, 1536 Mio, 2 CPU, 64 PID et un tmpfs `/tmp` de
  256 Mio. La suite PostgreSQL utilise les mêmes restrictions, un montage read-only de
  la seule copie de sources assainie et le seul réseau interne de données du projet.
  Aucun assouplissement Landlock, seccomp ou Docker.

La surcharge Windows existante rend le réseau proxy non interne pour permettre l'entrée
HTTPS depuis Docker Desktop ; seuls les réseaux de données/application restent internes.
Cette particularité locale n'est ni une modification du Compose de production ni la
preuve d'une isolation réseau complète du BFF. Les preuves du parseur sans réseau sont
apportées par le conteneur `--network none` et les tests natifs de confinement.

Les premiers appels WSL/Docker étaient refusés dans l'environnement restreint ; ils ont
ensuite fonctionné avec les permissions d'exécution locales nécessaires. Docker a utilisé
un chemin de configuration client distinct, sans lire les identifiants Docker existants.
Ubuntu ne disposait ni de pip ni d'ensurepip : le venv neuf a été créé sans pip puis
amorcé avec la copie locale de pip, sans paquet système ni changement global de droits.
Le premier répertoire `/tmp` n'était plus disponible à l'appel suivant ; la préparation
et les tests ont donc été exécutés dans `/var/tmp` dans une même session WSL. Les scripts
temporaires Bash ont été écrits en LF. Ce sont des incidents de préparation, pas des
échecs des assertions de sécurité.

### Résultats réels

| Validation supplémentaire | Réussis | Ignorés | Échoués |
| --- | ---: | ---: | ---: |
| Suite complète WSL / SQLite, Python 3.12.3 | 602 | 0 | 0 |
| Image Linux / Python 3.13, sans réseau ni volume : confinement + gateway + BYOK + comptes + uploads | 160 | 0 | 0 |
| Suite complète Linux / PostgreSQL avec `TEST_DATABASE_URL` dédié | 602 | 0 | 0 |
| Test IP renforcé, Windows | 3 | 0 | 0 |
| Parcours HTTPS normal de la stack jetable | 19 | 0 | 0 |
| Contrôles HTTP API directs de la stack jetable | 7 | 0 | 0 |
| Upload sans corps via HTTPS, avec `Connection: close` | 1 | 0 | 0 |

Ces campagnes se recoupent. Les 602 tests WSL ont duré 410,14 s ; ceux avec PostgreSQL,
460,53 s ; les 160 tests Docker isolés, 39,12 s. Les 35 cas non retenus par `-k` dans
le contrôle Windows ciblé sont désélectionnés, pas ignorés pour défaut de capacité.
Un avertissement historique Starlette/httpx est présent dans chaque campagne Python.
Les 72 cas confinement/protocole, dont les 40 ignorés sous Windows, passent sous Linux.

PostgreSQL est en version 17.11, l'extension pgvector en 0.8.7, le schéma applicatif en
`0006`. L'opérateur SQL de distance cosinus a été vérifié : deux vecteurs unitaires
orthogonaux donnent une distance de 1. La suite complète avec `TEST_DATABASE_URL` utilise
PostgreSQL pour la fixture applicative ; certains tests autonomes créent volontairement
leur propre SQLite, comme dans la CI existante.

Le test `test_ip_admission_uses_only_gateway_authenticated_forwarding` vérifie maintenant
aussi HTTP 200 pour la clé historique autorisée comme identité utilisateur, HTTP 401 pour
une clé incorrecte et pour la seule clé BFF. L'assertion du bucket IP reste inchangée.
Cette assertion et ce rapport sont les seules modifications supplémentaires destinées
à Git pendant cette validation finale. Aucun code applicatif supplémentaire n'a changé.

### Recette HTTPS et limite de transport observée

Traefik local 3.3.7 est joint sur `https://documind.test:56260`, avec résolution explicite
vers `127.0.0.1`, SNI `documind.test` et vérification du certificat autosigné neuf chargé
explicitement comme ancre de confiance de test, sans `-k` ni désactivation de TLS.
Le magasin de certificats système n'a pas été modifié. PostgreSQL, API et BFF sont
healthy ; Traefik est running et validé par les requêtes HTTPS, sans prétendre qu'il
possède un healthcheck Docker dédié.

Le parcours vérifie `/login`, `/bff/health`, le refus anonyme, les sessions inventées et
révoquées, une connexion personnelle fictive, les cookies Secure/HttpOnly/SameSite,
le refus CSRF, l'import TXT fictif 201, sa lecture, son analyse classique et le refus
d'accès 404 depuis un second compte. Les marqueurs de session ne sont pas renvoyés par
le BFF. Les contrôles API directs vérifient le refus 403 des clés historiques/incorrectes,
le marqueur HTTPS obligatoire, l'absence d'identité utilisateur accordée à la clé BFF
et le refus 401 d'un upload invalide sans émission du corps. Aucun `.part` résiduel
n'a été trouvé dans `/app/var`. Aucun appel IA ni ouverture des inscriptions.

**Réserve explicite :** une sonde supplémentaire devant Traefik annonçant un corps de
1024 octets avec `Expect: 100-continue`, sans l'envoyer et en conservant la connexion
persistante, a expiré (10 s puis diagnostic borné à 5 s), sans statut HTTP observé.
La même sonde avec `Connection: close` reçoit immédiatement HTTP 401, sans envoyer le
corps ; le parcours avec corps complet reçoit aussi le refus attendu. Cela établit une
différence liée au mode de connexion dans cette recette ; la cause interne précise
(drainage/flush du transport, par exemple) n'a pas été prouvée. Aucune règle Traefik ou
protection applicative n'a été changée pour masquer ce résultat. Cette sonde ne doit pas
être comptée comme réussie ni comme une preuve de rejet immédiat à la frontière Traefik
sur connexion persistante. Les assertions ASGI et BFF de non-lecture restent réussies.

### Commandes et traces de recette

Les scripts et résultats locaux sont sous `var/sec1003-f988dd887e/`, ignoré par Git.
Ils ne constituent pas une nouvelle infrastructure à publier. Les principales commandes
exécutées sont les suivantes (depuis la racine du dépôt, syntaxe PowerShell) :

Il s'agit d'un historique de cette exécution, pas d'un script à relancer sur une base
déjà utilisée. Une prochaine recette doit préparer un nouvel identifiant de projet,
de nouveaux répertoires et de nouvelles bases vides.

```powershell
$r = Join-Path (Get-Location) 'var/sec1003-f988dd887e'
$project = 'sec1003-f988dd887e'
$dockerConfig = Join-Path (Get-Location) 'var/sec10-03-docker-client'
wsl -d Ubuntu --exec bash /mnt/c/Users/Adeline/Documents/DocuMind_AI/var/sec1003-f988dd887e/linux-test.sh
docker --config $dockerConfig build --target isolation-tests --tag "${project}-isolation:local" .
docker --config $dockerConfig build --target production --tag "${project}-api:local" .
docker --config $dockerConfig build --tag "${project}-web:local" frontend
docker --config $dockerConfig run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges --memory 1536m --cpus 2 --pids-limit 64 --tmpfs /tmp:rw,noexec,nosuid,size=256m,mode=1777 --env DATABASE_URL=sqlite:// --env AI_ENABLED=false "${project}-isolation:local" python -m pytest -q -p no:cacheprovider --tb=short tests/test_extraction_linux.py tests/test_extraction_protocol.py tests/test_gateway_security.py tests/test_byok.py tests/test_accounts_saas.py tests/test_upload_admission.py
function dc { docker --config $dockerConfig compose --env-file "$r/recipe.env" -p $project -f compose.upload-test.yaml -f compose.upload-test.windows.yaml -f "$r/compose.local.yaml" @args }
dc up -d --no-build --wait db
dc exec -T db createdb -U upload_test gateway_tests
dc run --rm --no-deps api alembic upgrade head
dc up -d --no-build --wait api web traefik
docker --config $dockerConfig run --rm --network "${project}_data" --read-only --cap-drop ALL --security-opt no-new-privileges --memory 1536m --cpus 2 --pids-limit 64 --tmpfs /tmp:rw,noexec,nosuid,size=256m,mode=1777 --mount "type=bind,source=$r/suite,target=/suite,readonly" --workdir /suite --env DATABASE_URL=sqlite:// --env AI_ENABLED=false --env TEST_DATABASE_URL=postgresql+psycopg://upload_test:fictitious-upload-test-password@db:5432/gateway_tests "${project}-isolation:local" python -m pytest -q -p no:cacheprovider --tb=short
.\.venv\Scripts\python.exe "$r/recipe_checks.py"
.\.venv\Scripts\python.exe "$r/expect_probe.py"
git diff --check
```

Le script WSL prépare la copie/venv, installe `.[test]` sous contraintes de
`requirements.lock`, neutralise les credentials et exécute `python -m pytest -q
-p no:cacheprovider --tb=short` avec basetemp et JUnit dédiés. Les dépendances de test
et images de base ont été récupérées depuis les dépôts publics habituels ; aucune
Registry privée, API IA, instance GitHub ou machine VPS n'a été contactée.

Après les tests, les labels et noms des quatre conteneurs ont été vérifiés ainsi que
l'absence de montage de type volume. Un `dc down` limité à ce projet a supprimé ses
quatre conteneurs et ses trois réseaux, sans `-v`, prune ni suppression de volume.
Les conteneurs de tests `--rm` ont également disparu. Les images locales neuves et
les traces ignorées sont conservées pour revue. Les ressources préexistantes restent
intactes. La surcharge Windows préexistante reste ignorée et inchangée ; seuls les
deux nouveaux fichiers Git attendus (ce rapport et le test gateway) sont non suivis.

### Verdict final de livraison

**SEC10-03 est prêt à être proposé en Pull Request pour revue.** Les suites complètes
Linux/SQLite et Linux/PostgreSQL, les preuves Docker de confinement et le parcours
HTTPS normal passent sans régression d'authentification détectée. Le build frontend
TypeScript/Vite a réussi dans l'image ; la suite React n'a pas été relancée, et les
42 tests BFF restent ceux de la campagne précédente.

La réserve sur les connexions persistantes sans corps doit être examinée explicitement
avant de revendiquer un refus immédiat avant corps à la frontière Traefik ou une recette
SEC10-02 exhaustive. Elle ne remet pas en place le repli des anciennes clés BFF et ne
justifie aucun assouplissement automatique. La cause et son éventuelle portée pour une
livraison doivent être revues ; ce rapport n'accorde aucune autorisation de production.

Le noyau local et l'ABI 7 ne reproduisent pas exactement Linux 6.12 / ABI 6 du VPS.
Les limites de capacité complètes, HTTP/2/HTTP/3, la configuration réelle du proxy VPS
et toute validation de production restent hors de cette recette. Aucun commit, push,
PR, fusion, workflow distant, modification de secret ou déploiement n'a été effectué.
