# Public Beta — Correctif V5.1 : permissions des clés lifecycle

Date : 2026-10-31. Intervention locale uniquement. Aucun accès VPS, modification de clé, de volume, d'image, de .env, de production ou de capture existante. Aucune sauvegarde relancée. Les services signalés healthy par l'opérateur n'ont pas été manipulés. Les livraisons V5 précédentes restent intactes.

## Conclusion de l'analyse de sécurité

Le mode 0440 est explicitement intentionnel dans le Compose Public Beta :

- `Dockerfile` crée le compte app avec useradd puis définit USER app pour l'image finale. Son UID/GID numérique n'est pas fixé par une option du Dockerfile : l'identité 1000 provient du constat VPS fourni par l'opérateur, pas d'une garantie générale de useradd.
- `compose.public-beta.vps.yaml`, service lifecycle-init : exécution initiale 0:0, résolution de app_uid/app_gid par pwd.getpwnam('app'), répertoire keys appartenant à 0:app_gid en 0750, fichiers appartenant à 0:app_gid en 0440. Le provisionnement utilise 32 octets aléatoires et conserve les clés existantes. Il abandonne ensuite ses privilèges vers app et lit les clés pour initialiser les magasins HMAC.
- L'API hérite de USER app ; les clés sont dans le volume lifecycle, monté uniquement dans les services de confiance API et lifecycle-init. Les métadonnées numériques d'archive annoncées 0:1000 correspondent au modèle de groupe applicatif constaté.
- `backend/lifecycle_durability.py::_read_private_key` distingue clés privées du processus et clés administratives root lisibles par l'application ; la branche administrative refuse les droits publics et attend 32 octets. `backend/lite_authority.py::secure_path/read` refuse liens, écritures groupe/autres et identités non approuvées.

Dans cette frontière de confiance, donner uniquement la lecture au groupe applicatif autorisé est compatible avec la confidentialité : pas d'accès aux autres, pas d'écriture groupe, pas d'exécution ni bits spéciaux. Le défaut de sauvegarde était la politique propriétaire-seul appliquée à une clé délibérément lisible par le groupe. Le correctif n'accepte pas n'importe quel groupe : pour 0440/0640, il exige exactement UID 0, GID 1000 dans l'archive **et** dans le manifeste.

Cette validation de métadonnées n'atteste pas la composition réelle du groupe ou tous les accès privilégiés à l'hôte. Si l'image réelle n'utilise pas app avec GID 1000, si ce groupe inclut un consommateur non approuvé, ou si un conteneur non autorisé monte le volume, arrêter : aucune extension automatique de la politique n'est prévue.

### Limites applicatives identifiées, sans modification

Le répertoire lifecycle appartient à app en 0700 dans le Compose ; ce propriétaire peut renommer une entrée enfant. Les fichiers root:app readonly ne constituent donc pas une frontière d'intégrité contre une compromission d'app, qui est déjà autorisé à lire les secrets. Le correctif préserve la frontière de confidentialité envers les comptes non autorisés ; il ne prétend pas rendre les clés immuables pour l'application.

Le lecteur administratif strict appelle secure_path avec uid=0 sur l'ascendance ; il peut refuser le parent lifecycle appartenant à app. Cela explique une divergence potentielle entre provisionnement par read_bytes et lecture applicative stricte ; un healthcheck healthy ne prouve pas l'exécution de cette branche. Aucune validation applicative ni image n'est assouplie ici. Une exigence d'intégrité administrative plus forte nécessiterait une évolution séparée : répertoire racine des clés administré par root, montage readonly distinct, groupe applicatif vérifié et adaptation concertée des chemins. Ne pas changer les clés ou le volume en place pour résoudre ce point pendant la livraison d'outillage.

## Politique V5.1

