# DocuMind AI — application web documentaire

Interface React / TypeScript, import PDF/TXT, extraction par page, graphiques et analyse déterministe
du moteur Python existant, avec FastAPI et PostgreSQL. Un assistant OpenAI optionnel ajoute des résumés
et questions documentaires avec sources. L’IA reste désactivée par défaut.
L'application de bureau reste accessible par `main.py`.
L'[audit du code](docs/audit-sprint-1.md) détaille la réutilisation et les différences d'extraction.
L'[ancien guide de bureau](docs/desktop.md) est conservé intégralement.
Le [rapport de validation](docs/validation-sprint-1.md) précise les tests exécutés et la limite Docker rencontrée.

## VPS, Registry privée et CI/CD

Le [guide Sprint 6](docs/sprint-6-cicd.md) décrit les secrets GitHub, les paramètres VPS,
le déploiement manuel approuvé et le retour arrière. Le Compose de production réutilise
Traefik `web` / `websecure` / `letsencrypt` ; il ne crée aucun second proxy.
La CI publie des images identifiées par SHA après réussite des tests. Aucun push ne déploie le VPS.
Les secrets et les accès doivent être configurés par l’administrateur avant le premier lancement.

## Ouvrir l'application web

**Sprint 5 :** l’accès documentaire du navigateur nécessite désormais un compte et HTTPS.
Les comptes existants gardent leur identifiant et leurs documents. Consultez le
[guide des comptes et de migration des propriétaires](docs/sprint-5-accounts.md) et le
[rapport de validation](docs/validation-sprint-5.md).

Pour une installation existante des Sprints 1–3, suivre d’abord la [sauvegarde et mise à niveau Sprint 4](docs/sprint-4-rag.md).
Les migrations `0004` (pgvector/RAG) et `0005` (résumés persistants) conservent les données précédentes.
Ne jamais supprimer le volume PostgreSQL pour mettre à niveau.

Avec Docker Desktop démarré et votre `.env` existant configuré :

```powershell
docker compose --profile https up --build -d
docker compose ps
```

Ouvrez **https://localhost:8443/login** après installation du certificat local décrit dans
[le guide HTTPS](docs/sprint-3-ai-byok.md). Le service `web` contient le build React et le BFF Node.
Les services `api` et `db` restent séparés. Le BFF attend un backend opérationnel ; l'indicateur
« Services connectés » confirme la connexion à PostgreSQL via FastAPI.

Configurez une clé interne `BFF_SERVICE_KEY` aléatoire, distincte de `API_KEYS`, dans `.env`.
Elle authentifie le BFF ; les droits documentaires proviennent exclusivement de la session personnelle.
L’ancien réglage `BFF_API_KEY` reste compatible pour les installations non migrées.
`LEGACY_API_ENABLED=false` désactive l’accès X-API-Key des scripts, sans désactiver les comptes.
Ne créez aucune variable `VITE_*` contenant une clé. L’accès HTTP ne donne plus accès aux documents.

Parcours : **Importer un document** → choisir ou déposer un PDF/TXT → consulter le texte extrait →
**Lancer l'analyse** → explorer les sections et graphiques. La suppression demande confirmation.
Les graphiques ont des tableaux de valeurs accessibles. L’assistant documentaire apparaît sur la fiche du document ;
les générations exigent activation serveur, connexion HTTPS et consentement explicite.
La recherche de la bibliothèque et les filtres portent uniquement sur la page chargée.
La page distincte « Bibliothèque intelligente » recherche dans les documents sélectionnés et leurs passages.
Le tableau de bord distingue le total des documents des statistiques sur les six derniers imports.

Ports (tous limités à `127.0.0.1`) : `WEB_PORT=3000`, `API_PORT=8000` (ici `8001` si vous avez
conservé le réglage du Sprint 1), PostgreSQL `5432`. Si 3000 est occupé, définissez `WEB_PORT=3001`
et relancez `docker compose up -d web`, puis ouvrez l'adresse avec ce nouveau port.

```powershell
docker compose logs -f web api
docker compose stop
```

