# Sprint 14.4 — Quota public, identité et concurrence PostgreSQL

Date : 25 octobre 2026. Branche locale :
`preparation/sprint-14-4-quota-concurrency`, issue de l'arbre de travail non commité
des Sprints 14.2/14.3, sans retour à `main` ni perte de modifications.

**Ouverture publique : toujours No-Go.** Ce lot est une correction et une validation
locales. Aucun accès VPS, déploiement, commit, push, merge, activation d'inscriptions
ou d'IA en production. Aucun secret ni document réel, SMTP ou fournisseur IA réel.
Le schéma reste `0007` ; aucune migration nouvelle.

## 1. État initial et constats reproduits

Les rapports 14.1, 14.2 et 14.3 ont été relus. Les 27 fichiers déjà modifiés/non
suivis en début de mission ont été relevés par SHA-256 pour contrôler leur préservation.

Deux défauts sont reproduits avant correction :

- **B14-08** : après inscription, affecter `disabled_at` pour bloquer volontairement
  le compte n'empêchait pas `verify()` d'effacer ce champ et d'activer le compte.
  Le nouveau test recevait HTTP 200 au lieu du refus attendu.
- Un compteur négatif était annoncé disponible par `/auth/options` et satisfaisait
  le prédicat d'admission `issued_count < limit`. La première sélection a donné
  7 réussites et 2 échecs reproduisant ces défauts.

Le plafond positif et la fermeture disposaient déjà d'un `UPDATE` SQL conditionnel.
L'audit B14-03 demandait cependant une preuve du parcours complet avec transactions
indépendantes, au-delà du sémaphore RAM. B14-06 concernait l'absence du quota dans
l'inventaire d'intégrité complémentaire des sauvegardes.

## 2. Fichiers concernés

| Fichier | Modification 14.4 |
| --- | --- |
| `backend/public_registration.py` | Prédicat de compteur non négatif ; distinction attente/blocage ; renvoi refusé pour un compte bloqué ; vérification ne levant jamais un blocage. |
| `backend/account_api.py` | Capacité fermée si compteur négatif ; récupération/reset réservés aux comptes non bloqués. |
| `backend/account_admin.py` | Commande locale `pending-account block/release`, simulation par défaut, invalidation des liens et trace horodatée ; purge des comptes en attente excluant les blocages. |
| `tools/backup_local.py` | Inventaire du quota si présent, obligatoire en `0007`, et marqueur `integrity_version=2`. |
| `tools/verify_snapshot.py` | Vérification compteur/verrou ; compatibilité explicite des inventaires antérieurs ; fonction réutilisable sur projet isolé, toujours en lecture seule. |
| `tools/validate_restore.py` | Fermeture de la copie restaurée après vérification fidèle, sans changement de compteur ni d'archive. |
| `tests/test_public_beta_state.py` | Quota cinq/six, comptes historiques/invités, vérification, blocage/revue explicite et conservation. |
| `tests/test_public_beta_postgresql_concurrency.py` | Neuf scénarios PostgreSQL réels avec instances et connexions indépendantes. |
| `tests/test_public_beta_snapshot.py` | Compatibilité/versionnement, quatre restaurations indépendantes et altérations SQL réelles des deux champs. |
| `tests/test_public_beta.py` | Assertion d'état d'attente adaptée, en gardant les refus de login et d'upload avant vérification. |
| `tests/test_public_beta_authorization.py` | Même adaptation d'une assertion d'état, sans modifier les tests d'autorisation ni de compteur. |
| Ce rapport | Décisions, résultats et limites. |

Parmi les fichiers des Sprints 14.2/14.3, seuls `backend/account_admin.py` est étendu
et une assertion de `tests/test_public_beta_authorization.py` est adaptée au nouvel
état d'attente. Les autres empreintes sont conservées. Les contrôles d'autorisation
14.2 et les gardes IA 14.3 ne sont pas retirés. Aucun workflow, Compose de production,
Dockerfile, secret, politique Restic ou mécanisme Landlock/seccomp n'est changé par ce lot.

