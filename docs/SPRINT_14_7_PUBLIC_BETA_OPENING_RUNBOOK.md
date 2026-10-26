# Sprint 14.7 — Plan futur d'ouverture de la bêta publique

**NON EXÉCUTÉ — aucune commande de ce document n'est une autorisation.**
État annoncé de production : Sprint 13 `8243e0511c5505a9cc70f76ad02392f7a816590d`,
schéma 0007, inscriptions publiques et IA désactivées. Cet état n'a pas été inspecté
à distance. Aucune intervention VPS, Registry, B2 ou SMTP réel pendant 14.6.

**Mise à jour locale du 26 octobre 2026 :** B14-10 est traité par le lot
[14.6.1](SPRINT_14_6_1_SECURE_ROLLBACK_REPORT.md), non publié/non déployé.
Le nouveau contrôleur exige une attestation CI cohérente, une approbation root
indépendante et les guards de sauvegarde installés. Ces prérequis n'existent pas
automatiquement sur le VPS. L'ouverture reste No-Go tant que les preuves CI,
installation/recette et décisions opératrice ci-dessous ne sont pas validées.

Référence : [rapport de recette 14.6](SPRINT_14_6_PREPRODUCTION_VALIDATION_REPORT.md).
Chaque étape exige une décision opératrice explicite. Publication CI, déploiement
fermé et **réouverture SQL** sont trois autorisations différentes. L'IA reste fermée.

## 1. Revue du code et publication CI

**Préconditions :** revue de tous les fichiers suivis/non suivis des phases 14.1–14.6,
correctif B14-10 validé, absence de secrets/artefacts/`var/` dans le commit, stratégie
de rollback corrigée approuvée. Aucune modification réelle de quota pendant la revue.
Réexaminer aussi RF10-03 (entrées de build et chaîne de dépendances) : l'acceptation
historique visait une unique publication privée, jamais une ouverture publique.
Elle ne s'étend pas automatiquement à cette livraison. Aucun nouvel audit CVE distant
n'a été exécuté dans 14.6 ; ne pas présenter les constats historiques comme réactualisés.

Commandes locales de contrôle, à adapter à la branche approuvée, sans publication :

```text
git status --short --branch
git diff --check
git diff --cached --name-only
```

**Effets futurs :** après autorisations distinctes de commit/push/PR/merge, les jobs
`python`, `windows`, `frontend` doivent réussir. Une fusion vers `main` peut publier
automatiquement trois images **linux/amd64** dans la Registry privée ; pas de déploiement
automatique. Ne pas lancer `publish` manuellement pour contourner un échec.

**Preuves :** SHA final, numéro de PR/run, résultats Linux/Windows/PostgreSQL/frontend/
BFF, trois références par digest et bundle attesté complet à neuf fichiers. Rejouer la recette
avec les **digests publiés**, pas les overlays locaux ni des tags modifiables.
Tester sur Linux 6.12 / ABI 6 ou documenter une validation équivalente approuvée.

**Arrêt :** test échoué/incomplet, fichier requis absent, digest manquant, architecture
autre que celle certifiée, ancien binaire dans la liste de retour. Publication partielle :
RF10-04, arrêt et conservation des preuves, aucune relance/suppression/retag automatique.

### Approbation indépendante de sécurité, avant le déploiement

Le profil reconnu est `public-beta-2026-10-v1`, compatible 0007. L'artefact contient
les six fichiers antérieurs, `release_security.py`, `backup_production.py` et
`security-attestation.json`. Le statement lie SHA, trois références par digest,
checksums des huit fichiers et repository/workflow/run/attempt CI.

Depuis des **outils actuels revus**, jamais un script issu d'un ancien candidat :

```bash
python3 "$REVIEWED_TOOLS/release_security.py" check "$REVIEWED_BUNDLE"
python3 "$REVIEWED_TOOLS/release_security.py" propose-trust "$REVIEWED_BUNDLE" > "$PRIVATE_PROPOSAL"
sha256sum "$REVIEWED_BUNDLE/security-attestation.json"
```

