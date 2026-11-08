# Docnelo Public Beta — Audit documentaire sauvegarde/restauration V5/V5.1

1 novembre 2026. **NO-GO pour toute intervention sur la production.**
Audit local de sources et de manifestes uniquement. Aucun accès VPS,
import/exécution des outils, backup, restore, commande Docker/Restic,
redémarrage, migration ou changement de script effectué.

Références : `DOCNELO_API_CONTROLLED_RECONCILIATION_PLAN.md` et
`DOCNELO_API_RECONCILIATION_FUTURE_RUNBOOK.md`. La provenance H0 reste
non authentifiée ; cet audit n'autorise ni sa recréation ni Lifecycle 10.

## 1. Conclusion et niveau de qualification

L'outillage couvre structurellement PostgreSQL, documents, cinq snapshots
SQLite, deux clés et latch. **Cette couverture n'est pas une preuve
opérationnelle de restaurabilité ou de reprise applicative.**

Les principaux blocages sont :

| ID | Constat sourcé | Effet sur la décision |
|---|---|---|
| B1 | V5 refuse le profil de clé `0440` ; V5.1 accepte exactement les profils autorisés et borne les profils de groupe à `0:1000` | V5 ne convient pas aux clés root:app annoncées ; identité réelle et droits V5.1 à qualifier |
| B2 | L'orchestrateur utilise un seul Compose de base, pas la chaîne complète d'overrides ; pas de vérification de hash API H0 ou d'image active | Impossible de certifier sa fidélité à la chaîne actuelle sur la seule base de ses contrôles |
| B3 | La capture lifecycle écrit des temporaires dans les parents des magasins et peut créer `.backup.lock` | Une capture n'est pas une opération totalement sans écritures sur le volume lifecycle |
| B4 | Restore répartit les stores sous leurs noms logiques, pas tous sous les chemins API actuels | Pas de remise en service directe avec le Compose actuel |
| B5 | `_restore` n'appelle pas `seal_restored_registration` | `quarantined` ne garantit pas que le quota SQL est fermé |
| B6 | Validation d'archives/schémas et SHA, sans authentification HMAC des contenus ni fraîcheur externe | S2 complet ne signifie pas reprise autorisée ; lecteurs indépendants nécessaires |
| B7 | `remote_verified` vérifie une entrée Restic, pas une récupération des octets ni un restore | Une sauvegarde distante « présente » ne suffit pas |
| B8 | Restauration des données seulement ; image, Compose, overrides, contexte et instance H0 non restaurés | Aucun rollback exact du conteneur historique démontré |
| B9 | Daemon Docker implicite, délais non bornés dans certaines étapes, dépendances Linux non éprouvées par cet audit | Qualification de l'environnement et du traitement d'échec nécessaire avant interruption |
| B10 | Aucune capture réelle et restauration de son ID exact disponible dans le dossier local audité | **NO-GO opérationnel maintenu**, même si tous les sceaux locaux sont valides |

Les conclusions sont des propriétés des sources conservées. Les conditions
VPS annoncées dans les rapports antérieurs ne sont pas recontrôlées ici.
Aucun garde existant n'est modifié, désactivé ou remplacé.

## 2. Identité des versions auditées

Les 18 entrées de chacun des deux manifestes ont été recalculées et sont
conformes. Cela prouve leur intégrité locale relativement à ces manifestes,
pas leur transfert, leur installation ou leur exécution sur VPS.

| Release | SHA-256 de `SHA256SUMS` | Qualification historique conservée |
|---|---|---|
| `deliveries\docnelo-public-beta-backup-v5-20261031` | `abeb44119afd6a10bf6bbc15b229b0aa8b8317f5c28ee36d12ace124946a91ea` | Grammaire/imports locaux Python 3.13.7 Windows ; runtime Debian non établi |
| `deliveries\docnelo-public-beta-backup-v5.1-20261031` | `676d6d3f707c58f4dda150cef5cfd37196b7cf8e162434a7af042357574f6eda` | RELEASE annonce 101 tests réussis, 6 ignorés ; Python 3.11 et runtime Linux non exécutés |

