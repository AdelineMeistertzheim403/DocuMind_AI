# Docnelo V5.1 — Audit statique de la quarantaine applicative

1 novembre 2026. **NO-GO pour la qualification de la quarantaine applicative.**
Production et Lifecycle 10 restent en **NO-GO**.

## 1. Périmètre, méthode et conclusion

Audit statique du contenu courant du dépôt, incluant les sources modifiées
et modules Lite présents dans le workspace, pas uniquement HEAD. Aucun test,
serveur, migration, backup/restore, connexion DB/VPS ou service externe
n'a été exécuté. Aucun secret n'a été recherché ou utilisé. Seul ce rapport
est créé ; aucun code, release V5/V5.1, ZIP ou manifeste n'est modifié.

Les résultats communiqués par l'opérateur (77 tests Linux, PostgreSQL,
24 empreintes, cinq stores, deux clés et document restaurés) sont des éléments
de contexte non réexécutés. **Ils ne valident pas la quarantaine applicative.**
Le contenu courant du dépôt ne prouve pas non plus celui de l'image du labo.

**Démontré par le code :** une barrière HTTP globale refuse les nouvelles
requêtes lorsque le fichier effectivement lu est quarantiné, absent, invalide
ou inaccessible. Authentification valide, route publique et healthcheck
ne bénéficient d'aucune exemption dans ce middleware.

**Partiel :** démarrage sans traitement métier, couverture fonctionnelle
exhaustive, binding de l'API au latch restauré, visibilité des changements
du fichier monté, fermeture uniforme en profil Lite.

**Absent comme garantie générale :** arrêt atomique des requêtes/jobs déjà
engagés, blocage universel des programmes locaux/CLI, fermeture du shell Web
et irréversibilité d'une quarantaine dynamique dans un processus initialement
prêt.

Aucun chemin de contournement distant exploitable de la barrière HTTP n'a
été démontré. Les limites ci-dessous ne sont pas assimilées artificiellement
à des vulnérabilités.

## 2. Cartographie du mécanisme

```text
Settings.recovery_state_path
    -> read_recovery_state()
    -> lifespan : recovery_ready_at_start
       -> contrôle particulier si serving_closed
    -> requête HTTP :
       LiteBoundary
       -> RecoveryQuarantine (lecture fraîche du latch)
       -> audit / admission IP / upload / taille
       -> routeur -> authentification / sessions -> endpoint

Restore de développement :
    latch quarantined + état incomplete
    -> DB neuve / restore / comparaison originale / fermeture quota
    -> contrôles copies
    -> rapport quarantined ou blocked/failed, jamais autorisation d'ouverture
```

Le backend actif est lancé par `uvicorn backend.main:app`
(`Dockerfile:23-31`). La factory ASGI et les routeurs se trouvent dans
`backend\main.py:79-209`. Le point d'entrée desktop CustomTkinter
(`main.py:1-12`) est distinct ; il n'est pas protégé par un middleware HTTP.

### Chargement et validation du fichier

| Cas | Résultat du lecteur | Source |
|---|---|---|
| Chemin non configuré | `unconfigured`, pas une autorisation HTTP | `backend\recovery_quarantine.py:13-15,62-72` |
| Chemin relatif | Résolu depuis le CWD du processus | `backend\recovery_quarantine.py:16` |
| Fichier ou parent symbolique | `invalid` | `backend\recovery_quarantine.py:18-19` |
| Absence, permissions refusées, erreur d'ouverture | `unavailable` via OSError | `backend\recovery_quarantine.py:20-31` |
| Objet non régulier | `invalid` | `backend\recovery_quarantine.py:23-25` |
| Plus de 1 024 octets | `invalid`, contrôles avant/après lecture | `backend\recovery_quarantine.py:10,24-33` |
| UTF-8/JSON invalide ou clés dupliquées | `invalid` | `backend\recovery_quarantine.py:35-46` |
| Champs différents de format/state, format booléen ou version inconnue, état invalide | `invalid` | `backend\recovery_quarantine.py:47-50` |
| Schéma valide | `ready`, `quarantined` ou `serving_closed` seulement | `backend\recovery_quarantine.py:47-51` |

`backend\config.py:50` permet un chemin non configuré dans le profil standard ;
cela ne fait pas ouvrir HTTP. Le profil beta_lite exige le chemin configuré
(`backend\config.py:132-141`).