Ces commandes vérifient structure/checksums et préparent une proposition ; **elles
n'approuvent ni l'origine ni le profil**. L'opératrice doit vérifier séparément dans
GitHub le repository, SHA, run/attempt réussi, branche main protégée, contenu du
workflow actuel, tests requis et digests, puis revoir les correctifs applicatifs.
Les hashes ne sont pas une signature. Aucune attestation Sigstore ou autre preuve
cryptographique d'origine n'est supposée disponible.

Après autorisation d'administration dédiée, préparer un registre complet revu,
**fusionnant les entrées existantes et les candidats de secours à conserver**.
Ne pas écraser un registre existant avec la seule sortie `propose-trust`.
Installation future, à coordonner hors sauvegarde/déploiement sous leur verrou commun :

```bash
sudo install -d -o root -g root -m 0755 /etc/documind-ai
sudo install -o root -g root -m 0644 "$REVIEWED_TRUST_REGISTRY" /etc/documind-ai/release-security-trust.json
sudo install -d -o root -g root -m 0755 /srv/documind-ai/ops
sudo install -o root -g root -m 0644 "$REVIEWED_BUNDLE/backup_production.py" /srv/documind-ai/ops/backup_production.py
sudo install -o root -g root -m 0644 "$REVIEWED_BUNDLE/release_security.py" /srv/documind-ai/ops/release_security.py
```

Les chemins de staging ci-dessus doivent être réellement identifiés et revus ; ne
pas copier des fichiers non vérifiés. Le registre ne contient aucun secret, mais sa
propriété root et l'absence d'écriture groupe/autres sont obligatoires, de même que
son répertoire. Symlinks refusés. Aucun CLI/env du déployeur ne peut changer ce chemin.

Les deux scripts installés doivent avoir exactement les hashes de la version
attestée ; cela vaut aussi pour le candidat de retour. Les timers et la politique
de conservation restent inchangés. Un ancien script de sauvegarde ne doit pas
rester installé : il pourrait ignorer le verrou de maintenance de sécurité.
Le déployeur vérifie ce prérequis avant de stopper l'application renforcée.

La première version corrigée n'a pas nécessairement de précédent sûr : préparer
une autre version corrigée attestée si disponible, ou accepter explicitement l'arrêt
API/BFF et la correction en avant si le premier démarrage échoue. Ne jamais attester
artificiellement Sprint 13. Une future version de secours doit conserver les fixes
14.2–14.5, les guards 14.6.1, le schéma 0007 et la compatibilité des helpers installés.

## 2. Vérifications et approbations de production

**Préconditions :** autorisation d'accès VPS et de vérifications SMTP/B2 si nécessaires,
fenêtre DocuMind choisie, opératrice disponible, absence d'autre déploiement/maintenance.
Ne pas toucher aux autres projets Docker. Ne pas modifier les secrets.

Contrôles proposés, en lecture seule, uniquement après autorisation :

```bash
readlink -f /srv/documind-ai/current
df -h /srv/documind-ai /var/lib/docker
systemctl list-timers --all documind-backup.timer documind-monitor.timer documind-retention.timer
systemctl is-enabled documind-backup.timer documind-monitor.timer documind-retention.timer
```

Vérifier les configurations effectives **expurgées** : schéma 0007, un API/BFF, TLS,
Traefik existant `web`/`websecure`/`letsencrypt`, proxy de confiance réel, inscriptions
encore fermées et IA/demo/legacy false. Ne pas publier `docker inspect` complet,
`docker compose config` complet, env, cookies, DSN ou paramètres SMTP.

### Checklist opératrice SMTP et légal

- [ ] Autorisation d'envoyer à une boîte de recette appartenant à l'opératrice ;
  aucun test vers un destinataire tiers ni inscription réelle improvisée.
- [ ] Certificat SMTP/chaîne/hostname vérifiés, TLS direct ou STARTTLS sans repli clair,
  authentification réussie, expéditeur autorisé et bonne origine HTTPS des comptes.
- [ ] SPF, signature DKIM et politique DMARC cohérents ; réception observée, délai
  et indésirables vérifiés, liens sur le domaine DocuMind et jamais en query string.
