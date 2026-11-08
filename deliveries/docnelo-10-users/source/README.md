# DocuMind AI

Projet technique de gestion documentaire en Python et TypeScript : import de documents, analyse déterministe, recherche et assistance IA optionnelle. Le dépôt présente l'architecture, les protections et les tests du projet ; il ne constitue pas une annonce d'ouverture de bêta publique.

L'IA et les inscriptions publiques restent désactivées par défaut. Les documents juridiques présents dans l'interface restent des brouillons. Les fonctions futures DocuMind Business ne sont pas proposées comme disponibles.

## Fonctionnalités implémentées

- Import PDF/TXT, extraction par page, consultation et téléchargement des sources.
- Analyse de texte, statistiques, graphiques et comparaisons déterministes.
- Comptes, sessions, séparation des propriétaires et accès via un BFF côté serveur.
- Résumés, questions avec sources, indexation vectorielle et recherche documentaire dans les modules IA/RAG. Ces fonctions sont optionnelles, soumises aux paramètres, budgets et quotas ; leurs tests utilisent des fournisseurs simulés. La présence du code ne prouve pas une qualification en production d'un modèle externe.
- Limites d'upload, quotas de stockage, contrôle des accès et journalisation structurée.
- Mécanismes de suivi des suppressions, holds et restauration avec refus conservateur lorsque les preuves nécessaires manquent. Leur implémentation et les recettes synthétiques ne valent pas une validation de reprise de données réelles.

L'application de bureau historique reste dans le dépôt. Les développements Business et les dossiers opérationnels internes ne font pas partie de cette présentation publique.

## Architecture

| Composant | Rôle |
|---|---|
| [frontend](frontend/) | React/TypeScript, interface et BFF Node.js ; les secrets serveur ne sont pas transmis au navigateur |
| [backend](backend/) | API FastAPI, authentification, documents, analyse, tâches IA/RAG |
| [documind_extractor](documind_extractor/) | Extraction isolée sous Linux avec Landlock/seccomp |
| [migrations](migrations/) | Schéma SQLAlchemy/Alembic, PostgreSQL et pgvector |
| [tests](tests/) | Tests portables, preuves POSIX et intégrations sur bases jetables |
| [ops/testing](ops/testing/) | Sources de laboratoires synthétiques ; aucun lancement automatique |
| [tools](tools/) | Contrôles, manifestes et outils opérateur soumis à leurs prérequis |

Le navigateur communique avec le BFF ; le BFF appelle l'API. Les fichiers sources sont stockés séparément des métadonnées PostgreSQL. Les magasins lifecycle et le latch de restauration ont des responsabilités distinctes : le latch ne remplace pas les preuves de cohérence des données.

## Prérequis

- Python 3.13 pour les versions de dépendances qualifiées localement ; la déclaration de compatibilité du paquet ne garantit pas une validation de toutes les versions Python.
- Node.js 22 et npm pour le frontend/BFF.
- Docker Engine ou Docker Desktop avec conteneurs Linux et la commande `docker compose` pour le parcours local ci-dessous.
- Pour l'extraction confinée : noyau Linux prenant en charge Landlock ABI 3 ou supérieur et libseccomp2. L'application refuse le mode sandbox si le confinement requis est indisponible.

Sous Windows, Docker Desktop/WSL2 fournit le parcours conteneurisé. Les tests portables fonctionnent avec Python Windows ; les preuves de permissions et de confinement exigent Linux. L'adaptateur `EXTRACTION_MODE=development` hors Docker est non confiné et ne convient qu'à des fichiers synthétiques de développement.

Les dépendances déclarées et les contraintes sont dans [pyproject.toml](pyproject.toml) et [requirements.lock](requirements.lock). Le frontend utilise son [package-lock.json](frontend/package-lock.json).

## Démarrage local sur un checkout dédié

Ce parcours concerne une installation locale neuve et des fichiers fictifs. Il ne faut pas l'appliquer à une installation contenant des données réelles. Les commandes suivantes sont présentées pour un shell Linux/WSL ; elles ne sont pas un déploiement de production.

Préparer le fichier local depuis [le modèle de développement](.env.example), sans écraser une configuration existante :

```sh
cp -n .env.example .env
```

Dans ce fichier local, définir :

```dotenv
API_KEYS={}
LEGACY_API_ENABLED=false
OWNER_DEMO_ENABLED=false
REGISTRATION_MODE=disabled
AI_ENABLED=false
ACCOUNT_BASE_URL=https://localhost:8443
```