## 3. Politique exacte des cinq admissions

Le plafond reste **cinq admissions publiques cumulatives** :

- Historiques et invitations ne consomment pas le compteur.
- Une inscription publique admise consomme une place avant vérification d'email.
- Désactivation, suppression, purge, absence de vérification et échec ultérieur de
  livraison d'email ne rendent pas cette place.
- Fermeture/réouverture ne remettent jamais `issued_count` à zéro.
- La sixième demande reste un HTTP 202 générique, **sans** nouveau compte, workspace,
  membership ou jeton. Un 202 seul ne prouve donc pas une admission.

Le SQL exige maintenant simultanément la ligne `id='public'`, `closed=false`,
`issued_count >= 0` et `issued_count < limit`, puis incrémente et retourne le compteur.
L'incrément et la création du workspace/compte/jeton restent dans la même transaction.
L'absence de ligne, un compteur négatif ou un compteur au-dessus du plafond refuse
l'admission ; aucune réparation ou remise à zéro automatique n'est tentée.
L'interface de capacité tient également compte de la borne inférieure.

La limite 5 demeure imposée par les contrôles de livraison du Sprint 14.2. Le
sémaphore de création est conservé comme limite de ressources, pas comme preuve
d'atomicité SQL. Les limites IP/PoW sont testées séparément du quota ; les tests
de quota utilisent uniquement des IP fictives et des paramètres de fixture explicites.

## 4. Preuves de concurrence PostgreSQL réelle

PostgreSQL local 17/pgvector, base neuve dédiée et comptes fictifs. Le harnais démarre
deux instances FastAPI de test partageant seulement la base. Chacune dispose de ses
propres challenges, sémaphores, sessions SQLAlchemy et moteurs de connexion : le
premier sémaphore RAM ne peut pas rejeter la seconde admission à la place du SQL.
La production reste prévue avec un seul processus ; ce test n'autorise pas son scaling.

Les barrières SQL et événements coordonnent les opérations. Les tests observent
des `pg_backend_pid()` distincts et, pour les courses de fermeture, l'attente `Lock`
dans `pg_stat_activity`. Aucun délai fixe n'est utilisé pour deviner un ordre ; le
polling attend un état serveur précis. Délais de sécurité : barrières/événements
bornés, `lock_timeout` 8 s et `statement_timeout` 12 s sur transactions de test,
avec libération des événements et retrait des listeners en `finally`.

| Scénario | Résultat vérifié |
| --- | --- |
| Deux emails distincts à `issued_count=4` | Deux HTTP 202 génériques ; un seul compte/workspace/jeton supplémentaire ; compteur final 5. |
| Même email, deux transactions ayant lu son absence | Une seule identité ; rollback du perdant après conflit d'unicité ; aucun workspace/jeton orphelin ni place perdue. |
| Deux vérifications du même lien | Un 200 et un 400, une activation, même propriétaire/workspace et aucune session créée. |
| Deux renvois de vérification | Deux 202 ; un seul jeton actif après sérialisation, anciens liens refusés, seul le dernier jeton encore actif vérifie le compte. |
| Admission réservant avant fermeture | La fermeture attend réellement ; l'admission termine, puis verrou fermé à 5. |
| Fermeture écrivant avant admission | L'admission attend puis réévalue le prédicat fermé ; 202 générique sans compte, compteur restant à 4. |
| Admission pendant une réouverture non committée | Aucun compte créé pendant l'état fermé ; après commit, une nouvelle demande peut prendre la cinquième place. |
| Erreur injectée après réservation avant émission du jeton | HTTP 500 contrôlé dans le harnais ; compteur/compte/workspace/membership/jetons inchangés après rollback ; une demande suivante utilise la place. |
| Blocage administratif et vérification simultanés | Même verrou utilisateur : blocage gagnant → vérification refusée ; vérification gagnante → opération réservée aux comptes en attente refusée. |