| Mode | Décision | Condition |
| --- | --- | --- |
| 0400 | accepté | profil historique propriétaire seul |
| 0440 | accepté | UID 0, GID 1000 obligatoires |
| 0600 | accepté | profil historique propriétaire seul |
| 0640 | accepté | UID 0, GID 1000 obligatoires ; écriture propriétaire root seulement |
| 0444 | refusé | lecture publique |
| 0644 | refusé | lecture publique |
| 0660 | refusé | écriture groupe |
| 0777 | refusé | accès public, écritures et exécution |

La liste est exacte : tous les autres modes sont refusés, y compris setuid, setgid, sticky et exécution. Les bits ne sont plus masqués avant contrôle. Les profils 0400/0600 n'introduisent pas de contrainte UID/GID nouvelle ; si ces valeurs sont présentes dans le manifeste, elles doivent néanmoins correspondre à l'archive. Les anciens manifestes propriétaire-seul sans UID/GID restent lisibles. Un profil de groupe sans UID/GID dans le manifeste est refusé.

## Modifications minimales et cohérentes

- Nouveau `tools/lifecycle_key_policy.py` : unique politique commune, sans import applicatif ni dépendance tierce.
- `tools/backup_local.py` : valide mode et propriétaire avant le calcul des inventaires ; conserve le mode et ajoute uid/gid à lifecycle_keys. Le format de sauvegarde reste **5** ; 5.1 désigne la version d'outillage. Refuse aussi les membres dupliqués et les clés de taille vide.
- `tools/verify_snapshot.py` : applique la même politique aux métadonnées et membres, vérifie la correspondance des identités si renseignées. Les empreintes globales et individuelles, tailles, noms et contrôles S2 demeurent obligatoires.
- `tools/validate_restore.py` : applique la même politique, refuse les doublons, les tailles vides et les SHA mal formés. Crée le répertoire keys neuf en 0700 et les fichiers sans écrasement ni suivi de lien ; ferme leurs permissions à 0400 sur descripteur puis vérifie type, propriétaire effectif et nombre de liens.

Les contrôles préexistants de présence des deux fichiers, type régulier, absence de symlinks/hardlinks, chemins sûrs, tailles et SHA-256 sont préservés. Aucun chmod/chown des clés d'origine n'est effectué.

## Identité et permissions de restauration isolée

Le mode d'origine, l'UID et le GID restent des preuves dans le manifeste/archive. Ils ne sont jamais interprétés comme une instruction de chown. Le GID 1000 d'un conteneur n'est pas nécessairement un groupe de confiance sur l'hôte Debian.

Les nouvelles clés du laboratoire appartiennent au processus qui exécute la restauration, dans keys/0700 et sous les parents privés du laboratoire ; mode final 0400. Le processus peut les lire et l'archive n'accorde aucun accès au groupe hôte. La vérification POSIX de l'UID utilise geteuid, sans supposer que le restaurateur est root ou app. Le rapport de quarantaine indique cette politique. Un changement d'identité vers un processus API différent n'est pas automatique : le laboratoire demeure sans API, le latch quarantined, jusqu'à provisionnement isolé et revue opérateur. Ce correctif ne restaure pas directement les clés root:app dans un volume applicatif.

La réserve V5 antérieure demeure : seal_restored_registration est définie mais non appelée par _restore ; la fermeture réelle du quota doit être vérifiée séparément avant toute reprise. Ne pas exposer l'API du laboratoire.

## Autres contrôles avant manifeste

Le chemin complet create_backup a été relu, puis exercé avec archives SQLite synthétiques réelles et requêtes PostgreSQL simulées. La création de manifeste peut toujours être bloquée, intentionnellement, par :

