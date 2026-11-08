# Docnelo — Branding Test Report

Date (locale): 2026-10-31 (Europe/Paris)
Branche: `branding/docnelo`

## Résumé
- Frontend: ✅ PASS
- Backend (pytest): ⚠️ FAIL (échecs/erreurs déjà présents; cause principale identifiée)

---

## 1) Frontend

### Commande
```powershell
cd frontend
npm test
```

### Résultat
- `68 passed (68)`
- BFF node tests intégrés: `55 pass` (dans le même `npm test`)

### Notes
- Le premier essai en mode sandbox échouait (scan esbuild “Access is denied”). Les tests ont été exécutés en mode non-sandboxé pour refléter un run réel.

---

## 2) Backend (pytest)

### Commande complète
```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

### Résultat
- `1134 passed, 313 skipped, 15 failed, 71 errors` (durée ~24 minutes)

### Cause principale (erreur #1)
Le premier échec (avec `--maxfail=1`) est un **error de teardown** lié au shutdown du worker de synthèse:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --maxfail=1
```

Erreur racine:
- `RuntimeError: cannot join thread before it is started`
- Point de déclenchement: `backend/ai/long_summary.py` → `LongSummaryWorker.stop()` (join sur thread non démarré)

Impact:
- Provoque de nombreuses erreurs de teardown sur des suites (notamment IA/RAG/long_summary).
- Non lié aux changements de branding Docnelo (aucune logique de thread/worker modifiée dans cette mission).

---

## 3) Vérifications manuelles recommandées (post-déploiement bêta)
- Charger l’UI et confirmer:
  - Logo Docnelo visible (sidebar + pages compte)
  - Favicon / manifest
  - Absence de branding “Business”
  - Badge “Bêta” uniquement si `UI_ENVIRONMENT_LABEL=Bêta`
- Auth, upload, lecture, analyse
- Confirmer la fermeture des inscriptions en Public (prod)