Les neuf cas passent dans la campagne de non-régression, puis deux répétitions
complètes supplémentaires (9/9 à chaque fois), sans deadlock ni attente permanente
observés. Cela couvre ces entrelacements déterministes ; ce n'est pas une preuve
formelle de toutes les charges possibles.

Un premier harnais avait donné huit échecs HTTP 500 : son override de dépendance
FastAPI exposait par erreur l'objet application comme paramètre par défaut de route.
Il a été remplacé par une fermeture sans paramètre HTTP. Aucun contrôle applicatif
n'a été affaibli pour corriger ce défaut de test.

## 5. Vérification email, identité et isolation

Les tests couvrent lien valide, expiré, altéré, consommé et mauvais mot de passe.
Un mot de passe incorrect ne consomme pas définitivement le jeton : le rollback
préserve sa disponibilité. Après renvoi, les anciens liens sont inutilisables.
La vérification conserve UUID utilisateur, propriétaire, workspace et membership.
Elle ne crée pas automatiquement de session ; le login reste une action distincte.

Avant vérification, login et accès documentaire sont refusés. Le test d'upload avec
une session fabriquée côté fixture conserve le refus avant lecture du corps
(`receive_calls=0`), même si le champ de blocage administratif est nul. Les parcours
existants de vie du compte et d'isolation documentaire restent dans les régressions.

Doublons et refus de quota restent génériques ; un renvoi ou une récupération pour
compte bloqué ne révèle pas directement son existence. Aucun mot de passe, lien brut,
cookie ou clé n'est publié dans ce rapport. La résistance à toute analyse temporelle
et l'efficacité anti-abus réelle ne sont pas déduites de ces égalités de réponse.

## 6. B14-08 : décision sans migration

La distinction fiable utilise deux champs **déjà présents** :

| Compte public | `email_verified_at` | `disabled_at` |
| --- | --- | --- |
| En attente d'email, non bloqué | NULL | NULL |
| En attente et bloqué volontairement | NULL | Horodatage |
| Vérifié et utilisable | Horodatage | NULL |
| Vérifié et désactivé | Horodatage | Horodatage |

Login et authentification des comptes publics vérifiaient déjà l'email ; il n'est
donc pas nécessaire de détourner `disabled_at` pour représenter l'attente. `verify()`
ne renseigne désormais que l'email vérifié et ne lève jamais un blocage. Le renvoi,
la récupération et le reset ne permettent pas de contourner `disabled_at`.
Les comptes bloqués sont exclus de la purge des inscriptions en attente.

**Pas de migration nécessaire** : pas de nouvelle colonne ni d'encodage caché dans
le rôle, le type d'inscription ou la table de jetons. Les identités historiques et
invitées gardent leurs règles. Les comptes publics déjà en attente selon l'ancien
code, avec `disabled_at` non nul, sont ambigus : **ils restent bloqués**. Aucun
backfill automatique ne prétend distinguer une ancienne attente d'une intention
administrative. Une revue opérateur est nécessaire.

Commandes locales proposées pour une future revue approuvée, jamais exécutées sur
la production pendant ce lot :

```text
python -m backend.account_admin pending-account block UUID_REVU
python -m backend.account_admin pending-account block UUID_REVU --execute
python -m backend.account_admin pending-account release UUID_REVU
python -m backend.account_admin pending-account release UUID_REVU --execute
```

Sans `--execute` : simulation. La mutation verrouille l'utilisateur, refuse un compte
déjà vérifié, historique/invité ou faisant l'objet d'une demande de suppression,
puis invalide ses liens de vérification/reset non consommés. `release` est une
décision de revue explicite : elle ne vérifie pas l'email, n'envoie aucun mail,
ne crée aucune session et ne rouvre ni quota ni place. L'utilisateur doit demander
un nouveau lien, avec son mot de passe et une nouvelle preuve. Les anciens liens ne
revivent pas. La trace JSON horodatée ne contient pas d'adresse ni de token.

