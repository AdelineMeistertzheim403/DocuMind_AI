# Sprint 14.2 — Autorisation sécurisée de la bêta publique

Date : 25 octobre 2026. Branche locale :
`preparation/sprint-14-2-public-beta-authorization`.
Base de travail : `8243e0511c5505a9cc70f76ad02392f7a816590d`.
Référence : [audit 14.1](SPRINT_14_1_PUBLIC_BETA_AUDIT.md), notamment B14-01, B14-04 et B14-05.

**Ce lot prépare un déploiement fermé, pas l'ouverture de la bêta.** Aucune commande
de production, activation, publication, migration distante, modification de secret,
commit ou push n'a été exécuté. Aucune modification de `.env.production`.

## 1. Fichiers concernés

| Fichier | Changement |
| --- | --- |
| `tools/public_beta_policy.py` | Politique commune, sans dépendances applicatives, et sonde des paramètres effectifs expurgés. |
| `tools/prepare_production.py` | Autorisation distincte `--approve-public-beta`, validation avant écriture des références d'images ; import utilisable aussi comme module. |
| `tools/deploy_production.py` | Validation Compose/image, contrôle SQL fermé en lecture seule, conservation du compteur et preuves dans le rapport. |
| `backend/account_admin.py` | Contrôle local factorisé, fermeture transactionnelle, vérification après commit et résultat JSON horodaté ; réouverture plus restrictive. |
| `.github/workflows/ci.yml` | Inclusion du module de politique dans le bundle ; aucune modification des déclencheurs ou de la publication des images. |
| `.github/workflows/deploy.yml` | Input manuel booléen, faux par défaut, transmis au déployeur ; validation des nouveaux bundles et compatibilité des anciens bundles ordinaires. |
| `tests/test_public_beta_authorization.py` | Tests des profils, préflights, préparation, simulation de livraison, CLI, quota et verrou PostgreSQL réel. |
| `tests/test_deployment.py` | Adaptation de la simulation existante au retour JSON typé de la sonde et du préflight. |
| Ce rapport | Architecture, procédures proposées, preuves et limites. |

Le rapport 14.1 préexistant, non suivi en début de mission, est conservé sans modification.
Ni Compose, Dockerfile, migration, authentification HTTP, admission d'upload,
Landlock/seccomp, ni scripts de sauvegarde/surveillance/conservation ne sont modifiés.

## 2. Architecture de l'autorisation

### 2.1 Trois niveaux de contrôle cohérents

`validate_registration_config()` centralise le profil de livraison :

- Les modes `disabled` et `invite` restent permis sans autorisation supplémentaire.
- `public` exige **explicitement** `--approve-public-beta` ; la présence de
  `--initialize`, `--allow-migration` ou `--rollback` ne fournit aucune autorisation.
- Le manifeste doit annoncer exactement le schéma `0007`.
- `PUBLIC_REGISTRATION_LIMIT` doit valoir exactement `5`.
- `AI_ENABLED`, `OWNER_DEMO_ENABLED`, `LEGACY_API_ENABLED` doivent être explicitement
  faux. Des valeurs manquantes ou ambiguës sont refusées ; les formes booléennes
  `False` et textuelles `false`/`0` sont acceptées.

Cette politique est utilisée par le préparateur hors ligne, le préflight du Compose
**résolu**, puis le préflight des paramètres **effectifs dans l'image API**. La sonde
construit `Settings()`, ce qui conserve les validations BFF, SMTP et informations
légales du Sprint 13. Elle retourne seulement mode, limite et trois booléens ;
aucune clé, URL de base SQL, adresse email ou configuration SMTP n'est retournée.
Les clés historiques restent interdites par la sonde aussi dans les modes ordinaires.
Une divergence de mode entre Compose et image entraîne un refus.

Le préparateur ne contacte pas la base et ne prétend donc pas vérifier son verrou.
L'autorisation qu'il accepte permet uniquement de préparer les références d'images.
La preuve SQL appartient au déployeur.

### 2.2 Autorisation manuelle, attachée à une version

