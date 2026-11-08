# Public Beta — Sauvegarde V5 chiffrée hors VPS

Procédure opérateur pour Linux, à déployer puis exécuter séparément. Aucune exécution VPS n'a été effectuée pendant cette évolution.

## Préparation

Utiliser une release physique directement sous `/opt/documind-public-beta` (pas un lien symbolique), Docker Compose, Restic et le Python de la release avec ses dépendances installées, notamment SQLAlchemy. Les conteneurs doivent déjà exister. Aucun `up`, provisionnement ou changement de configuration de production n'est nécessaire.

La configuration existante est exclusivement `/home/debian/.config/restic/documind-public-beta.env`, privée (`0600`). Elle doit contenir des affectations littérales, éventuellement préfixées par `export`, pour `B2_ACCOUNT_ID`, `B2_ACCOUNT_KEY`, `RESTIC_REPOSITORY` et `RESTIC_PASSWORD_FILE`. Ce dernier doit désigner un fichier privé existant dans le même répertoire, sans lien symbolique. Ne pas afficher, sourcer, recopier ou passer les secrets en arguments. Ne pas activer `set -x`.

Le bucket et le préfixe approuvés doivent provenir de l'inventaire opérateur Public Beta indépendant du fichier Restic. Ils ne sont pas connus dans ce dépôt : les renseigner avant les commandes ci-dessous. Le script exige une égalité exacte avec `b2:<bucket>:<prefix>`, y compris l'éventuel `/` initial du préfixe. La destination doit contenir `public-beta` et ne doit pas contenir `prod`.

Le latch existant est fixé explicitement à `/opt/documind-public-beta/recovery-state.json`. Il doit contenir exactement le schéma `{"format":1,"state":"ready"}` (ou un état valide `quarantined` / `serving_closed`). Le script le lit, valide son schéma et vérifie son montage en lecture seule vers `/run/documind/recovery-state.json`. Il ne change jamais son état. `RECOVERY_CONTROL_FILE` est fourni explicitement à tous les processus Compose, même si le fichier `.env.public-beta` contient une autre valeur.

## Enregistrer le dépôt une seule fois

Les variables ci-dessous sont des coordonnées non secrètes. Remplacer les deux valeurs d'attente par celles de l'inventaire approuvé ; elles sont volontairement refusées telles quelles.

```bash
set -euo pipefail
ROOT=/opt/documind-public-beta/public-beta-candidate-20261030T234818Z
EXPECTED_BUCKET=REPLACE_WITH_APPROVED_BUCKET
EXPECTED_PREFIX=REPLACE_WITH_APPROVED_PUBLIC_BETA_PREFIX
cd "$ROOT"
python3 -m tools.public_beta_backup --root "$ROOT" \
  --expected-bucket "$EXPECTED_BUCKET" --expected-prefix "$EXPECTED_PREFIX" \
  --record-repo-id
```

Ce mode ne capture ni ne transfère rien. Il valide d'abord bucket, préfixe et variables B2, interroge `restic cat config`, puis ajoute uniquement `DOCUMIND_PUBLIC_BETA_RESTIC_REPO_ID` au fichier Public Beta existant si absent. Un ID identique est accepté sans réécriture ; un ID différent est un échec. Ne jamais retirer l'ID pour contourner un conflit : diagnostiquer la destination avec l'opérateur.

## Capturer, valider et transférer

Dans le même shell préparé ci-dessus :

```bash
python3 -m tools.public_beta_backup --root "$ROOT" \
  --expected-bucket "$EXPECTED_BUCKET" --expected-prefix "$EXPECTED_PREFIX"
```

L'orchestrateur :

1. Prend un verrou interprocessus commun aux releases, dans `/opt/documind-public-beta/.public-beta-backup.lock`.
2. Charge explicitement les quatre variables Restic/B2 dans l'environnement des processus Restic. Aucun secret ambiant ni contenu du fichier n'est journalisé.
3. Vérifie bucket, préfixe et ID attendu avant l'arrêt ; vérifie projet Compose, noms exacts des trois volumes Public Beta et latch.
4. Arrête `api/web`, démarre uniquement le conteneur `db` existant. La capture exige ensuite DB seule, réseaux isolés, absence de clients DB et absence de conteneurs incontrôlés sur les volumes.
5. Capture avec `include_lifecycle_keys=True` dans un répertoire unique privé `var/backups/public-beta-v5-<UTC>-<uuid>`. Il utilise exclusivement ce chemin, sans sélection du dernier backup.
6. Exige format V5 et les deux clés `keys/authentication.key`, `keys/admission.key`. Vérifie les archives, permissions, SHA-256, les cinq stores, S2 et les empreintes de la base du projet Public Beta. Vérifie aussi que le latch capturé correspond au latch opérateur.
7. Recontrôle le latch et l'ID du dépôt, puis transfère le répertoire courant, le latch et les deux fichiers `.env.public-beta` / `.env.public-beta.images` via Restic.
8. Exige un code retour nul, aucun message d'erreur JSON, aucun stderr Restic (politique conservatrice), un résumé unique et un ID valide. Interroge cet ID distant ; exige un seul snapshot avec ID complet correspondant, tags de projet et d'exécution et chemins exacts.

La dernière ligne JSON doit indiquer `status=remote_verified`, `backup_dir`, `snapshot_id` complet et `services=api_web_stopped`. Le code retour doit être zéro. Conserver cette preuve dans le dossier opérateur. Une vérification de présence distante ne remplace pas un exercice de restauration isolée.

## Échec et reprise

Un code non nul ou `status=failed` impose le diagnostic. Les erreurs sont volontairement génériques pour éviter de divulguer des secrets. L'échec peut avoir lieu avant l'arrêt : contrôler l'état réel des services. Après l'arrêt, l'orchestrateur ne redémarre jamais `api/web`, même après succès. Il ne supprime aucune capture, même partielle. Un upload interrompu peut avoir créé un snapshot distant : conserver les données et examiner la situation avant de relancer une nouvelle capture.

Aucun nettoyage automatique ou manuel destructif n'est inclus. Aucune commande de suppression de volume, de réinitialisation, de déverrouillage ou de rétention Restic n'est autorisée dans cette procédure.

## Redémarrage manuel après succès

Seulement après preuve `remote_verified`, contrôle opérateur du latch et examen des exigences de reprise :

```bash
RECOVERY_CONTROL_FILE=/opt/documind-public-beta/recovery-state.json \
  docker compose --project-directory "$ROOT" -p documind-public-beta \
  --env-file "$ROOT/.env.public-beta" --env-file "$ROOT/.env.public-beta.images" \
  -f "$ROOT/compose.public-beta.vps.yaml" start api web
```

Le redémarrage ne doit pas modifier le latch ni ouvrir les admissions après restauration. Voir le [runbook VPS](VPS_BACKUP_RESTORE_RUNBOOK.md) pour déploiement et retour arrière.