Le schéma `0007` reste compatible au niveau structurel. **Un rollback vers du code
antérieur à 14.4 réintroduirait cependant B14-08**, notamment via un renvoi suivi
d'une vérification. Une compatibilité de schéma ne certifie pas le niveau de sécurité.
Avant usage public du blocage, prévoir un candidat de retour applicatif corrigé ou
garder le service fermé/hors exposition pendant une réparation ; ne pas promettre
qu'un ancien binaire reste sûr parce qu'il accepte `0007`.

## 7. B14-06 : sauvegarde et restauration du quota

Les nouveaux inventaires incluent `public_registration_quota` avec ses trois colonnes
`id`, `issued_count`, `closed`, dans l'empreinte ordonnée des lignes. En schéma `0007`,
un nouveau backup qui omet cette table échoue. Le manifeste annonce
`integrity_version=2`, sans modifier les deux archives ni le format des digests existants.
Le vérificateur refuse l'absence du quota en v2/0007 et une projection ne couvrant
pas ses deux champs d'état. Les altérations SQL réelles de `issued_count` et de
`closed` sont détectées par les tests d'intégrité.

Les anciens inventaires v1, y compris sans marqueur de version ni quota, restent
lisibles. Ils émettent une indication **quota NOT certified** et ne sont pas présentés
comme une preuve de fidélité du compteur. Ils ne sont ni édités ni enrichis a posteriori.
Le nouveau vérificateur est nécessaire pour les nouveaux inventaires ; un ancien
binaire ignorant la table peut refuser ces nouvelles archives.

### Recette indépendante exécutée

Un projet Compose exclusivement local contient un PostgreSQL neuf sur tmpfs et un
service d'archivage éphémère lisant seulement un répertoire fictif en bind readonly.
Ce service utilise l'image PostgreSQL locale pour `tar`, **pas** l'API de production.
Ni volume existant, ni Docker socket monté, ni clé réelle ; aucune image téléchargée.

Le vrai `create_backup()` produit `database.dump`, `documents.tar.gz`, manifestes et
inventaire. `pg_restore` restaure le dump dans une base **nouvelle**, nommée
`documind_restore_s14_4_<UUID>`, jamais une base existante. Le vérificateur réel relit
les empreintes via `psql` ; une lecture SQL indépendante confirme compteur 4 et
verrou identique à la source, pour les quatre combinaisons v1/v2 × ouvert/fermé.
La compatibilité v1 est simulée dans une **nouvelle copie fictive** de l'inventaire ;
aucune archive existante n'est modifiée.

Ensuite seulement, `seal_restored_registration()` ferme la copie, sans modifier le
compteur ni les fichiers du snapshot. Les SHA-256 des fichiers restent identiques,
et le quota source est relu inchangé. Les bases de restauration nouvellement créées
sont supprimées après fermeture des connexions. Le reste du projet de test est
nettoyé après les campagnes ; son état final est consigné ci-dessous.

Cette séparation est intentionnelle : **prouver d'abord la fidélité du verrou**,
puis **fermer explicitement la copie hors service** avant toute réutilisation possible.
Le vérificateur reste en lecture seule. `validate_restore.py` ne connecte jamais
d'API/BFF à sa copie et conserve ses contrôles de nom/création d'une base neuve.
Le déployeur 14.2 refuse également le mode public si la ligne SQL est ouverte.
Aucune restauration ne déclenche automatiquement un `reopen`.

Un ancien backup peut porter un compteur inférieur au dernier état de production.
Il faut réconcilier l'historique avant une décision manuelle de réouverture, pas remettre
le compteur à zéro. Le helper retourne `requires_review=true`. Cela ne transforme
pas un inventaire v1 en certificat, et ne prétend pas protéger un `pg_restore`
arbitraire suivi d'un démarrage manuel contournant toute la procédure.