**Format de sauvegarde V5 ≠ version d'outillage V5.1.** V5.1 conserve
`backup_format_version=5`, corrige la politique et l'extraction des clés,
ajoute le helper partagé `lifecycle_key_policy.py`.

| Source | Correspondance actuelle vérifiée |
|---|---|
| `tools\public_beta_backup.py` et `public_beta_restic_guard.py` | Identiques dans workspace, V5 et V5.1 |
| `tools\backup_local.py`, `verify_snapshot.py`, `validate_restore.py` | Workspace identique à V5.1 ; différents de V5 |
| `tools\lifecycle_key_policy.py` | Workspace identique à V5.1 ; absent de V5 |
| `backend\lifecycle_snapshot.py` et `lifecycle_backup_lock.py` | Identiques dans les trois ensembles |

Empreintes des sources V5.1 utilisées pour les références ci-dessous :

| Fichier | SHA-256 |
|---|---|
| `tools\public_beta_backup.py` | `7b4dfe83f941fb4bc8317af3b37534f7105c369be82d170183499c4522ad8607` |
| `tools\public_beta_restic_guard.py` | `72c2da58dcda0020e0f0cffe6a31d0017a7d252d367d3cdc72c4b0e76a6b3bde` |
| `tools\backup_local.py` | `c431234d9113966d94201ce23ab386f6b86dc8ba9b51222c5df2cb15794cf75c` |
| `tools\verify_snapshot.py` | `0ccbf6c01ad2a3eceaef31e64376ad9e4a071524f454a6794eb4c82f248e5532` |
| `tools\validate_restore.py` | `b3c39b07b09135b8c7793629f5963c1dd85977e387f373ba3bf9fba534f50899` |
| `tools\lifecycle_key_policy.py` | `5f1d23507ecf19717fe248b15974f7dcf13d7325c312c949db1cc59edda50bee` |
| `backend\lifecycle_snapshot.py` | `e5ec61e50467e7376fdd266ba800262e811e55001bb44b1ee77ec32ba2e30733` |
| `backend\lifecycle_backup_lock.py` | `24427332fdbf3589d4efebfab50d375eb49bbe13b30cfb6ad54ccd3f75c90d19` |

Les références `tools\…` et `backend\…` désignent ces contenus identiques
à V5.1. Ne pas mélanger un script V5 avec le validateur V5.1 ou importer
accidentellement le workspace à la place de la release choisie.

Les modules backend livrés sur l'hôte sont **des références**.
`backup_local` exécute `backend.lifecycle_snapshot` dans l'image API
résolue par Compose, pas dans ce dossier d'outillage.
L'audit de contenu antérieur `reference-audit.json`, entrées
`backend/lifecycle_snapshot.py` et `backend/lifecycle_backup_lock.py`,
rapporte les mêmes empreintes pour l'archive API 4aa850… ;
cela ne vérifie pas la résolution d'image du prochain processus de capture.

## 3. Chaîne réellement exécutée par les outils

`public_beta_backup.main → verrou opérateur → execute → validation
Restic/latch/config → stop API/Web → start DB existante → create_backup
→ validate_v5/verify_snapshot → recontrôles latch/Restic → upload`.

L'orchestrateur :

- Charge la configuration Restic privée fixe ; compare bucket/préfixe
  indépendants et ID de dépôt déjà enregistré.
- Construit un contexte Compose depuis `--root`, deux env-files puis un
  seul `compose.public-beta.vps.yaml`.
- Vérifie les noms physiques des trois volumes et le bind readonly du latch.
- Arrête API/Web ; après quiescence, capture et valide ; laisse les deux
  services arrêtés après succès **et** après échec survenu après l'arrêt.

