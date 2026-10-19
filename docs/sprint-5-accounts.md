# Sprint 5 — Comptes, isolation et préparation SaaS

**Déploiement VPS :** la configuration de production autonome décrite à la fin de ce guide
est remplacée par le [Sprint 6](sprint-6-cicd.md), qui réutilise votre Traefik existant et les
images de votre Registry. Ne pas installer le proxy supplémentaire de l’ancienne préparation.

## Audit et stratégie des propriétaires

Avant modification : FastAPI et PostgreSQL, moteur Python indépendant, Express BFF,
React, compte local `users`, scrypt, cookie HTTPS et coffre de sessions BYOK en RAM.
Le navigateur sans session pouvait encore accéder aux documents du propriétaire de la
clé serveur. Il n’existait pas de parcours d’inscription ni de récupération.

Tables avec `owner_id` : `users`, `documents`, `ai_reservations`, `ai_usage`,
`ai_summaries`, `ai_interactions`, `chunk_embeddings`, `index_jobs`, `rag_results`,
`long_summary_jobs`. Pages, chunks et analyses héritent de la propriété du document ;
sources, étapes et liens RAG sont autorisés via leurs documents/réservations/résultats.
Il n’existe pas de table de conversations indépendante : les questions/réponses sont
dans `ai_interactions`. Les comparaisons sont des `rag_results` liés aux documents.

La migration `0006` conserve tous les UUID, fichiers, résultats, historiques, budgets et
hachages existants. Elle ajoute `users.email` facultatif et `disabled_at`, puis
`workspaces`, `workspace_memberships`, `account_tokens` et `account_deletion_requests`.
Chaque propriétaire historique reçoit un espace dont l’identifiant est son `owner_id`.
Les comptes existants sont rattachés à leur propre espace. Aucun changement de propriétaire
ni fusion de documents n’est effectué. Les nouveaux comptes reçoivent un UUID serveur.
Le rôle est exclusivement `owner`, un compte et un propriétaire par espace. Le registre
prépare des espaces partagés ; aucune route ne permet actuellement d’inviter des collaborateurs.

Les mots de passe scrypt restent utilisables et sont remplacés par Argon2id à la connexion
réussie. Le retour à `0005` conserve ces nouveaux hachages : **l’ancien code scrypt seul ne
peut pas les vérifier**. Un retour applicatif doit garder le lecteur Argon2id, ou passer
par une réinitialisation ; restaurer une sauvegarde ancienne perd les écritures postérieures.

## Mise à jour locale sans perte

Ne jamais utiliser `down -v`. Prévoir une interruption des sessions ; aucune tâche IA
n’est relancée automatiquement.

```powershell
docker compose stop api web
python tools/backup_local.py
# Remplacer par le chemin effectivement affiché :
python -m tools.validate_restore var/backups/sprint5-YYYYMMDD-HHMMSS
docker compose --profile https up --build -d
docker compose ps
```

`validate_restore` crée une base `documind_restore_*` neuve, restaure le dump, compare les
empreintes des colonnes historiques, teste montée/retour de migration et vérifie chaque
fichier par taille et SHA-256. Il retire seulement la copie de test après succès. La base
locale n’est pas remplacée. En cas d’échec, la copie reste à inspecter ; ne pas réutiliser
son nom sans contrôle. L’utilitaire local suppose PostgreSQL accessible sur 127.0.0.1.

Configurer `BFF_SERVICE_KEY` avec un secret aléatoire de 32 caractères minimum. Ce secret
serveur est distinct des clés des scripts. L’installation locale a reçu une clé interne
sans modifier les clés historiques ni la configuration IA. Aucun secret n’est livré dans
les exemples. Ouvrir `https://localhost:8443/login` ; les identifiants historiques fonctionnent.

## Administration des comptes historiques

Commandes locales dans le conteneur API ; aucune route HTTP ne permet de revendiquer un UUID.

```powershell
docker compose exec api python -m backend.account_admin owners
docker compose exec api python -m backend.accounts administrateur --owner-id UUID_HISTORIQUE --email admin@example.test
docker compose exec api python -m backend.account_admin attach-email IDENTIFIANT_EXISTANT personne@example.test
```

Le premier outil affiche uniquement les UUID, leur état de rattachement et le nombre de
documents. Le second demande le mot de passe de manière interactive et refuse un propriétaire
déjà associé. Un compte existant n’est jamais réaffecté automatiquement. L’email est considéré
comme vérifié par l’administrateur : vérifier réellement l’identité avant cette commande.
Un propriétaire historique non rattaché garde ses données, accessibles aux scripts autorisés,
mais n’est plus exposé par défaut dans le navigateur.

## Inscription et récupération

`REGISTRATION_MODE=disabled` par défaut ; seul `invite` permet l’inscription. Pas d’inscription
publique libre. Activer volontairement ce mode dans `.env`, redémarrer l’API, puis :

