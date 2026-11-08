# Docnelo Public Beta R2 — Tests et compatibilité

Date : 31 octobre 2026. Commit graphique b046e5d8256d45b65bf575a8a006351616b69fc9 ; référence reconstituée fa02986ae0a92e02e6bb4b576171ce1deb18d5f2 ; image active de référence 9301710690ea… . Aucun test sur VPS ni donnée réelle.

## Résultats finaux

| Vérification | Résultat |
| --- | --- |
| Archive d'entrée | SHA-256 conforme avant utilisation ; configuration interne Image ID 930171… et linux/amd64 conformes |
| npm ci sur contexte propre | Réussi, 297 paquets depuis le lockfile inchangé |
| Reconstruction des statiques de référence | **5/5 fichiers identiques aux octets actifs** |
| Correspondance BFF/package à Git | **9 fichiers server + 2 package*.json identiques** |
| React/Vitest | **64 réussis, 0 échoué**, dont 12 tests juridiques |
| BFF/Node | **50 réussis, 0 échoué, 0 ignoré** |
| Précontrôles/état Docker simulés | **20 réussis, 0 échoué** |
| Total des tests automatisés précédents | **134 réussis, 0 échoué** |
| Build R2 | TypeScript et Tailwind/Vite réussis ; 2 250 modules, environ 5,68 s de Vite |
| Navigateur R2 CSS actif | **36 vues réussies**, desktop 1440×1000 et mobile 390×844 |
| Comparaison avec la référence active | Mêmes 36 vues exercées ; appels BFF observés identiques |
| Contenus juridiques rendus | **12 vues historiques/fallback de version inconnue identiques par SHA-256 du texte** |
| Image R2 réelle, conteneur jetable | **24 assertions réussies** |
| Image de référence réelle, conteneur jetable | **22 assertions réussies** sur les mêmes contrats, sans nouveaux assets graphiques |
| Statique dans les couches de l'image R2 | **13 fichiers conformes au build** |
| Image/runtime | Configuration identique, 9 couches de base conservées, aucun fichier régulier hors dist modifié |

Les vues et assertions d'image ne sont pas additionnées artificiellement aux 134 tests. Les preuves machine sont conservées dans le dossier R2 ; seules les preuves sans contenu extrait sensible sont reprises dans le payload privé.

## Exécution locale

Depuis le frontend du worktree R2 :

```powershell
npm.cmd ci --no-audit --no-fund --cache C:/Users/Adeline/Documents/DocuMind_AI/deliveries/docnelo-web-branding-r2/npm-cache
npm.cmd test
npm.cmd run build
```

Depuis le dossier privé R2 :

```powershell
$env:R2_CHROMIUM='C:/Users/Adeline/AppData/Local/ms-playwright/chromium-1248/chrome-win64/chrome.exe'
node browser-smoke.mjs
C:/Users/Adeline/Documents/DocuMind_AI/.venv/Scripts/python.exe -B test-gates.py -q
```

Environnement de build : Windows, Node 22.12.0, npm 10.9.0, Vite 6.4.4, Vitest 3.2.7. Runtime réel inventorié dans l'image : Linux amd64, Node 22.23.4, 118 paquets installés. Ces dépendances ne sont pas réinstallées dans l'image dérivée.

Un premier essai depuis c420808… seul donnait un JavaScript différent malgré un CSS identique. Il a été rejeté. Le frontend de 1bc1a4a… a ensuite reproduit les cinq artefacts actifs ; le BFF a été figé séparément à sa version exacte. Le compte-rendu ne présente donc pas une simple correspondance partielle comme preuve de provenance.

## Recette navigateur avec CSS actif

Chromium 156.0.8078.4 headless ; origine synthétique HTTPS documind-r2.test. Toutes les requêtes sont interceptées : statiques réellement construits et API simulée, sans DNS/service réel. Toute requête externe ou inattendue échoue. Les comptes/documents utilisés sont synthétiques et ne proviennent pas du VPS.

Chaque format couvre connexion, inscription fermée, tableau de bord, documents, détail, paramètres IA, profil, sécurité, confidentialité du compte, informations /legal, bibliothèque, comparaison et les six vues juridiques suivantes : mentions, confidentialité, CGU courantes, deux versions explicites et version inconnue. Le menu mobile est exercé. Les liens de téléchargement existants sont présents dans la liste et le détail, sans ajout ou suppression.

Mesures R2 : bleu calculé #126bee, menthe #3ad8b4, bouton principal rgb(18,107,238), logo de 160px. Aucun débordement global dans R2 ; le tableau défile intérieurement. La référence reproduit son débordement Documents mobile préexistant (483px pour 390px). La correction CSS déjà validée en R1 est reprise.

Les cinq fichiers juridiques/routage et les deux composants de liens documentaires sont identiques à la référence. Les hashes du texte rendu des versions historiques concordent sur les deux formats ; les avertissements de brouillon et les identifiants ne changent pas. Aucun texte légal nouveau n'est substitué silencieusement sous un ancien identifiant.

## Contrats BFF et image réelle

Les recettes d'image utilisent --network none, --read-only, --cap-drop ALL et no-new-privileges, sans port publié ou volume. L'upstream est créé dans le même conteneur, en boucle locale. Elles vérifient index, CSS, manifest et logo R2, six routes juridiques SPA, santé, options d'inscription simulées disabled, refus documentaire anonyme, CSRF et cookies historiques, login protégé et accès documentaire authentifié.

ui-config et deletion-status restent absents. Le téléchargement BFF est **404 sur la référence et R2**, alors que le frontend actif possède des liens : comportement antérieur confirmé par les deux images. Aucun correctif métier ou nouvelle route n'a été glissé dans le rebranding. Cet écart n'est pas présenté comme un téléchargement fonctionnel.

Les méthodes et chemins BFF observés par le navigateur sont identiques avant/après. Le fichier services/api est identique après inversion de son seul message de marque ; services/account, AppRoutes, types et Workspace ne changent pas. Les neuf fichiers BFF et les dépendances de l'image sont hérités sans modification.

Les contrôles opérateur testés hors ligne refusent : mauvaise image/provenance, changement API, label/route Web, environnement, override absent, redémarrage DB/API, changement de volume/paramètres Docker, santé incorrecte, ouverture publique ou changement de version/URL juridique. Un fingerprint compare les paramètres effectifs sans enregistrer les valeurs Env : HostConfig, paramètres Config, labels non variables, identités de projet/service, montages et réseaux. Seuls les éléments nécessairement alloués à la recréation sont exclus.

## Limites et verdict

Les inscriptions réelles n'ont pas été sondées et aucune donnée d'exploitation n'a été créée/supprimée. Les fixtures E2E Docker du dépôt n'ont pas été exécutées contre le VPS. Les paramètres effectifs de ses conteneurs/overrides et leur éventuelle dérive depuis l'export doivent être vérifiés par l'opérateur. Les scripts sont analysés avec la grammaire Python 3.11, mais pas exécutés à distance.

Les réénoncés de répertoires /app et /etc dans les couches changent leurs mtime de build, pas leurs permissions/propriétaires ni leurs fichiers hors dist. Ces métadonnées sont conservées dans image-proof.json ; l'identité complète de tous les timestamps n'est pas revendiquée.

**GO local pour le lot graphique R2**, sur la référence exacte démontrée, avec l'incohérence de téléchargement préexistante explicitement conservée. Ce verdict ne vaut ni GO VPS sans précontrôles ni autorisation de déploiement ou de publication.
