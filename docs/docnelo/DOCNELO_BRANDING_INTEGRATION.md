# Docnelo — Branding Integration Plan

Date (locale): 2026-10-31 (Europe/Paris)
Branche de travail: `branding/docnelo`

## Objectif
Intégrer l’identité **Docnelo** dans l’application (environnements Public et Bêta) **sans changer**:
- les règles d’inscription (et notamment la fermeture des inscriptions en Public),
- les données, DB, volumes, chemins persistants,
- les secrets / variables existantes,
- les identifiants techniques (services Docker, cookies, headers, DB name/user, etc.).

## 1) Organisation des assets

### Assets utilisés par l’application
Les assets du kit Docnelo sont copiés dans:
- `frontend/public/brand/docnelo/`

Fichiers (kit v1):
- Logos: `docnelo-horizontal-dark-transparent.png`, `docnelo-horizontal-transparent.png`, `docnelo-icon-transparent.png`
- Icônes: `favicon.ico`, `docnelo-icon-32.png`, `docnelo-icon-64.png`, `docnelo-icon-192.png`, `docnelo-icon-512.png`
- Tokens (non appliqués automatiquement): `docnelo-tokens.css`
- Logos Business (stockés mais **non utilisés**): `docnelo-business-*.png`

### Docs du kit
La charte et l’aperçu sont copiés dans:
- `docs/docnelo/brand-kit/`

## 2) Logos effectivement utilisés

- Sidebar / navigation: `frontend/src/components/Brand.tsx` utilise `docnelo-horizontal-dark-transparent.png`.
- PWA/manifest + icônes navigateur: `frontend/public/manifest.webmanifest` et `frontend/index.html` pointent sur les PNG/ICO du kit.

> Les logos "Docnelo Business" sont présents dans `frontend/public/brand/docnelo/` uniquement pour conservation, mais ne sont référencés nulle part.

## 3) Indicateur “Bêta” (optionnel, configuré)

Objectif: garder un indicateur discret uniquement en environnement bêta, **par configuration**, sans dupliquer le branding.

- BFF ajoute un endpoint non-auth: `GET /bff/ui-config` renvoyant:
  - `{ environment_label: "" | "Bêta" | "..." }`
- Variable d’environnement (optionnelle) côté BFF:
  - `UI_ENVIRONMENT_LABEL=Bêta` (à définir uniquement en bêta)

Frontend:
- `frontend/src/components/Layout.tsx` affiche le badge et le footer “environnement de test” uniquement si `environment_label` est défini.

## 4) Tokens / couleurs

- Les tokens Docnelo du kit (`docnelo-tokens.css`) sont importés comme **référence**, mais ne remplacent pas les tokens UI existants.
- Raison: l’UI actuelle est construite autour d’un accent violet (`--color-accent: #8B5CF6`) et d’un mint (`--color-mint: #34E4D4`). Une retouche globale (violet → bleu Docnelo) serait une refonte plus large.

> L’intégration vise d’abord le nom + logo + favicon/manifest, en minimisant les risques de régression.

## 5) Renommage contrôlé (remplacements réalisés)

Remplacements **visibles** "DocuMind" → "Docnelo" (sans toucher les identifiants techniques):
- HTML title/meta + favicon/manifest: `frontend/index.html`
- Navigation + footer + avatar initials: `frontend/src/components/Layout.tsx`
- Pages compte: `frontend/src/pages/Account.tsx`
- Pages IA/assistant: `frontend/src/pages/AISettings.tsx`, `frontend/src/components/Assistant.tsx`
- Messages UX: `frontend/src/services/api.ts`
- Emails: `backend/account_api.py`
- OpenAPI title: `backend/main.py`
- Prompt IA: `backend/ai/providers.py`
- Pages légales (texte affiché) **sans changer le domaine/URL**: `frontend/src/legal/documents.ts`

## 6) Identifiants techniques conservés volontairement

- Compose project / services / labels / volumes:
  - `documind-prod`, `documind-public-beta`, `public_beta_*`
- Secrets/vars techniques:
  - `DOCUMIND_GATEWAY_TOKEN`
- Cookie/session:
  - `__Host-documind` (BFF)
- Header gateway:
  - `X-Documind-Gateway` (Caddy)
- Noms internes / packaging:
  - `frontend/package.json` name: `documind-web`
  - DB defaults: `documind` (backend config)

## 7) Fichiers modifiés (branding)

- `frontend/index.html`
- `frontend/public/manifest.webmanifest`
- `frontend/public/brand/docnelo/*`
- `frontend/src/components/Brand.tsx`
- `frontend/src/components/Layout.tsx`
- `frontend/src/pages/Account.tsx`
- `frontend/src/pages/AISettings.tsx`
- `frontend/src/components/Assistant.tsx`
- `frontend/src/services/api.ts`
- `frontend/src/types/api.ts`
- `frontend/server/app.mjs`
- `frontend/src/styles.css`
- `backend/main.py`
- `backend/account_api.py`
- `backend/ai/providers.py`
- `frontend/src/legal/documents.ts`
