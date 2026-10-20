# Validation du Sprint 10 — audit de phase A

Date : **20 octobre 2026, Europe/Paris**. Hôte local Windows, Python **3.13.7**, Node
**22.12.0**. Rapport principal : [audit](sprint-10-security-audit.md) ; suite proposée :
[plan de remédiation](sprint-10-remediation-plan.md).

## Résultats exécutés

| Contrôle | Résultat | Portée et limites |
|---|---|---|
| Suite pytest complète | **455 réussis**, 1 avertissement, 262,88 s | SQLite temporaire, données fictives ; aucun PostgreSQL de production |
| Tests BFF Node | **25 réussis** | HTTP local et upstream simulé ; cookies/CSRF/proxy/healthcheck/méthodes/erreurs |
| Tests React Vitest | **37 réussis**, 7 fichiers | jsdom ; pas de navigateur réel ni Traefik |
| TypeScript `tsc --noEmit` | Réussi | Vérification statique, sans modifier les sources |
| actionlint CI/deploy | Réussi | shellcheck/pyflakes désactivés dans cette commande ; pas de workflow GitHub exécuté |
| npm audit complet | Code 1, **3 paquets signalés** | 1 modéré et 2 critiques selon npm ; outillage de développement |
| npm audit `--omit=dev` | Code 0, **0 signalement** | Dépendances runtime analysées, pas le système de l'image Node |
| pip-audit lock | Code 0, **47 versions**, aucun avis connu | Résolution transitive désactivée, exclusivement les versions listées |
| pip-audit installé | Code 0, **50 distributions**, aucun avis connu | Versions réelles de l'environnement local, hors projet et pip ; pas les variantes Linux absentes |
| Sonde admission avant auth | Confirmée | 1 048 692 octets reçus avant HTTP 401 ; aucun document créé |
| Sonde API directe | Confirmée | Bearer fictif valide, sans service/HTTPS : GET documents 200, espace vide |
| Sonde structures PDF actives | Confirmée | PDF synthétique avec action JS/pièce jointe bénigne accepté pour extraction ; aucun script exécuté |
| Recherche limitée de secrets suivis | Aucune signature trouvée | Noms de fichiers/compteurs uniquement, pas d'historique Git exhaustif |

Le seul avertissement pytest est la dépréciation Starlette/httpx de l'infrastructure de test,
sans échec. L'exit 1 de npm audit complet indique des alertes connues, pas une panne de scanner.
Le premier lancement des tests React était bloqué par l'accès d'esbuild aux répertoires parents,
et le premier npm audit par la restriction réseau locale. Leur relance autorisée hors de ces
restrictions a réussi : ces contrôles ne sont pas laissés non exécutés.

## Commandes principales

Depuis le dépôt, avec **aucun `TEST_DATABASE_URL` de production** :

```powershell
Remove-Item Env:TEST_DATABASE_URL -ErrorAction SilentlyContinue
.venv/Scripts/python.exe -m pytest -q
```

Les fixtures exigent une base de test vide, appliquent/annulent les migrations et utilisent
des dossiers temporaires. L'absence de variable sélectionne SQLite dans le répertoire pytest.
Une fixture automatique interdit les clients OpenAI réels ; les tests IA utilisent des doubles.
Les outils d'exploitation testent leurs commandes Docker/Restic/SMTP via simulations.

Depuis `frontend/` :

```powershell
npm.cmd run test:bff
npm.cmd run test:ui
npm.cmd audit --json --ignore-scripts --registry=https://registry.npmjs.org
npm.cmd audit --omit=dev --json --ignore-scripts --registry=https://registry.npmjs.org
```

Depuis la racine :

```powershell
.\frontend\node_modules\.bin\tsc.cmd -p frontend/tsconfig.json --noEmit
.\var\tools\actionlint\actionlint.exe -shellcheck= -pyflakes= .github/workflows/ci.yml .github/workflows/deploy.yml
```