```powershell
docker compose exec api python -m backend.account_admin invite personne@example.test
```

Transmettre le code uniquement au destinataire vérifié, par un canal approprié. L’invitation
est liée à l’email, valable 24 heures et consommée par UPDATE conditionnel atomique. Seule son
empreinte est persistée. Le formulaire n’accepte ni `owner_id` ni rôle.

La récupération par email demande `SMTP_HOST`, `SMTP_PORT`, `SMTP_FROM`, éventuellement
`SMTP_USERNAME`/`SMTP_PASSWORD`. TLS implicite par défaut ; `SMTP_STARTTLS=true` exige STARTTLS.
`ACCOUNT_BASE_URL` est une origine HTTPS fixe. Le lien contient un jeton en fragment, retiré
immédiatement de l’adresse par le frontend. Jamais de token dans les journaux d’accès.
La réponse HTTP est identique pour une adresse connue ou inconnue. L’envoi est asynchrone,
borné et sans journaliser le destinataire ou le contenu. Aucun SMTP n’est contacté dans les tests.
Sans configuration mail, aucun message n’est envoyé : associer/configurer l’email avant usage.
Les tokens de récupération expirent après `RESET_TTL_SECONDS=900`, sont à usage unique et
invalident les autres tokens de récupération et toutes les sessions après changement du mot
de passe. Les erreurs de livraison sont techniques et ne sont pas exposées au demandeur.

## Sessions, CSRF et droits

Cookie `__Host-documind`, HttpOnly, Secure, SameSite=Strict, Path=/, sans Domain, expiration
fixe de 30 minutes par défaut. Les empreintes des sessions et les clés BYOK restent en RAM,
avec révocation et destruction à l’expiration/redémarrage. La page Sécurité liste les sessions
de l’utilisateur uniquement et permet leur révocation. Changer le mot de passe révoque tout.
Chaque requête authentifiée relit le statut du compte et sa propriété en base.

Le BFF ne transmet au backend que des routes explicitement autorisées. Il impose HTTPS
et une session pour les données documentaires, y compris les lectures. Il ignore les clés et
autorisations fournies par le navigateur. Les appels API directs par X-API-Key sont réservés
aux scripts internes des propriétaires configurés, et désactivables avec `LEGACY_API_ENABLED`.
Ces clés ne donnent aucun droit sur le profil, la clé BYOK ou la suppression d’un compte.

Pour chaque mutation, le frontend récupère un jeton CSRF éphémère. Le BFF vérifie son cookie
HttpOnly Secure, le jeton d’en-tête et une signature HMAC liée à la session. Le même mécanisme
protège la connexion contre le login CSRF ; le jeton anonyme devient invalide après connexion.
Les contrôles Origin/Fetch Metadata et la CSP restent actifs. Aucun token permanent dans
localStorage/sessionStorage ; les secrets de formulaire sont vidés et restent hors du cache
des mutations React Query. React affiche les textes sans HTML brut.

Les workers de résumé et d’indexation revalident contexte et compte avant chaque appel.
La révocation supprime la clé et interdit l’étape suivante ; un appel déjà envoyé peut finir
et reste comptabilisé. Les traitements ambigus conservent leur réservation pour réconciliation.
Les plafonds DocuMind sont des estimations cumulées, jamais le solde réel OpenAI.

## Ressources et stockage

| Variable | Défaut | Portée |
|---|---:|---|
| `REQUESTS_PER_MINUTE` | 120 | utilisateur/propriétaire ; IP à 4 fois ce plafond |
| `UPLOADS_PER_MINUTE` | 5 | propriétaire |
| `MAX_DOCUMENTS_PER_OWNER` | 100 | quota atomique des imports |
| `MAX_STORAGE_BYTES_PER_OWNER` | 524288000 | fichiers persistés par propriétaire |
| `MAX_STORAGE_BYTES_TOTAL` | 5368709120 | tous les fichiers persistés |
| `AI_MAX_CONCURRENT_PER_OWNER` | 1 | réservations IA actives par propriétaire |

Connexion : 5 tentatives/minute par identifiant et 10/minute par IP ; récupération limitée
par IP et email. Les clés des compteurs sont hachées. Deux dérivations de mots de passe
simultanées maximum, chacune Argon2id 64 MiB, trois itérations, parallélisme 1. Les imports
gardent limites taille/contenu, extraction dans un processus borné, noms aléatoires et stockage
privé. Le verrou global des budgets sérialise aussi les vérifications de quotas documentaires,
avant insertion. Les fichiers temporaires en échec sont retirés. Pas d’exécution de documents.
Les noms stockés ne dépendent jamais d’un chemin client ; aucune route ne sert ces fichiers.