Sources : `tools\public_beta_backup.py:59-96,139-198`.
Le succès requiert V5 et les deux clés ; il ne signifie ni healthy après
reprise, ni provenance historique retrouvée.

`backup_local.create_backup` peut recevoir une liste Compose complète ;
son CLI propose des `--compose-file` et `--env-file` répétables
(`:385-408`). Il n'arrête pas les services et ne réalise pas l'upload gardé.
**Ce helper n'est pas proposé comme chemin de substitution permettant
d'éviter les gardes ou la procédure Restic approuvée.**

`tools\backup_production.py` vise une autre orchestration, avec projet et
volumes `production_*` : ce n'est pas une alternative Public Beta.
Le laboratoire `ops\testing\combined_restore_lab.py` est lui aussi un
programme mutateur de ressources synthétiques, pas un diagnostic readonly.

## 4. Matrice des éléments sauvegardés et restaurés

| Élément | Capture et validation existantes | Restore isolé existant | Lacune / refus requis |
|---|---|---|---|
| PostgreSQL | `pg_dump -Fc` de la base du conteneur DB ; `pg_restore --list` ; inventaires count/digest/colonnes, quota pour 0007 | Nouvelle DB, `pg_restore --no-owner --exit-on-error`, comparaison SQL | Versions réelles et extensions nécessaires ; vérification par liste de tables, pas inventaire universel des rôles/ACL/cluster |
| Documents | Tar de `/app/var/documents`, refus de liens et chemins dangereux ; SHA archive | Extraction privée, contrôle SHA/taille par ligne SQL, fichiers manquants/non référencés et tombstones | Ne couvre pas tout `/app/var` ; intégrité fine des documents surtout vérifiée au restore |
| Registry | Snapshot SQLite via backup API, schéma 1, tables attendues | `lifecycle/registry/registry.sqlite` | HMAC/fraîcheur et compatibilité applicative restent indépendantes |
| Witness/confirmation | Snapshot SQLite, schéma 1 | `lifecycle/witness/witness.sqlite` | Diffère du chemin API courant `confirmation/confirmation.sqlite` |
| Authenticated | Snapshot SQLite, schéma 2 et header présent | `lifecycle/authenticated/authenticated.sqlite` | Diffère de `authenticated/authenticated-confirmation.sqlite` ; header présent ≠ HMAC validé |
| Holds | Snapshot SQLite, schéma 2 | `lifecycle/holds/holds.sqlite` | Même nom relatif que la source actuelle, sans certification de lecteur ou d'ownership API |
| Admission anchor | Snapshot SQLite, schéma 2 | `lifecycle/admission_anchor/admission_anchor.sqlite` | Diffère de `admissions/admission-anchor.sqlite` |
| Clé authentication | Tar exact de `keys/authentication.key`, métadonnées et SHA V5.1 | `lifecycle/keys/authentication.key`, propriétaire restaurateur, `0400` | Pas de restauration des UID/GID/modes d'origine ; usage par API d'autre UID non démontré |
| Clé admission | Même politique, second membre exact obligatoire | `lifecycle/keys/admission.key`, propriétaire restaurateur, `0400` | Taille non vide seulement ; 32 octets, clés distinctes et validité HMAC exigent contrôles applicatifs |
| Latch | Fichier canonique readonly capturé, schéma strict, SHA ; égalité au latch opérateur | Original copié en `source-recovery-state.json` ; copie de travail toujours `quarantined` | Aucune promotion à ready ; copie source conservée pour preuve seulement |
| Quota SQL | Inventaire `id,issued_count,closed`, comparaison à la DB | Valeurs restaurées et rapportées | Sealer non appelé : quota peut rester `closed=false` ; aucun service ne doit être attaché |
| `.env.public-beta` et `.env.public-beta.images` | Ajoutés comme chemins Restic séparés, pas dans le répertoire de capture vérifié | Non restaurés par `validate_restore` | Récupération privée et preuve d'identité à organiser ; pas d'édition des originaux |
| Compose / overrides / contexte | Non inclus par l'upload standard, pas de sceau global des entrées | Non restitués | Dossier H0/prospectif complémentaire obligatoire |
| Image, conteneur, réseau et volume Docker | Noms de volume/config vérifiés partiellement ; pas d'archive de l'instance | Aucun conteneur API, réseau ou volume applicatif recréé par le restaurateur | Pas de rollback de l'ID, Created, labels ou allocations Docker H0 |