Le workflow de déploiement reste exclusivement `workflow_dispatch`, avec environnement
`production` et vérification des approbateurs déjà existante. Son nouvel input
`approve_public_beta` est booléen et vaut `false` par défaut. Il n'est ni un secret,
ni un mécanisme de réouverture SQL. Les paramètres de migration et d'initialisation
restent distincts. Le déployeur reçoit le flag seulement si cet input vaut `true`.

La CI joint `public_beta_policy.py` aux cinq fichiers existants du bundle ; aucune
modification du format des trois digests dans `release.json`. Les bundles historiques
à cinq fichiers restent acceptés pour les opérations ordinaires, sans nouveau flag.
Une approbation bêta exige le bundle à six fichiers : un vieux script ne peut pas
être traité comme capable de vérifier la nouvelle autorisation.

L'autorisation d'une exécution ne devient pas un paramètre persistant du serveur.
Chaque nouveau déploiement en mode public doit la recevoir de nouveau. La version
est liée au SHA/digests existants et à l'exécution approuvée ; le rapport de déploiement
ajoute `public_beta.approved`, `preparation_only`, `limit`, `quota_before` et `quota_after`.
L'identité de l'approbateur reste portée par GitHub et les procédures opérateur ; elle
n'est pas inventée à partir d'une variable locale non authentifiée.

## 3. Préparation fermée en deux décisions

Pour le mode public, le déployeur exige une installation **déjà existante en `0007`**,
un pointeur `current` valide et la ligne SQL du quota fermée. Il refuse la première
installation publique, la récupération d'installation partielle en mode public et
la combinaison d'une ouverture avec une montée de schéma `0006 → 0007`, même si
la migration est approuvée. Installer d'abord `0007` dans un mode fermé.

La requête SQL du contrôle n'effectue qu'un `SELECT`. Elle exige un booléen
`closed=true` et un entier `issued_count` de 0 à 5 ; absence, erreur de lecture,
JSON ambigu/inexploitable, verrou ouvert ou compteur incohérent empêchent la livraison.
Un compteur à 5 permet un déploiement fermé, mais pas une réouverture sans capacité.

Contrôles répétés : avant téléchargement des images, après sauvegarde des services
arrêtés, avant démarrage API/BFF et avant déplacement du pointeur `current` après
les sondes HTTPS. Le compteur et le verrou doivent être identiques entre ces étapes.
Le redémarrage automatique de l'application précédente après un échec de préparation
publique exige également un verrou fermé et un schéma compatible.

**Le déployeur n'exécute ni fermeture SQL, ni `reopen`, ni remise à zéro.** Si le
verrou est ouvert, il s'arrête et demande une décision opérateur préalable. Les
procédures de sauvegarde, d'approbation de migration, de rollback sans downgrade,
de santé, HTTPS, CSRF et refus anonyme restent en place.

Procédure future, non exécutée :

1. Lire le statut sur la release active encore en mode fermé ; fermer explicitement
   le verrou et vérifier le résultat, sans changer le compteur.
2. Préparer une configuration approuvée `public / 5 / IA false / demo false / legacy false`,
   avec SMTP et textes validés. Ce sprint n'édite pas cette configuration.
3. Après validation des phases suivantes, publier puis déployer une version compatible
   avec `approve_public_beta=true`. Les admissions restent fermées.
4. Vérifier les résultats de recette, le rapport et la configuration effective.
5. Une décision distincte pourra autoriser le CLI `reopen --execute` ; aucune tâche
   de déploiement ne l'appelle. **Cette dernière décision n'est pas autorisée ici.**

## 4. Compteur et commande opérateur

`registration_control()` lit la ligne de quota ; les mutations exécutées utilisent
`SELECT ... FOR UPDATE` puis un `UPDATE closed=...`, dans la même transaction sous
PostgreSQL. Ce verrou se sérialise avec l'incrément conditionnel de l'admission.
Après commit, la commande recharge la ligne et vérifie l'état attendu et le compteur.
Une admission peut suivre immédiatement une réouverture : la vérification accepte
alors uniquement un compteur croissant, toujours inférieur ou égal à cinq. Pour une
fermeture, le compteur doit être strictement inchangé. Un test provoque cette course
par une inscription fictive entre le commit et la relecture, sans délai arbitraire.
Elle retourne un JSON horodaté, avec action, état préalable, état final, limite,
mode, indicateur de simulation et vérification. Aucun identifiant personnel ni secret.