- [ ] Vérification et renvoi après échec observés, ancien lien refusé ; aucune donnée
  du message/token dans les journaux ou preuves partagées. Un succès SMTP seul ne
  prouve pas la remise en boîte et un HTTP 202 ne prouve pas l'envoi.
- [ ] Mentions légales, confidentialité et CGU publiées et accessibles ; identité,
  coordonnées, version de consentement, conservation et suppression approuvées.
- [ ] Navigation clavier/lecteur d'écran, contraste, zoom et mobile réel examinés.
- [ ] Risque de file RAM et de places consommées en attente explicitement accepté,
  ou correctif ciblé livré ; saturation du reset et surveillance traitées.

Ni Codex ni le validateur `PUBLIC_LEGAL_READY` ne valident juridiquement ces textes.

### Vérification future Restic/B2, avec autorisation propre

Les secrets restent dans `/home/debian/.config/restic/documind.env`. Ne pas les
afficher ni les passer sur la ligne de commande. Le lecteur sécurisé existant gère
`export`, `RESTIC_PASSWORD_FILE` et B2 sans exécuter de shell. Exemple à faire revoir
sur le VPS autorisé, avec journaux privés et verrou partagé, **jamais exécuté ici** :

```bash
cd /srv/documind-ai
umask 077
python3 - <<'PY'
from pathlib import Path
import subprocess, sys, tempfile
sys.path.insert(0, '/srv/documind-ai/ops')
import backup_production as backup
root = Path('/srv/documind-ai')
with backup.deployment_lock(root):
    env = backup.restic_environment()
    evidence = Path(tempfile.mkdtemp(prefix='b2-check-', dir=root / 'var'))
    with (evidence / 'snapshots.json').open('wb') as out, (evidence / 'diagnostics.log').open('wb') as err:
        subprocess.run(['restic', 'snapshots', '--json', '--tag', 'documind-ai'],
                       env=env, stdout=out, stderr=err, check=True, timeout=300)
    with (evidence / 'check.log').open('wb') as out:
        subprocess.run(['restic', 'check'], env=env, stdout=out,
                       stderr=subprocess.STDOUT, check=True, timeout=1800)
    print('Vérification terminée ; preuves privées enregistrées.')
PY
```

Cela contacte B2 et peut consommer des opérations : approbation requise. Aucun
`init`, `unlock`, `forget`, `prune`, restauration de production ou changement de
politique. Retenir un identifiant **complet** de snapshot confirmé ; ne pas se
contenter de `latest` ou d'un préfixe ambigu. Préparer une restauration indépendante
dans une cible neuve hors service, vérifier les SHA-256, inventaire v2, schéma,
documents, compteur et verrou, puis fermer la copie. Un inventaire v1 reste lisible
mais ne certifie pas le quota. Une sauvegarde ancienne exige réconciliation des
admissions avant toute réouverture, jamais remise à zéro.

Le CLI historique `validate_restore.py` utilise des defaults Compose/DB : ne pas
le lancer aveuglément contre la production. Employer un préfixe Compose explicitement
isolé et les fonctions éprouvées `verify_snapshot(..., compose=...)` et
`seal_restored_registration()` sur cette copie, selon procédure revue.

**Effet attendu :** dossier d'approbation sans changement de service ni ouverture.
**Preuves :** espace disponible, santé, timers, snapshot confirmé/restauration, réception
SMTP et textes approuvés, sans données de destinataire ni tokens.
**Arrêt :** backup ancien/non vérifié, alerte disque, version inconnue, indisponibilité
SMTP, textes absents, risque non accepté ou impossibilité de fermer rapidement.

## 3. Contrôle du compteur et fermeture SQL

**Préconditions :** release active identifiée, schéma 0007, autorisation de fermeture,
pas de maintenance concurrente. Les commandes suivantes ciblent uniquement DocuMind.