## 8. Campagnes de validation

| Campagne terminée | Réussis | Ignorés | Échoués |
| --- | --- | --- | --- |
| Windows, première sélection quota/identité/14.2 | 82 | 9 | 0 |
| Windows, blocage/inventaire/backups opérationnels | 100 | 4 | 0 |
| PostgreSQL, huit premiers entrelacements | 8 | 0 | 0 |
| PostgreSQL, quota/identité/concurrence/14.2/14.3/déploiement | 201 | 0 | 0 |
| Répétition PostgreSQL des neuf entrelacements, passage 1 | 9 | 0 | 0 |
| Même répétition, passage 2 | 9 | 0 | 0 |
| Backup/restauration réels et inventaires, première campagne | 12 | 0 | 0 |
| Confirmation finale avec altération SQL réelle des deux champs | 13 | 0 | 0 |
| BFF Node, suite complète | 50 | 0 | 0 |
| Linux WSL, identité/public/inventaire | 38 | 6 | 0 |
| Windows Python 3.13.7, suite complète finale | 695 | 56 | 0 |

La première sélection Windows précède le dernier scénario de concurrence et les
deux contrôles d'altération réels ; les sélections se recouvrent et leurs nombres
ne doivent pas être additionnés comme des tests distincts. Les cas PostgreSQL et
Docker explicitement ignorés sur SQLite ne sont pas des preuves d'exécution de ces
chemins : leurs campagnes dédiées ci-dessus apportent cette preuve.

La suite complète Windows a duré 587,68 secondes. Ses 56 ignorés sont les 40 cas
natifs Linux, le cas PostgreSQL du Sprint 14.2, les neuf courses PostgreSQL 14.4 et
les six tests Docker d'intégrité/restauration, tous inapplicables à cette campagne
SQLite Windows. Les cas PostgreSQL/Docker 14.4 sont réellement exécutés dans leurs
campagnes dédiées, pas déclarés réussis à partir de ces skips. WSL Python 3.12.3 a
passé la sélection en 81,41 secondes ; les six ignorés sont les restaurations/altérations
Docker sans configuration de projet dans cette sélection Linux.
L'avertissement Starlette/httpx existant est conservé. Les analyses AST, les blancs
des nouveaux fichiers et `git diff --check` ne présentent pas d'erreur.

Les deux serveurs PostgreSQL jetables et leurs réseaux dédiés ont été arrêtés puis
supprimés après vérification des labels et des montages tmpfs. Les conteneurs
d'archivage éphémères avaient été supprimés par `--rm`. Les filtres Docker sur les
labels `sprint-14-4` et `sprint-14-4-backup` ne montrent plus de ressource restante.
Les fichiers fictifs de preuve restent sous `var/`, ignoré par Git. Aucun volume
persistant, conteneur ou réseau préexistant n'a été modifié.

