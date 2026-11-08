# Docnelo Public Beta — Provenance de l’API de référence

31 octobre 2026. **Provenance de contenu démontrée ; GO technique local pour la préparation, sans ouverture.**

## Entrée vérifiée avant utilisation

| Élément | Valeur |
| --- | --- |
| Archive privée | deliveries/docnelo-10-users/api-active.tar |
| Octets | 305131008 |
| SHA-256 vérifié | 2ee6ab4f9a5eee4e6dad475e0a2988745472e12a918e186580a36e2e6c631081 |
| ID/config Docker vérifié | sha256:4aa850b6fb8d16b32fd731d94b232b2f817f461892b3f39a28e7557a25a5eb3d |
| Tag d’origine dans le manifeste | documind-public-beta-backend:2026-10-31 |
| Plateforme | linux/amd64 |
| Couches de référence | 15, chaque SHA-256 vérifié contre rootfs.diff_ids |
| Labels de provenance CI | Absents |

L’empreinte de l’archive a été vérifiée avant son inspection et à nouveau avant chargement. Les whiteouts ont été appliqués lors de l’inventaire des fichiers finaux. Aucun fichier brut de l’image n’a été extrait dans Git. Le chargement local utilise une copie sans RepoTags, puis un alias neuf lifecycle10-base-4aa850b6fb8d ; les tags existants restent inchangés. Aucun conteneur VPS ou tag d’origine n’est remplacé.

## Correspondance Git exacte

- 65 modules backend : tous leurs contenus correspondent à des objets Git accessibles.
- 103 entrées applicatives vérifiées : backend, modules Python d’extraction/analyse, migrations, alembic.ini, pyproject.toml et requirements.lock.
- Sur 170 commits accessibles examinés, aucun arbre historique unique ne correspond exactement à l’ensemble : les meilleurs ont 102/103 entrées, un pyproject différent et un module lifecycle_bootstrap.py supplémentaire absent de l’image.
- La référence composite **a323afc5c9d63a8a9f59ac10c365710b58d1c868** reproduit les 103 entrées à l’octet près, depuis les objets Git existants : pyproject historique exact rétabli et module supplémentaire exclu. Aucun identifiant de check-out CI n’est inventé.
- L’export candidat correspond bien aux 65 modules ; cette conclusion découle maintenant de la comparaison de l’archive réelle, pas du nom de l’export. Le workspace principal n’en reproduit que 62 et l’ancien backend associé à Web R2, 48.

Cette attestation est une preuve de correspondance des contenus, **pas une reconstruction prétendue de la chaîne CI historique** ni de son horodatage. La construction candidate hérite directement de l’image active vérifiée ; elle ne réinstalle aucune dépendance depuis un Dockerfile historique approximatif.

## Runtime et dépendances

46 distributions installées ont été inventoriées par leurs métadonnées et SHA-256. La candidate en conserve exactement les 46, ainsi que toutes les couches de base et la configuration d’image. Les versions comprennent SQLAlchemy 2.0.55 et Psycopg 3.3.6 ; l’interpréteur reste celui de la base Python 3.13. Les bibliothèques supplémentaires pytest/cryptography sont réservées à l’image de test distincte ; aucune n’est ajoutée au runtime API.

Le runtime de test présente les mêmes 46 métadonnées aux mêmes empreintes, plus six distributions de test, dont cryptography 50.0.2, installé depuis une roue verrouillée par SHA-256. Les scripts d’exploitation/outillage sont aussi analysés avec la grammaire Python 3.11. Ne pas confondre Python 3.11 de l’outillage VPS avec Python de l’image API.

## Source candidate et invariants

Branche isolée : preparation/docnelo-public-beta-lifecycle-10. Worktree : deliveries/docnelo-lifecycle-10-api/source. Commit : **8b11d4daf47bd7c3c6766b9f5231ea8a84fdbf71**.

Le diff depuis la référence composite contient exactement 15 fichiers : neuf backend, la politique de livraison Public Beta et cinq nouveaux fichiers de tests. L’image ne reçoit que les neuf backend. Les autres entrées applicatives, migrations Alembic, packages, runtime Docker et image Web R2 sont conservés. Les archives et extractions privées sont exclues localement de Git et n’ont pas été committées.

Preuves : reference-audit.json, git-reference-comparison.json, source-reference.json, source-release.json, load-base-proof.json, test-runtime-parity.json et image-proof.json dans deliveries/docnelo-lifecycle-10-api. Elles contiennent des empreintes et métadonnées sélectionnées, pas les fichiers .env, clés ou contenus bruts extraits.

**GO de provenance pour cette référence de contenu précisément figée.** L’opérateur devra confirmer que le VPS utilise toujours 4aa850… au moment de la future intervention ; aucun accès VPS n’a été effectué ici.