```bash
ROOT=/srv/documind-ai
CURRENT="$(readlink -f "$ROOT/current")"
export ROOT CURRENT
python3 - <<'PY'
import os
from pathlib import Path
root = Path(os.environ['ROOT']).resolve()
current = Path(os.environ['CURRENT']).resolve(strict=True)
assert current.parent == root / 'releases'
assert (current / 'release.json').is_file() and (current / 'images.env').is_file()
PY
dc() {
  docker compose --project-directory "$ROOT" --project-name documind-prod \
    --env-file "$ROOT/.env.production" --env-file "$CURRENT/images.env" \
    -f "$CURRENT/compose.production.yaml" "$@"
}
dc exec -T api python -m backend.account_admin public-registration status
dc exec -T api python -m backend.account_admin public-registration close
dc exec -T api python -m backend.account_admin public-registration close --execute
dc exec -T api python -m backend.account_admin public-registration status
```

**Effets :** `close` sans flag simule ; avec flag verrou fermé, compteur inchangé,
comptes conservés. Une transaction ayant réservé avant l'acquisition du verrou peut
terminer ; prendre pour référence le statut après fermeture confirmée.
**Preuves :** JSON avant/après horodatés, opératrice, SHA, compteur et limite ; pas de
liste d'adresses. **Arrêt :** ligne absente, compteur négatif/incohérent, changement
inexpliqué ou fermeture non confirmée. À cinq, aucune nouvelle place ne peut être ouverte.

## 4. Déploiement candidat, inscriptions toujours fermées

**Préconditions :** étapes 1–3 validées et B14-10 corrigé ; candidat et retour sûr
revus, sauvegarde possible, configuration approuvée explicitement pour
`public / 5 / AI_ENABLED=false / OWNER_DEMO_ENABLED=false / LEGACY_API_ENABLED=false`.
Ne pas éditer un env en croyant changer un processus vivant ; aucune commande de
modification de secret n'est proposée ici.

Workflow manuel `deploy.yml`, environnement `production` avec approbation :

| Entrée | Valeur à choisir après approbation |
| --- | --- |
| `release_sha`, `ci_run_id` | SHA complet et run réussi réellement contrôlés |
| `operation` | `deploy` |
| `initialize` | `false` |
| `allow_migration` | `false` : schéma déjà 0007 |
| `approve_public_beta` | `true` uniquement pour la préparation publique fermée |

Le flag ne rouvre jamais le SQL. Le déployeur sauvegarde sous verrou, vérifie la
configuration résolue puis celle de l'image, le compteur/verrou avant/après et
les healthchecks/HTTPS. Pas de build sur VPS. Le déployeur ordinaire appelle aussi
`up db` et `upgrade head` : la migration est un no-op si head reste 0007, mais un
nouveau digest PostgreSQL peut recréer **le PostgreSQL DocuMind**. Prévoir cette
interruption dans l'approbation ; ne pas prétendre que cette opération est le backup
quotidien qui, lui, ne redémarre pas PostgreSQL.

Le workflow utilise désormais un contrôleur issu du checkout actuel de main protégé,
stagié séparément sous `deploy-controls/<SHA-du-contrôleur>-<run>-<attempt>`, avec
`--bundle <chemin-du-candidat>`. Il n'exécute jamais le déployeur d'un ancien bundle
cible. Conserver dans les preuves les deux identités : contrôleur et candidat.

**Effets :** version candidate active, verrou toujours fermé et compteur identique.
**Preuves :** rapport complet, sauvegarde, trois digests, current et schéma, santé et
`public_beta.quota_before/after`. **Arrêt :** digest/version différent, migration
inattendue, quota ouvert/modifié, backup ou démarrage/HTTPS en échec. Aucun lien current
créé à la main et aucune relance automatique après échec.

## 5. Contrôles après livraison fermée

**Préconditions :** livraison réussie et current confirmé ; reconstruire la fonction
`dc` avec **le nouveau current** (étape 3), sans réutiliser l'ancien chemin.

```bash
dc ps
dc exec -T api alembic current
dc exec -T api python -m backend.account_admin public-registration status
curl --fail --show-error https://documind.adelinemeistertzheim.fr/bff/health
```

Vérifier les trois services healthy et leur architecture/digest sans afficher
l'inspection entière. Relever seulement les flags non sensibles, schéma et capacité.
Les contrôles de compte/document doivent utiliser des comptes fictifs déjà autorisés,
pas consommer une nouvelle admission sans décision. Les tests SMTP réels restent
conditionnés à l'autorisation de l'étape 2. Aucun appel IA, même pour « valider une clé ».