Commandes principales exécutées, avec dossiers temporaires dédiés :

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_public_beta_postgresql_concurrency.py tests/test_public_beta_state.py tests/test_public_beta.py tests/test_public_beta_authorization.py tests/test_ai_disabled_enforcement.py tests/test_deployment.py -q -p no:cacheprovider --basetemp=var/pytest-14-4-pg-regressions --tb=short
.\.venv\Scripts\python.exe -m pytest tests/test_public_beta_snapshot.py -q -p no:cacheprovider --basetemp=var/pytest-14-4-restore-final --tb=short
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp=var/pytest-14-4-windows-full --tb=short
```

Les deux premières commandes utilisent explicitement des `TEST_DATABASE_URL`
distinctes vers les bases Docker fictives. La restauration reçoit aussi le préfixe
Compose de test dans `TEST_SNAPSHOT_COMPOSE` ; les variables sont restaurées en
`finally`. Les fixtures refusent toute base non vide à l'entrée. Les seuls nettoyages
de jeux de données sont ceux des bases jetables du harnais ; aucun chemin métier,
de restauration ou de reprise ne remet le quota à zéro.

Les ressources de test utilisent le pipe Docker Desktop local explicitement fixé,
des images déjà présentes, des labels dédiés, des ports PostgreSQL loopback et des
réseaux neufs sans masquerading. Aucun projet Docker existant n'est rejoint.
Les gardes IA et l'interdiction des vrais clients SDK sont maintenues dans les tests.

## 9. Limites et risques résiduels

- Les tests déterministes ne remplacent pas un test de capacité complet ; les limites
  anti-abus par IP, difficulté PoW réelle et délivrabilité SMTP sont du ressort 14.5.
- Les anciens comptes publics en attente doivent être revus : aucun automatisme ne
  peut déduire sûrement l'intention d'un ancien `disabled_at` non nul. Ne pas faire
  de mise à NULL en masse.
- Un compte en attente volontairement bloqué reste conservé et exclu de la purge.
  Après une libération explicite, les règles ordinaires d'expiration/nettoyage
  reprennent ; demander rapidement un nouveau lien et coordonner les opérations.
- Le quota reste cumulatif : cinq inscriptions en attente peuvent épuiser la bêta.
  Une suppression ne constitue pas une procédure de récupération de place.
- Les copies restaurées restent hors service et fermées. Une décision opérateur
  reste indispensable après restauration, surtout avec un inventaire ancien ou une
  sauvegarde plus vieille que les dernières admissions connues.
- Les empreintes complémentaires ne sont pas une signature contre un administrateur
  malveillant pouvant réécrire les métadonnées. Les protections externes des archives
  et procédures Restic restent inchangées ; aucun transfert B2 réel n'est testé ici.
- La recette Docker concerne SQL/backup/restauration, pas une stack applicative
  complète Traefik/BFF/API ni une nouvelle certification Landlock/seccomp.
- Les suites complètes Linux/PostgreSQL, React/build et un navigateur E2E ne sont
  pas relancés pour ce lot. Les sources frontend, sandbox et workflow sont préservées.
- Les procédures de rollback doivent tenir compte de la version du correctif, pas
  seulement du schéma `0007`. Les codes antérieurs restent des candidats vulnérables.

## 10. Préparation 14.5 et verdict

Conserver `AI_ENABLED=false`, les admissions fermées et la politique de cinq places.
La phase 14.5 doit traiter UX de fermeture et de récupération, SMTP/TLS en recette,
textes et consentement, PoW sur clients réels, limites NAT, alertes et information
claire sur les places consommées par des comptes en attente. La procédure de
restauration/retour arrière et les validations d'exploitation restent à approuver
avant la décision d'ouverture.

**Verdict : lot prêt pour revue Git locale, avec limites documentées.** B14-08 est
corrigé pour les comptes en attente et le parcours de revue explicite ; B14-06 est
traité par l'inventaire v2, la compatibilité signalée des anciens inventaires et la
fermeture des copies restaurées. B14-03 dispose désormais des preuves demandées à
cinq admissions et des entrelacements PostgreSQL déterministes, sans prétendre à
une certification générale de capacité. Le refus des compteurs négatifs est corrigé.
Les garanties 14.2/14.3 passent les régressions, dont les scénarios zéro appel IA.

B14-04 (preuves d'exploitation réelles), B14-05 (places en attente cumulatives),
les contraintes anti-abus/capacité B14-07, la préparation du retour applicatif corrigé
et les validations 14.5–14.7 restent ouverts ou à approuver.
**L'ouverture publique demeure No-Go ; aucune opération distante n'est autorisée
par ce rapport.** Aucun fichier n'a été indexé ou commité, et la production Sprint 13
n'a pas été modifiée.
