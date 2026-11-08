# Docnelo — Branding Audit (Public + Bêta)

Date (locale): 2026-10-31 (Europe/Paris)

## Objectif
Identifier **où** le branding "DocuMind" apparaît aujourd'hui, **comment** les environnements Public/Production et Bêta sont séparés, et **quels identifiants techniques** doivent rester inchangés afin d'éviter toute régression (accès, données, volumes, secrets, chemins persistants, cookies, etc.).

> Ce document est un audit. Aucune modification fonctionnelle (règles d'inscription, secrets, domaines, volumes, DB) n'est prévue dans la phase branding.

---

## 1) Structure du dépôt

- Frontend (React + Vite + Tailwind v4): `frontend/`
  - SPA: `frontend/index.html`, `frontend/src/`
  - Assets publics: `frontend/public/`
  - BFF (Node/Express): `frontend/server/`

- Backend (Python / FastAPI): `backend/`
  - Application: `backend/main.py`
  - Configuration: `backend/config.py`
  - Emails d'auth: `backend/account_api.py`
  - IA (prompts/providers): `backend/ai/`

- Docker / déploiement:
  - Dev local: `compose.yaml` + `.env`
  - Production: `compose.production.yaml` + `.env.production` (par défaut)
  - Public Bêta / VPS: `compose.public-beta.vps.yaml` + `.env.public-beta`
  - Overrides: `compose.public-beta.vps.registration-gate.override.yaml`

---

## 2) Séparation Public / Production vs Bêta

### Production (Public)
- Fichier principal: `compose.production.yaml`
- `name: documind-prod` (identifiant technique)
- Reverse-proxy attendu: Traefik (labels, routers, middlewares).
- DB, documents, lifecycle: volumes **production** (à conserver tels quels).

### Bêta (Public beta / environnement distinct)
- Fichier principal: `compose.public-beta.vps.yaml`
- Project/stack name attendu (Traefik labels): `documind-public-beta` (identifiant technique)
- Isolation: réseaux dédiés + volumes dédiés (`public_beta_*`).
- Une override optionnelle gère le "registration gate" côté VPS.

### Configuration applicative (Backend)
- `backend/config.py`:
  - `registration_mode`: `'disabled' | 'invite' | 'public'` (doit rester identique par environnement).
  - `application_profile`: `'standard' | 'beta_lite'`.

**Conclusion:** la séparation Public vs Bêta repose sur la **configuration** (env + compose) et non sur un fork du branding. C'est compatible avec l'objectif: identité graphique unique, avec un indicateur Bêta éventuellement conditionnel.

---

## 3) Branding actuel — emplacements identifiés

### Frontend — HTML, favicon, métadonnées
- `frontend/index.html`
  - `<title>`: "DocuMind AI — Votre espace documentaire"
  - `<meta name="description">`: texte marketing
  - `<meta name="theme-color">`: `#0B1120`
  - favicon: `/favicon.svg`

- `frontend/public/favicon.svg`
  - icône SVG actuelle (couleurs `#34E4D4` et `#8B5CF6`).

### Frontend — navigation, login, footer, messages
- `frontend/src/components/Layout.tsx`
  - Brand sidebar: "DocuMind AI" + icône `BookOpen`
  - Footer: "DocuMind AI" + mentions "Bêta en préparation".
  - Avatar: "DM".

- `frontend/src/pages/AISettings.tsx`, `frontend/src/components/Assistant.tsx`, `frontend/src/pages/Account.tsx`
  - Mentions textuelles "DocuMind" dans l'UX (messages, disclaimers, pages compte).

- `frontend/src/services/api.ts`
  - Message d'erreur: "Vérifiez que DocuMind est démarré."

### Backend — OpenAPI / emails / prompt IA
- `backend/main.py`
  - `FastAPI(title="DocuMind AI", ...)` (visible sur /docs, OpenAPI).

- `backend/account_api.py`
  - Sujet email: "Vérification DocuMind" / "Réinitialisation DocuMind"
  - Corps email: "Ouvrez ce lien DocuMind : ..."

- `backend/ai/providers.py`
  - Prompt SYSTEM: "Tu es l'assistant documentaire DocuMind..."

### Docs légales (attention: versioning)
- `frontend/src/legal/documents.ts`
  - Texte des CGU/mentions/politique contenant "DocuMind AI".
  - Contrainte explicite: "Published versions must be retained unchanged" → nécessite **une nouvelle version** si on veut passer à "Docnelo".

---

## 4) Couleurs et typographies — état actuel

- `frontend/src/styles.css`
  - Utilise Tailwind v4 + `@theme`:
    - `--color-night: #0B1120`
    - `--color-surface: #151F35`
    - `--color-accent: #8B5CF6`
    - `--color-mint: #34E4D4`
    - `--font-sans: "Segoe UI", Inter, ui-sans-serif, ...`

- Observation: au-delà des 4 tokens ci-dessus, de nombreuses couleurs sont **codées en dur** dans le CSS (gradients, bordures, backgrounds). Lors de l'intégration Docnelo, il faudra éviter d'introduire une seconde source de vérité.

---

## 5) Références à remplacer vs à conserver

### A. À remplacer (commercial / visuel)
- Nom affiché: "DocuMind" → "Docnelo" (UI, title HTML, footer, pages compte, emails, messages).
- Identité visuelle (logo/icônes) via le kit Docnelo.
- Prompt IA / intitulés UI: "assistant DocuMind" → "assistant Docnelo".

### B. À conserver (technique / stabilité)
Ces éléments **ne doivent pas** être renommés pour éviter une régression (sessions, volumes, DB, traefik, compat):
- Noms Docker Compose / stacks:
  - `documind-prod` (production)
  - `documind-public-beta` (bêta)
- Volumes, réseaux, DB names et users: `documind`, `public_beta_*`, etc.
- Variables et en-têtes techniques:
  - `DOCUMIND_GATEWAY_TOKEN`
  - Header `X-Documind-Gateway` (Caddy)
- Cookies / sessions:
  - Cookie `__Host-documind` (BFF) — le changer invaliderait les sessions.
- Identifiants internes:
  - Nom du package frontend: `documind-web`
  - Modules/paths Python `documind_*` (ex: `documind_extractor/`) si utilisés en import/packaging.

---

## 6) Kit de marque Docnelo — inventaire

Archive fournie: `C:/Users/Adeline/Downloads/Docnelo_Kit_Marque_v1.zip`

Contenu détecté (extraits):
- Logos:
  - `docnelo-horizontal-transparent.png` (fond clair)
  - `docnelo-horizontal-dark-transparent.png` (fond sombre)
  - `docnelo-icon-transparent.png` (icône seule)
  - `docnelo-business-*.png` (à **ne pas** intégrer dans l'app publique actuelle)

- Favicons / PWA icons:
  - `favicon.ico`
  - `docnelo-icon-32.png`, `docnelo-icon-64.png`, `docnelo-icon-192.png`, `docnelo-icon-512.png`

- Tokens:
  - `docnelo-tokens.css`

- Charte:
  - `CHARTE_GRAPHIQUE_DOCNELO.md`
  - `CHARTE_GRAPHIQUE_DOCNELO.pdf`

---

## 7) Écarts / points d'attention avant intégration

- PWA: aucune `manifest.webmanifest` n'est actuellement servie (seulement `favicon.svg`). Ajouter un manifest + icônes est faisable, mais doit être validé comme une évolution **non-fonctionnelle**.
- Legal: les documents légaux sont versionnés → un renommage DocuMind→Docnelo implique une **nouvelle version** de documents (à valider).
- Bêta indicator: aujourd'hui la mention "Bêta en préparation" est affichée partout (footer). L'objectif serait de la rendre **conditionnelle** à l'environnement, via configuration.
