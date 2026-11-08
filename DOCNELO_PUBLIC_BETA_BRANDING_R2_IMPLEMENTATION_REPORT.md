# Docnelo Public Beta — Implémentation Web Branding R2

Date : 31 octobre 2026. **Verdict : GO local pour R2**, sans autorisation de déploiement. L'image est construite et testée localement depuis la référence réelle fournie par l'opérateur. Aucun accès VPS, push registre ou changement de Production.

## Identités retenues

| Élément | Identité |
| --- | --- |
| Archive d'entrée privée | deliveries/docnelo-web-branding-r2/web-active.tar |
| SHA-256 vérifié avant utilisation | 321ea808f4dc246291adf484c9ee25245470545dec0a7774d4404f052100792b |
| Image réellement exportée | sha256:9301710690ea35cd3b81db3acf48deb38638c6e7fa3c29dac77756d60025f487 |
| Plateforme | linux/amd64 |
| Worktree R2 | deliveries/docnelo-web-branding-r2/source |
| Branche R2 | branding/docnelo-public-beta-web-r2 |
| Référence source reconstituée | fa02986ae0a92e02e6bb4b576171ce1deb18d5f2 |
| Commit graphique R2 | b046e5d8256d45b65bf575a8a006351616b69fc9 |
| Image R2 locale | documind-public-beta-frontend:docnelo-r2-b046e5d8256d |
| Image ID R2 | sha256:ebdbc7fba1c61c03349088ca093470c78eec9dd91c5e2aa92ab1d8c0db5be362 |

R1 reste sur sa branche/son worktree et son commit 22b6428… ; ses rapports et artefacts ne sont pas réécrits. Le workspace principal reste sur branding/docnelo.

## Vérification de l'archive et chargement sans remplacement

L'archive d'entrée de 257 984 000 octets a d'abord été hachée ; l'empreinte correspond exactement à celle fournie. Le hash du JSON de configuration interne correspond également à l'Image ID 930171… et la plateforme à linux/amd64. L'image était absente de Docker Desktop local.

Une copie **locale privée** de l'archive a été créée en retirant RepoTags et le fichier repositories. Elle a été chargée par ID, sans restaurer le tag d'origine documind-public-beta-frontend:2026-10-31 et donc sans remplacer un tag existant. L'archive originale est inchangée. Un alias de base neuf r2-base-9301710690ea a ensuite été créé avec contrôle de conflit. Tous les appels Docker utilisent explicitement le contexte desktop-linux, jamais le VPS.

Les archives, extractions, caches et preuves privées R2 sont protégés d'un ajout Git accidentel par une règle ajoutée à .git/info/exclude, sans suppression des règles existantes ni modification de .gitignore. Aucun fichier extrait brut, archive Docker ou inventaire potentiellement sensible n'a été commité ou publié. Seules des sources déjà présentes dans Git et les assets graphiques approuvés entrent dans les commits R2.

## Provenance démontrée par reconstruction

L'image active n'a pas de label OCI de commit. Le commit CI/check-out original ne peut donc pas être affirmé à partir de cette métadonnée absente ; il reste explicitement inconnu.

La provenance **de contenu** a en revanche été démontrée :

1. La reconstruction du seul commit c420808… reproduisait le CSS mais pas les deux chunks JavaScript actifs. Elle a été rejetée comme référence frontend insuffisante.
2. Les entrées frontend de 1bc1a4a5bb49395acabdce5e7604d1a6b97dea61 reproduisent **octet pour octet les cinq fichiers dist** extraits de 930171… : index.html, favicon.svg, index-C53-zXRw.js, index-DWUazs-2.css et Analysis-CHoTqwnH.js. Ce n'est pas une simple recherche de chaînes ou une confiance dans un tag.
3. Les neuf fichiers server de l'image sont identiques à c420808… ; les deux package*.json sont également identiques aux entrées Git conservées. Le BFF plus récent de HEAD ne correspond pas au runtime actif.
4. Le commit de référence fa02986… assemble ces entrées Git exactes : frontend reproductible de 1bc1a4a… et BFF de c420808…. Il ne prétend pas être le commit de construction original ; il fige la correspondance vérifiée pour l'audit et les tests. Les tests BFF utilisent ce runtime exact.

Le critère de provenance n'est donc pas laissé en supposition : source canonique figée, reconstruction et comparaison complète des statiques actifs, BFF/package identiques. provenance.json contient les SHA-256 et les révisions d'entrée distinctes. Si les artefacts n'avaient pas correspondu, le verdict aurait été NO-GO.

## Différences de la référence réelle face à R1

