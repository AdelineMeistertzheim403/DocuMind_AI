# Docnelo Public Beta — Manifeste API capacité dix

31 octobre 2026. **GO_TECHNIQUE_LOCAL_CLOSED_ONLY**. Aucun déploiement, changement de quota réel ou push registre.

| Élément | Valeur |
| --- | --- |
| Référence API | sha256:4aa850b6fb8d16b32fd731d94b232b2f817f461892b3f39a28e7557a25a5eb3d |
| Archive d’entrée privée SHA-256 | 2ee6ab4f9a5eee4e6dad475e0a2988745472e12a918e186580a36e2e6c631081 |
| Référence source composite exacte | a323afc5c9d63a8a9f59ac10c365710b58d1c868 |
| Commit candidat | 8b11d4daf47bd7c3c6766b9f5231ea8a84fdbf71 |
| Branche isolée | preparation/docnelo-public-beta-lifecycle-10 |
| Image candidate | documind-public-beta-backend:capacity10-8b11d4daf47b |
| ID candidat | sha256:32a1516206d9e648e3741b54dc0543c0b455f22cdf676e7d69d9a971e1f4213d |
| Plateforme | linux/amd64 |
| Archive privée livrée | payload/api-capacity10.tar |
| Taille | 305294336 octets |
| SHA-256 export | 6bb4d7f6b6cd865f80c729b3f8b13287a7a6750e4c95f135079fc5bdb4458847 |
| Couches | 15 héritées intactes + 9 copies de sources |
| Configuration Docker | Identique à l’image active ; mêmes ENV d’image, USER, CMD, Entrypoint et paramètres |
| Dépendances runtime | 46 métadonnées identiques ; aucune installation ou mise à jour |
| Web R2 à conserver | sha256:ebdbc7fba1c61c03349088ca093470c78eec9dd91c5e2aa92ab1d8c0db5be362 |
| Alembic | 0007 ; aucun fichier de migration modifié |
| SQLite | witness 1→3 ; admission_anchor 2→3 ; autres magasins inchangés |
| Outillage compatible | tooling-v5.2, dérivé séparément du bundle V5.1 ; format de capture V5 conservé |

Les fichiers réguliers changés/ajoutés dans les couches candidates sont exactement les neuf modules backend inventoriés dans image-proof.json, sous /app/backend. Les copies sont root:root 0644 ; aucun fichier de clé ou de donnée n’entre dans le contexte. Les éventuels réénoncés de répertoires parents sont des métadonnées de couche, pas une modification de configuration ou dépendance. Le commit CI historique original reste inconnu ; la preuve de contenu est détaillée dans le rapport de provenance.

La configuration **d’image** reste identique. Le déploiement fermé proposé ajoute une seule variable de service, LIFECYCLE_AUTHENTICATED_NAMESPACE=documind-public-beta, pour lire l’en-tête signé conforme au provisionnement publié. Cette valeur doit être authentifiée par le probe avant migration ; aucune réécriture d’en-tête ou adoption implicite du namespace lu n’est permise. Les autres environnements conservent le défaut historique local ; aucun .env existant n’est modifié par la livraison.

## Contenu et empreintes

Livraison privée : deliveries/docnelo-lifecycle-10-api/payload. Elle contient l’archive API, les cinq rapports, le Dockerfile minimal, les manifestes/preuves sélectionnés, le diff Git des 15 fichiers, les overrides proposés, les précontrôles en lecture seule et l’outillage compatible. INVENTORY.json fournit la liste exacte ; SHA256SUMS couvre tous les fichiers sauf lui-même, avec chemins relatifs au payload. Son empreinte est conservée séparément sur le poste source et doit être comparée avant toute utilisation sur VPS.

Sont exclus : api-active.tar, sa copie sans tags, le worktree complet, toute extraction brute, caches, anciennes archives, dumps SQL de laboratoire, fichiers de clés, données utilisateur, .env et environnements Python. L’archive candidate hérite néanmoins de l’image privée de référence : la traiter entièrement comme privée, sans garantie générale d’absence de secret historique. Ne pas committer, publier ou pousser cette archive.

Le bundle V5.1 original est conservé intact. Dans ses neuf modules Python hérités, seuls le schéma de capture et le validateur de schéma évoluent ; les sept autres sont identiques par SHA-256. La politique Public Beta du commit candidat est ajoutée en tant que module séparé. Aucun outil de Production ou dépôt Restic n’est modifié.

## Qualification et conditions

288 tests finaux réussis, zéro échec/erreur/skip ; round-trip PostgreSQL 17 physique et contrôles d’image séparés réussis. Les clés et données utilisées sont synthétiques. Le default de la nouvelle garde opérationnelle est false ; le premier déploiement proposé reste disabled, quota closed=true/issued_count=0, limite cinq et flags juridiques/latch inchangés.

L’outillage compatible doit être disponible pour toute capture des schémas étendus. Une fois migré, ne pas utiliser l’image ancienne bornée à cinq comme rollback automatique, même avant d’envisager de nouvelles admissions. Après la sixième, ce rollback est explicitement interdit sans qualification de compatibilité. La procédure de fermeture utilise la candidate compatible dix en mode disabled, garde opérationnelle false et compteur conservé ; elle ne restaure pas une ancienne base.

**GO technique local pour une livraison fermée.** Les précontrôles VPS, la décision humaine d’intervention et la validation juridique avant toute future ouverture restent obligatoires.

Cette livraison conserve Web R2 : elle ne remplace ni les textes « cinq admissions » ni les brouillons juridiques existants. Leur évolution sous de nouvelles versions relève de la future phase d’ouverture, séparée de ce lot technique.
