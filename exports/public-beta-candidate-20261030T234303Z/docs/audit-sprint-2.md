# Audit et architecture — Sprint 2

## État inspecté

Le dépôt local contient le backend du Sprint 1, l'application desktop et leurs tests.
Il ne contient ni frontend ni manifeste Node initialement, et n'est toujours pas initialisé comme dépôt Git.
Aucun fichier AGENTS.md n'est présent. Le README et les schémas Pydantic ont été lus,
puis `/openapi.json` et les réponses réelles de FastAPI sur le port 8001 ont été consultés.
PostgreSQL et FastAPI sont opérationnels dans Docker.

## Contrats réellement disponibles

| Source | Données utilisées |
| --- | --- |
| Liste documents | `items`, `total`, `offset`, `limit` ; chaque document porte `id`, `filename`, `media_type`, `size_bytes`, `sha256`, `created_at` |
| Détail document | Métadonnées précédentes et `pages` (`id`, `page_number`, `text`) |
| Analyse | `id`, `document_id`, `engine_version`, `parameters`, `result`, `created_at` |
| Statistiques | `nombre_caracteres`, `nombre_mots`, `nombre_phrases`, `longueurs_phrases` |
| Qualité / lisibilité | `resume_qualite`, `lisibilite` : règles locales et mesures descriptives |
| Vocabulaire | `mots_frequents` sous forme de couples `[mot, occurrences]`, `termes_techniques`, `termes_techniques_absents` |
| Phrases / structure | `phrases_longues` avec page, alertes et suggestion ; `structure_document` avec listes et éléments paginés |
| Style / graphiques | `indice_style_artificiel`, `repartition_longueurs`, `phrases_longues_par_page`, `alertes_complexite`, `connecteurs_frequents`, `formules_generiques` |

L'API ne fournit ni compteur global d'analyses, ni statut d'analyse dans la liste, ni recherche serveur,
ni agrégation globale des tailles. Le tableau de bord présente le vrai total `total` et des statistiques
explicitement limitées aux six derniers imports chargés. Les filtres et la recherche de la bibliothèque
s'appliquent uniquement aux douze documents de la page chargée. Aucun champ de statut fictif n'est ajouté.
Une consultation d'analyse absente répond 404 ; le frontend propose alors d'en lancer une depuis la fiche.

## Architecture retenue

```text
Navigateur → React (routes, TanStack Query)
           → /bff/* sur la même origine
           → BFF Node/Express (clé uniquement serveur)
           → /api/v1/* FastAPI
           → PostgreSQL + stockage privé + moteur original
```

Le frontend utilise React, TypeScript, Vite, Tailwind CSS, React Router, TanStack Query,
Recharts et Lucide React. Les versions exactes sont conservées dans `frontend/package-lock.json`.
Les graphiques et la page de résultats sont chargés à la demande.
Les types TypeScript reproduisent les contrats Pydantic inspectés ; les réponses HTTP sont JSON,
donc les clés de `phrases_longues_par_page` sont des chaînes représentant les numéros de page.

En production locale, un même conteneur `web` héberge le build React et le BFF sur le port 3000.
En développement, Vite sur 5173 transmet `/bff` au BFF sur 3000 ; le BFF transmet ensuite à FastAPI.
Les documents ne sont pas servis comme fichiers statiques. React rend le texte sans `innerHTML`.
Le moteur, les modèles, les migrations et l'application de bureau restent inchangés.

## Choix de sécurité

- Clé jamais incluse dans `src`, une variable `VITE_*`, le stockage navigateur ou le build.
- Le BFF reprend automatiquement l'unique clé serveur dans `API_KEYS`.
  Avec plusieurs clés, `BFF_API_KEY` doit désigner explicitement le propriétaire local.
- Méthodes, routes avec UUID et paramètres de pagination explicitement autorisés ; aucune URL client arbitraire.
- Redirections amont refusées ; aucune transmission d'en-têtes ou de cookies du backend au navigateur.
- Erreurs HTTP contrôlées sans trace interne ni valeur de clé.
- Origines étrangères, `Sec-Fetch-Site: cross-site` et noms d'hôte étrangers refusés.
- Réponses BFF non mises en cache, limites de corps et délai amont, en-têtes de sécurité via Helmet.
- Publication de tous les ports sur `127.0.0.1` uniquement dans Compose.

Le BFF représente **un espace local partagé**, pas une authentification utilisateur.
Toute personne/processus ayant accès au port local peut utiliser cet espace. Ne pas publier ce service
via un tunnel ou une écoute Internet avant d'implémenter les sessions, autorisations et quotas.
La clé API communiquée précédemment dans la conversation n'est pas recopiée dans le code ni les documents.

## Préparation du Sprint 3

Ajouter un service fournisseur IA derrière FastAPI, avec une interface interchangeable et les secrets côté serveur.
Séparer les diagnostics locaux des résultats générés et conserver la provenance, la version et les paramètres.
Prévoir consentement d'envoi externe, minimisation des textes, quotas/coûts, délais, reprise et tests de panne.
Pour le RAG : réutiliser les pages/chunks déjà persistés, ajouter embeddings/recherche et citations de pages.
Avant une démo publique : sessions sécurisées, contrôle propriétaire par requête, révocation, protection CSRF,
limites par utilisateur et journalisation sans textes ni clés. La rubrique Assistant IA est actuellement désactivée.

Références techniques : [Tailwind avec Vite](https://tailwindcss.com/docs/installation/using-vite),
[TanStack Query](https://tanstack.com/query/latest/docs/framework/react),
[proxy de développement Vite](https://vite.dev/config/server-options).
