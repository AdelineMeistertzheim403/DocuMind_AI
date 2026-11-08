# Docnelo Public Beta — Runbook préparatoire d’ouverture à dix

31 octobre 2026. **NO-GO actuellement : ne pas exécuter de bascule.** Les commandes proposées ci-dessous n’ont pas été exécutées sur VPS. Les premières étapes sont des contrôles en lecture seule à faire par l’opérateur ; les actions d’ouverture ne deviennent applicables qu’après une nouvelle qualification et décision humaine.

## 1. Dossier de décision

Archiver de façon privée : preuve du déploiement Web R2, ID/architecture API réelle, empreintes des sources, état des migrations et quota, cohérence des témoins indépendants, statut du latch, dernière sauvegarde V5.1 et restauration labo, décision juridique avec versions/hashes, capacité disque et SMTP. Ne jamais collecter inspect complet/Env, .env, clés, jetons, emails d’utilisateurs ou dumps dans un ticket public.

Conditions cumulatives de GO :

- API active attestée, profil standard confirmé, nouvelle release dix signée/revue et protocole durable qualifié de bout en bout ; aucune garde contournée.
- État SQL et témoins cohérents, issued_count >=0 et <=10, comptes existants recensés, nombre total de personnes compatible avec le périmètre de cohorte approuvé.
- Nouvelle commande administrative à dix approuvée si closed=true ; pas de réouverture automatique ou SQL de reset.
- CGU/notice/confidentialité approuvées et publiées sous de nouvelles versions, anciennes versions inchangées ; API/UI/acceptations cohérentes.
- SMTP TLS/délivrabilité, reset et vérification qualifiés ; IA, owner demo et legacy désactivés ; capacité et sauvegardes adaptées à dix.
- Recette finale sur PostgreSQL 17 + lifecycle strict + BFF R2 passée, y compris onzième refusée, concurrence, crash/restart/restauration et fermeture d’urgence.
- Fenêtre, responsable, métriques, image de fermeture compatible dix et retour arrière validés.

Un test diagnostique en mode lifecycle réduit ne satisfait pas ces conditions. Un succès V5.1 ne signifie pas que le compteur restauré est frais.

## 2. Précontrôles opérateur en lecture seule

Sur Debian, shell dédié ; Docker local du VPS, noms techniques inchangés :

```bash
set -euo pipefail
umask 077
D=(docker --host unix:///var/run/docker.sock)
APP_ROOT=/opt/documind-public-beta/public-beta-candidate-20261030T234818Z
"${D[@]}" inspect --format '{{.Name}} {{.Image}} {{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}' \
  documind-public-beta-db-1 documind-public-beta-api-1 documind-public-beta-web-1
API_ID=$("${D[@]}" inspect --format '{{.Image}}' documind-public-beta-api-1)
"${D[@]}" image inspect --format '{{.Id}} {{.Os}}/{{.Architecture}} {{json .RepoDigests}}' "$API_ID"
"${D[@]}" image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$API_ID"
"${D[@]}" inspect --format '{{index .Config.Labels "com.docker.compose.project.config_files"}}' documind-public-beta-api-1
"${D[@]}" inspect --format '{{index .Config.Labels "com.docker.compose.project.config_files"}}' documind-public-beta-web-1
"${D[@]}" exec documind-public-beta-api-1 python -B -m alembic current
"${D[@]}" exec documind-public-beta-api-1 python -B -m backend.account_admin public-registration status
"${D[@]}" stats --no-stream documind-public-beta-db-1 documind-public-beta-api-1 documind-public-beta-web-1
df -h /opt/documind-public-beta
test -r /opt/documind-public-beta/recovery-state.json
cat /opt/documind-public-beta/recovery-state.json
```

Le latch est seulement lu. Il doit rester dans son état approuvé, jamais réécrit pour faire passer la recette. Si la CLI est indisponible ou refuse en Beta Lite, **arrêter**, ne pas changer le profil. Ne pas faire alembic upgrade/downgrade pendant cet audit.

Le probe livré deliveries/docnelo-10-users/api_readonly_probe.py est à relire et vérifier par empreinte avant transmission à l’opérateur. Il ne lit que les sources backend et une allowlist de paramètres non secrets ; pas de DB ni de réseau. Une fois placé dans un nouveau dossier d’audit privé, sans écraser la release active :

```bash
# Adapter uniquement ce chemin au fichier de probe privé vérifié.
PROBE=/home/debian/docnelo-ten-audit/api_readonly_probe.py
test -f "$PROBE"
"${D[@]}" exec -i documind-public-beta-api-1 python -B - < "$PROBE"
```

Comparer les hashes aux inventaires source-inventory.json et candidate-api-inventory.json. Si aucune correspondance ne permet de figer l’origine, obtenir l’archive/source API exacte via un circuit privé, sans publier ses fichiers. Ne pas inventer le commit à partir du seul nom de release.

