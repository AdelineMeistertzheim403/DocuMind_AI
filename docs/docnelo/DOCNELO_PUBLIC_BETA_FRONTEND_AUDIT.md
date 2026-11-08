# Docnelo — Public Beta — Frontend Audit (rebranding DocuMind → Docnelo)

Date: 2026-10-31
Scope: **frontend uniquement** (Public Beta). Aucun déploiement.

## 1) Où “DocuMind” apparaît encore

### 1.1 Références techniques à **conserver** (risque de régression si renommage)
Ces références ne sont pas du branding visible, et sont liées à la compatibilité / sécurité :

- **Cookies / sessions / CSRF**: `__Host-documind`, `__Host-documind-csrf` (BFF)
  - Implémentation: `frontend/server/app.mjs`
  - Tests: `frontend/server/app.test.mjs`, `frontend/server/upload-admission.test.mjs`, `frontend/server/security-audit.test.mjs`
- **Headers de sécurité/gateway**: `x-documind-gateway`, `x-documind-secure`, `x-documind-client-ip`
  - Implémentation: `frontend/server/app.mjs`
- **Nom NPM**: `documind-web` (package)
  - `frontend/package.json`, `frontend/package-lock.json`

➡️ Recommandation: conserver ces identifiants tant que le backend/BFF et les clients existants les attendent.

### 1.2 Références visibles / semi-visibles à traiter au cas par cas
- **URLs du domaine bêta**: `https://documind.adelinemeistertzheim.fr/...`
  - Présentes dans `frontend/src/legal/documents.ts`
  - À **conserver** tant que le domaine bêta n’est pas changé/validé.

## 2) Branding Docnelo déjà intégré (constaté)

### 2.1 Métadonnées / favicon / PWA
- `frontend/index.html`: titre + favicons Docnelo.
- `frontend/public/manifest.webmanifest`: `name`/`short_name` Docnelo + icônes.

### 2.2 Assets Docnelo présents dans le repo
Dossier: `frontend/public/brand/docnelo/`

- Logos
  - `docnelo-horizontal-transparent.png`
  - `docnelo-horizontal-dark-transparent.png`
  - `docnelo-icon-transparent.png`
- Favicons / PWA
  - `favicon.ico`
  - `docnelo-icon-32.png`, `docnelo-icon-64.png`, `docnelo-icon-192.png`, `docnelo-icon-512.png`
- **Docnelo Business** (à ne pas utiliser dans Public Beta)
  - `docnelo-business-transparent.png`
  - `docnelo-business-dark-transparent.png`

### 2.3 Composants UI
- `frontend/src/components/Brand.tsx`: utilise `docnelo-horizontal-dark-transparent.png`.

## 3) Système de styles actuel

- Styles principaux: `frontend/src/styles.css`
  - CSS “app” custom + quelques tokens (Tailwind v4 via `@import "tailwindcss";` + `@theme`).
  - Beaucoup de couleurs étaient historiquement codées en dur (accent violet #8B5CF6, mint #34E4D4).

## 4) Charte Docnelo (référence)
Palette cible (donnée):
- Marine `#0B1D3B`
- Bleu principal `#126BEE`
- Azur `#5BAAF5`
- Menthe `#3AD8B4`
- Fond clair `#F7FAFD`

Source locale (tokens Docnelo): `frontend/public/brand/docnelo/docnelo-tokens.css`

## 5) Écart principal identifié
- Le frontend est **dark-first** aujourd’hui (pas de commutateur de thème dans le code).
- La “signature” visuelle la plus marquante était l’accent violet → à remplacer par l’accent Docnelo (bleu).

## 6) Plan recommandé (incrémental, sans refonte globale)
1. Centraliser l’usage de la palette Docnelo via variables CSS.
2. Remplacer en priorité:
   - boutons primaires,
   - focus states,
   - navigation active,
   - éléments “brand” (logo/mark),
   - notices clés.
3. Phase ultérieure (sur validation) : migration des multiples teintes “violet-alpha” restantes vers des variantes d’accent Docnelo.

## 7) Fichiers candidats à modification (si on pousse l’harmonisation)
- `frontend/src/styles.css` (tokens + remplacements)
- `frontend/src/components/Brand.tsx` (si besoin de gérer clair/sombre)
- `frontend/src/legal/documents.ts` (uniquement changements de nom, **sans** modifier les versions déjà publiées)

