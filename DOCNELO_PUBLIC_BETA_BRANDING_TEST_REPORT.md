# Rapport de tests — Rebranding Public Beta

Date : 31 octobre 2026. Branche branding/docnelo ; HEAD 1bc1a4a5bb49395acabdce5e7604d1a6b97dea61 avec changements non commités. Tests des sources courantes, **pas d'une future sélection de changements graphiques isolés**. Aucun accès VPS/Production, aucune DB utilisateur utilisée.

## Résultats réellement obtenus

| Contrôle | Résultat | Portée |
| --- | --- | --- |
| npm.cmd test — Vitest | 12 fichiers, 68 tests réussis, 0 échoué | React/services avec mocks, jsdom |
| npm.cmd test — Node BFF | 55 tests réussis, 0 échoué, 0 ignoré | Serveurs locaux éphémères et upstreams simulés |
| Total tests | **123 réussis, 0 échoué** | Aucune preuve de compatibilité contre l'API réellement active |
| npm.cmd run build — TypeScript | étape tsc -b réussie | Types courants cohérents |
| npm.cmd run build — Vite/Tailwind | **échec**, code retour 1, après 3 modules transformés | Import /brand/docnelo/docnelo-tokens.css introuvable |
| Assets | 9 PNG avec canal alpha, dimensions lues ; ICO 16/32/48/64 | Présence et métadonnées techniques contrôlées |
| Inspection visuelle | Logo horizontal sombre et PNG 32 ouverts | Pas de rendu intégré ni de capture navigateur |
| Références de marque | 3 lignes DocuMind dans les sources UI hors tests, toutes des URLs conservées | Hors messages d'une API réelle et contenus externes |
| Alembic | Aucun fichier suivi modifié sous migrations | Contrôle statique, aucune commande DB exécutée |
| Docker/image/recette Debian | Non exécutés | Aucune image construite, tirée ou publiée |
| E2E Playwright existants | Non exécutés | Fixtures qui créent/suppriment des comptes et données via un docker compose par défaut ; impropres à un contrôle aveugle sur la bêta active |

Commandes exécutées localement depuis frontend :

```powershell
node --version
npm.cmd --version
npm.cmd test
npm.cmd run build
```

Environnement : Node v22.12.0, npm 10.9.0, Vitest 3.2.7, Vite 6.4.4, dépendances node_modules existantes. Vitest : 8,74 s ; Node : environ 1,03 s. Aucun npm ci ni changement du lockfile n'a été effectué. Les images utilisent une base Node 22 Alpine figée par digest, pas cet environnement Windows.

Les premières tentatives tests/build ont été bloquées par les droits de lecture d'esbuild sur les répertoires parents dans le sandbox. Elles ont été réexécutées localement avec l'escalade d'exécution autorisée : les tests passent, et l'échec CSS réel demeure. Ce problème de build n'est donc pas imputable au seul sandbox.

## Régression bloquante de build

Dans frontend/src/styles.css :

```css
@import "tailwindcss";
@import "/brand/docnelo/docnelo-tokens.css";
```

Tailwind tente de résoudre le second import depuis src et échoue. Diagnostic constaté : Can't resolve '/brand/docnelo/docnelo-tokens.css'. Le fichier existe bien dans public/brand/docnelo ; sa présence ne suffit pas pour cet import de compilation. La configuration Vitest comporte css:false, ce qui explique pourquoi les 68 tests React ne détectent pas ce défaut.

Correction proposée pour le futur lot isolé : résoudre ce fichier comme une dépendance CSS de compilation par un chemin relatif vérifié, ou placer les tokens dans src/styles et les importer relativement. Garder une seule définition canonique ; ne pas masquer l'erreur par la désactivation de Tailwind ou du build CSS. Aucun de ces changements n'a été appliqué par cet audit. Refaire npm ci, tests et build sur le contexte propre, puis vérifier les variables CSS effectivement calculées dans le navigateur.

## Ce que couvrent les tests passants

- Parcours documentaire et navigation simulée, analyse, confirmation/demande/statuts de suppression, recherche et affichage de résultats.
- Compte, Public Beta, Beta Lite, pages juridiques, paramètres IA, consentement, assistants, graphiques et preuve d'inscription WebCrypto.
- BFF : HTTPS/Host, authentification, CSRF, cookies, bornes des réponses, upload admission/capacité/timeouts, audit de sécurité, santé et réponses Lite simulées.

Ils couvrent les évolutions fonctionnelles de l'arbre courant aussi bien que des libellés graphiques. Ils ne donnent pas permission de les embarquer dans une release de marque. Les appels ui-config sont mockés dans les tests d'application ; cela ne démontre pas que le BFF actif possède cet endpoint. Les pages juridiques passent sans test d'identité des octets des anciennes versions.

## Recette requise avant autorisation de déploiement

1. Résoudre la provenance source/image du Web actif ; geler un commit contenant uniquement les différences autorisées. Refaire les tests sur ce commit, avec BFF identique à l'actif et mêmes package-lock/dépendances runtime.
2. Build production réussi dans l'étage Node Alpine figé ; artefacts dist ne contenant ni Beta Lite ajouté ni nouveaux appels ui-config/deletion-status/download au-delà du contrat déjà actif. Un grep ne remplace pas une comparaison de contrats et la recette d'intégration.
3. Recette navigateur sur environnement jetable, avec CSS actif : 1440px et 390px, login et récupération, navigation, pages principales, logo/favicon/manifest, messages, focus et absence de débordement. Contrôler les polices effectivement chargées et les contrastes dans ce contexte. Aucun CDN de police ajouté.
4. Comparer les anciennes versions juridiques à leur référence ; une nouvelle version ne doit jamais remplacer silencieusement le contenu sous le même identifiant. Maintenir les URLs et conditions d'admission configurées.
5. Sur une API isolée de version identique à l'actif : session existante, lecture/consultation, opérations documentaires avec données synthétiques, refus d'accès anonyme, CSRF et inscriptions fermées selon la configuration actuelle. Aucune fixture E2E de création/suppression contre le VPS réel.
6. Vérifier l'image finale : même BFF, mêmes dépendances, USER/ENV/CMD/healthcheck que la base active, seuls fichiers statiques et métadonnées d'image autorisés différents. Test de rollback sur recette.

Verdict de cette session : **tests unitaires/BFF passants, build bloquant ; recette graphique et déploiement non autorisés**. Les commandes proposées dans le plan restent conditionnelles à ces validations ; aucun succès Docker, navigateur, email réel ou VPS n'est revendiqué.