Le [guide d'architecture Sprint 2](docs/audit-sprint-2.md) décrit les contrats et protections du BFF.
Le [rapport Sprint 2](docs/validation-sprint-2.md) détaille les vérifications.

## Assistant IA et clé personnelle — Sprint 3

Le [guide Sprint 3 / BYOK](docs/sprint-3-ai-byok.md) présente l’architecture, toutes les variables,
les budgets, les limites, la révocation et la procédure d’essai réel.
Le [rapport de validation Sprint 3](docs/validation-sprint-3.md) consigne les vérifications exécutées.

```powershell
docker compose --profile https up --build -d
docker compose exec api python -m backend.accounts adeline
```

Configurer d’abord le secret serveur `DOCUMIND_GATEWAY_TOKEN` si absent. La commande de compte demande
un mot de passe sans l’afficher. Ouvrir **https://localhost:8443/settings/ai** après avoir approuvé
le certificat de votre propre Caddy selon le guide ; ne pas saisir de vraie clé tant que le navigateur
affiche un avertissement de certificat.

Le mode `USER_BYOK` conserve la clé personnelle uniquement dans une session serveur de 30 minutes.
La connexion de la clé ne fait aucun appel fournisseur ; un bouton distinct valide l’accès au modèle.
Le mode `OWNER_DEMO` utilise la clé serveur et peut être désactivé. Les consommations sont isolées,
réservées atomiquement et consultables avec leurs tokens et coûts estimés.
Ces plafonds applicatifs ne garantissent pas un plafond absolu de facturation OpenAI.

`AI_ENABLED=false` laisse les fonctions classiques disponibles. Aucun appel OpenAI payant n’est lancé
par les tests. Le compte, la clé et l’essai réel doivent être configurés volontairement ; aucun compte
utilisateur avec mot de passe prédéfini n’est livré.

## Recherche hybride et comparaison — Sprint 4

Sur l’accès HTTPS, après connexion :

- **[Bibliothèque intelligente](https://localhost:8443/library)** : sélection de documents, indexation explicite,
  recherche lexicale ou hybride pgvector/RRF, questions multi-documents et références ouvrant le passage exact.
- **[Comparer deux documents](https://localhost:8443/compare)** : différences locales avec pages sources,
  puis synthèse IA facultative des seuls changements détectés.
- **Résumé approfondi**, dans la fiche d’un document long : plan et coût maximal avant confirmation,
  worker dédié, étapes persistées, progression réelle, reprise et annulation.

L’import ne déclenche aucune indexation payante. Les appels IA restent soumis au consentement et aux
plafonds OWNER_DEMO/BYOK. PostgreSQL utilise une recherche cosinus exacte ; aucun HNSW n’est créé.

Consulter le [guide RAG et migration](docs/sprint-4-rag.md), la [correction des résumés longs](docs/long-document-summary.md)
et le [rapport de validation final](docs/validation-sprint-4.md). La génération réelle du mémoire de 53 pages
n’a pas été lancée : son plan est disponible avant confirmation explicite.

## Développement React et BFF hors Docker

Prérequis : Node.js 22.12+ et npm. Gardez FastAPI/PostgreSQL démarrés avec
`docker compose up -d db api`. Arrêtez le service web pour libérer le port local du BFF :

```powershell
docker compose stop web
cd frontend
npm.cmd ci
npm.cmd run bff
```

Dans un second terminal, depuis `frontend` :

```powershell
npm.cmd run dev
```

Ouvrez http://127.0.0.1:5173. Vite transmet `/bff/*` à `127.0.0.1:3000` ; la clé n'est jamais ajoutée par Vite.
Le BFF lit le `.env` à la racine. Il utilise `API_PORT` pour joindre FastAPI, ou `BFF_BACKEND_URL`
si cette variable est définie (par exemple `http://127.0.0.1:8001`). Docker remplace cette URL
par `http://api:8000` pour utiliser son réseau interne.
Conservez `BFF_PORT=3000` en développement, car le proxy Vite vise ce port.
Sous Git Bash/Linux/macOS, `npm` remplace `npm.cmd`. Sous PowerShell, `npm.cmd` évite les restrictions de scripts `npm.ps1`.

```powershell
npm.cmd test
npm.cmd run build
npm.cmd start
```

`npm start` sert le build `dist` et le BFF ; ne le lancez pas en même temps que `npm run bff` sur le même port.

Tests de bout en bout, avec l'application Docker déjà lancée sur 3000 :

```powershell
npx.cmd playwright install chromium
npm.cmd run test:e2e
```

Ces tests importent puis suppriment leurs propres documents de vérification. Ils couvrent les formats
ordinateur et mobile. Pour un autre port, définissez `E2E_BASE_URL` avec l'origine de l'application.
Vitest utilise des réponses simulées ; les tests BFF utilisent un serveur HTTP local et un amont simulé.
Les tests Playwright utilisent les vrais services Docker/PostgreSQL.

## Limites de déploiement

Le BFF refuse les routes arbitraires et les origines étrangères. Ne rendez pas l’espace HTTP partagé
public ou accessible par un tunnel. Les sessions personnelles HTTPS sont prévues pour un seul processus
FastAPI ; elles sont invalidées au redémarrage. Une production publique nécessite notamment une
authentification gérée, une récupération de compte et une infrastructure de sessions adaptée.
Les clés serveur et les documents ne doivent jamais entrer dans le contexte de build ou le stockage navigateur.
Le guide Sprint 3 décrit les protections et limites actuelles ; les rapports des Sprints 1 et 2 restent
des comptes rendus historiques de ces étapes.

## Installation locale (PowerShell)

Prérequis : Python 3.11+ (testé avec 3.13), PostgreSQL 17 ou Docker Compose.
Depuis la racine du projet :

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -c requirements.lock -e '.[test]'
Copy-Item .env.example .env
```

Si l'alias `python` ouvre Microsoft Store, utilisez le chemin de votre vrai interpréteur
pour créer l'environnement, puis `.\.venv\Scripts\python.exe` pour les commandes suivantes.
L'activation n'est pas obligatoire avec ce chemin complet.
`requirements.lock` fixe les versions résolues et testées sous Windows ; les dépendances
optionnelles propres à une autre plateforme sont résolues par pip.
Sous Linux/macOS : `python3 -m venv .venv`, puis `source .venv/bin/activate`.

Générez une clé et un identifiant propriétaire localement :

```powershell
python -c "import secrets,uuid,json; print('API_KEYS=' + json.dumps({secrets.token_urlsafe(32):str(uuid.uuid4())}))"
```

Copiez la ligne produite dans `.env` à la place de `API_KEYS={}`.
Conservez la clé pour Swagger. Les clés sont secrètes, ne commitez pas `.env`.
Une clé désigne un propriétaire défini côté serveur : le client ne choisit jamais son `owner_id`.
Plusieurs clés peuvent désigner le même propriétaire pour faciliter la rotation.
Le serveur refuse de démarrer si aucune clé n'est configurée.

## PostgreSQL et FastAPI

Docker Desktop doit être démarré. Pour lancer **la base et FastAPI ensemble**, utilisez
`docker compose up --build -d`, puis ouvrez http://127.0.0.1:8000/docs.
Si le port 8000 est déjà utilisé, ajoutez `API_PORT=8001` dans `.env`, relancez
`docker compose up -d api`, puis ouvrez http://127.0.0.1:8001/docs.
La commande `docker compose up -d db` ci-dessous lance uniquement PostgreSQL :
elle doit être suivie du lancement de FastAPI sur votre machine.

```powershell
docker compose up -d db
alembic upgrade head
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000 --limit-concurrency 32
```

Avec PostgreSQL installé directement, créez une base et un rôle dédiés, puis adaptez `DATABASE_URL`.
Les tables sont créées uniquement par Alembic, jamais automatiquement au lancement de l'API.

Pour lancer l'ensemble via Docker Compose après configuration de `.env` :

```powershell
docker compose up --build -d
docker compose logs -f api
```

Le conteneur API attend PostgreSQL et applique les migrations avant Uvicorn.
Les ports sont liés à `127.0.0.1`, les documents sont dans un volume privé et le processus API
tourne sans privilèges root. Les limites du conteneur complètent celles des processus d'extraction.
Une instance Uvicorn est prévue pour ce MVP ; les migrations ne doivent être lancées qu'une fois
avant le démarrage en cas de déploiement futur avec plusieurs instances.
`docker compose down` arrête les services en conservant les volumes.

## Parcours Swagger

1. Ouvrez http://127.0.0.1:8000/docs.
2. Cliquez **Authorize** et entrez votre clé dans `X-API-Key`.
3. Dans `POST /api/v1/documents`, choisissez un PDF ou TXT UTF-8, puis **Execute**.
4. Copiez l'`id` reçu (HTTP 201).
5. Appelez `POST /api/v1/documents/{document_id}/analyze` avec cet identifiant.
   Le corps JSON est facultatif ; `{}` utilise les réglages par défaut.
6. Consultez le JSON typé sous `result`, ou récupérez-le ensuite avec
   `GET /api/v1/documents/{document_id}/analysis`.

Exemple de paramètres d'analyse :

```json
{
  "limite_phrase_longue": 35,
  "termes_techniques": ["API", "Docker", "base de données"],
  "mode_memoire": false,
  "filtrer_blocs_non_narratifs_actif": true,
  "ignorer_titres": true
}
```

Le moteur produit les statistiques, mots fréquents, termes présents/absents, phrases longues et
leurs pages, structure, lisibilité, heuristiques de style et résumé **qualité**. Ce dernier
est un diagnostic déterministe, pas un résumé sémantique du document.
`mode_memoire=true` conserve le comportement historique Introduction → Conclusion ; utilisez
`false` pour analyser l'ensemble du texte. Les options de filtrage concernent l'analyse ;
le texte brut conservé en base reste intégral.
Sur certains PDF, les courtes lignes sans ponctuation peuvent être assimilées à des titres
par le moteur historique ; passez `ignorer_titres` à `false` pour les inclure dans l'analyse.

## Contrat HTTP

| Route | Succès | Comportement |
| --- | --- | --- |
| `POST /api/v1/documents` | 201 | Multipart `file`, extraction et stockage des pages/chunks |
| `GET /api/v1/documents` | 200 | `items`, `total`, `offset` (0+), `limit` (1–100, défaut 20) |
| `GET /api/v1/documents/{id}` | 200 | Métadonnées et texte extrait page par page |
| `DELETE /api/v1/documents/{id}` | 204 | Suppression fichier, pages, chunks et analyses |
| `POST /api/v1/documents/{id}/analyze` | 201 | Nouvelle analyse historisée, options JSON facultatives |
| `GET /api/v1/documents/{id}/analysis` | 200 | Dernière analyse persistée |
| `GET /api/v1/health` | 200 | Test de connexion base, sans authentification |

Les routes documents exigent une authentification : `X-API-Key` pour l’accès API direct,
ou une session personnelle transmise par le BFF HTTPS. Une authentification absente/invalide donne **401**.
Un document absent ou appartenant à un autre propriétaire, ou une analyse inexistante, donne **404**.
**413** : fichier > limite ou requête > limite + 64 Kio de marge multipart.
**415** : extension autre que `.pdf`/`.txt`.
**422** : paramètres invalides, vide, binaire, contenu incohérent, PDF corrompu/chiffré,
absence de texte extractible ou limite de ressources dépassée.
**503** : base indisponible ou tous les processus de traitement occupés ; réessayez plus tard.
Les erreurs métier ont la forme `{"detail":"message"}` ; les erreurs de validation FastAPI
ont `detail` sous forme de liste localisant les champs invalides. Les schémas détaillés sont
disponibles dans Swagger et `/openapi.json`. Aucun chemin de stockage ni secret n'est renvoyé.

## Variables d'environnement

| Variable | Défaut | Utilité |
| --- | --- | --- |
| `DATABASE_URL` | PostgreSQL local `documind` | URL SQLAlchemy avec pilote `postgresql+psycopg` |
| `API_KEYS` | `{}` (démarrage refusé) | Objet JSON clé secrète ≥32 caractères → UUID propriétaire |
| `STORAGE_DIR` | `var/documents` | Répertoire privé, hors fichiers servis par HTTP |
| `API_PORT` | `8000` | Port local publié par Docker Compose ; utilisez `8001` si 8000 est occupé |
| `WEB_PORT` | `3000` | Port local du service web Docker (React + BFF) |
| `BFF_PORT` | `3000` | Port du BFF lancé hors Docker ; attendu par le proxy Vite |
| `BFF_BACKEND_URL` | API locale selon `API_PORT` | Origine FastAPI côté serveur ; `http://api:8000` dans Docker |
| `BFF_API_KEY` | unique clé de `API_KEYS` | Sélection explicite obligatoire si plusieurs clés sont configurées |
| `MAX_UPLOAD_BYTES` | `10485760` | 10 Mio par fichier (10 × 1024 × 1024 octets) |
| `MAX_PDF_PAGES` | `200` | Nombre maximal de pages |
| `MAX_TEXT_CHARS` | `1000000` | Texte total maximal PDF ou TXT |
| `WORKER_TIMEOUT_SECONDS` | `30` | Durée maximale par extraction/analyse |
| `WORKER_MEMORY_MB` | `512` | Plafond mémoire par processus de traitement |
| `MAX_CONCURRENT_WORKERS` | `2` | Processus simultanés par instance API |
| `CHUNK_CHARS` | `1500` | Taille des fragments, offsets par page |
| `POSTGRES_USER/PASSWORD/DB` | `documind` | Paramètres Compose de développement local |

Les identifiants PostgreSQL d'exemple sont des valeurs publiques de développement local,
sans clé API ni secret réel. Modifiez-les pour tout autre usage. Si un mot de passe contient
des caractères réservés, encodez-les dans l'URL `DATABASE_URL`.
Les variables du processus prennent priorité sur `.env`.

## Stockage, sécurité et limites du MVP

L'extension est une liste d'autorisation, puis le contenu est vérifié : signature PDF et ouverture
PyMuPDF stricte ; TXT UTF-8 sans contrôles binaires et sans signatures binaires usuelles.
Un TXT peut contenir du code ou du balisage en tant que texte : aucun contenu n'est exécuté
ou rendu en HTML. Le MIME annoncé par le client n'est pas utilisé comme preuve.
Aucun endpoint de téléchargement public ni montage statique du stockage n'existe.

Les fichiers sont nommés par UUID serveur, écrits en `.part`, extraits puis enregistrés en base
dans une transaction. Tout échec normal annule les données et nettoie les fichiers.
La suppression renomme d'abord le fichier en `.deleted`, supprime les données par cascade,
puis efface le fichier ; une erreur de transaction restaure le fichier.
Le système de fichiers et PostgreSQL n'ont pas de transaction atomique commune : un arrêt brutal
peut laisser un fichier temporaire/orphelin. La commande de maintenance ci-dessous permet de
réconcilier le stockage **API arrêtée**, d'abord en simulation puis en application.

```powershell
python -m backend.maintenance
python -m backend.maintenance --apply
```

Les traitements s'exécutent dans des processus jetables. Le parent surveille durée et mémoire
sous Windows et Linux et termine le processus si nécessaire ; sous Linux, des limites système
CPU/espace d'adressage s'ajoutent. Sous Windows, la mémoire est contrôlée par sondage, avec
un dépassement transitoire possible ; les plafonds du conteneur renforcent la protection sous Docker.
Ce mécanisme ne constitue pas une sandbox contre les vulnérabilités natives de PyMuPDF ;
maintenez les dépendances à jour. Pas d’OCR, antivirus ni quota disque par utilisateur.
Les comptes HTTPS ajoutés au Sprint 3 et les clés API serveur résolvent tous deux un `owner_id` ;
les clés API conviennent à l’accès administratif local.

## Tests

```powershell
python -m pytest -q
```

Par défaut, les tests utilisent une base SQLite temporaire créée avec les migrations Alembic,
des fichiers PDF générés pendant les tests et les vrais processus d'extraction/analyse.
Pour tester contre PostgreSQL, utilisez une **base de test dédiée vide et jetable** : les tests
appliquent puis annulent les migrations à chaque cas.

```powershell
$env:TEST_DATABASE_URL = 'postgresql+psycopg://documind:documind@127.0.0.1:5432/documind_test?connect_timeout=5'
python -m pytest -q
Remove-Item Env:TEST_DATABASE_URL
```

Couverture : PDF/TXT valides, extraction/pages/chunks/statistiques, fichiers vides/corrompus/chiffrés,
contenu binaire et falsifié, taille, limites pages/texte/temps, CRUD et cascade, erreurs HTTP,
authentification, isolation des propriétaires et nettoyage après échec.
Les tests IA/BYOK ajoutent sorties et références validées, expiration/révocation des sessions,
absence de fuite de secret, budgets concurrents, quotas et idempotence. Aucun appel OpenAI réel.

## Organisation

```text
analyseur_documents/       moteur et application de bureau conservés
backend/
  main.py                 application, cycle de vie, limite de requête
  api.py                  routes /api/v1 et authentification
  auth.py, accounts.py    comptes et sessions éphémères, création administrative
  ai/                     fournisseurs, recherche, résumés, budgets et paramètres BYOK
  config.py               variables d'environnement validées
  db.py, models.py        sessions et modèles SQLAlchemy 2
  schemas.py              contrats JSON Pydantic
  services/               import, stockage, extraction et analyse isolée
  maintenance.py          réconciliation hors ligne du stockage
migrations/               migrations Alembic versionnées
tests/                    tests pytest
docs/                     audit et guide de bureau historique
```

Pour le bureau : `pip install -e '.[desktop]'`, puis `python main.py`.
Tkinter doit être disponible dans votre installation Python ; le backend n'en dépend pas.

Références : [fichiers multipart FastAPI](https://fastapi.tiangolo.com/tutorial/request-files/),
[authentification par clé](https://fastapi.tiangolo.com/reference/security/),
[cascades SQLAlchemy](https://docs.sqlalchemy.org/en/20/orm/cascades.html).
