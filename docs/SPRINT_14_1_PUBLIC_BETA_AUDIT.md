# Sprint 14.1 — Audit préalable à la bêta publique

Date : 25 octobre 2026. Audit statique local du commit
`8243e0511c5505a9cc70f76ad02392f7a816590d`, branche `main`.

**Verdict : No-Go pour l'ouverture immédiate.** Le parcours public est largement
implémenté, mais son autorisation dans la chaîne de livraison, la politique de
désactivation complète des appels IA et la recette à cinq admissions restent à valider.
Ce rapport ne constitue aucune autorisation d'ouverture, de publication ou de déploiement.

## 1. Périmètre et niveau de preuve

Seul ce document a été ajouté. Aucun code, workflow, migration ou paramètre n'a été
modifié. Aucun service, test dynamique, accès distant ou appel fournisseur n'a été lancé.
Les conclusions « confirmé » ci-dessous proviennent de la lecture du dépôt ; elles ne
remplacent pas une validation d'exécution.

L'état de production fourni par l'administratrice est : version ci-dessus déployée,
schéma `0007`, inscriptions publiques et IA désactivées. Les valeurs effectives des
conteneurs, les digests, les règles GitHub et le fonctionnement SMTP ne sont pas
vérifiables depuis cet audit local. Aucun fichier privé de configuration n'a été consulté.

Sources principales : [configuration](../backend/config.py),
[comptes](../backend/account_api.py), [admission publique](../backend/public_registration.py),
[authentification](../backend/auth.py), [passerelle](../backend/gateway.py),
[administration](../backend/account_admin.py), [BFF](../frontend/server/app.mjs),
[Compose](../compose.production.yaml), [tests publics](../tests/test_public_beta.py).

## 2. Architecture réelle du parcours

### 2.1 Chaîne HTTP et identité

Navigateur HTTPS → Traefik → BFF Express → API FastAPI → PostgreSQL.
Seul le BFF est connecté au réseau externe `web` ; PostgreSQL et FastAPI ne publient
pas de port hôte dans le Compose de production. Le BFF utilise son identité technique
`BFF_SERVICE_KEY`, distincte des sessions utilisateur et des anciennes clés API.

Les routes du routeur de comptes exigent `secure_gateway()` : clé BFF valide et
`X-Documind-Secure: 1`. Leur caractère public signifie « sans session utilisateur
préalable », pas « API directement accessible sans passerelle ».
Les en-têtes d'adresse client ne sont admis par `client_ip()` qu'avec l'identité BFF.
La confiance du BFF dans Traefik dépend de l'adresse de proxy fournie par le déployeur.

Le BFF conserve les contrôles Host, Origin, transport HTTPS et CSRF. Les opérations
publiques de compte ne nécessitent pas de cookie de connexion existant ; elles
restent soumises au CSRF pour les écritures. Un cookie présent n'est jamais une preuve
de session : l'API valide la session serveur, son propriétaire et l'état du compte.
Les mécanismes d'admission des uploads SEC10-02 et d'identité SEC10-03 sont conservés.
Les corps JSON relayés par le BFF sont bornés à 32 768 octets ; les uploads gardent
leurs limites distinctes de taille, concurrence, durée et espace temporaire.

### 2.2 Routes et composants

Les chemins BFF `/bff/...` sont relayés vers `/api/v1/...`.

| API | Fonction | Comportement |
| --- | --- | --- |
| `GET /auth/options` | `options()` | Mode, capacité disponible, version des conditions et informations légales ; pas de liste de comptes. |
| `GET /auth/registration-challenge` | `registration_challenge()` → `challenge()` | Challenge de preuve de travail limité en débit. |
| `POST /auth/register` | `register()` → `admit()` | Public : réponse générique 202 ; invitation : parcours distinct 201 ; désactivé : 403. |
| `POST /auth/verify-email` | `verify_email()` → `verify()` | Jeton et mot de passe choisi ; activation 200, lien invalide/expiré/rejoué 400. |
| `POST /auth/resend-verification` | `resend_verification()` → `admit(resend=True)` | Réponse générique 202 ; nouvelle preuve et mot de passe ; anciens liens invalidés. |
| `POST /auth/login` | `backend/ai/settings_api.py:login()` | Session serveur après vérification d'identité et état du compte. |
| `POST /auth/forgot-password`, `/auth/reset-password` | `forgot()`, `reset()` | Récupération séparée ; reset à usage unique et révocation des sessions. |