Agrégats SQL, sans identifiants personnels, à exécuter **seulement si le schéma audité correspond** :

```bash
"${D[@]}" exec -i documind-public-beta-db-1 sh -c 'exec psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' <<'SQL'
BEGIN READ ONLY;
SELECT version_num FROM alembic_version;
SELECT id, issued_count, closed FROM public_registration_quota;
SELECT registration_kind, COUNT(*) AS accounts,
       COUNT(*) FILTER (WHERE email_verified_at IS NOT NULL) AS verified,
       COUNT(*) FILTER (WHERE email_verified_at IS NULL) AS unverified,
       COUNT(*) FILTER (WHERE disabled_at IS NOT NULL) AS disabled
FROM users GROUP BY registration_kind;
SELECT terms_version, COUNT(*) AS acceptances,
       COUNT(*) FILTER (WHERE terms_accepted_at IS NULL) AS missing_timestamp
FROM users WHERE registration_kind='public' GROUP BY terms_version;
SELECT table_name,column_name,data_type FROM information_schema.columns
WHERE table_schema='public' AND table_name IN ('public_registration_quota','users')
ORDER BY table_name,ordinal_position;
SELECT state, COUNT(*) FROM pg_stat_activity WHERE datname=current_database() GROUP BY state;
ROLLBACK;
SQL
```

Ne pas utiliser COUNT(users) pour remplacer issued_count : des comptes peuvent avoir été supprimés. Vérifier aussi les témoins via une commande de diagnostic approuvée de la release réelle, sans imprimer les clés ni fabriquer une nouvelle ancre. Ce dossier ne contient pas de commande qui certifie leur fraîcheur ou autorise S2.

La lecture HTTPS GET /bff/auth/options doit confirmer disabled/closed pendant cette phase. Préférer une sortie allowlist (mode, disponibilité, versions/URLs juridiques) ; ne jamais envoyer POST register/reset comme sonde VPS. Le certificat HTTPS doit être vérifié, sans option insecure.

## 3. Préparation hors VPS actif

1. Développer et faire revoir les lots décrits dans le plan d’implémentation : lifecycle dix, migration SQLite des témoins, administration, politique de livraison, emails et nouveaux textes. Ne pas inclure les changements non liés du workspace.
2. Qualifier les images/outils cibles dans un environnement jetable synthétique. Produire commits, IDs/digests, architecture, hashes, inventaires et procédures de migration/rollback testées.
3. Faire approuver juridiquement les nouvelles versions ; vérifier les preuves de conservation réelle. Ne pas définir PUBLIC_LEGAL_READY=true comme substitut à cette décision.
4. Préparer une release immuable distincte, sans lien current, sans changement des fichiers .env existants. Préparer une surcharge API dédiée pour la future configuration à dix ; préserver le Web R2 et tous les overrides actifs, dont le gate d’inscription et ses labels.
5. Préparer explicitement une version de fermeture compatible avec des compteurs 6..10. Ne pas recycler l’ancienne API bornée à cinq comme rollback automatique.

Configuration cible : PUBLIC_REGISTRATION_LIMIT=10, AI_ENABLED=false, OWNER_DEMO_ENABLED=false, LEGACY_API_ENABLED=false. Pendant toute la préparation, conserver REGISTRATION_MODE=disabled, le flag légal courant et le latch existant. Aucun exemple .env prêt à ouvrir n’est généré.

## 4. Séquence future d’ouverture, bloquée à ce stade

Cette séquence est une spécification opérateur, **pas un script applicable à la release actuelle**. Les IDs de l’API corrigée, sa migration lifecycle, la commande de réouverture dix et la version légale approuvée n’existent pas encore dans cette livraison ; fournir un docker compose up ou un UPDATE closed=false aujourd’hui masquerait ces blocages.