Sources : `tools\backup_local.py:218-378`,
`tools\verify_snapshot.py:21-276`,
`tools\validate_restore.py:91-179,249-365`.
Les chemins courants comparés sont ceux de
`compose.public-beta.vps.yaml:249-257` ; ce fichier local n'est pas
une preuve du contenu VPS actuel.

### Clés : décision exacte des versions

V5 applique une politique propriétaire-seul ; `0440` échoue après les
captures précédentes, avant validation finale/upload. Les captures partielles
ne doivent pas être « réparées » avec un manifeste ajouté.
Source : release V5, `tools\backup_local.py:290-296`.

V5.1 accepte exactement `0400`, `0440`, `0600`, `0640`.
Pour les modes de groupe, UID/GID du membre et du manifeste doivent être
entiers et exactement `0:1000`. Bits spéciaux, exécution, modes publics,
doublons, liens et membres manquants sont refusés
(`tools\lifecycle_key_policy.py:5-30`).
Les profils propriétaire-seul n'ajoutent pas de contrainte `0:1000`.

L'acceptation d'une archive ne certifie ni la composition réelle du groupe,
ni 32 octets de clé, ni deux clés différentes, ni la validité des signatures.
Le restore ferme les droits des **copies** à `0400`, sans chown vers
l'ownership archivé. Il ne provisionne pas une API root:app.

## 5. Compose, overrides Web R2 et chemins effectifs

| Sujet | Garantie de source | Ce qui manque |
|---|---|---|
| Root/projet | Root physique directement sous `/opt/documind-public-beta`, projet fixé | Compatibilité exacte avec la release installée |
| Ordre CLI env-files | `.env.public-beta`, puis `.env.public-beta.images` | Conservation/scellement des octets et absence de dérive pendant la capture |
| Service env_file | Résolution de `${PUBLIC_BETA_ENV_FILE:-.env.public-beta}` par le moteur | Contexte capturé ne reprend pas toutes les variables de session de H0 |
| Overrides actifs | Orchestrateur : un seul `-f` ; helper : chaîne répétable possible | Aucun contrôle d'inclusion/ordre des labels `config_files` dans l'orchestrateur |
| Web R2 | Arrêt du service Web du projet, sans recréation | Pas de contrôle d'image/hash Web R2 ni de capture de son override |
| Image API | Référence du modèle de capture | Pas de comparaison à l'ID H0 ; `run` n'explicite pas `--pull never` |
| Volume/latch | Noms physiques attendus et bind du latch validés | Pas d'équivalence intégrale Config/HostConfig/Mounts/réseaux/env à H0 |
| Cinq paths effectifs | `backend.lifecycle_snapshot` lit l'environnement du one-off | Ne lit pas automatiquement celui du conteneur API existant |
| Daemon | Commandes `docker` sans `--host` explicite ; environnement Compose réduit à PATH/HOME/USER/LOGNAME + latch | Choix et cohérence du daemon/default config à certifier, notamment pour les inspections globales |

Source : `tools\public_beta_backup.py:139-164`,
`tools\backup_local.py:73-164,182-216,237-247`.

Si l'override Web R2 n'affecte que Web, son omission ne démontre pas à elle
seule une mauvaise capture des magasins. Elle empêche néanmoins d'attester
la chaîne complète et la reprise Web. Inversement, si un override ou une
variable change les chemins API, une capture depuis la base seule peut
capturer un autre modèle, échouer ou ne pas couvrir l'état H0 attendu.
Ces alternatives doivent être discriminées en laboratoire, sans retirer
un override ou fabriquer un root aplati pour forcer la validation.