**Limite de confiance :** le lecteur ne vérifie ni propriétaire/mode d'écriture
ni liaison cryptographique à une capture (`backend\recovery_quarantine.py:13-51`).
La valeur ready repose sur le provisionnement opérateur et les contrôles
filesystem/montage extérieurs. Le chemin relatif rend le CWD déterminant.

## 3. Contrôles au démarrage

Le lifespan valide la configuration d'authentification puis lit le latch.
`recovery_ready_at_start` n'est vrai que pour ready ou après validation
particulière de serving_closed (`backend\main.py:83-94`).
Le processus ASGI peut donc exister en quarantaine : il ne s'agit pas d'un
arrêt du processus, mais d'une fermeture des accès métier.

Quand le démarrage est quarantiné, les branches conditionnelles évitent
le contrôle d'extraction, la création du dossier documentaire, les récupérations
de jobs IA, le worker de résumé, la livraison des courriels et l'expiration
périodique des sessions (`backend\main.py:95-143`).

**Garantie partielle avant lifespan :** create_app construit moteurs,
sessions et services (`backend\main.py:160-184`). Les factories SQLAlchemy
ne prouvent pas à elles seules une connexion (`backend\db.py:10-28`).
En revanche, le chargement de l'autorité Lite provisionnée précède le latch
(`backend\main.py:164-166`) et peut initialiser des tables SQLite ou renouveler
un challenge (`backend\lite_authority.py:476-508,601-606,785-795`).
On ne peut donc pas affirmer « zéro écriture locale avant quarantaine ».

## 4. Points d'entrée HTTP, authentification et administration

L'ordre d'ajout des middlewares est décrit dans `backend\main.py:185-191`.
Avec l'empilement FastAPI/Starlette, la frontière Lite est extérieure à la
quarantaine, elle-même extérieure aux admissions, audit et routage.

`RecoveryQuarantineMiddleware` relit le latch à chaque requête HTTP et peut
retourner directement 503 sans transmettre au routeur
(`backend\recovery_quarantine.py:58-75`). **Aucune exemption HTTP** n'y figure :
pas de health, login, documentation, route publique ou clé administratrice.
Les handlers de validation/SQL ne créent pas d'ouverture
(`backend\main.py:199-207`).

Les routeurs suivants sont enregistrés dans la même application
(`backend\main.py:192-197`) :

| Surface sous /api/v1 | Points d'entrée | Sources |
|---|---|---|
| Documents | Liste, dépôt, lecture, téléchargement, suppression, analyse et statuts | `backend\api.py:41-166` |
| Santé/interne | health, internal/upload-admission | `backend\api.py:172-191` |
| Auth/inscription | Options, challenge, vérification/renvoi email, inscription, oubli/reset mot de passe | `backend\account_api.py:105-192,229-266` |
| Sessions | Login/logout | `backend\ai\settings_api.py:47-75` |
| Compte | Compte, sessions, révocation, mot de passe, suppression | `backend\account_api.py:269-355` |
| Effacement dérivé | Résultats IA et embeddings | `backend\account_api.py:358-388` |
| IA | Statut, consommation, résumés, historiques, question documentaire | `backend\ai\api.py:54-98` |
| BYOK | Préférences/clé, connexion, déconnexion, validation | `backend\ai\settings_api.py:78-150` |
| RAG | Indexation/statut, recherche, question, comparaison, résumé | `backend\rag\api.py:26-83` |
| Jobs longs | Plan, création/liste, consultation, reprise, annulation | `backend\ai\long_api.py:66-98` |

L'authentification Owner des documents (`backend\api.py:19-23,37-38`),
la dépendance secure_gateway des comptes (`backend\account_api.py:28`)
et les gardes login/BYOK (`backend\ai\settings_api.py:47-125`) interviennent
en aval de la quarantaine. Le secret BFF et le transport sécurisé sont
contrôlés par `backend\gateway.py:6-20`, sans exemption de quarantaine.

### Exceptions de périmètre et réponses

- En profil Lite, certaines routes IA/recherche/vérification email sont
  refusées avec **403 avant la quarantaine**, pas nécessairement 503
  (`backend\lite_admissions.py:228-244`). Elles restent fermées.
- Les routes de documentation FastAPI par défaut appartiennent à cette app
  et au même middleware (`backend\main.py:160`,
  `backend\recovery_quarantine.py:58-75`).