Le proxy authentifié transmet l’IP ; les en-têtes forgés d’un navigateur sont remplacés.
Les compteurs RAM nécessitent **un seul processus API/BFF** et se remettent à zéro au redémarrage.
Les budgets financiers et quotas documentaires restent atomiques et persistants. Les réservations
partielles comptent dans la concurrence personnelle : reprendre/annuler, ne pas contourner.

## Confidentialité, suppression et conservation

La page Confidentialité permet de supprimer un document, ses résultats IA seulement ou ses
embeddings seulement. Ces opérations effacent immédiatement les enregistrements concernés ;
la suppression du document retire également le fichier. Une tâche active peut bloquer l’effacement
jusqu’à sa fin/annulation. Les comparaisons et recherches liées sont invalidées quand nécessaire.
Le cache navigateur n’est pas une archive ; recharger une page après une suppression.

La demande de suppression du compte exige le mot de passe, désactive immédiatement l’accès et
révoque toutes les sessions/BYOK. Elle est persistée pour traitement administratif. Après arrêt
des workers actifs et réconciliation éventuelle des réservations :

```powershell
docker compose exec api python -m backend.account_admin purge UUID_DU_COMPTE
```

La commande refuse un compte sans demande préalable. Elle annule les résumés suspendus sûrs,
efface documents/fichiers, résultats, embeddings, invitations/reset liés et identité. Elle conserve
l’UUID propriétaire pseudonymisé et la comptabilité sans textes ni clés pour prévenir le contournement
des quotas. La suppression matérielle de la RAM, des blocs de disque et des copies tierces n’est pas garantie.

Politique opérationnelle à adopter avant production : traitement des demandes sous 30 jours,
sauvegardes chiffrées avec rotation maximale de 30 jours, journaux techniques sans contenu avec
rétention de 30 jours maximum, et décision documentée sur la durée de comptabilité pseudonymisée.
**Ces délais ne sont pas automatisés dans ce MVP.** Les sauvegardes locales existantes sont conservées
pour sécurité de migration ; l’exploitant doit les retirer selon sa politique. Après restauration,
réappliquer les demandes de suppression avant réouverture des accès.

Préparer identité/contact du responsable, finalités, base légale, sous-traitants et transferts,
durées par catégorie, procédure de droits/export et traitement des incidents. L’IA doit rester
optionnelle, avec information sur les données envoyées et les règles du fournisseur. Cette préparation
technique ne garantit pas la conformité RGPD : validation juridique et organisationnelle nécessaire.

## Configuration de production préparée, non lancée

`compose.production.yaml` utilise un projet et des volumes distincts, PostgreSQL et réseau
applicatif privés, un BFF sans port publié, et Traefik via fournisseur de fichiers. Aucun socket
Docker n’est monté. Le seul port préparé reste `127.0.0.1:9443`, donc non public.
Pas de tableau de bord Traefik. API/BFF en lecture seule, répertoires temporaires bornés,
limites CPU/mémoire/PID et rotation des journaux Docker. Les trois services métier ont des healthchecks.

```powershell
Copy-Item .env.production.example .env.production
# Renseigner les secrets localement, l’hôte et ACCOUNT_BASE_URL.
python tools/prepare_production.py
# Fournir un certificat de confiance et sa clé dans var/production/tls/cert.pem et key.pem.
docker compose --env-file .env.production -f compose.production.yaml config --quiet
```

Ces commandes préparent/valident ; elles n’ouvrent pas l’application. La configuration Traefik
générée contient le secret proxy et reste sous `var/`, ignoré. Les mots de passe PostgreSQL doivent
être aléatoires et compatibles avec une URL (base64url conseillé). Choisir des secrets distincts.
L’exploitant doit définir quotas disque au niveau du système de fichiers/volume : Compose ne limite
pas de façon portable la taille d’un volume nommé. Prévoir de la marge pour PostgreSQL/WAL,
sauvegardes, fichiers transitoires et extraction. Monitorer disque, tâches bloquées, erreurs et SMTP.

Pour sauvegarder l’environnement de production préparé, arrêter ses services `api`/`web`, puis
`python tools/backup_local.py --production`. Le test de restauration fourni cible le PostgreSQL local ;
sur un serveur distant, adapter explicitement la connexion de restauration et tester sur une instance
isolée. Aucune restauration automatique ne remplace une base existante.

Avant ouverture publique : certificats/domaines, gestionnaire de secrets et rotation, sauvegarde chiffrée
hors machine et exercices de restauration, alertes et supervision, politique de rétention automatisée,
sécurité du serveur et des volumes, validation mail, tests de charge, audit indépendant, procédure
incidents et validation de la politique de confidentialité. MFA et authentification fédérée ne sont pas
implémentés. Un déploiement distribué exige un coffre éphémère et un limiteur partagés.

Sources techniques : [OWASP Password Storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html),
[OWASP CSRF Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html).