- Le BFF et les deux manifests NPM sont identiques à ceux de la base historique R1. Les images complètes sont néanmoins différentes : 930171… a neuf couches de base, contre onze pour f1585594… ; leurs identités ne sont pas interchangeables.
- L'interface active possède les routes /mentions-legales, /confidentialite, /cgu et /cgu/versions/:version, les archives juridiques et leur navigation. Les informations de stockage serveur et certains avertissements de confidentialité/suppression ont aussi évolué. R2 les conserve.
- L'interface active affiche des liens de téléchargement dans la liste et le détail documentaire. **Son BFF ne fournit pas cette route : HTTP 404 sur la référence et R2.** Cette incohérence préexistante est documentée, conservée et testée ; elle n'est ni réparée par ajout de contrat, ni masquée par suppression du lien dans un lot graphique.
- Aucun ui-config, parcours frontend Beta Lite ou nouveau contrat deletion-status n'est introduit. Les développements correspondants du workspace principal restent exclus.

## Changements graphiques R2 et fonctions conservées

Le diff fa02986… → b046e5d… contient exactement **16 chemins frontend**. Les nouveaux assets/index/manifest/BrandMark sont repris de R1. Les fichiers mixtes Account, Layout et services/api sont adaptés depuis la référence réelle : seules les occurrences de marque, le logo, les initiales et le badge statique sont modifiés.

L'import CSS reste résolu relativement à public/brand/docnelo/docnelo-tokens.css, sans désactiver Tailwind. Les styles graphiques R1 sont réutilisés après vérification que leur fichier source de départ était identique à celui de la référence active. La correction CSS de confinement du tableau mobile est conservée ; aucun comportement métier n'est ajouté.

Le footer conserve **LegalNavigation**, l'indication IA indisponible et les informations de stockage serveur. AppRoutes, Workspace, services/account, les types API et les deux composants portant les liens de téléchargement sont inchangés. Le service API TypeScript est identique à la référence après inversion de son unique remplacement DocuMind → Docnelo dans le message d'erreur.

Les cinq fichiers juridiques/routage protégés sont inchangés, notamment documents.ts, Legal.tsx et App.tsx. Les versions beta-2026-10-v1 et beta-2026-10-26-draft-1, leurs textes, leurs avertissements et leurs liens ne sont pas réécrits. DocuMind reste intentionnellement visible dans des textes historiques et le domaine technique. Les douze vues juridiques desktop/mobile ont des empreintes de texte identiques entre référence et R2.

## Runtime et nouvelle image

Le runtime actif a été inventorié en lecture seule dans un conteneur local hors réseau : Node v22.23.4, 118 paquets installés, manifests/package-lock conservés. runtime-summary.json contient les versions directes, noms de routes, cookies, headers et paramètres d'image non secrets ; l'inventaire complet extrait reste privé.

La nouvelle image hérite des **neuf couches de 930171…** et ajoute deux couches. Aucun npm install runtime, nouveau serveur BFF ou fichier de configuration n'est copié. La configuration d'image est intégralement identique : ENV, USER, CMD, Entrypoint, WorkingDir, ports et healthcheck compris. Les onze fichiers BFF/package sont comparés identiques ; les treize fichiers dist finaux correspondent aux SHA-256 du build.

Seuls les fichiers réguliers et le whiteout de /app/dist changent. Docker réénonce aussi les répertoires parents /app et /etc : leurs modes/UID/GID sont identiques, leurs mtime de build diffèrent. Ces métadonnées sont explicitement enregistrées ; aucun fichier /etc ou dépendance runtime n'est modifié. On ne revendique pas l'identité de tous les timestamps hors dist.

Une recette a exercé le BFF réel de l'image R2 et celui de 930171… avec une API en boucle locale, dans des conteneurs jetables sans réseau externe, ports ou volumes. Aucun conteneur API, DB ou Traefik n'a été reconstruit, lancé ou modifié.

## Préservation et livraison

La vérification finale SHA-256 des 2 328 fichiers préexistants recensés avant R2 est réussie : aucun fichier modifié ou manquant, y compris l'archive d'entrée et les artefacts R1 (preservation-result.json). La règle d'exclusion Git locale et les nouvelles références/worktrees sont les seules modifications de métadonnées Git prévues ; aucun reset du workspace principal.

Le payload privé se trouve dans deliveries/docnelo-web-branding-r2/payload. Il contient l'image R2, les hashes, les rapports, un patch graphique et des précontrôles en lecture seule. Il exclut l'archive d'entrée, sa copie sans tags, les extractions brutes, npm-cache et node_modules. Aucun registre ni stockage public n'a reçu d'archive ou de fichier.

Le GO local repose sur les tests et l'équivalence de référence démontrée. Les contrôles VPS restent obligatoires : image toujours 930171…, services healthy, overrides actuels préservés, absence d'ouverture publique et comparaison des paramètres Docker effectifs avant/après. Aucun déploiement n'est autorisé automatiquement.

Voir [tests](DOCNELO_PUBLIC_BETA_BRANDING_R2_TEST_REPORT.md), [manifeste](DOCNELO_PUBLIC_BETA_BRANDING_R2_RELEASE_MANIFEST.md), [runbook](DOCNELO_PUBLIC_BETA_BRANDING_R2_DEPLOYMENT_RUNBOOK.md) et [inventaire](DOCNELO_PUBLIC_BETA_BRANDING_R2_FILE_INVENTORY.md).