Sans `--execute`, `close` et `reopen` simulent et ne changent pas la base. La fermeture
ne requiert pas l'autorisation de déploiement ni le profil de réouverture ; elle reste
possible en mode `disabled`/`invite`. Comme auparavant, le démarrage du CLI nécessite
néanmoins une configuration `Settings` chargeable et une base accessible.

La réouverture exécutée exige désormais mode public, limite 5, trois drapeaux faux
et `0 <= issued_count < 5`. Elle ne peut pas servir à vider le compteur, à ouvrir
un mode désactivé ou à recycler une place. Il n'existe aucune route HTTP pour ce CLI.

### Politique métier conservée

- Cinq admissions **publiques cumulatives**, et non cinq comptes actifs.
- Comptes historiques/invités exclus ; un public en attente d'email compte déjà.
- Suppression, désactivation, absence de vérification et perte d'un mail ne rendent
  aucune place. La purge existante ne décrémente pas le compteur.
- Fermeture et réouverture conservent le compteur ; à `n` admissions, il reste `5-n`
  places. À cinq, une nouvelle demande reçoit le 202 générique, sans nouveau compte.
- B14-05 demeure : cinq comptes en attente peuvent consommer toute la bêta. Le renvoi
  et la récupération existants restent disponibles ; la file SMTP reste non durable.

## 5. Fermeture d'urgence proposée

Les commandes suivantes sont une procédure à faire approuver, **pas des actions
exécutées sur le VPS**. Depuis la release active vérifiée :

```bash
cd /srv/documind-ai/current
export PRODUCTION_ENV_FILE=/srv/documind-ai/.env.production
dc() {
  docker compose --env-file "$PRODUCTION_ENV_FILE" \
    --env-file /srv/documind-ai/current/images.env \
    --project-name documind-prod -f compose.production.yaml "$@"
}
dc exec -T api python -m backend.account_admin public-registration status
dc exec -T api python -m backend.account_admin public-registration close --execute
dc exec -T api python -m backend.account_admin public-registration status
```

Vérifier version active, mode, limite, compteur et `closed` avant l'action. Conserver
les JSON expurgés avec opérateur et référence d'incident dans un dossier privé ou
le journal de l'opération ; l'horodatage seul n'identifie pas l'opérateur. Confirmer
`closed=true`, compteur inchangé, puis capacité indisponible dans les options BFF.
Ne jamais consigner de cookie, jeton de lien ou sortie complète d'environnement.

Aucun arrêt PostgreSQL, downgrade, suppression ou modification des comptes existants.
Les connexions et vérifications de comptes déjà admis continuent de fonctionner.
Une transaction ayant réservé sa place avant la fermeture peut terminer et envoyer
un mail ensuite : la fermeture est effective lorsque sa transaction a acquis puis
validé le verrou SQL, pas dès l'envoi de la commande.

Si l'opération échoue ou n'est pas confirmée, ne pas annoncer la fermeture comme
réussie. Ne pas compenser par un reset SQL, une restauration ou un arrêt global de
Traefik. Une fermeture durable de configuration vers `disabled` reste une opération
séparée et approuvée ; éditer un fichier env ne change pas un processus existant.

## 6. Validation locale

Toutes les données sont fictives. Le venv Windows est Python 3.13.7 ; le venv WSL
réutilisé est Python 3.12.3. Les bases SQLite et dossiers `--basetemp` sont dédiés ;
aucun fichier privé n'est copié dans une image. Les fixtures interdisent les vrais
clients OpenAI. Les tests de préparation remplacent le lecteur d'environnement
par une configuration fictive et n'écrivent pas `.env.production`.