Frontend : `frontend/src/pages/Account.tsx` (`AccountAccess`),
`frontend/src/services/registration.ts` (`registrationProof`), service HTTP de comptes,
routes dans `frontend/src/App.tsx`, pages d'information publique et tests
`frontend/src/pages/PublicBeta.test.tsx`.
Le formulaire public remplace l'invitation par consentement/version des conditions,
preuve de travail et honeypot. Le mode fermé désactive l'offre d'inscription dans l'UI ;
une page déjà ouverte peut devenir obsolète, mais la base reste autoritaire.

### 2.3 Création et vérification

`admit()` normalise l'adresse via le schéma Pydantic, vérifie mode et consentement,
applique les limites puis consomme le challenge. Une transaction crée ensemble :
compteur d'admission, `Workspace`, `User`, `WorkspaceMembership`, budget BYOK et jeton.
L'utilisateur public est créé avec `disabled_at` renseigné et sans email vérifié.
Il ne peut donc ni se connecter ni importer un document avant activation.
L'identifiant propriétaire et le nom interne sont générés côté serveur.

Le jeton aléatoire est stocké seulement sous forme de digest SHA-256 dans
`account_tokens`. `consume_token()` est un `UPDATE` conditionnel atomique sur type,
expiration et absence d'usage précédent. La vérification verrouille d'abord le compte,
puis consomme le jeton ; un mauvais mot de passe entraîne un rollback, sans brûler le lien.
Elle exige aussi un compte public non vérifié et sans demande de suppression.
Le jeton vérifié ne crée pas automatiquement de session.

Le TTL de vérification vaut 3 600 secondes par défaut, configurable de 300 à 86 400.
Le reset utilise son propre TTL, 900 secondes par défaut. Le frontend extrait les
jetons du fragment `#token=...`, nettoie l'URL et attend une action explicite ; les
jetons ne sont pas placés dans le stockage navigateur ni transmis en query string.

L'envoi SMTP intervient **après commit**, via une file RAM bornée à 100 éléments et
un thread (`backend/main.py`). SMTP_SSL ou STARTTLS utilise un contexte TLS vérifié,
avec timeout. Un échec ou redémarrage peut perdre un mail déjà accepté en file ; le
compte reste en attente et sa place reste consommée. Le renvoi permet une récupération,
sans garantie de livraison durable ni retry automatique. Les échecs sont journalisés.

Une adresse déjà inscrite n'est ni écrasée ni réactivée par une nouvelle inscription.
Les doublons, preuves refusées et capacités épuisées reçoivent la même réponse publique
générique 202. Les erreurs de schéma, de consentement, de débit ou de saturation peuvent
avoir des codes distincts : il ne s'agit pas d'une garantie d'indistinguabilité temporelle.

## 3. Plafond de cinq : sémantique et concurrence

`PublicRegistrationQuota`, créé et initialisé par `0007_public_beta.py`, possède une
ligne `id='public'`, `issued_count=0`, `closed=false`.
L'admission réalise dans sa transaction :

```sql
UPDATE public_registration_quota
SET issued_count = issued_count + 1
WHERE id = 'public' AND issued_count < :limit AND closed = false
RETURNING issued_count;
```

Le verrouillage de cette ligne et la condition SQL assurent que deux transactions
concurrentes ne réservent pas la même dernière place. La création du compte et
l'incrément sont atomiques ; un rollback ne consomme pas la place. Une ligne absente
refuse les admissions. Le sémaphore RAM de création, capacité 1 par processus,
réduit aussi les travaux concurrents, avec 503 si occupé ; il ne remplace pas le SQL.

**La limite est cumulative, pas un nombre de comptes actifs.** Sont comptés les
comptes publics admis, y compris non vérifiés ou privés de mail. La vérification,
désactivation, suppression, purge et fermeture/réouverture ne décrémentent pas le
compteur. Les comptes historiques et les invitations ne sont pas comptés.
Avec une limite 5 et un compteur préexistant `n`, il reste `max(0, 5-n)` admissions,
pas cinq nouvelles places. Le mode public n'offre pas de parcours d'invitation parallèle
dans `register()` ; les comptes préexistants gardent leur fonctionnement.

Le plafond atteint produit 202 générique sans nouveau compte ; `options()` annonce
une capacité indisponible. Ce comportement doit être expliqué dans l'UI, sans promettre
qu'un mail arrivera pour toute réponse 202.

