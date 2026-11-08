# Public Beta — Finalisation V5 : orchestration et rapport de tests

Date : 2026-10-31. Travail et tests locaux uniquement. Aucune commande sur le VPS, aucun fichier de production modifié pendant cette intervention. Les modifications graphiques Docnelo déjà présentes dans l'espace de travail n'ont pas été touchées ni incluses dans le périmètre ci-dessous.

## Livrables et périmètre de livraison

- `tools/public_beta_backup.py` : nouvel orchestrateur Linux opérateur, avec verrou partagé entre releases.
- `tools/public_beta_restic_guard.py` : validation explicite du bucket/préfixe avant enregistrement, ajout sous verrou sans troncature, refus des conflits, contrôle des réponses et de stderr Restic.
- `tools/verify_snapshot.py` : capture de stderr de la vérification PostgreSQL pour éviter son exposition dans le terminal de l'orchestrateur. Les autres changements V5 de ce helper étaient déjà présents.
- `tests/test_public_beta_backup.py` : simulations de l'orchestration sans réseau ni Docker.
- `tests/test_public_beta_restic_guard.py` : adaptation du test d'enregistrement aux coordonnées B2 approuvées et permissions privées.
- `ops/public_beta/BACKUP_ENCRYPTED_OFF_VPS.md` : procédure exécutable via le module Python ; suppression des anciennes chaînes manuelles et du chemin alternatif GPG non validé.
- `ops/public_beta/VPS_BACKUP_RESTORE_RUNBOOK.md` : déploiement, exploitation et retour arrière.
- Le présent rapport.

Les helpers de capture/restauration V5 existants et leurs dépendances doivent accompagner la release. Ce périmètre ne constitue pas un bundle complet déployé : ne pas exporter sans revue l'ensemble de cet espace de travail, qui comporte d'autres modifications préexistantes.

## Garanties mises en œuvre

| Exigence | Contrôle |
| --- | --- |
| Variables Restic explicites | Environnement dédié à chaque processus Restic avec B2_ACCOUNT_ID, B2_ACCOUNT_KEY, RESTIC_REPOSITORY, RESTIC_PASSWORD_FILE ; aucun sourcing shell |
| Fichier existant | Chemin fixé à /home/debian/.config/restic/documind-public-beta.env ; aucun accès à la configuration Restic de production |
| Destination et ID | Coordonnées B2 fournies indépendamment, comparaison exacte avant tout enregistrement ou upload ; ID existant différent refusé ; ID identique non réécrit |
| Latch explicite | /opt/documind-public-beta/recovery-state.json transmis via RECOVERY_CONTROL_FILE ; schéma et montage readonly vérifiés ; contenu capturé comparé ; aucun changement d'état |
| Répertoire courant | Chemin unique UTC + UUID passé directement à create_backup puis à la validation et à Restic ; aucune recherche du dernier répertoire |
| Validation avant upload | Format strictement V5, deux clés obligatoires, inventaires/archives/permissions/empreintes et S2, empreintes PostgreSQL et quota certifié |
| Confirmation distante | Codes retour, stderr et erreurs JSON vérifiés ; résumé unique ; ID distant complet exact ou résolution unique d'un ID court de huit caractères ; tags et chemins contrôlés |
| Échec conservateur | Aucune suppression de capture ni reprise automatique ; après arrêt, api/web restent arrêtés ; contrôle réel des services requis si échec préalable |
| Opérations limitées | Aucun down, aucune suppression de volume, aucun init/unlock/forget/prune Restic ; seule mutation du dépôt : création de la sauvegarde demandée |
| Isolation Public Beta | Projet et noms exacts des trois volumes vérifiés avant arrêt ; contrôle de quiescence/réseaux/conteneurs par le helper de capture |

Le mode `--record-repo-id` est distinct de la capture : son seul effet de configuration est l'ajout de l'ID au fichier Public Beta existant. Le mode de sauvegarde ne réécrit aucun fichier de configuration. Les exceptions ne sont pas imprimées ; le diagnostic CLI est volontairement générique pour éviter les fuites de secrets.

## Résultats des tests locaux

Commande réellement exécutée sous Windows avec le Python de l'environnement virtuel du projet :

```powershell
.\.venv\Scripts\python.exe -m pytest -q --tb=short tests/test_public_beta_backup.py tests/test_public_beta_restic_guard.py tests/test_backup_offline_compose.py tests/test_public_beta_snapshot.py tests/test_snapshot_backup_integrity.py tests/test_lifecycle_keys_restore.py
```

Résultat final : **49 réussis, 0 échoué, 6 ignorés**, en 5,02 secondes. Un avertissement de dépréciation Starlette/httpx est émis.

Les 25 cas d'orchestration couvrent notamment :

- upload réussi avec sauvegarde ancienne déjà présente, environnement Restic explicite et utilisation exclusive de la capture courante ;
- échec réseau à la lecture du dépôt, pendant l'upload et pendant la confirmation distante ;
- dépôt d'ID incorrect, mauvais bucket ou préfixe et préfixes non sûrs ;
- format V4, clé manquante, rejet S2 et échec de capture partielle ;
- snapshot distant absent, ID incohérent, résumé sans ID, message d'erreur JSON et stderr Restic ;
- résolution d'un ID court vers l'ID distant complet ;
- conservation des fichiers locaux et absence de reprise/destruction ;
- absence de secrets et de traceback dans l'échec CLI ;
- conflit d'ID enregistré et idempotence de l'enregistrement existant ;
- mauvais volume, mauvais montage du latch ou schéma de latch invalide avant arrêt.

Les tests existants vérifient aussi les archives V5 réelles générées localement : clés absentes/altérées, permissions, membres inattendus et restauration des clés dans l'arbre isolé.

Les 6 tests ignorés sont les intégrations PostgreSQL/Docker de `test_public_beta_snapshot.py`, conditionnées à `TEST_SNAPSHOT_COMPOSE` et à un projet Docker jetable explicitement configuré. Aucune intégration B2 réelle, capture Docker VPS ou restauration réelle distante n'a été exécutée. Les verrous `fcntl` et permissions Linux doivent être vérifiés dans l'environnement Linux de recette avant exploitation ; ils n'ont pas été exercés par ces simulations Windows.

## Déploiement VPS et retour arrière

Les commandes et préconditions sont dans [VPS_BACKUP_RESTORE_RUNBOOK.md](VPS_BACKUP_RESTORE_RUNBOOK.md) et [BACKUP_ENCRYPTED_OFF_VPS.md](BACKUP_ENCRYPTED_OFF_VPS.md).

Déployer une release Public Beta séparée, conserver la précédente, vérifier dépendances/aide/compilation, puis faire valider par l'opérateur les coordonnées B2 indépendantes, les fichiers privés existants et le latch. Le bucket et le préfixe réels ne sont pas fournis dans ce dépôt : les exemples exigent leur substitution explicite, jamais leur déduction depuis la configuration à contrôler.

En cas d'échec, conserver les sauvegardes locales, contrôler les services et diagnostiquer. Pour revenir au code précédent, sélectionner la release opérateur précédente sans modifier le latch, les secrets, les volumes ou le dépôt. Conserver les outils V5 pour vérifier les captures V5 déjà créées. Aucun rollback de données ni redémarrage automatique n'est prévu. Toute restauration reste isolée et quarantinée, admissions fermées jusqu'à revue opérateur.
