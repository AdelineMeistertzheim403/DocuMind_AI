# Docnelo Public Beta — Implémentation Web Branding R1

Date : 31 octobre 2026. Périmètre : préparation locale, aucun accès VPS ni Production.

## Résultat

Un candidat concret est préparé : worktree propre, commit graphique de 16 fichiers, dist construit, recette navigateur avec CSS actif et image Web distincte exportée. **Verdict de déploiement : NO-GO tant que l'opérateur n'a pas relié l'image effectivement active du VPS à la référence reproduite et confirmé la fermeture des inscriptions publiques.** Les défauts locaux de build et de mélange des changements sont levés.

- Worktree : `deliveries/docnelo-web-branding-r1/source`.
- Branche distincte : `branding/docnelo-public-beta-web-r1`.
- Commit R1 : `22b6428f961e98c6482a9881579361f53c114934`.
- Base source : `f3c92eb8ba2bb69b83a9798ebc3df8a70f48fbb2`.
- Image R1 retenue : `documind-public-beta-web:docnelo-r1-22b6428-v2`.
- ID R1 : `sha256:b8dcd1edd1c0e366f0bc605914424585a96d261b49b82e952458dfab1a911a1a`.
- Livraison transférable : `deliveries/docnelo-web-branding-r1/payload`.

## Provenance démontrée et limite restante

L'export historique public-beta-candidate-20261030T234818Z désigne l'image Web `sha256:f15855942fb4382375648841bbcdc486fd39d252e80e8fdf8eb42999d6590019`, linux/amd64. Cette image existe dans Docker Desktop local. Son label OCI est uncommitted-sprint-14-6 ; ce label seul était insuffisant.

La recherche dans l'historique a retrouvé f3c92eb comme correspondance exacte des neuf fichiers BFF exportés. Un npm ci et une reconstruction propre de ce commit ont ensuite reproduit **octet pour octet** les cinq fichiers effectivement utilisés de la référence : index.html, favicon.svg, JS principal index-C9-hkbxL.js, CSS index-CGwBGTsa.css et chunk Analysis-DH7bL-mu.js. Les 75 fichiers frontend couverts par MANIFEST.sha256 de l'export ont également été vérifiés sans écart. L'inspection d'un conteneur local jamais démarré confirme les neuf fichiers server et les deux package*.json de l'image, identiques aux sources R1 conservées.

La provenance source → image **historique** est donc désormais étayée par reproduction, pas par supposition depuis HEAD. L'ID de l'image **active sur le VPS aujourd'hui** reste inconnu : aucun inspect distant n'a été exécuté. S'il diffère de f1585594…, ce candidat ne doit pas être déployé ; il faut reproduire cette autre base avant rebase et nouveaux tests. Aucune valeur d'ID active n'a été inventée.

## Isolation et préservation du workspace

Le worktree principal reste sur branding/docnelo, à son HEAD initial. Un relevé SHA-256 de **1 620 fichiers préexistants** a été établi avant préparation puis vérifié : aucun contenu supprimé ou modifié. Les anciens rapports, développements Beta Lite, outils V5/V5.1, exports et fichiers mixtes du workspace restent intacts. Les modifications Git nécessaires sont limitées à la création d'un worktree/branche/commit distincts ; aucun stash, reset ou nettoyage du workspace principal.

La différence f3c92eb → R1 porte sur exactement 16 chemins frontend. Aucun backend, migration, .env, Compose, package-lock, runtime BFF, types API, services/account, Workspace, DocumentTable ou DocumentDetail n'est modifié. Les scripts de contrôle et preuves de livraison sont hors du commit graphique, dans le dossier R1 ; ils ne sont pas injectés dans l'image.

## Changements effectués uniquement dans R1