**Effets :** preuves de fermeture, fonctionnement classique et refus IA. **Preuves :**
version, santé/HTTPS, fermeture, CSRF/cookies et réception SMTP autorisée. **Arrêt :**
session/proxy/Host/Origin défaillant, IA activée, comportement divergent ou logs sensibles.

## 6. Décision Go / No-Go distincte

**Préconditions :** tous les points bloquants du rapport 14.6 levés, recette des
images publiées réussie, fermeture et retour sûrs, personne disponible pour surveiller.
Accepter par écrit cinq admissions **cumulatives**, comptes en attente inclus,
aucun recyclage de place après suppression et limites NAT trois demandes/heure/IP.

**Effet attendu :** décision datée de l'opératrice, liée aux SHA/digests, domaine,
compteur connu, preuve SMTP/juridique et risque RAM. **Preuve :** checklist signée
ou dossier de décision privé. **Arrêt :** point non validé ; rester fermé. Une CI
verte ou un déploiement réussi ne remplace pas cette autorisation.

## 7. Réouverture SQL explicite et vérifiée

**Préconditions :** autorisation d'ouverture propre à cette exécution, profil public
5/IA/demo/legacy fermés, quota cohérent `0 <= issued_count < 5`, fenêtre surveillée,
current corrigé et aucune maintenance. Aucun flag de workflow ne vaut cette décision.

```bash
dc exec -T api python -m backend.account_admin public-registration status
dc exec -T api python -m backend.account_admin public-registration reopen
# Seulement après validation du résultat simulé et de l'autorisation :
dc exec -T api python -m backend.account_admin public-registration reopen --execute
dc exec -T api python -m backend.account_admin public-registration status
```

**Effets :** ouverture du verrou uniquement, pas de création de compte ni de remise
à zéro ; une admission peut suivre immédiatement la réouverture. **Preuves :** JSON
avant/après et compteur monotone, mode/limite et capacité frontend. **Arrêt :** profil
incorrect, compteur cinq, statut ambigu ou absence de confirmation ; ne pas corriger
par SQL manuel, suppression de compte ou augmentation de plafond.

## 8. Surveillance des premières inscriptions

**Préconditions :** opératrice disponible, fermeture d'urgence prête ; pas d'inscription
réelle de test supplémentaire. **Effets :** aucune mutation hors inscriptions demandées
par les utilisateurs ; contrôle rapproché puis fréquence décidée selon observations.

Relever compteur/verrou et santé toutes les deux à cinq minutes pendant la première
heure. Examiner les événements SEC10-04 expurgés ; ne pas transmettre les logs bruts.
Exemple de décompte restreint, sans adresses, headers ou corps :

```bash
dc logs --no-color --no-log-prefix --since 1h api web 2>&1 | python3 -c '
import collections,json,sys
allowed={"system.mail.failed","system.database.unavailable","system.audit.dropped",
 "account.registration.requested","account.registration.denied","account.email.verified","rate_limit.exceeded"}
counts=collections.Counter()
for line in sys.stdin:
 try: row=json.loads(line)
 except ValueError: continue
 event=row.get("event") if isinstance(row,dict) else None
 if event in allowed: counts[event]+=1
print(json.dumps(counts,sort_keys=True))'
```

Ne pas appeler les CLI `owners`/`invite` pour alimenter un journal : leur sortie est
sensible. Le monitoring à 08:00 ne prouve pas une alerte immédiate pour chaque mail.
Ne pas ouvrir de métrique publique de profondeur de file. Conserver seulement les
comptages, états et décisions dans les preuves partagées.

**Preuves :** admissions/vérifications agrégées, erreurs/débit, disque/backup. **Arrêt :**
mail répété en échec, état SQL incohérent, accès croisé, IA active ou service instable :
étape 9. À cinq admissions, vérifier capacité indisponible et fermer explicitement ;
ne pas libérer une place en supprimant un compte.

## 9. Fermeture d'urgence

**Préconditions :** identité du current et connexion opératrice fiables ; aucune
autorisation de restauration nécessaire pour fermer les nouvelles admissions.