| Campagne | Réussis | Ignorés | Échoués | Portée |
| --- | --- | --- | --- | --- |
| Windows, autorisation + déploiement + parcours public, première sélection | 158 | 0 | 0 | Avant ajout du test natif PostgreSQL et du cas de migration publique. |
| Linux WSL, mêmes trois fichiers | 159 | 1 | 0 | Test PostgreSQL explicitement ignoré sur SQLite ; avant le dernier cas de réouverture concurrente. |
| PostgreSQL 17.11 / pgvector 0.8.7, trois fichiers | 160 | 0 | 0 | Verrou réel et limite cinq/six ; avant le dernier cas de réouverture concurrente. |
| Windows, fichier d'autorisation final | 52 | 1 | 0 | Inclut l'inscription immédiatement après réouverture ; test PostgreSQL ignoré. |
| Linux WSL, fichier d'autorisation final | 52 | 1 | 0 | Même correction et même test de course, sans assouplissement du contrôle. |
| PostgreSQL 17.11 / pgvector 0.8.7, confirmation finale des trois fichiers | 161 | 0 | 0 | Toutes les sources finales, y compris la course de réouverture et le verrou natif. |
| Windows, confirmation finale des trois fichiers | 160 | 1 | 0 | Sources finales ; test spécifique PostgreSQL ignoré sur SQLite. |
| Windows, suite Python complète de confirmation | 656 | 41 | 0 | 561,25 s ; collecte antérieure au dernier test de course, voir limite ci-dessous. |

Les suites complètes Linux/PostgreSQL et les suites React/BFF ne sont pas relancées
dans ce lot. Le dernier ajustement de relecture après
réouverture et son nouveau test ont été ajoutés après le lancement de cette suite
complète ; ils sont couverts par les confirmations ciblées finales sur les trois
environnements, et ne doivent pas être attribués rétrospectivement à la collecte complète.

Commandes utilisées (adapter seulement le dossier temporaire et le port de la base
**jetable**, jamais une URL existante) :

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_public_beta_authorization.py tests/test_deployment.py tests/test_public_beta.py -q -p no:cacheprovider --basetemp=var/pytest-14-2-targeted --tb=short
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp=var/pytest-14-2-windows-final --tb=short
```

```bash
# Depuis les sources locales ; venv WSL préexistant, aucune installation réseau.
env -u TEST_DATABASE_URL /var/tmp/documind-s13-a7b75801/.venv/bin/python -m pytest \
  tests/test_public_beta_authorization.py tests/test_deployment.py tests/test_public_beta.py \
  -q -p no:cacheprovider --basetemp=/tmp/documind-s14-2-linux-confirm-20261025 --tb=short
```

Pour PostgreSQL, les mêmes trois fichiers ont été exécutés avec `TEST_DATABASE_URL`
pointant exclusivement vers le port loopback éphémère du conteneur de test, utilisateur
et mot de passe fictifs, base neuve `documind_beta_test`. La variable est restaurée
dans un `finally`. La fixture refuse toute base contenant des tables au départ.
Le cas natif de verrou n'est donc pas compté comme validé par une exécution SQLite.

Docker Desktop local 29.8.2 est ciblé explicitement par le pipe
`npipe:////./pipe/dockerDesktopLinuxEngine`, jamais par un contexte distant. L'image
locale `documind-postgres-vector:17` est utilisée avec `--pull never`, PG 17.11 et
pgvector 0.8.7. Les conteneurs ont des labels dédiés, un stockage tmpfs, aucun volume
persistant, un réseau neuf sans masquerading, un port publié uniquement sur loopback,
utilisateur `70:70`, capacités supprimées, `no-new-privileges`, mémoire 512 Mio,
CPU 1 et limite de 64 processus. Aucun réseau existant n'est joint. Le premier essai
sur réseau `--internal` n'exposait pas de port utilisable depuis Windows ; ce n'était
pas un échec PostgreSQL. Il a été remplacé par le réseau de test dédié ci-dessus.
Les trois conteneurs PostgreSQL successifs et leurs trois réseaux de test ont été
arrêtés/supprimés après contrôle des labels et montages tmpfs ; les filtres Docker
sur le label de cette mission ne retournent aucune ressource restante. Aucun volume
persistant ni conteneur préexistant n'a été modifié, et aucune image téléchargée.