La configuration accepte actuellement de 0 à 10 000 admissions : **5 est une décision
d'exploitation, pas un invariant codé pour cette bêta**. Ne jamais réinitialiser ou
augmenter automatiquement le compteur pour récupérer des places perdues.

## 4. Protections anti-abus et confidentialité

| Protection confirmée | Limite ou vérification restante |
| --- | --- |
| Challenge aléatoire, lié à l'IP, TTL 300 s, consommé une seule fois, magasin RAM borné à 1 024. | Disponible même en mode fermé, notamment pour le renvoi ; disparition au redémarrage. |
| SHA-256 avec difficulté configurable 10–18, défaut 12 ; honeypot. | Freine l'automatisation mais ne prouve pas l'humanité ; mesurer sur mobile avec difficulté réelle. |
| Création : 10/min global ; IP et adresse 3/h par défaut ; challenge 60/min global et 5/min/IP. | Création et renvoi partagent des budgets ; NAT partagé et abus ciblé peuvent bloquer un destinataire. |
| Vérification : 10/min/IP ; récupération limitée par IP et adresse. | Limiteurs et challenges locaux au processus ; conserver une seule API/BFF selon les contraintes actuelles. |
| Champs bornés, mots de passe 12–256 caractères, types stricts et champs inconnus refusés. | Validation syntaxique email ne garantit pas la délivrabilité ; ne pas déduire une conformité juridique. |
| Hachage du mot de passe même pour un doublon ; réponses génériques. | Vérifier contenu, codes, délais et erreurs SQL/SMTP, sans promettre une égalité temporelle absolue. |
| Événements SEC10-04 structurés et test de non-fuite spécifique à l'inscription. | Vérifier aussi Traefik, SMTP et l'accès aux journaux réels ; aucun token/email/mot de passe à copier dans les preuves. |

Le calcul navigateur est borné à environ 20 secondes et 4 194 304 essais, avec
restitution périodique de la main. Une difficulté trop élevée peut donc refuser des
clients légitimes. Il faut annoncer la limite de cinq et la consommation des places
en attente ; un attaquant possédant cinq adresses peut épuiser le quota malgré la PoW.

`PUBLIC_LEGAL_READY=true` est une attestation de configuration, pas un audit des textes.
Le validateur exige opérateur, contact, version et URLs HTTPS sans identifiants ni
fragment. Le contenu, l'accessibilité et l'approbation des documents restent externes.

## 5. Isolation des fonctionnalités IA

### Garanties trouvées

`backend/ai/service.py:configuration_issue()` vérifie `ai_enabled` avant clé/prix/budget.
Les réservations de nouvelles générations et opérations RAG appellent ce contrôle.
`settings_for_request()` ne remplace pas `ai_enabled` dans la configuration BYOK : une
clé personnelle ne réactive donc pas à elle seule les générations.
Les comptes publics ne peuvent pas choisir `OWNER_DEMO`, ni dépasser leur plafond
individuel public dans les préférences. Leur identité historique est refusée.
Les reprises de résumés vérifient aussi la configuration ; la récupération des workers
au démarrage ne reprend pas automatiquement les appels fournisseur.

La recherche peut retomber sur le lexical sans appel externe ; les résultats IA déjà
en cache peuvent être relus. L'analyse classique PDF/TXT, les statistiques et les
comparaisons locales doivent rester utilisables. Lire un historique, annuler un travail,
libérer une réservation ou déconnecter une clé ne doit pas être bloqué aveuglément.

### Lacune confirmée : validation d'une clé

`backend/ai/settings_api.py:validate_key()` ne consulte pas `ai_enabled` : après
authentification, une clé connectée peut déclencher `OpenAI(...).models.retrieve(...)`
même si l'IA est désactivée. `connect_key()` reste également accessible. Le BFF ne
constitue pas un coupe-circuit global IA et relaie cette route protégée.

Il s'agit d'un **appel externe de métadonnées**, pas d'une preuve de génération de texte,
d'envoi documentaire ou de facturation de tokens. Néanmoins, une politique « aucune
fonction IA activée et aucun appel fournisseur » n'est pas garantie aujourd'hui.
Prévoir un refus explicite côté API avant toute construction de client fournisseur et
une UI cohérente. Décider si la connexion de clé doit être interdite tant que l'IA est
fermée ; conserver sa suppression. Tester les comptes publics ET préexistants.