- Les commandes d'administration locales ne sont pas des routes HTTP :
  pas de protection universelle par ce middleware
  (`backend\account_admin.py:1,23-57,197`).
- Les scopes non HTTP sont transmis
  (`backend\recovery_quarantine.py:58-60`). Aucun endpoint WebSocket actif
  n'a été identifié dans les routeurs examinés ; pas de bypass actuel établi.
- Le frontend sert configuration/CSRF et SPA sans lecture du latch
  (`frontend\server\app.mjs:155-156,194-199,362-365`). Son health relaie
  l'indisponibilité backend (`frontend\server\app.mjs:160-172`).
  La page peut rester visible ; accès aux données et affichage du shell
  ne sont pas la même garantie.

## 5. Transitions et états

Sources : `backend\main.py:87-94`,
`backend\recovery_quarantine.py:62-74`,
`backend\lite_release.py:452-472`.

| État de démarrage | État lu ensuite | Comportement |
|---|---|---|
| Quarantiné/absent/invalide/inaccessible | Même ready | Fermé dans ce processus : readiness initiale non acquise |
| ready | quarantined/absent/invalide | Nouvelles requêtes fermées |
| ready | ready | Accès soumis aux autres gardes |
| ready sans release contrôlée | serving_closed | Fermé, release manquante |
| serving_closed validé initialement | serving_closed | Accès conditionnel de recette, admissions fermées |
| Processus recovery avec release | ready | Refus : la release recovery interdit cette ouverture |

**Limite importante :** dans un processus démarré ready, sans recovery_release,
`ready -> quarantined -> ready` peut rouvrir les nouvelles requêtes.
La fermeture dynamique n'est pas mémorisée comme irréversible
(`backend\recovery_quarantine.py:62-69`). Cela suppose un changement du fichier
de contrôle ; ce n'est pas une élévation de droit par requête HTTP.
Le contrat opérationnel doit décider si ce comportement est acceptable.

Serving_closed est un parcours distinct de recette : destination réconciliée,
autorisation indépendante, scellement/contrôles SQL-lifecycle, manifeste,
identité POSIX non-root, superviseur et PostgreSQL loopback marqué laboratoire
(`backend\lite_release.py:309-398,401-449`). La garde par requête exige
manifeste inchangé, superviseur, paths sûrs, quota fermé et IA désactivée
(`backend\lite_release.py:452-472`). Le superviseur remet le latch à quarantined
en sortie et utilise loopback (`backend\lite_release.py:520-561`).
Ce code n'est pas une autorisation de production ou Lifecycle 10.

Les exceptions OSError/ValueError sont traitées dans serving_gate, mais pas
toutes les erreurs SQL (`backend\lite_release.py:452-472`) : une erreur peut
donner autre chose que le JSON 503 attendu, sans constituer un fail-open.

## 6. Relation au quota et au restore

Trois contrôles différents :

1. Quarantaine HTTP : refuse aussi les lectures, sessions et téléchargements.
2. Quota fermé : refuse les nouvelles admissions, pas l'application entière.
3. Serving contrôlé : peut autoriser certains usages avec admissions fermées.

L'incrément public exige atomiquement une ligne ouverte et un compteur dans
les bornes (`backend\public_registration.py:58-64,106-123`).
Lite vérifie également quota/cohérence puis réutilise cet incrément
(`backend\lite_admissions.py:177-206`). Serving_closed refuse l'inscription
canonique et exige le quota fermé
(`backend\recovery_quarantine.py:73-74`,
`backend\lite_release.py:466-469`).
Le profil historique standard/invite consomme une invitation, pas le quota
public (`backend\account_api.py:163-192`) : ce quota n'est pas un plafond
universel de tous les modes.

Le restore de développement écrit quarantined avant création/restauration DB
(`tools\validate_restore.py:321-332`), conserve le latch source séparément
et force la copie quarantined (`tools\validate_restore.py:385-391`).
Le sealer ferme et relit après commit sans remettre le compteur à zéro
(`tools\validate_restore.py:35-74`).

Son rapport ne prétend pas avoir observé une API attachée :
api_attached=null, api_attachment_verified=false, opening_authorized=false
(`tools\validate_restore.py:439-457`). Un restore réussi **ne démontre pas**
que la future API utilisera ce latch et ces copies.