`pip-audit` n'était pas installé dans le venv applicatif. Un environnement d'outillage séparé
ignoré par Git a été créé sous `var/security-audit-env/`, puis pip-audit **2.10.1** installé
depuis PyPI. Les dépendances applicatives n'ont pas été installées ou mises à jour par cet outil :

```powershell
.venv/Scripts/python.exe -m venv var/security-audit-env
.\var\security-audit-env\Scripts\python.exe -m pip install --disable-pip-version-check --index-url https://pypi.org/simple pip-audit
.\var\security-audit-env\Scripts\python.exe -m pip_audit -r requirements.lock --no-deps --disable-pip --format json
.\var\security-audit-env\Scripts\python.exe -m pip_audit -r var/security-audit-python-installed.txt --no-deps --disable-pip --format json
```

Le dernier fichier a été généré par `importlib.metadata.distributions()` du venv applicatif,
avec noms/versions uniquement, dédupliqués et triés, en excluant `documind-ai` et `pip`.
Il couvre notamment `argon2-cffi-bindings` 26.1.0, `cffi` 2.1.1 et `pycparser` 3.11, absents du
lock. Les 47 versions du lock étaient identiques à celles installées. L'outil recommande
un verrouillage avec hashes ; aucune commande `--fix` n'a été utilisée.

Les vulnérabilités npm et leur contextualisation sont décrites dans SEC10-05. Les 3 entrées
ne sont pas 3 failles du serveur déployé : deux avis Tinypool sont aussi remontés par leur
parent Vitest, et le runtime omet ces dépendances de développement.

## Sondes locales complémentaires : protocole et preuves

Ces contrôles ont été exécutés en scripts temporaires via stdin, sans ajout ou modification
de tests applicatifs. Aucun token ou hash de mot de passe réel n'a été journalisé. Les
réponses imprimées se limitent aux statuts, compteurs et booléens ci-dessous.

### 1. Réception avant authentification

Configuration explicite `Settings(_env_file=None, database_url='sqlite://', api_keys={},
legacy_api_enabled=False, bff_service_key=<valeur fictive>, storage_dir=<temporaire>)`.
`httpx.AsyncClient(ASGITransport(app=app))` appelle l'application sans startup des workers.
Un générateur asynchrone fournit une enveloppe multipart valide contenant un fichier TXT
fictif de 1 Mio ; il compte les octets réellement demandés. La requête porte un Bearer
inexistant et ne crée aucun utilisateur ni fichier documentaire.

```json
{"probe":"preauthentication-body-buffering","status":401,"consumed_bytes":1048692,"document_created":false}
```

Assertions exécutées : statut 401 ; tous les octets de l'enveloppe ont été consommés ;
répertoire temporaire resté vide. Cela confirme l'ordre de réception/authentification,
sans démontrer de saturation. Aucun test de charge ou de corps géant concurrent n'a été lancé.

### 2. Bearer direct sans provenance BFF

Configuration explicite, clés historiques désactivées et clé de service fictive présente.
Création de tables dans une base SQLite temporaire, d'un seul utilisateur fictif et d'une
session via le coffre serveur. GET `/api/v1/documents` en HTTP via transport ASGI, avec
Bearer seul, sans `X-API-Key`, sans `X-Documind-Secure`, sans cookie navigateur.

```json
{"probe":"direct-api-bearer-without-service-or-https-header","status":200,"empty_fictitious_workspace":true}
```

Assertions : 200 et total zéro. Sessions effacées, moteur fermé, base temporaire nettoyée.
La sonde ne prouve ni accès sans session, ni accès à un autre compte, ni exposition du port
API sur Internet. Elle mesure le contrat réel d'authentification de cette route interne.

### 3. PDF synthétique avec structures actives

PyMuPDF crée une page avec texte fictif, une `OpenAction` de type JavaScript contenant
uniquement un appel d'alerte fictif et une pièce jointe TXT bénigne. Le PDF reste dans un
répertoire temporaire et n'est jamais ouvert dans un navigateur/lecteur interactif.
Le contrôle confirme l'existence de l'action et de la pièce jointe, puis appelle la fonction
`extract` avec les limites normales. Son résultat est du texte attendu.