Le validateur `Settings` public n'exige pas `AI_ENABLED=false`. La livraison doit donc
imposer explicitement ce paramètre pour cette bêta, ainsi que `OWNER_DEMO_ENABLED=false`
et `LEGACY_API_ENABLED=false`. Un budget BYOK nul ou l'absence de clé serveur ne
remplacent pas ce contrôle. Une modification du fichier env seule ne change pas les
paramètres d'un processus déjà lancé : aucune fermeture IA à chaud n'est démontrée.

## 6. Livraison et exploitation

Trois garde-fous distincts interdisent actuellement le mode public :

1. `tools/prepare_production.py:main()` accepte seulement `disabled` ou `invite`.
2. `tools/deploy_production.py:check_config()` refuse le mode public dans le Compose résolu.
3. `execute()` exécute dans l'image `Settings()` puis une assertion identique, avec
   interdiction des clés historiques.

Le helper `prepare_production.py` n'est pas le chemin automatique du workflow de
déploiement : corriger uniquement ce helper ne suffit pas. Ces refus sont volontaires,
pas une incompatibilité de la migration `0007` avec l'application.

La CI lance Linux/SQLite, PostgreSQL/pgvector, confinement Linux/Docker, Windows et
frontend/BFF/TypeScript. `publish` dépend des jobs `python`, `windows`, `frontend`,
est exclu des PR et publie sur `main` trois images `linux/amd64`, figées par digest
dans le bundle. Une fusion sur `main` peut donc publier des images ; aucun déploiement
n'en découle automatiquement. `deploy.yml` est manuel, avec environnement `production`
et contrôles d'approbation. L'état effectif des protections GitHub n'a pas été consulté.

Le déployeur compare les révisions, exige une approbation de migration si elles
diffèrent, sauvegarde sous verrou et vérifie santé/HTTPS/CSRF/refus anonyme. La base
annoncée étant déjà en `0007`, activer la bêta ne nécessite pas de nouvelle migration.
`ALLOW_MIGRATION`, `INITIALIZE` ou un rollback ne sont pas des autorisations d'ouverture.

Les sauvegardes conservent le dump PostgreSQL complet et les documents de `/app/var`.
`deployment.lock` est partagé par déploiement, sauvegardes et conservation ; la
conservation Restic ne doit pas quitter son mode simulation dans ce sprint.
**L'inventaire de `tools/backup_local.py` pour `integrity.json` omet
`public_registration_quota`** : le dump l'inclut normalement, mais la vérification
complémentaire par table ne prouve pas la conservation de son compteur/verrou.
La liste autorisée de `tools/verify_snapshot.py` l'omet également ; une future
extension doit donc couvrir le producteur et le vérificateur de l'inventaire.
Ajouter cette preuve dans une restauration indépendante, jamais sur les volumes réels.

Le downgrade `0007` refuse d'effacer une histoire d'admissions publiques. Préférer un
retour applicatif compatible `0007`, inscriptions fermées, sans downgrade ni remise à
zéro du compteur. Une restauration ancienne peut remettre le compteur à une valeur
antérieure : garder l'ouverture fermée et réconcilier les admissions avant toute reprise.
Ne pas restaurer automatiquement la base pour fermer l'inscription.

### Activation proposée, à implémenter et approuver ultérieurement

Créer une autorisation dédiée, par défaut refusée, distincte de la migration : validation
manuelle d'un environnement protégé, liée au SHA/digests, au domaine, à la limite 5 et
aux drapeaux IA fermés. Centraliser les mêmes invariants dans les chemins de préparation
et les deux préflights, au lieu de supprimer leurs refus sans remplacement.
L'approbation doit produire une preuve sans secret : auteur, date, version, compteur,
capacité restante, portée et résultat des contrôles. Aucun secret dans les inputs Actions.

Procéder en deux temps :

1. Relever le statut puis fermer le verrou SQL avec le mode actuel encore désactivé.
2. Livrer une version approuvée autorisant explicitement `public`, limite 5, IA false,
   démonstration false et legacy false, **sans rouvrir le verrou SQL**.
3. Vérifier configuration effective expurgée, schéma, compteur, santé, SMTP, textes,
   tests de refus IA et procédure de fermeture. Conserver le compteur existant.
