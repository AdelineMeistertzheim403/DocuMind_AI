# Docnelo Public Beta Web Branding R2 — Manifeste

Date : 31 octobre 2026. **GO_LOCAL_ONLY — aucun déploiement autorisé automatiquement.** La version machine est deliveries/docnelo-web-branding-r2/payload/RELEASE.json.

| Champ | Valeur |
| --- | --- |
| Archive d'entrée privée vérifiée | web-active.tar, 257 984 000 octets |
| SHA-256 de l'entrée | 321ea808f4dc246291adf484c9ee25245470545dec0a7774d4404f052100792b |
| Image active de référence | sha256:9301710690ea35cd3b81db3acf48deb38638c6e7fa3c29dac77756d60025f487 |
| Tag déclaré par l'opérateur | documind-public-beta-frontend:2026-10-31 |
| Chargement local | Copie sans RepoTags, puis alias neuf ; aucun ancien tag remplacé |
| Plateforme | linux/amd64 |
| Source des entrées statiques reproduites | 1bc1a4a5bb49395acabdce5e7604d1a6b97dea61 |
| Source BFF | c420808… ; SHA complet dans provenance.json |
| Référence source composite figée | fa02986ae0a92e02e6bb4b576171ce1deb18d5f2 |
| Commit graphique R2 | b046e5d8256d45b65bf575a8a006351616b69fc9 |
| Branche isolée | branding/docnelo-public-beta-web-r2 |
| Image nouvelle | documind-public-beta-frontend:docnelo-r2-b046e5d8256d |
| Image ID nouvelle | sha256:ebdbc7fba1c61c03349088ca093470c78eec9dd91c5e2aa92ab1d8c0db5be362 |
| Archive privée de livraison | payload/web-r2.tar, 259 197 440 octets |
| SHA-256 de livraison | de8f742edd34bf0182e746916376599686fcd7d5a176e43cdf0979caa32fc54b |
| Publication registre | Aucune ; pas de RepoDigest de publication créé |
| Images API/PostgreSQL/Traefik | Ni construites ni remplacées |

## Attestation de provenance et portée

Les cinq fichiers dist de 930171… sont reconstruits octet pour octet. Les neuf fichiers server et les deux manifests NPM sont identiques aux entrées Git de référence ; ils sont hérités par l'image dérivée. Le commit de check-out CI original n'est pas connu, faute de label : aucun identifiant historique n'est inventé. La preuve retenue est l'équivalence complète des artefacts et des entrées, figée dans fa02986…, et non une assertion d'auteur/date de build.

Le diff graphique fa02986… → b046e5d… contient exactement 16 chemins. Le commit de référence ne contient que deux restaurations BFF depuis des objets Git connus, pour refléter le runtime actif ; aucune extraction brute n'est committée. L'image de livraison ne contient pas le worktree : seulement la base active et le remplacement dist.

## Invariants vérifiés

- Neuf couches de base conservées, deux couches ajoutées ; configuration d'image identique.
- Treize statiques finaux vérifiés par SHA-256 dans l'image ; tous les fichiers réguliers modifiés sont sous /app/dist.
- Réénoncés de métadonnées /app et /etc : mode/UID/GID inchangés, mtime différent, documenté.
- Routes, cookies, CSRF, sessions, headers et dépendances runtime conservés.
- Archives juridiques et AppRoutes inchangés ; douze textes de vues comparés identiques.
- Liens de téléchargement présents ; 404 BFF préexistant conservé, sans réparation fonctionnelle cachée.
- Aucun .env, migration, volume, outil de sauvegarde ou paramètre Restic modifié.

## Tests et fichiers de preuve

134 tests automatisés réussis ; 36 vues navigateur ; 24 contrôles de l'image R2 et 22 de la référence ; cinq artefacts actifs reproduits et treize statiques livrés vérifiés. Les données de test sont synthétiques et les conteneurs de recette hors réseau externe.

Les SHA-256 individuels sont dans payload/SHA256SUMS et INVENTORY.json. Voir [l'inventaire exact](DOCNELO_PUBLIC_BETA_BRANDING_R2_FILE_INVENTORY.md). Les preuves livrées ne contiennent ni archive d'entrée ni code brut extrait ; les inventaires privés complets restent hors payload et hors Git. L'image de livraison elle-même reste un artefact **privé**, à transférer uniquement à l'opérateur autorisé, jamais à publier ou committer.

Le hash de SHA256SUMS doit être calculé sur le poste source, conservé séparément et comparé sur Debian avant utilisation ; SHA256SUMS ne contient pas sa propre empreinte. Aucun operator-proof.json n'est fabriqué localement pour simuler une lecture du VPS.

## Conditions opérateur et rollback

Le précontrôle doit confirmer que Web est toujours sur 930171…, en linux/amd64, avec services healthy, mode d'inscription fermé au public et paramètres/overrides attendus. La bascule ne change que l'image Web ; les .env et le lien current ne sont pas édités. Le fingerprint de runtime et les contrôles de version juridique/inscription doivent rester conformes après bascule.

Rollback prévu vers **930171…**, via un alias neuf documind-public-beta-frontend:r2-rollback-9301710690ea contrôlé par ID. Ne pas revenir à f1585594… ni utiliser les overrides R1. Conserver R1 comme historique, sans la déployer sur cette référence.

**GO local**, sous réserve des précontrôles VPS obligatoires et d'une décision opérateur distincte. Aucun push ni déploiement n'a été exécuté.