## 7. Limites et possibilités de contournement à distinguer

| Situation | Niveau établi | Conséquence |
|---|---|---|
| Requête distante avec identifiants valides et latch effectivement quarantiné | Protection statique démontrée | Aucun accès métier démontré ; pas d'exception auth/admin HTTP |
| Autre fichier ready configuré, mauvais CWD ou mauvaise image | Liaison non qualifiée | Protection du bon latch non démontrée ; précontrôle de déploiement nécessaire |
| Writer local autorisé remet ready après démarrage ready | Réouverture permise par code | Contrat des transitions à formaliser ; pas bypass HTTP |
| CLI/desktop et scopes non HTTP | Hors couverture générale du middleware | Ne pas appeler la quarantaine un verrou global sur tous les programmes |
| Requête ou worker déjà engagé | Arrêt non garanti | Le latch ferme l'admission de nouvelles requêtes, pas tous les effets en vol |
| Fichier bind-monté remplacé atomiquement côté hôte | Non qualifié | L'ancien inode peut rester une question opérationnelle ; visibilité à mesurer |
| Frontend statique | Pas de fermeture globale par latch | Shell accessible ne signifie pas données accessibles |

La lecture du latch précède call_app, sans annulation ultérieure
(`backend\recovery_quarantine.py:62-75`). Le téléchargement lit son flux sans
nouveau contrôle (`backend\api.py:88-107`). Workers résumé/indexation et thread
mail n'ont pas de relecture du latch dans les boucles examinées
(`backend\ai\long_summary.py:179-205`, `backend\rag\indexing.py:68-118`,
`backend\rag\providers.py:23-30`, `backend\main.py:111-129`).

Les Compose utilisent un bind du fichier readonly sans création automatique
(`compose.production.yaml:51-62`, `compose.public-beta.vps.yaml:246-266`).
Cela empêche l'écriture via ce montage par le conteneur, mais ne prouve
pas la propagation d'un remplacement atomique de l'inode sur l'hôte.
Aucun test de cette visibilité n'est crédité réussi ici.

## 8. Tests existants : preuves dans les sources, non exécutées ici

| Source | Comportement testé | Limite |
|---|---|---|
| `tests\test_recovery_quarantine.py:4-11` | Chemin relatif | Pas couverture HTTP |
| `tests\test_recovery_quarantine.py:14-27` | Absence, JSON invalide, doublon, surplus, types, quarantined | Health, liste documents, inscription seulement |
| `tests\test_recovery_quarantine.py:30-45` | Quarantaine initiale puis ready reste fermé | Non-démarrage workers insuffisamment discriminant |
| `tests\test_recovery_quarantine.py:48-53` | ready puis quarantined | Deux routes seulement |
| `tests\test_restore_hardening.py:20-81` | Fermeture quota et échecs | SQL simulé, pas fermeture HTTP |
| `tests\test_restore_hardening.py:124-148,238-245` | Latch/échec restore, dérive quota | Pas preuve d'attachement API |
| `tests\test_lite_admissions.py:278-290` | Plafond cumulatif et absence de recyclage | Admission, pas quarantaine |
| `tests\test_lite_release.py:120-145,417-443` | Serving, refus inscription, dérive quota/latch/superviseur | Vrai serveur/labo requis, ne pas lancer dans cet audit |
| `ops\testing\combined_restore_payload.py:159-181` | Client in-process : health/liste/téléchargement/inscription fermés | Source d'un scénario, pas exécution attestée ici |

Le test des workers hérite d'une fixture ai_enabled=false
(`tests\conftest.py:65-72`), alors que le worker dépend déjà de ce flag
(`backend\main.py:104-109`). L'absence d'appel ne discrimine donc pas à elle
seule l'effet du latch ; un contrôle positif avec IA activée mais entièrement
simulée manque.

### Tests manquants dans la couverture dédiée examinée

- None non configuré ; PermissionError ; UTF-8 invalide ; fichier trop grand,
  non régulier, symlink fichier/parent.
- Authentification/login/logout/reset, email, compte, IA/RAG/jobs,
  documentation, route inconnue et méthodes alternatives.
- Preuve qu'aucune dépendance DB/auth, endpoint ni lecture du corps ne s'exécute.
- Distinction 403 Lite/503 quarantaine ; workers avec contrôle positif.
- ready -> quarantined -> ready ; requêtes déjà engagées.
- Image/RECOVERY_STATE_PATH réellement utilisés et propagation du bind.

