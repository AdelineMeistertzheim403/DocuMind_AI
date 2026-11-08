# Docnelo Public Beta R1 — Rapport de tests

Date : 31 octobre 2026. Commit testé : 22b6428f961e98c6482a9881579361f53c114934. Toutes les opérations ont été locales, sur données synthétiques ; aucun E2E sur le VPS.

## Résultats

| Contrôle | Résultat final |
| --- | --- |
| npm ci sur contexte propre | Réussi, 297 paquets installés depuis le package-lock inchangé |
| Reconstruction de référence f3c92eb | Réussie ; cinq fichiers servis identiques aux octets historiques |
| Manifeste frontend de l'export | 75 fichiers vérifiés, zéro écart |
| React/Vitest | **52 réussis, 0 échoué**, 10 fichiers |
| BFF/Node | **50 réussis, 0 échoué, 0 ignoré** |
| Contrôles de déploiement simulés | **15 réussis, 0 échoué** : dérive API/DB, image, environnement, labels/overrides, inscription et contrat juridique refusés |
| Total des tests automatisés ci-dessus | **117 réussis, 0 échoué** |
| Build R1 final | TypeScript + Tailwind/Vite réussis, 2 248 modules, Vite environ 5 s |
| Navigateur R1 CSS actif | **20 vues réussies** : desktop 1440×1000 et mobile 390×844 |
| Comparaison navigateur de référence | Mêmes 20 vues exercées ; débordement Documents mobile préexistant mesuré à 512px |
| Recette image Web réelle | **18 assertions réussies** dans un conteneur local sans réseau externe ni volume |
| Conservation runtime | Config identique, 11 couches de base inchangées, 11 fichiers server/package comparés identiques |
| Préservation workspace principal | 1 620 empreintes préexistantes identiques ; branche branding/docnelo conservée |

Les 20 vues et 18 assertions d'image ne sont pas présentées comme des tests unitaires supplémentaires. Les preuves machine sont dans deliveries/docnelo-web-branding-r1 : provenance.json, browser-results.json, image-proof.json, container-results.json, payload/preservation-result.json et les captures navigateur.

## Commandes réellement exécutées

Dans le frontend du worktree distinct :

```powershell
npm.cmd ci --no-audit --no-fund --cache C:/Users/Adeline/Documents/DocuMind_AI/deliveries/docnelo-web-branding-r1/npm-cache
npm.cmd test
npm.cmd run build
```

Dans le dossier de preuves R1 :

```powershell
$env:R1_CHROMIUM='C:/Users/Adeline/AppData/Local/ms-playwright/chromium-1248/chrome-win64/chrome.exe'
node browser-smoke.mjs
C:/Users/Adeline/Documents/DocuMind_AI/.venv/Scripts/python.exe -B test-gates.py -q
```

Le navigateur est Chromium 156.0.8078.4, en headless. L'origine synthétique HTTPS documind-r1.test est intégralement interceptée par Playwright : statiques du dist sur disque et réponses API simulées. Aucun accès DNS/HTTP à un vrai service n'est nécessaire ; les requêtes externes ou inattendues font échouer le test. Le test effectue une connexion synthétique seulement ; aucune création/suppression de compte ou de donnée réelle.

Le conteneur de recette utilise l'image R1 réelle avec --network none, --read-only, --cap-drop ALL et no-new-privileges, sans port/volume. Son seul upstream est une API HTTP synthétique créée dans sa propre boucle locale. Aucun conteneur API ou PostgreSQL n'est lancé ou reconstruit.

Environnement de build : Windows, Node 22.12.0, npm 10.9.0, Vitest 3.2.7, Vite 6.4.4. Runtime de l'image : Node 22.23.4, linux/amd64. Les dépendances runtime sont celles de l'image de référence, pas celles réinstallées sur Windows.

## Écrans, couleurs et contrats vérifiés

Chaque format couvre connexion, inscription fermée, tableau de bord, Documents, détail de document, paramètres IA, profil, sécurité, confidentialité et informations juridiques /legal. Navigation mobile ouverte puis refermée après sélection. Aucun débordement global dans R1 ; le tableau conserve son défilement horizontal interne.

Mesures navigateur : bleu calculé #126bee, menthe #3ad8b4, bouton principal rgb(18,107,238), logo de 160px. Les images sont décodées ; captures desktop-dashboard, mobile-documents et mobile-login inspectées visuellement. Les autres violets/décorations de la référence ne sont pas tous remplacés : pas de refonte générale prétendument exhaustive.

Aucune requête ui-config, deletion-status ou download dans ces parcours. Le service API TypeScript est identique à la référence après inversion de son unique remplacement de marque dans le message d'erreur ; routes, corps, méthodes et CSRF inchangés. Workspace, types, services/account, AppRoutes et les composants documentaires sont inchangés.

La recette du BFF réel de l'image vérifie : index/titre, manifest, CSS, logo, santé, options d'inscription disabled, refus des documents anonymes, absence des trois nouveaux contrats, refus du login sans CSRF, émission du cookie CSRF, login synthétique protégé, cookie de session historique et flags HttpOnly/Secure/SameSite=Strict, accès documentaire authentifié et chemins upstream attendus.

Les liens juridiques synthétiques historiques restent ceux des options API. Aucun nouveau texte n'a été servi sous un ancien identifiant. Les versions juridiques supplémentaires du workspace ne sont pas intégrées à cette base historique.

## Échecs intermédiaires traités et limites

- La première recette a nécessité de corriger le harnais : casse hexadécimale après minification, mesure de backgroundColor, routage statique de / et deux réponses de mocks existantes. Ces corrections ne changent pas l'application pour faire passer les tests.
- Un vrai débordement mobile a été reproduit dans la référence puis corrigé dans R1 par position:relative sur le conteneur du tableau. Les recettes finales ont été relancées avec succès.
- Le décodeur JSON du test d'image respecte le BOM UTF-8 du manifest, comme le décodage navigateur ; le manifest copié reste valide et son nom a été vérifié.
- Le vérificateur de couches distingue les fichiers de contenu des réénoncés de métadonnées des répertoires /app et /etc, documentés dans le manifeste. Aucun fichier hors dist ni permission/propriété de ces parents n'est modifié.

Les scripts de précontrôle sont analysés avec la grammaire Python 3.11 et testés hors ligne ; ils n'ont pas été exécutés sur Debian. La disponibilité réelle des inscriptions, l'image actuellement active, les overrides/valeurs d'environnement effectifs et les URLs juridiques du VPS ne sont pas certifiés par les mocks. Ces preuves sont à collecter en lecture seule avant un GO de déploiement.

## Verdict

Les blocages de préparation locale sont levés : build, tests, isolement, CSS desktop/mobile et image Web concrète. **NO-GO de déploiement en l'absence de la preuve opérateur sur l'image active et la fermeture publique.** Le runbook refuse une base différente au lieu de supposer qu'un export historique représente encore le VPS.