La politique de référence d'image/pull doit être vérifiée avec le moteur
et les images réels du laboratoire. `--no-deps` n'interdit pas à lui seul
une résolution/pull d'image manquante. Aucun build/pull VPS n'est autorisé
par cet audit ni accepté comme correction opportuniste.

## 6. Toutes les mutations/interruption identifiées dans la chaîne

| Opération | Effet du code et frontière |
|---|---|
| Entrée CLI orchestrateur | `umask(077)` ; fichier `.public-beta-backup.lock` créé si absent, conservé, verrou interprocessus |
| Mode `--record-repo-id` | Peut ajouter et fsync l'ID dans le fichier Restic existant ; ce n'est pas une vérification readonly |
| Capture orchestrée | Stop API/Web, start DB existante ; pas de reprise automatique, ni de recréation explicite des trois services |
| Capture helper | Nouveau répertoire de backup et fichiers plaintext privés, archives, inventaires/manifeste ; aucun écrasement de destination existante |
| Isolation du one-off | Écrit un Compose éphémère `networks: !reset []`, `network_mode: none`, puis l'efface ; ne modifie pas les Compose originaux |
| Docker `run --rm` | Crée/exécute/supprime des conteneurs de capture ; montage des volumes source, pas snapshot immuable des volumes Docker |
| Lock lifecycle | Ouvre avec `O_CREAT|O_RDWR`, peut créer `.backup.lock` ; verrou exclusif coopératif pendant les cinq snapshots |
| Snapshot SQLite | Source `mode=ro`, copie via backup API ; crée `.snapshot-*` **dans chaque parent de magasin**, écrit copie SQLite/chmod `0600`, normalise DELETE sur la copie, efface les temporaires |
| Effets SQLite système | Fichiers originaux non mis à jour par SQL dans ce code ; effets de sidecars/WAL/SHM, atime et métadonnées à mesurer sur le runtime réel |
| Vérificateur | Lectures DB ; temporaires SQLite locaux et connexions sur copies si contrôle SQLite activé ; nettoyage des temporaires |
| Restic | Nouveau snapshot et objets distants ; cache/locks et effets auxiliaires du client à inventorier selon version ; pas de forget/prune/unlock/init demandé |
| Restore | Crée une DB isolée et ses objets/données ; nouveaux répertoires/fichiers, chmod des copies, latch quarantiné, rapport `quarantine.json` |
| Sealer séparé | Si appelé explicitement, UPDATE du quota de **DB restore** vers closed=true ; non appelé par le chemin principal |
| Laboratoire combiné | Crée DB, conteneurs/volumes/réseaux et données synthétiques, exporte rootfs DB, écrit un wrapper pg_restore, arrête ses propres ressources ; ne doit pas être lancé comme audit readonly |

Sources : `public_beta_backup.py:127-198`,
`public_beta_restic_guard.py:204-232`,
`backup_local.py:182-262`,
`backend\lifecycle_backup_lock.py:25-59`,
`backend\lifecycle_snapshot.py:109-193`,
`validate_restore.py:27-50,249-365`,
`ops\testing\combined_restore_lab.py:42-155`.

Le mode `required=True` du lock exige sa **configuration**, mais n'empêche
pas sa création si le fichier manque. Ne pas considérer la capture comme
un probe refusant automatiquement toute absence de témoin.
Le volume lifecycle doit pouvoir héberger les temporaires : montage
intégral readonly incompatible avec ce mécanisme inchangé.

Pas de migration Alembic, init lifecycle ou réécriture de magasin prévue
par cette chaîne. La normalisation journal DELETE cible la copie, pas le
store source. Cependant « pas de SQL d'écriture source » n'est pas
« aucune écriture dans le volume ». Les journaux d'erreur du helper direct
peuvent contenir stderr ; l'orchestrateur masque les erreurs. Les sorties
directes et preuves réelles doivent donc rester privées.