```bash
dc exec -T api python -m backend.account_admin public-registration status
dc exec -T api python -m backend.account_admin public-registration close --execute
dc exec -T api python -m backend.account_admin public-registration status
curl --fail --show-error https://documind.adelinemeistertzheim.fr/bff/health
```

**Effets :** fermé, compteur conservé ; pas d'arrêt PostgreSQL/Traefik, pas de suppression
de compte, pas d'invalidation générale des sessions. Connexion/vérification/renvoi
existants restent disponibles selon les règles. Un mail d'une admission antérieure
peut arriver après fermeture.
**Preuves :** incident, opératrice, SHA/date et JSON fermé ; capacité publique indisponible.
**Arrêt :** fermeture non confirmée : annoncer l'incertitude, diagnostiquer ; ne jamais
compenser avec reset, down -v, restauration ou arrêt des autres applications.
Une fermeture de configuration vers disabled est une décision/delivery séparée.

## 10. Retour applicatif compatible sans downgrade improvisé

**Préconditions :** admissions confirmées fermées, snapshot cohérent, B14-10 corrigé,
candidat de retour explicitement attesté par CI et tests des correctifs 14.2–14.5,
schéma 0007 supporté. Le Sprint 13 seul n'est **pas** admissible.

Après revue du bundle réel sous `/srv/documind-ai/releases/`, commande du déployeur
existante à réévaluer avec le correctif B14-10, **ne pas exécuter maintenant** :

```bash
# CANDIDATE est le chemin réel du bundle CORRIGÉ et approuvé, jamais un ancien SHA improvisé.
python3 "$REVIEWED_CONTROLLER/deploy_production.py" --bundle "$CANDIDATE" --root /srv/documind-ai --rollback --approve-public-beta
```

Ou sélectionner `operation=rollback` dans le workflow manuel protégé avec SHA/run
attestés ; jamais `initialize=true` ou une migration approuvée par défaut.
**Effets :** changement applicatif contrôlé, compteur et verrou conservés, aucune
restauration ou descente de schéma automatique. **Preuves :** rapport, sauvegarde,
digests et santé, fermé avant/après. Reconnexion des sessions RAM attendue.
**Arrêt :** absence de candidat corrigé, schéma incompatible, preuve manquante ou
échec de santé : rester fermé et traiter l'incident. Ne pas contourner par un ancien
script, un current fabriqué, une image retaguée ou une modification d'ancien rapport.

`REVIEWED_CONTROLLER` est le contrôleur actuel revu et identifié, pas le répertoire
du candidat de retour. Tout rollback manuel exige une approbation indépendante,
même en mode disabled. Le redémarrage automatique exige aussi un candidat attesté
dès qu'un profil est adopté, qu'une source/cible est publique ou que des identités/
admissions publiques existent. Le simple passage de public à disabled n'efface pas
cette obligation. Les opérations historiques fermées sans passé public peuvent
rester compatibles, mais ne sont pas certifiées rétroactivement.

Sans précédent sûr, API/BFF restent arrêtés, PostgreSQL et les données restent en
place. `var/security-maintenance.json` bloque la sauvegarde et son `--resume`, même
si current désigne encore l'ancien bundle. Ne pas supprimer ce marqueur à la main.
Préparer une correction en avant, même schéma 0007, nouvelle CI réussie, attestation,
approbation root et guards installés, puis utiliser le contrôleur actuel avec le
nouveau `--bundle`. Après succès seulement, le contrôleur enlève son marqueur et les
opérations normales peuvent reprendre. Aucune restauration/downgrade n'est nécessaire
pour ce cas. Si un marqueur de sauvegarde antérieur existe aussi, préserver les deux
preuves et faire revoir une procédure dédiée : ne pas débloquer par suppression.

La sauvegarde quotidienne d'un current certifié vérifie à nouveau son approbation
et ses images avant reprise ; elle conserve le verrou SQL tel quel, ouvert ou fermé.
Une révocation bloque cette reprise. Toute évolution du registre doit donc être
coordonnée avec la maintenance ; conserver un candidat sûr utilisable avant révocation.

Ce runbook n'active aucun timer, aucune purge, aucun service ni inscription.
**L'ouverture demeure interdite sans autorisation explicite ultérieure.**