1. Résolution Compose, quiescence DB seule, isolation des réseaux/volumes et absence de client PostgreSQL, avant puis après capture. Les tests de Compose existants vérifient aussi l'override offline et son refus s'il n'est pas effectif.
2. Destination existante, droits ou espace disque insuffisants, échec d'un processus de capture, timeout de l'orchestrateur ou dump non lisible par pg_restore --list. Aucun fichier ancien n'est réutilisé ou réparé.
3. Archive documents contenant chemins ou liens dangereux ; inventaire SQLite incomplet, membres non réguliers, capture_id divergent ou jeux de stores incohérents.
4. Politique des deux clés ; latch absent, trop grand, JSON dupliqué ou schéma/état invalide.
5. Liste et colonnes des tables, exécution/format des résultats de comptage et digest SQL ; lecture de la migration ; quota absent pour migration 0007.
6. Derniers contrôles de quiescence, empreintes SQLite et empreintes de tous les fichiers ; écriture effective du manifeste.

Les étapes S2 détaillées et la comparaison à la base vivante restent exécutées après création, avant upload, par l'orchestrateur. Aucune garde Restic, de latch, de destination, de format V5 ou de reprise n'est supprimée. Une erreur laisse les captures partielles sur place, sans upload ni redémarrage automatique. Les contraintes système (espace, permissions, binaires/images réels) restent à vérifier sur Debian ; les simulations ne les certifient pas.

## Tests exécutés localement

```powershell
.\.venv\Scripts\python.exe -m pytest -q --tb=short tests/test_lifecycle_key_permissions_v51.py tests/test_snapshot_backup_integrity.py tests/test_lifecycle_keys_restore.py tests/test_public_beta_backup.py tests/test_public_beta_restic_guard.py tests/test_backup_offline_compose.py tests/test_public_beta_snapshot.py
```

Résultat final : **101 réussis, 0 échoué, 6 ignorés**, en 13,97 s. Un avertissement préexistant Starlette/httpx. Le nouveau fichier comporte 52 cas, dont la matrice des huit modes pour capture, vérification et restauration. Les captures synthétiques positives produisent integrity.json avec 23 tables puis manifest.json V5 et passent verify_capture(require_s2=True).

Régressions couvertes : UID/GID non approuvés, modes spéciaux et types invalides, doublons/liens, dump invalide, documents dangereux, inventaire/identité/empreinte SQLite incorrects, latch invalide, erreur SQL, résultat SQL mal formé, quota absent et perte de quiescence. Les suites antérieures couvrent les altérations SHA et l'orchestration Restic, notamment la conservation locale après échec.

Les six intégrations Docker/PostgreSQL exigeant TEST_SNAPSHOT_COMPOSE ne sont pas exécutées. L'interpréteur local est Python 3.13 sous Windows : les branches POSIX de scellement sont testées par simulation de descripteur/UID ; le contrôle réellement POSIX sous Python 3.11 est fourni dans le bundle et n'a pas été exécuté sur le VPS. Ne pas assimiler les tests simulés à une validation du système de fichiers ou de l'image Debian réelle.

## Livraison et déploiement

Le bundle versionné `deliveries/docnelo-public-beta-backup-v5.1-20261031` contient les six modules tools nécessaires (dont la politique commune), les trois sources backend de référence, runbooks, inventaire, rapport, audit des copies, contrôle Python 3.11 et manifeste SHA-256. Aucun secret, .env, volume, base, frontend ou image n'est livré.

Suivre README_DEPLOIEMENT.md du bundle pour un transfert SCP manuel puis une installation neuve dans `/opt/documind-public-beta/backup-tools-v5.1-20261031`, sans écraser la V5. L'orchestrateur est importé depuis cette release d'outillage ; son --root continuera de désigner la release applicative existante lors d'une future opération explicitement décidée. La procédure de livraison n'exécute que des contrôles locaux de syntaxe/imports/API/permissions synthétiques et les aides CLI ; aucune capture ni reprise de service.

Retour arrière : réutiliser l'ancienne release d'outillage si nécessaire, conserver les preuves V5.1 et les anciennes captures. La V5 antérieure refusera toujours les profils de groupe ; ne pas la relancer en boucle. Aucun changement de configuration, de clés, de volumes, d'images, de latch ni redémarrage n'est nécessaire pour retirer l'outillage V5.1.