4. Une décision opérateur distincte autorise `reopen --execute`. Ne jamais réouvrir
   automatiquement lors d'un déploiement ou d'une restauration.

Le CLI actuel sait rouvrir, mais ne réalise pas cette checklist complète et n'émet pas
un événement dédié à cette décision ; prévoir validation et traçabilité autour de lui.

## 7. Tests existants et lacunes

**Aucune suite n'a été relancée pour cette phase d'audit.** La présence d'un test dans
le dépôt ne constitue pas ici un résultat d'exécution, ni une preuve de production.

| Domaine | Couverture existante lue | Validation à ajouter/compléter |
| --- | --- | --- |
| Inscription | `test_public_beta.py` : compte en attente, workspace, membership, authentification refusée avant vérification. | Première inscription via HTTPS/BFF avec configuration exacte limite 5. |
| Email | Jeton expiré/invalide/rejoué, mauvais mot de passe, renvoi, récupération d'un compte en attente non sollicité. | SMTP TLS réel de recette, panne/file pleine/restart ; vérifications concurrentes et renvoi concurrent sans deadlock. |
| Quota | Saturation générique à limite 1 ; deux demandes concurrentes ; incrément SQL direct sans sémaphore. | Cinq admissions puis sixième refusée, compteur et comptes cohérents, dont comptes en attente ; plusieurs connexions PostgreSQL à 4/5. |
| Fermeture | Mode désactivé, fermeture SQL, réouverture, renvoi toujours permis. | Fermeture concurrente à la dernière admission, changement de processus/mode, persistance après redéploiement, fermeture quand quota déjà atteint. |
| Historique | Migration 0006→0007 préservant identités et comptes désactivés ; downgrade refusé après admission ; purge ne libérant pas de place. | Comptes historiques/invités exclus du compteur ; restoration du compteur et du verrou ; aucune remise à zéro sur réactivation. |
| Anti-abus | PoW expirée/rejouée/mauvaise IP, honeypot, consentement, débit avant hash, bornes mémoire, non-fuite des journaux. | Difficulté 12 sur mobiles, IP NAT, test multi-IP borné, proxy effectif et trafic hostile local mesuré. |
| Frontend/BFF | Tests `PublicBeta.test.tsx`, routes publiques sous HTTPS/CSRF ; tests passerelle et uploads existants. | Page ouverte avant fermeture, CSRF/Origin négatifs sur chaque écriture, trajet complet via Traefik local. |
| IA fermée | `test_ai_disabled_and_consent`, isolation BYOK et quotas ; refus OWNER_DEMO pour public. | Matrice public/historique avec clé BYOK validée, résumés courts/longs et reprises, questions/RAG/indexation/comparaison, validation de clé : zéro invocation fournisseur. |
| Exploitation | Tests déploiement/sauvegarde/restauration existants. | Autorisation explicite public + refus sans approbation ; cap différent de 5/IA true refusés ; rollback `0007` fermé, fermeture opérateur tracée. |

Les fixtures publiques utilisent notamment une limite 4, une difficulté 10 et un
plafond IP/email de 10/h, pas le profil envisagé. Les tests concurrents HTTP peuvent
être refusés par le sémaphore avant le SQL : compléter par de vraies transactions
PostgreSQL distinctes utilisant la logique complète `closed=false`.
Avec le débit réel 3/h/IP, cinq inscriptions depuis une seule IP ne sont pas censées
réussir dans l'heure ; séparer recette du quota et recette des limites anti-abus,
sans relever arbitrairement les limites de production.

## 8. Risques classés et modifications nécessaires

