# Bilan du Sprint 2 — 19 octobre 2026

## Livrable

L'application est construite et démarrée localement : **http://127.0.0.1:3000**.
Les services `db`, `api` et `web` sont sains dans Docker Compose.
Swagger reste disponible au port API configuré, ici **8001**.
Aucune clé n'est à saisir dans React : le BFF la conserve côté serveur.

Fonctionnalités : tableau de bord sur données réelles, import PDF/TXT par sélection ou dépôt,
validation de format/taille, bibliothèque paginée et recherche dans la page chargée,
consultation des métadonnées et du texte par page, réglages d'analyse, neuf sections de résultats,
six familles de graphiques et suppression confirmée. L'assistant IA est désactivé.

## Fichiers ajoutés ou modifiés

| Zone | Fichiers et rôle |
| --- | --- |
| Configuration frontend | `frontend/package.json`, `package-lock.json`, `tsconfig.json`, `vite.config.ts`, `index.html`, favicon |
| React | `frontend/src/App.tsx`, `main.tsx`, `styles.css` : routes, identité visuelle, responsive et accessibilité |
| Pages | `frontend/src/pages/` : tableau de bord, bibliothèque, fiche document, résultats |
| Composants | `frontend/src/components/` : layout, fenêtres d'import/suppression, tableaux, états et graphiques |
| Contrats et accès API | `frontend/src/types/api.ts`, `services/api.ts`, `hooks/useDocuments.ts` |
| BFF serveur | `frontend/server/config.mjs`, `app.mjs`, `index.mjs` : configuration privée, routes autorisées, contrôles d'origine, limites et erreurs |
| Tests | Tests Vitest dans `frontend/src/`, tests HTTP BFF, Playwright dans `frontend/e2e/`, fixture PDF synthétique et configuration navigateur |
| Docker | `frontend/Dockerfile`, `frontend/.dockerignore`, `compose.yaml`, `.dockerignore` racine |
| Configuration locale | `.env.example` documente les ports et réglages BFF ; la clé et les réglages actuels du `.env` sont conservés |
| Documentation | README, `docs/audit-sprint-2.md`, ce bilan |

Aucun module métier Python, modèle, migration ou fichier de l'application de bureau n'est modifié.

## Vérifications exécutées

| Commande / vérification | Résultat |
| --- | --- |
| `npm.cmd run build` | TypeScript et build Vite réussis |
| `npm.cmd test` | **24 tests Vitest + 15 tests BFF réussis** |
| `python -m pytest -q` | **29 tests backend réussis** |
| `npm.cmd run test:e2e` | **6 tests Chromium réussis**, ordinateurs et mobiles |
| `npm.cmd audit --omit=dev --audit-level=high` | Aucune vulnérabilité de production connue signalée au moment de l'exécution |
| `docker compose up --build -d web` | Image React/BFF construite, dépendances démarrées, trois services sains |
| Santé depuis le BFF Docker | HTTP 200, `status=ok`, `database=ok` |
| Inspection des sources et de `dist/` | Aucune des clés API configurées trouvée |

Les tests navigateur passent par le vrai BFF, FastAPI et PostgreSQL : sélection de TXT et de PDF,
import, lecture du texte, lancement d'analyse, résultats (9 mots attendus), résumé qualité,
graphiques puis suppression. Ils vérifient aussi l'absence de clé dans les requêtes navigateur,
la navigation mobile, la fermeture des fenêtres et du menu avec Échap et l'absence de débordement
horizontal aux largeurs 390, 768 et 1440 pixels. Leurs documents de vérification sont nettoyés.

La vérification visuelle a porté sur le tableau de bord (ordinateur/mobile), la fiche mobile et
les graphiques sur ordinateur. Les captures locales sont dans `frontend/test-results/` (ignoré par Git).
Les graphes disposent de tableaux de valeurs ; les valeurs zéro ne sont pas confondues avec des données absentes.
Les fenêtres utilisent le dialogue natif, et le menu mobile gère focus, tabulation et touche Échap.

Les graphiques sont chargés à la demande : bundle initial environ 352 Ko et module d'analyse
environ 384 Ko minifiés, séparés. Le build final ne signale plus de chunk supérieur à 500 Ko.

## Limites restantes

- Le BFF est un accès à un espace **local unique** ; ce n'est pas une connexion de comptes.
  Il ne doit pas être exposé publiquement avant l'ajout de sessions, autorisations et quotas.
- Recherche et filtres limités aux documents de la page chargée ; statistiques de volume/format
  limitées aux imports récents explicitement indiqués. Le total des documents vient bien du serveur.
- Les tests responsive utilisent Chromium, y compris l'émulation mobile ; Firefox et Safari n'ont pas été automatisés.
  L'accessibilité n'a pas fait l'objet d'une certification ou d'un audit exhaustif.
- Le résumé est un diagnostic qualité déterministe ; l'indice de style n'est pas un détecteur fiable d'IA.
- Les limites du moteur existant sont conservées : pas d'OCR, pas de PDF chiffré, filtres de titres heuristiques.
- Une dépréciation tierce Starlette/HTTPX reste signalée par les tests Python sans les bloquer.
- La suite Python utilise SQLite temporaire. Les parcours navigateur valident PostgreSQL réel,
  mais la suite Python complète sur PostgreSQL n'a pas été relancée dans une base de test dédiée.
- Le dossier n'est pas initialisé comme dépôt Git ; aucun commit n'a été créé.

## Sprint 3

Préparer une interface de fournisseur IA interchangeable côté FastAPI, avec secrets exclusivement serveur,
consentement d'envoi des documents, provenance des résultats et budgets/quotas. Réutiliser les pages/chunks
pour le RAG et les citations, puis tester délais, erreurs et absence de fuite de données.
Avant une démo publique, ajouter l'authentification utilisateur et les autorisations au BFF/backend.
Les points d'architecture sont détaillés dans l'audit Sprint 2 ; aucune intégration IA n'est effectuée ici.