- index, favicon/PNG et manifest Docnelo ; sept assets nécessaires seulement, sans variante Business.
- BrandMark, logo 160px de large avec ratio préservé, alt Docnelo et badge **Public Beta statique** sur connexion et navigation.
- Noms/initiales dans Layout, Account, Assistant, AISettings et unique message d'erreur de services/api. Les fichiers mixtes ont été reconstruits à partir de la base historique, sans reprendre leurs nouvelles fonctions.
- Import des tokens résolu par `../public/brand/docnelo/docnelo-tokens.css`. Tailwind est conservé. Bleu principal et menthe appliqués ; survol bleu corrigé. Les autres éléments de style historiques ne font pas l'objet d'une refonte complète.
- Correction strictement CSS du contexte de positionnement de `.table-scroll` : `position:relative`. La référence avait un débordement document de 512px pour une fenêtre de 390px, dû à un élément sr-only du tableau ; R1 le confine au tableau défilant. Aucune ligne/document, action ou route n'est ajoutée.

Aucun /bff/ui-config ni variable UI_ENVIRONMENT_LABEL. Aucun parcours Beta Lite, suppression différée, statut de suppression ou téléchargement nouveau. Les cookies __Host-documind et __Host-documind-csrf, headers, routes, CSRF et sessions restent ceux de la référence.

## Pages juridiques et contenu historique

Le dist de référence reproduit expose /legal et des liens juridiques configurés par l'API ; il ne contient pas les nouvelles routes locales /cgu, /mentions-legales et /confidentialite ajoutées ultérieurement dans le workspace. R1 conserve exactement cette table de routes. Les fichiers documents.ts/Legal.tsx du workspace et leurs identifiants restent intacts, sans intégration ni réécriture dans R1.

Les URLs/versions juridiques retournées par l'API ne sont pas changées. La recette utilise des liens **synthétiques** versionnés et vérifie leur conservation. Leur correspondance aux valeurs du VPS est une condition opérateur, vérifiée avant/après par les scripts livrés. Si l'image active sert une autre génération de pages juridiques, le contrôle d'ID impose l'arrêt plutôt que leur suppression accidentelle.

Emails, titre OpenAPI, textes métiers historiques de stockage « local » et autres contenus non graphiques restent ceux de la référence. R1 ne prétend pas finaliser le rebranding de l'API ni corriger ces contenus dans ce lot.

## Image immuable et différence réellement vérifiée

L'image finale hérite des **11 couches** de la référence, avec deux couches de remplacement de /app/dist. Configuration d'image entièrement identique à la base : ENV, USER node, CMD, ports et healthcheck compris. Aucun npm install runtime ; node_modules et le serveur sont hérités sans modification.

Tous les fichiers réguliers ajoutés/modifiés et le whiteout de suppression sont confinés à /app/dist. Docker réénonce aussi les répertoires parents /app et /etc : mode/UID/GID identiques, **mtime différent**. Cette nuance figure dans image-proof.json et RELEASE.json ; on ne revendique pas une identité de chaque métadonnée de filesystem hors dist. Aucun fichier de configuration sous /etc n'est modifié. L'usage d'un tmpfs /etc pendant le build est éphémère, sans volume applicatif et sans effet sur le runtime.

Une première image exploratoire locale e153947d… n'est pas livrée ; seule l'image v2 b8dcd1ed… et son archive vérifiée sont retenues. Aucun ancien tag ni conteneur applicatif n'a été remplacé. Le nouveau runtime a été exercé dans un conteneur local jetable, sans réseau externe, port publié ou volume, avec une API simulée en boucle locale.

## Livrables et étape nécessaire

- [Tests R1](DOCNELO_PUBLIC_BETA_BRANDING_R1_TEST_REPORT.md).
- [Manifeste de release](DOCNELO_PUBLIC_BETA_BRANDING_R1_RELEASE_MANIFEST.md).
- [Runbook opérateur](DOCNELO_PUBLIC_BETA_BRANDING_R1_DEPLOYMENT_RUNBOOK.md).
- [Inventaire exact](DOCNELO_PUBLIC_BETA_BRANDING_R1_FILE_INVENTORY.md).

L'opérateur doit maintenant exécuter uniquement le collecteur de précontrôle en lecture seule et fournir/archiver sa preuve. Aucun déploiement, reconstruction API/PostgreSQL, migration, opération Restic, modification de latch ou fichier .env n'a été effectué. La branche R1 propre et l'image sont prêtes pour cette revue ; elles ne sont pas autorisées à remplacer une base VPS non confirmée.