| Référence | Criticité | Constat et preuve | Action avant ouverture |
| --- | --- | --- | --- |
| B14-01 | Haute / bloquant livraison | Trois refus explicites du mode public dans les outils. | Autorisation dédiée, cohérente et testée ; ne pas contourner par exécution manuelle non contrôlée. |
| B14-02 | Haute / bloquant politique IA | `validate_key()` appelle le fournisseur sans contrôle global ; mode public compatible avec AI true dans `Settings`. | Gate API et invariants de livraison, puis preuve zéro appel fournisseur avec BYOK. |
| B14-03 | Haute / bloquant recette | Pas de recette auditée exactement à cinq, concurrence PG complète et fermeture en course. | Tests déterministes et stack jetable ; pas d'affirmation de dépassement observé : le SQL est correctement conditionné. |
| B14-04 | Haute / externe non vérifié | SMTP, textes approuvés, drapeaux réels, observabilité et sauvegarde récente non inspectés. | Preuves opérateur expurgées et recette indépendante, sans ouverture ni données réelles. |
| B14-05 | Moyenne | Cinq places peuvent être consommées par des comptes en attente ; file SMTP non durable. | Accepter explicitement la sémantique cumulative, tester renvoi/récupération et alerter sur échecs ; ne pas recycler automatiquement. |
| B14-06 | Moyenne | Compteur/verrou absents de l'inventaire d'intégrité complémentaire des backups. | Étendre vérification et restauration isolée ; protéger toute réouverture après restauration. |
| B14-07 | Moyenne | Limiteurs/challenges/sessions RAM ; NAT et PoW mobile ; capacité réelle non mesurée. | Garder un processus, budgets bornés, tests de capacité locaux ; limites explicites et suivi. |
| B14-08 | Moyenne | `verify()` remet `disabled_at=None` pour un public non vérifié sans demande de suppression. | Définir le blocage administratif d'un compte en attente : le seul timestamp ne distingue pas blocage volontaire et attente d'email. Tester cette politique avant de la proposer aux opérateurs. |
| B14-09 | Faible à moyenne | UI potentiellement obsolète, information de fermeture générique, acceptation légale purement déclarative. | Messages cohérents et revue des informations publiques ; conserver la décision côté serveur. |

Aucune nouvelle faille permettant de dépasser effectivement le compteur ou de prendre
le compte d'un tiers n'est démontrée par cet audit. Aucun risque critique confirmé
n'est attribué sur la seule base d'une validation de production manquante.

## 9. Plan proposé des phases 14.2 à 14.7

Chaque phase requiert validation avant implémentation ; ce plan ne modifie rien.

| Phase | Travaux | Critères d'acceptation mesurables |
| --- | --- | --- |
| 14.2 — Politique et autorisation | Fixer cinq admissions cumulatives, traitement des comptes en attente, approbation explicite et invariants communs de préparation/livraison ; activation en deux temps. | Sans approbation : public refusé ; avec IA true ou limite autre que 5 : refus ; avec verrou fermé : aucune admission ; schéma 0007 conservé. |
| 14.3 — IA strictement fermée | Contrôler validation de clé et autres appels externes, adapter UI sans casser lecture historique, annulation ou déconnexion. | Compteurs mock de tous les clients fournisseur à zéro pour public et historique, y compris BYOK et reprises ; analyse classique fonctionnelle. |
| 14.4 — Compteur, identité et concurrence | Tests 5/6, vérification/rejeu/renvoi en concurrence, fermeture, restauration et blocage administratif en attente. | Au plus cinq comptes admis, compteur égal aux admissions validées ; aucun nouveau compte après fermeture acquise ; aucune double activation ni deadlock sur PG17. |
| 14.5 — UX, email et anti-abus | SMTP TLS, récupération après panne, consentement/textes approuvés, PoW mobile, limites NAT et confidentialité. | Livraison et renvoi démontrés en recette, liens expirés/rejoués refusés ; aucun secret dans preuves/logs ; parcours fermé compréhensible. |
| 14.6 — Recette et exploitation | CI Windows/Linux/PG/frontend/BFF, Docker jetable proche production, restauration B2 indépendante, intégrité compteur, fermeture/rollback et suivi. | Aucun échec inexpliqué, zéro ressource de production utilisée, compteur/verrou restaurés identiques, fermeture testée sans arrêter PG ni les autres services. |
| 14.7 — Décision puis ouverture contrôlée | Revue du dossier Go/No-Go ; autorisations distinctes publication, déploiement fermé, puis réouverture SQL ; surveillance renforcée. | SHA/digests/flags et capacité restante relevés, opérateur disponible, alerte et fermeture éprouvées ; limite atteinte annoncée et aucune activation IA. |

La recette Docker doit utiliser un projet Compose dédié, volumes et PG17/pgvector
neufs, comptes/documents fictifs, identité BFF fictive, TLS local et SMTP de recette.
Les fournisseurs IA sont remplacés par des espions refusant tout appel ; aucune clé
réelle. Le sandbox garde Landlock ABI ≥3, seccomp et les restrictions Docker. Les
besoins HTTP locaux du BFF/PG/SMTP sont limités au réseau de test ; aucune sortie vers
OpenAI ni accès aux volumes, réseaux ou secrets de production. Aucun test de charge
n'est exécuté contre le VPS ou un service public.