## 7. Cohérence, limites de vérification et conditions de refus

La capture exige DB seule, API/Web et init quiescents, aucun client DB autre
que le contrôle, réseaux internes/DB exclusifs et absence de consommateurs
incontrôlés des volumes (`backup_local.py:79-180`). Ces conditions sont
recontrôlées après capture. Un one-off conservé, même arrêté, référençant
un volume sensible peut entraîner un refus.

Le lock protège les cinq copies contre les accès lifecycle coopératifs.
PG dump, documents, copies SQLite et tar des clés se succèdent ; ils ne
partagent pas une transaction globale DB/filesystem. Le tar des clés se
fait hors du verrou SQLite. L'absence de writers et l'exclusivité opératrice,
y compris l'accès privilégié hors bande, restent indispensables.
Cette dernière frontière est déclarée non vérifiable par machine dans le
manifeste. Un contrôle avant/après n'est pas un verrou Docker global.

`verify_capture` exige l'inventaire exact, capture_id, SHA payload,
métadonnées et schémas déclarés. La lecture effective `PRAGMA integrity_check`
et des tables des copies par ce vérificateur est conditionnée à
`DOCUMIND_VERIFY_SQLITE=always` (`verify_snapshot.py:166-181`).
L'orchestrateur ne transmet pas cette variable dans son environnement
Compose réduit ; la variable du vérificateur hôte est à documenter
séparément. Le moteur de capture contrôle déjà l'intégrité des sources
et copies ; cela ne remplace pas une vérification indépendante du restore.

`quota_certified` indique un inventaire SQL complet et concordant, pas
closed=true, la fraîcheur du quota ou sa concordance avec les preuves HMAC.
Les hashes SHA garantissent l'intégrité relativement au manifeste ; ce
manifeste doit être authentifié indépendamment pour attester l'origine.
Aucune vérification applicative de signatures ou fraîcheur externe n'est
effectuée par ces deux vérificateurs de backup.

Délais : certains appels de l'orchestrateur sont bornés, mais
`create_backup` est un appel Python interne sans délai global ; ses
subprocess de capture et le `flock` lifecycle peuvent attendre sans borne
configurée. Une durée maximale de fenêtre et un traitement sûr d'échec/
interruption doivent être éprouvés avant la première interruption réelle.
Ne pas déduire un RTO du seul timeout Restic.

## 8. Restauration isolée : conditions et garanties exactes

Le CLI impose :

- `DOCUMIND_RESTORE_LAB=isolated`, root physique existant avec marqueur
  `.synthetic-only` exact et snapshot canonique.
- URL PostgreSQL loopback, port explicite, base d'administration
  `documind_restore_admin`; pas de fallback Compose du restaurateur.
- Cluster marqué `cluster_name=documind-restore-lab`, nouvelle DB
  `documind_restore_<12 hex>`, cible filesystem absente.
- `pg_restore` local disponible, dump/extensions/versions compatibles.

Sources : `validate_restore.py:61-87,249-282`.
Loopback et marqueur ne prouvent pas seuls l'absence de tunnel vers VPS
ou de montage de données actives : isolation physique et réseaux doivent
être établis indépendamment.

Pour ce lot, exiger **format 5 et les deux clés avant toute création de DB**.
Le restaurateur accepte aussi des formats antérieurs complets pour son
périmètre historique ; `require_s2=True` n'est pas une exigence V5.
Une V4 peut restituer zéro clé. La couverture V5 doit donc être vérifiée
explicitement, sans modifier le restaurateur ni l'archive.

Le restore compare la DB puis documents/receipts, conserve les originaux,
force uniquement la copie du latch à quarantined et écrit un rapport.
Les conflits de résurrection, éléments manquants/non référencés ou états
pending donnent `blocked`. Des erreurs peuvent laisser une DB et un arbre
partiels : pas de transaction globale, suppression ou nettoyage automatique
de ces preuves. Une nouvelle cible est requise pour un nouvel essai.