1. Fenêtre approuvée : relever les états/IDs/StartedAt et quotas, confirmer les inscriptions fermées, suspendre les autres opérations d’exploitation concurrentes selon la procédure revue.
2. Réaliser une nouvelle sauvegarde complète V5.1 avec l’outillage déjà approuvé, répertoire produit par la capture, deux clés lifecycle, validation S2 hors ligne, snapshot Restic distant vérifié et restauration isolée. Utiliser le runbook V5.1 existant ; aucun restic forget/prune, suppression locale ou sélection par ls -dt.
3. Installer uniquement les nouveaux artefacts approuvés dans une nouvelle release. Migrer les témoins selon la procédure qualifiée, en conservant toutes leurs séquences et preuves. Vérifier SQL et témoins avant toute ouverture.
4. Recréer seulement les services nécessaires avec leurs images figées et tous les overrides réels. Une configuration d’API ne peut pas être changée par docker restart ; elle exige une recréation contrôlée. Ne pas reconstruire PostgreSQL/Traefik ; ne pas recréer lifecycle-init comme raccourci de migration.
5. Maintenir disabled/closed pendant les contrôles de santé, UI juridique, BFF, capacité, absence IA et tests de reprise. Une sonde sur un compte technique existant et autorisé reste distincte d’un E2E créant/supprimant des données.
6. Décision humaine finale : version légale approuvée et configuration correspondante, puis changement de mode public avec la limite dix. Si closed=true, utiliser uniquement la future commande de réouverture approuvée, jamais la commande actuelle refusant dix. Préserver issued_count et les admissions déjà attribuées.
7. Valider GET options puis superviser la fenêtre. Ne créer aucun faux testeur sur la bêta. Les premiers inscrits doivent être les personnes effectivement autorisées.
8. À issued_count=10, vérifier full et refus de nouvelles attributions via métriques/lecture de l’état ; la fermeture ne bloque pas les comptes existants. Si souhaité, close explicite selon la procédure ci-dessous. Ne jamais simuler une onzième inscription sur le VPS pour vérifier le refus.

Tant que les éléments manquants ne sont pas qualifiés, rester au point 2 de ce runbook (lecture seule), pas à la séquence d’ouverture.

## 5. Suivi des dix admissions

Suivre issued_count, closed et mode effectif séparément des comptes présents/vérifiés/non vérifiés et du nombre de sessions. Agréger succès/quota/429/503, échecs SMTP et longueur de file, erreur de preuve/commit incertain, état des témoins. Ne pas stocker mots de passe, liens, adresses ou corps de requêtes dans le monitoring.

Avant la fenêtre, fixer des seuils d’arrêt selon la mesure réelle : disque et inodes (y compris marge d’une capture), mémoire/OOM/restarts Docker, CPU, connexions/attentes PostgreSQL, latence et erreurs HTTP. Une cadence opérateur de cinq minutes pendant l’ouverture est proposée, puis revue quotidienne, avec alertes immédiates pour quota incohérent, témoin pending, IA activée ou échec backup. Les limites source (500 Mio/owner, 5 Gio global) ne constituent pas une mesure de capacité VPS.

Le runbook V5.1 reste la référence de récupération. La promesse juridique de sauvegardes trois mois et les règles d’effacement doivent être reliées à une rétention réellement validée ; ne pas lancer un nettoyage pour « aligner » le texte pendant la fenêtre.

## 6. Fermeture d’urgence et rollback sans perte

Proposition de commande **future, pour une API standard attestée avec la CLI observée**, si ouverture déjà autorisée et nécessité réelle de fermer les nouvelles admissions :

```bash
"${D[@]}" exec documind-public-beta-api-1 python -B -m backend.account_admin public-registration close --execute
"${D[@]}" exec documind-public-beta-api-1 python -B -m backend.account_admin public-registration status
```

Cette fermeture est une écriture volontaire de closed=true, protégée par verrou de ligne ; **elle n’est pas exécutée pendant cette préparation**. Contrôler issued_count inchangé, options closed et accès des comptes vérifiés maintenu. En Beta Lite cette CLI refuse : appliquer seulement le plan de fermeture propre au profil confirmé, pas un changement opportuniste de profil. Si l’API est indisponible, déclencher la procédure d’incident opérateur ; aucun SQL improvisé n’est fourni pour contourner l’état durable.

Fermer ensuite le mode d’inscription par une surcharge/recréation API approuvée si nécessaire, en gardant la limite et le schéma compatibles dix, l’IA désactivée et le latch inchangé. Une fermeture n’est pas un purge-pending, un reset de compteur, une désactivation générale des comptes ou une restauration de la base d’avant ouverture.

Si le code doit revenir en arrière, utiliser uniquement l’image de fermeture préqualifiée compatible avec toutes les admissions déjà attribuées et les nouvelles tables/témoins. Après la sixième admission, retour à une version bornée cinq **interdit sans preuve de compatibilité**. Conserver la nouvelle version de textes acceptée dans ses archives. Si perte/corruption de données, traiter un incident séparé : services fermés aux nouvelles inscriptions, restauration V5.1 en laboratoire/quarantaine, réconciliation indépendante, puis décision opérateur ; aucune bascule automatique du latch ni restauration destructive.

## Verdict

**NO-GO ouverture.** Les contrôles locaux décrivent et testent le mécanisme et ses refus ; l’API active et les compteurs n’ont pas été lus sur VPS. Il faut une évolution lifecycle/outillage à dix et une approbation juridique avant toute ouverture. Aucune commande de changement de mode, quota, flag légal, latch ou déploiement n’a été exécutée sur le VPS.