Générer deux valeurs différentes avec `python -c "import secrets; print(secrets.token_urlsafe(32))"` et renseigner `BFF_SERVICE_KEY` et `DOCUMIND_GATEWAY_TOKEN`. Ne pas réutiliser ces secrets ailleurs et ne pas versionner le fichier local. Les identifiants PostgreSQL du modèle de développement sont exclusivement locaux.

Le garde de restauration reste actif. Pour cette installation neuve synthétique seulement, créer son fichier local, sans écraser un fichier existant :

```sh
python - <<'PY'
import json
from pathlib import Path
path = Path("var/recovery-state.json")
path.parent.mkdir(parents=True, exist_ok=True)
with path.open("x", encoding="utf-8") as stream:
    json.dump({"format": 1, "state": "ready"}, stream)
PY
```

Ce fichier ne constitue pas une preuve de restauration et ne doit pas être utilisé en production. Il n'initialise aucun magasin lifecycle ; les opérations exigeant des preuves supplémentaires peuvent rester refusées.

Le [Compose de développement](compose.yaml) monte ce fichier en lecture seule et conserve les données locales dans des volumes distincts. Démarrer ensuite les services et créer un compte **local** :

```sh
docker compose --profile https up --build -d
docker compose exec api python -m backend.accounts demo
```

Le mot de passe est demandé de manière interactive. Ouvrir `https://localhost:8443/login` après avoir installé la confiance dans l'autorité de certification **locale** de Caddy ; conserver la vérification TLS. Les inscriptions publiques et les appels IA restent désactivés.

Le parcours de démarrage complet n'est pas requalifié par les seuls tests de configuration ; vérifier les prérequis Linux, la santé des services et les droits locaux. Aucun compte ou secret préexistant n'est fourni par le dépôt.

## Tests et contrôles

Utiliser un second checkout de test sans fichier `.env` ou `.env.production`, sans connexion à une base réelle et sans variable de fournisseur réel. Les fixtures emploient des fichiers et identités synthétiques et interdisent les clients OpenAI réels.

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -c requirements.lock -e '.[test]'
python -m pytest -q
python tools/build_materials.py --require-pins --npm-lock frontend/package-lock.json
```

Sous Windows, utiliser `.venv\Scripts\python.exe` et sélectionner `python -m pytest -q -m "not posix"`. Les cas POSIX restent exécutés dans les suites Linux. Un test ignoré n'est pas un succès.

Les tests PostgreSQL exigent un service **créé pour les tests**, jamais une base existante ou partagée. Leurs contrats distinguent `TEST_DATABASE_URL` pour l'application et `DOCUMIND_TEST_POSTGRES_DSN` pour le protocole de laboratoire. La [CI](.github/workflows/ci.yml) prépare ce service et impose `--require-no-skips` aux groupes requis ; les preuves root/non-root ont des étapes distinctes. Les résultats locaux ne prouvent pas l'exécution d'un workflow GitHub.

Tests frontend, dans le même environnement de développement isolé :

```sh
cd frontend
npm ci
npm run test:ui
npm run test:bff
```

Les tests nécessitant un service ou une plateforme indisponible doivent être signalés comme non exécutés, sans déduction de validation globale.

## Local, recette et production

| Environnement | Usage et limites |
|---|---|
| Local | Compte et documents fictifs, paramètres de développement, accès loopback et HTTPS local |
| Recette | Services neufs isolés, clés synthétiques, injections d'erreurs et preuves de tests ; aucune donnée utilisateur |
| Production | Images et bundle exacts attestés, configuration explicite, validation humaine et procédures opérateur séparées |

Le [modèle de production](.env.production.example) ne fournit ni hôte ni secret utilisable. Le [Compose de production](compose.production.yaml) exige les images, l'hôte et les secrets nécessaires ; il conserve les trois volumes de données et le latch externe en lecture seule.

Le [workflow de déploiement](.github/workflows/deploy.yml) reste manuel, soumis aux approbations et au contrôle d'une release CI précise. Son affichage d'URL utilise des variables explicites, sans valeur nominative par défaut. La neutralisation de ces modèles ne rend pas les contrôleurs historiques génériques : certains helpers imposent encore des hôtes, registres ou chemins propres à leur contrat existant. Un autre déploiement n'est pas qualifié par ces fichiers.

Aucune ouverture de bêta, validation juridique, conformité globale ou disponibilité d'une offre Business n'est annoncée. Les procédures internes de récupération et les décisions de diffusion documentaire doivent être conservées dans un support privé adapté.