Le restore **ne force pas le quota fermé** : le sealer est défini mais
non invoqué. Un rapport `quarantined`, `api_attached=false` ne vérifie pas
l'absence physique d'une API attachée ; cette absence doit être garantie
par l'architecture du laboratoire et son inventaire.
Les clés 0400 du restaurateur et les noms logiques de stores ne sont pas
directement une configuration API fonctionnelle.

## 9. Retour arrière démontrable sans recréer H0

| Garantie | Niveau actuellement justifié |
|---|---|
| Cesser d'utiliser V5.1, garder V5 et toutes les preuves | Retour arrière documentaire/outillage, sans service ou données à restaurer |
| Avant capture réelle, garder l'application actuelle | Aucun effet de cet audit ; pas une preuve de la future fenêtre |
| Après arrêt de backup, conserver H0 et envisager son start | H0 n'est pas explicitement recréé par l'orchestrateur ; sa reprise exige un chemin distinct approuvé et une qualification, interdite aujourd'hui |
| Restaurer copies DB/documents/stores/clés en laboratoire | Support structurel présent ; restaurabilité du snapshot réel non démontrée |
| Reprise fonctionnelle depuis modèle de repli prospectif | À qualifier séparément ; l'outillage de restore ne crée pas l'API |
| Retrouver l'ID, Created/StartedAt et hash historique H0 après remplacement | **Non garanti** par dump/tar/Restic ; configuration de création inconnue |
| Restaurer des volumes actifs pour effacer une dérive | Exclu ; incident distinct, sans reset/rollback de témoins ou admissions |

Une restauration isolée réussie peut prouver la récupération d'un état
documenté, pas la provenance de son conteneur historique. Ni backup
`remote_verified`, ni restore `quarantined` n'accordent une autorisation
d'ouverture ou de réconciliation API.

## 10. Qualification existante, lacunes et prochaine barrière

Le rapport V5.1 conservé annonce **101 tests réussis et 6 intégrations
Docker/PostgreSQL ignorées**. Il ne revendique ni runtime POSIX réel,
ni récupération Restic/B2 réelle. Ces tests ne sont pas réexécutés ici.
Les suites existantes couvrent clés, archives, quota, isolation offline,
orchestration simulée et erreurs.

Le laboratoire combiné existant appelle `create_backup` **sans**
`include_lifecycle_keys=True` (`combined_restore_lab.py:137`) : sa capture
par défaut est V4, pas un round-trip V5.1 avec les deux clés. Il utilise
des images de preuve et des données synthétiques ; pas H0/root:app.
Le payload règle ses chemins sur les noms logiques restaurés, utilise
un vérificateur synthétique indépendant et une fixture de quota déjà fermé.
Il ne démontre donc ni la fermeture automatique d'un quota ouvert,
ni la reprise de l'API actuelle sur les chemins réels.

Le plan d'exercice complémentaire, sans exécution, est dans
`DOCNELO_PUBLIC_BETA_BACKUP_RESTORE_LAB_QUALIFICATION_PLAN.md`.

Un **GO futur de sauvegarde seulement** exigerait : release Linux identifiée,
voie autorisée sans refus de garde ignoré, contexte/chaîne/images H0
qualifiés, interruptions et écritures temporaires autorisées, quiescence
prouvée, chemins/clé/versions conformes, délais/RPO/RTO chiffrés, stockage
privé disponible, dépôt distant authentifié, backup antérieur récupérable
et traitement de reprise qualifié. Il n'autoriserait ni remplacement API,
ni restauration active, ni Lifecycle 10.

**Verdict actuel : NO-GO pour toute intervention sur la production.**
Seuls les contenus locaux et les limites documentaires ont été qualifiés.
Les scripts, releases, configurations et preuves existants restent inchangés.