Historique des vérifications : les 24 premiers tests ont produit 22 échecs attendus et
2 réussites avant implémentation. Une campagne WSL intermédiaire (155 réussis,
3 échecs) et une première suite Windows complète (652 réussis, 40 ignorés, 3 échecs)
avaient chargé une ancienne fixture renvoyant `"false"` au lieu des booléens de
`Settings`. La fixture a été corrigée ; le contrôle typé de production est conservé.
Ces campagnes ne sont pas présentées comme des suites réussies.
L'avertissement de dépréciation Starlette/httpx préexistant est conservé, pas masqué.
Les vérifications de syntaxe AST des six fichiers Python et de parsing des deux
workflows YAML réussissent. `git diff --check` est sans erreur ; les blancs de fin de
ligne des nouveaux fichiers non suivis sont contrôlés séparément.

Couverture ajoutée : refus sans autorisation (y compris avec migration approuvée),
profils incorrects, manque de paramètres, modes ordinaires, sonde d'image différente,
verrou SQL absent/ouvert, compteur invalide/modifié, absence de réouverture pendant
déploiement et rollback, préparation sans SQL, import des scripts en bundle plat,
fermeture simulée/exécutée, réouverture contrôlée, scénario cinq/six et conservation
du compteur après suppression/désactivation.

Un test PostgreSQL supplémentaire maintient la transaction de la cinquième admission
ouverte, observe réellement l'attente `Lock` de la fermeture dans `pg_stat_activity`,
puis la libère par événement. Il vérifie l'état fermé à cinq et le refus d'une
nouvelle réservation. Les attentes ont des bornes de sécurité ; SQLite ignore
explicitement ce seul test spécifique PostgreSQL.

## 7. Limites, arbitrages et Sprint 14.3

- **Pas de Go pour l'ouverture publique.** B14-02 reste ouvert : la validation d'une
  clé BYOK peut encore contacter le fournisseur malgré `AI_ENABLED=false`. Ce lot
  impose la configuration fermée mais ne prétend pas corriger ce chemin. Le Sprint
  14.3 doit ajouter le gate et la matrice zéro appel fournisseur public/historique.
- B14-04 : aucune preuve du SMTP, des textes, des drapeaux, alertes ou backups réels
  n'est créée par cet exercice. L'approbation Github est configurée dans le code du
  workflow mais ses règles distantes n'ont pas été consultées ou modifiées.
- Aucun déploiement réel ni recette complète BFF/API/Traefik/SMTP avec ces nouvelles
  options n'a été exécuté. La recette Docker décrite ici concerne PostgreSQL jetable,
  pas une certification du chemin de livraison réel.
- Les vérifications SQL répétées ne constituent pas une exclusion contre un autre
  administrateur privilégié qui rouvrirait pendant l'opération. Coordonner les
  décisions opérateur, ne jamais exécuter `reopen` pendant déploiement/maintenance.
- Un redémarrage ne change pas le verrou SQL : un verrou fermé reste fermé, un
  verrou déjà explicitement ouvert reste ouvert. Les déploiements publics exigent
  de le refermer avant préparation ; aucune réouverture automatique n'est ajoutée.
- Aucun outil de restauration de production automatique n'est ajouté. Un ancien
  dump peut contenir `closed=false` : restaurer hors service ou en mode désactivé,
  fermer et vérifier avant exposition publique. Le déployeur refuse un tel état
  ouvert. La recette complète de restauration, et l'inventaire d'intégrité manquant
  pour cette table (B14-06), restent à traiter avant ouverture ; ne pas leur attribuer
  une garantie globale apportée par ce lot.
- Les prochaines étapes conservent les quotas, sessions, séparation propriétaires,
  protections d'upload et confinement sans repli. Aucune migration nouvelle n'est nécessaire.

Les changements sont destinés à une revue locale ; toute publication, utilisation
des nouveaux inputs en production et réouverture nécessitent des autorisations distinctes.

**Verdict de clôture : mécanisme 14.2 prêt pour revue Git locale, avec limites de
validation explicites ci-dessus ; ouverture publique toujours No-Go.** Terminer
notamment 14.3 et les recettes SMTP, concurrence complète, restauration et exploitation
avant toute décision de réouverture. Aucun fichier n'a été indexé ou commité.