```json
{"probe":"pdf-active-structures","open_action_present":true,"attachments":1,"text_extracted":true,"original_file_download_endpoint":false}
```

La dernière propriété résume l'inventaire statique des routes, pas une interrogation du VPS.
Le script a émis un SyntaxWarning Python sur l'échappement d'une parenthèse dans sa chaîne
fictive ; les assertions et l'extraction ont abouti. Un contrôle `Get-Command` ultérieur
n'a trouvé ni Trivy, Grype ni Bandit et rendait le code de sortie global de cette cellule
égal à 1 : cela ne correspond pas à un échec de la sonde PDF. Aucun exploit natif n'a été testé.

## Revue statique et secrets

Lecture des chemins HTTP versionnés et des contrôles parents/indirects, recherche de SQL
dynamique, URL externe, rendu HTML non échappé, stockage navigateur de secrets et exécution
de commandes. L'analyse des outils administratifs distingue les commandes locales des
surfaces HTTP. Les outils sauvegarde, surveillance et rétention et les unités associées
ont été lus ; les tests existants de leurs scénarios d'erreur ont été exécutés dans pytest.

Recherche ciblée sur les seuls fichiers suivis par Git : entêtes de clés privées, formats
de clés fournisseur et identifiants cloud connus, en ne retournant que chemins/types/nombres
de correspondances. Résultat : zéro correspondance ; fichiers env suivis uniquement
`.env.example` et `.env.production.example`. Limites : formats arbitraires, historique,
fichiers non suivis, artefacts CI, couches Docker et logs non couverts par cette recherche.

Les avis officiels Vitest/Tinypool ont été consultés pour distinguer versions affectées et
préconditions. Aucun outil d'audit OpenAI ni appel à un modèle externe n'a été utilisé.

## Contrôles non réalisés et limites de preuve

- Aucune connexion SSH, requête vers le domaine DocuMind, Registry privée ou dépôt B2.
- Aucun accès aux comptes/documents réels, volumes PostgreSQL ou sauvegardes de production.
- Aucun scan d'images/OS : Trivy/Grype indisponibles ; pas d'installation de ces scanners.
  Bandit indisponible également ; analyse manuelle, sans prétendre à un scan SAST complet.
- Pas de PostgreSQL/pgvector local pour cet audit, ni de test natif Linux/systemd/seccomp.
- Pas de Playwright E2E complet ; les tests React utilisent jsdom et les tests BFF un upstream
  simulé. Pas de test du cache multi-onglets/BFCache dans un navigateur réel.
- Pas de test statistique d'énumération temporelle, fuzzing massif, charge, exploitation CVE
  ou test de pollution de prototype sur la machine de développement.
- Pas de vérification des versions réellement déployées, des permissions/pare-feu du VPS,
  des règles Traefik globales, des protections GitHub distantes ou de l'intégrité des images.
- Les bases d'avis Python/npm ne couvrent pas toutes les failles inconnues, paquets Linux,
  bibliothèques natives embarquées ou logiciels système. Aucun certificat de sécurité n'en découle.

## Intégrité du périmètre de livraison

Les seuls fichiers ajoutés pour ce sprint sont :

- `docs/sprint-10-security-audit.md` ;
- `docs/sprint-10-remediation-plan.md` ;
- `docs/validation-sprint-10-audit.md`.

Avant l'audit, l'arbre contenait déjà des modifications suivies de `README.md`,
`tests/test_deployment.py`, `tools/deploy_production.py` ainsi que les fichiers non suivis
des Sprints 7–9. Ils ont été conservés ; aucune correction ne leur a été ajoutée en phase A.
Les fichiers temporaires/cache des tests et l'outillage isolé restent hors des sources livrées.
Contrôle des espaces Git exécuté en fin de rédaction.

**Phase A terminée. Aucune phase B, modification distante, mise à jour applicative, suppression,
activation de timer, ouverture d'inscriptions/IA, publication ou push GitHub effectué.**
