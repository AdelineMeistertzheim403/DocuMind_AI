# Docnelo Public Beta Web Branding R1 — Manifeste

Date : 31 octobre 2026. Source machine : deliveries/docnelo-web-branding-r1/payload/RELEASE.json. **Statut : NO-GO_PENDING_OPERATOR_ACTIVE_IMAGE_AND_REGISTRATION_PROOF.**

| Champ | Valeur vérifiée |
| --- | --- |
| Branche principale conservée | branding/docnelo |
| Branche isolée | branding/docnelo-public-beta-web-r1 |
| Commit source R1 | 22b6428f961e98c6482a9881579361f53c114934 |
| Commit source de référence reproduit | f3c92eb8ba2bb69b83a9798ebc3df8a70f48fbb2 |
| Image de référence historique vérifiée localement | sha256:f15855942fb4382375648841bbcdc486fd39d252e80e8fdf8eb42999d6590019 |
| ID de l'image actuellement active sur le VPS | **Non collecté — null ; ne pas le remplacer par supposition** |
| Nouvelle image locale retenue | documind-public-beta-web:docnelo-r1-22b6428-v2 |
| Nouvelle image ID | sha256:b8dcd1edd1c0e366f0bc605914424585a96d261b49b82e952458dfab1a911a1a |
| Architecture | linux/amd64 |
| RepoDigest publié | Aucun ; pas de push registre effectué |
| Archive livrée | payload/web-image.tar |
| Taille de l'archive | 260 080 640 octets |
| SHA-256 de l'archive | 72ec517904aa3eb74a520c9aacc49cfb9ba63b390c19c32843a15f27b70378ea |
| Changement d'image | 11 couches de base conservées, 2 ajoutées ; fichiers de contenu sous /app/dist seulement |
| Configuration runtime de l'image | Identique à la base, y compris ENV, USER, CMD, ports et healthcheck |
| Tests | 52 React + 50 BFF + 15 contrôles opérateur simulés réussis ; 20 vues navigateur et 18 assertions d'image réussies |

Le tag n'est pas utilisé comme preuve d'immuabilité : contrôler l'ID exact ci-dessus après chargement, avant et après bascule. Le rollback utilise le même principe pour l'image historique. L'archive et toutes les métadonnées de payload sont couvertes par SHA256SUMS ; conserver aussi l'empreinte du manifeste hors du transfert.

## Entrées, artefacts et périmètre

L'inventaire exact des 16 fichiers sources modifiés, leurs tailles/SHA-256, les 13 fichiers dist, les changements du workspace exclus et les fichiers de livraison est dans [l'inventaire](DOCNELO_PUBLIC_BETA_BRANDING_R1_FILE_INVENTORY.md) et payload/INVENTORY.json.

Le patch binaire branding-r1.patch correspond strictement à f3c92eb → 22b6428. Le worktree et le commit restent disponibles localement ; aucun fichier d'application n'est à recopier sur le VPS. Le Dockerfile livré utilise exclusivement le contexte dist et la base historique déjà contrôlée. Les sources backend et les exemples .env présents dans le worktree de référence ne sont pas dans le payload et ne doivent pas être déployés.

Les preuves provenance.json, image-proof.json, browser-results.json, container-results.json et preservation-result.json sont livrées avec l'archive. Elles documentent des faits locaux/historiques. **Aucun operator-proof.json n'est préfabriqué** : seul le collecteur exécuté ultérieurement sur le VPS peut établir la liaison manquante.

## Métadonnées de filesystem

Les nouvelles couches ne changent aucun fichier régulier hors de /app/dist. Elles réénoncent les entrées de répertoires /app et /etc, en conservant mode/UID/GID mais avec une date mtime de build différente. Les timestamps exacts sont dans RELEASE.json. Aucun fichier /etc, serveur BFF, node_modules, cookie/header/route ou configuration n'est changé. Ne pas confondre identité des contenus/runtime et identité de tous les timestamps de filesystem.

## Éléments exclus

Aucun secret, .env, sauvegarde, base, document utilisateur, frontend Business inutilisé, évolution Beta Lite, nouvel endpoint, migration ou image API/PostgreSQL n'est livré. L'image Web hérite des dépendances runtime de sa base ; npm ci n'a servi qu'au build du contexte propre. Les anciennes pages/versions juridiques du workspace sont conservées sans intégration silencieuse dans cette référence.

## Vérifications avant go

1. Preuve collectée sur VPS : image active exactement f1585594…, linux/amd64, trois services healthy, projet et chemins attendus.
2. Inscription publique indisponible ; mode/profil/versions/URLs enregistrés pour comparaison. Ne modifier aucune valeur, en particulier ne pas définir PUBLIC_LEGAL_READY=true.
3. Overrides actifs conservés, environnement Web résolu identique au conteneur actif, seule image/pull_policy différente.
4. Nouvelle archive conforme aux SHA-256, image chargée b8dcd1ed…, ancienne image conservée et rollback prêt.

Sans ces preuves, le statut demeure **NO-GO**, même si les tests locaux sont tous réussis. Si l'ID actif est différent, ne pas contourner le collecteur : retrouver et reproduire cette autre référence, puis préparer un nouveau candidat.

Le fichier SHA256SUMS complet est livre dans payload. Son empreinte doit etre calculee sur Windows avant SCP et comparee sur Debian ; il ne contient pas sa propre empreinte.