Ces lacunes sont des absences de preuve, pas des vulnérabilités supposées.

## 9. Proposition de test fonctionnel hors réseau — non implémentée

Créer ultérieurement un harness ASGI in-process, sans socket d'écoute,
Uvicorn, Docker ou sous-processus de serveur. TestClient ou ASGITransport
peut appeler l'application directement ; toute connexion réseau, SQL réelle,
SMTP, fournisseur et création de worker externe doit être interdite.
Utiliser uniquement configuration synthétique _env_file=None, fichiers neufs
et moteurs/sessionmakers factices. Ne pas utiliser les fixtures générales
qui exécutent Alembic ou nettoient une base.

**Précaution d'import :** `backend\main.py:212-217` crée une application globale.
Neutraliser configuration et factories avant l'import initial, sans modifier
les gardes à tester. En profil Lite, surveiller aussi l'autorité SQLite.
Les espions doivent observer les effets et non forcer la décision du latch.

Matrice proposée :

1. Démarrage avec absence, illisible simulé, schéma invalide, quarantined,
   ready et serving_closed sans autorisation.
2. Énumérer les routes réellement enregistrées, toutes méthodes ; paramètres
   synthétiques, aucune identité puis identité synthétique valide.
3. Attendre 503 ou le 403 Lite documenté ; vérifier zéro endpoint, dépendance
   DB/auth, lecture du corps, mail, job et donnée documentaire retournée.
4. Tester les transitions, dont démarrage quarantiné puis ready reste fermé.
5. Activer les flags workers mais remplacer leur travail par espions et
   ajouter un contrôle positif ready : preuve causale du blocage.
6. Tester serving_closed côté décision middleware avec garde simulée,
   explicitement sans crédit cryptographique/SQL de la vraie release.
7. Utiliser des barrières de synchronisation pour documenter les flux et
   mutations déjà admis au moment du passage en quarantaine.
8. Tester séparément le BFF in-process si sa fermeture visuelle est exigée.

Ce harness ne qualifierait ni le montage Docker réel ni l'absence de tunnel,
ni une autorisation de release. Ces points nécessitent une recette isolée
distincte et explicitement autorisée, sans lancement automatique ici.

## 10. Correctifs ou décisions proposés — sans implémentation

Définir d'abord le contrat : fermeture des nouvelles requêtes seulement,
ou arrêt de toute activité. Selon ce contrat :

- Ajouter la matrice exhaustive et rendre discriminant le test des workers.
- Retarder les initialisations Lite mutantes si zéro écriture pré-latch
  devient une exigence.
- Prévoir des contrôles coopératifs des traitements en cours si leur arrêt
  est requis ; ne pas prétendre qu'un middleware suffit à annuler un commit.
- Décider si une quarantaine dynamique doit rester verrouillée jusqu'à
  redémarrage/réautorisation explicite.
- Vérifier le lien image/configuration/path/latch restauré et le mode de
  mise à jour du fichier monté avant toute qualification d'ouverture.
- Décider du comportement du frontend et des programmes administratifs
  locaux ; ne pas élargir sans décision le périmètre du middleware HTTP.
- Uniformiser si nécessaire les erreurs de serving_gate en refus 503
  sans masquer les incidents ; aucun fail-open n'est démontré actuellement.

## 11. Résultats de sécurité et recommandation

| # | Severity | File | Lines | Vulnerability | Confidence |
|---|----------|------|-------|---------------|------------|
| — | — | — | — | Aucune vulnérabilité exploitable démontrée par cet audit statique | — |

**NO-GO pour déclarer cette étape qualifiée.** Condition minimale de reprise :
contrat de quarantaine explicite, preuve de l'attachement effectif au latch,
matrice in-process exécutée avec assertions d'absence d'effets, tests des
transitions et visibilité du montage si elle fait partie de la garantie.
Les limites connues doivent être acceptées explicitement ou corrigées dans
une révision distincte, jamais dissimulées par un PASS de composant.

Ce verdict ne remet pas artificiellement en cause les résultats de composants
annoncés ; il interdit de les convertir en validation de la quarantaine.
Production, ouverture des inscriptions, S2 et Lifecycle 10 restent non autorisés.