## 10. Critères Go / No-Go

**Go uniquement lorsque tous ces points sont prouvés et approuvés :**

- Autorisation dédiée et cohérente, configuration effective public/5, AI false,
  OWNER_DEMO false, legacy false ; aucun flag déduit de la seule absence de clé.
- Compteur SQL connu et inchangé, capacité restante acceptée ; cinq n'inclut pas les
  comptes historiques. Verrou maintenu fermé jusqu'à décision explicite.
- Tests 5/6, concurrence PG, sessions/révocations, email, CSRF, séparation propriétaires,
  uploads et zéro appel IA réussis sur stack jetable.
- SMTP et documents légaux approuvés ; procédure et limites de comptes en attente
  comprises ; aucune identité ou coordonnée fictive dans l'information publique réelle.
- Sauvegarde récente confirmée et restauration indépendante `0007`, documents,
  compteur et verrou vérifiés ; retour applicatif compatible et fermeture testés.
- Santé, alertes, disque, quotas et accès aux journaux vérifiés sans secrets ; capacité
  et réseau Traefik réels validés par l'opératrice, hors de cet audit.
- CI de la version candidate réussie et revue des risques résiduels explicitement acceptée.

**No-Go** si un point manque, si un appel IA externe demeure possible contrairement à
la politique, si le compteur est inconnu, si une migration/downgrade est improvisée,
ou si la seule façon d'ouvrir est de retirer les garde-fous manuellement.

## 11. Fermeture d'urgence proposée

Le mécanisme existant est `backend.account_admin public-registration close --execute`.
Sans `--execute`, l'action reste une simulation. À intégrer à une procédure opérateur
approuvée et tracée ; **aucune commande ci-dessous n'a été exécutée**.

Depuis l'installation prévue `/srv/documind-ai`, avec la release réellement active
et ses digests, l'opératrice peut utiliser :

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

Vérifier d'abord l'identité de `current` et l'absence de déploiement/maintenance en
cours ; ne pas changer de release pour cette opération. Le CLI restitue statut,
compteur, limite et mode, sans mot de passe. Conserver cette preuve agrégée avec date,
opérateur et version dans le dossier d'incident privé, pas dans des logs de secrets.

`closed=true` bloque toute nouvelle réservation d'admission sans redémarrage, sans
arrêt de PostgreSQL et sans invalider les comptes existants. Une transaction déjà
admise avant acquisition du verrou peut terminer ; la fermeture SQL attend les
transactions concurrentes. Un mail peut donc arriver après fermeture pour une place
déjà réservée. Les vérifications, renvois et connexions existantes restent permis.

Confirmer via les options BFF que la capacité est fermée, puis observer absence de
nouvelles admissions et santé. Ne pas utiliser de nouvelles adresses réelles pour
tester une création en urgence. Si le verrou ne peut pas être confirmé, considérer
la fermeture comme non prouvée et escalader à l'opératrice ; aucun arrêt global
Traefik, restauration ou suppression de volume n'est une solution automatique.

Pour une fermeture durable de configuration, conserver le verrou fermé et préparer
séparément un changement approuvé vers `REGISTRATION_MODE=disabled`, avec contrôles
habituels. Une édition env ne modifie pas le processus actif et peut créer une
incohérence si elle n'est pas appliquée de façon contrôlée. Ne pas réouvrir lors d'un
rollback. Une future réouverture exige nouvelle décision et statut préalable ; elle
ne réinitialise jamais `issued_count` et n'active jamais l'IA.

## 12. Informations restant à relever hors dépôt

Par l'opératrice, sans communiquer de valeurs sensibles : SHA/digests actifs,
révision unique `0007`, mode effectif et flags IA/legacy/démonstration, limite,
`issued_count` et `closed`, santé, délivrabilité TLS de l'email de recette, documents
légaux approuvés, dernier backup confirmé/restauration indépendante et configuration
des alertes. Vérifier également proxy de confiance, CSRF/cookies Secure, sessions,
limitations et ressources disponibles sur la stack réelle.

Ne transmettre aucun dump, email utilisateur, document, URL de jeton, cookie,
mot de passe, clé privée ou sortie complète d'environnement/inspection Docker.
L'ouverture reste interdite tant que les phases suivantes ne sont pas validées.
