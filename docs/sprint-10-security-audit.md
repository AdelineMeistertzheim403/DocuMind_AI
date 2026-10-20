# Sprint 10 — audit de sécurité applicative, phase A

Date : **20 octobre 2026, Europe/Paris**. Périmètre : dépôt local à partir du commit
`5ac8d3f1ce4474d1d4742637beb22192194dfbe2`, incluant les fichiers et modifications des
sprints précédents déjà présents dans l'arbre de travail. Ce commit ne prouve pas l'identité
des images actuellement exécutées sur le VPS.

**Avis : ne pas ouvrir au public sur la seule base de cet audit.** Aucun accès intercompte
ou contournement d'authentification n'a été démontré dans les parcours testés. Les contrôles
existants sont substantiels, mais les risques du traitement PDF, de disponibilité et de
traçabilité doivent être traités ou acceptés explicitement, puis validés sur la configuration
déployée. Aucune compromission critique directement exploitable n'est confirmée ici.

Cette livraison contient uniquement les trois rapports de phase A. Aucun fichier applicatif,
Compose, dépendance de l'application, compte, secret ou service de production n'a été modifié.
Les correctifs appartiennent à une **phase B soumise à validation explicite**.

## Méthode, modèle de menace et limites

Analyse manuelle des routes et dépendances FastAPI, services, workers, sessions, BFF,
frontend, Dockerfiles, Compose de production, workflows et outils d'exploitation Sprints 7–9.
Exécution des suites existantes, de trois sondes locales complémentaires et de contrôles
de dépendances. Les comptes, documents, clés de service et bases des tests sont fictifs.
Les sondes ne lisent pas les documents ou comptes réels. Les fichiers privés `.env`, Gmail
et Restic n'ont pas été ouverts pour en publier les valeurs ; seuls leurs exemples versionnés
et les mécanismes de lecture ont été examinés.

Menaces considérées : client Internet non authentifié ; utilisateur authentifié malveillant ;
document contrôlé par cet utilisateur ; vol d'une session ; dépendance compromise ; accès
indésirable au réseau interne ; compromission conditionnelle d'un parseur natif. Un accès
root/Docker préexistant au VPS n'est pas assimilé à une faille HTTP de DocuMind.

Les constats concernent le **code disponible**, pas une inspection du VPS. Aucun scan de
ports, test TLS distant, test d'intrusion, charge, restauration ou appel fournisseur IA n'a
été lancé contre la production. PostgreSQL/pgvector n'a pas été exécuté pour cet audit :
les tests utilisent SQLite temporaire ; les verrous PostgreSQL nécessitent une validation
séparée. Le confinement Linux, les permissions réelles, les journaux Traefik, les règles de
pare-feu, l'environnement GitHub et les digests en production restent à vérifier.

Les résultats et commandes sont détaillés dans [la validation](validation-sprint-10-audit.md).

## Synthèse des constats

La gravité ci-dessous concerne DocuMind dans son contexte. Une CVE critique d'outil de test
n'est pas, à elle seule, une exécution distante critique dans le BFF de production.

| Identifiant | Constat | Gravité contextualisée | Confiance | Décision avant ouverture |
|---|---|---|---|---|
| SEC10-01 | Parseur PDF dans un processus disposant des droits de l'API | Élevée, conditionnelle à une compromission native | Absence de confinement confirmée ; exploitation non démontrée | Bloquant : confinement ou acceptation documentée après expertise |
| SEC10-02 | Corps d'upload reçu et bufferisé avant validation de session | Moyenne | Comportement confirmé ; saturation non testée | Bloquant : admission précoce et budget de ressources validé |
| SEC10-03 | Routes documentaires accessibles avec Bearer seul sur le réseau API | Moyenne, conditionnelle à l'accès réseau et à un jeton valide | Confirmé localement ; exposition publique non constatée | Vérifier l'isolement réel et décider de la politique BFF obligatoire |
| SEC10-04 | Traçabilité insuffisante des opérations de sécurité | Moyenne | Confirmé dans le code | Bloquant : journal de sécurité minimal et procédure d'incident |
| SEC10-05 | Dépendances de test vulnérables et branche Vitest ancienne non maintenue | Moyenne dans ce contexte ; alertes amont modérée/critique | Versions/avis confirmés ; exploitation locale non tentée | Traiter avant la prochaine chaîne de publication publique |
| SEC10-06 | Verrouillage Python incomplet et entrées de build mutables | Moyenne, supply chain | Confirmé | Compléter l'inventaire et le contrôle des builds avant publication publique |
| INFO10-01 | Structures actives PDF acceptées, sans exécution ni restitution du PDF | Information | Confirmé sur fichier synthétique | Documenter ; réévaluer si téléchargement/visualisation ajouté |
| INFO10-02 | Confiance opérationnelle et rôle Docker de sauvegarde à confirmer | Information | Déclarations disponibles ; état VPS à vérifier | Revue d'exploitation obligatoire avant ouverture |

Classification utilisée : critique = compromission directe démontrable ; élevée = impact
important ou contrôle manquant avec scénario grave et préconditions explicites ; moyenne =
protection insuffisante ou vulnérabilité conditionnelle ; faible = durcissement limité ;
information = amélioration ou validation sans vulnérabilité démontrée. Aucun constat n'est
étiqueté faible pour remplir artificiellement une catégorie.

## Authentification et sessions

### Contrôles présents

- [backend/auth.py:35](../backend/auth.py#L35) : Argon2id, coût mémoire 65536 Kio, trois
  passes, parallélisme 1 ; deux dérivations simultanées maximum et refus contrôlé de capacité.
  Les anciens hashes scrypt sont reconnus et migrés à la connexion réussie.
- [backend/account_api.py:42](../backend/account_api.py#L42) : mots de passe de 12 à 256
  caractères pour inscription, réinitialisation et changement ; contrôle analogue au CLI.
  Pas de liste de mots de passe compromis ni MFA : pistes de durcissement, sans contournement
  démontré de la politique actuelle.
- [backend/ai/settings_api.py:48](../backend/ai/settings_api.py#L48) : réponse de connexion
  générique, dérivation factice pour compte absent, limitation par IP et par identifiant normalisé.
  La récupération de mot de passe renvoie une réponse générique et délègue SMTP à une file.
  L'absence de différence statistique de temps entre comptes connus/inconnus n'a pas été mesurée.
- [backend/auth.py:82](../backend/auth.py#L82) : tokens aléatoires de 32 octets, indexés par
  SHA-256 en RAM, TTL absolu de 1800 secondes par défaut, plafonné à 3600, 256 sessions maximum.
  Expiration périodique et à la résolution ; pas de renouvellement glissant silencieux.
- [frontend/server/app.mjs:144](../frontend/server/app.mjs#L144) et
  [ligne 205](../frontend/server/app.mjs#L205) : cookie `__Host-documind`, Secure, HttpOnly,
  SameSite=Strict, Path=/, sans Domain ; token retiré de la réponse navigateur.
- Nouvelle connexion : token neuf et révocation de l'ancien token s'il est présenté.
  Déconnexion, révocation ciblée, changement/réinitialisation du mot de passe et désactivation
  révoquent les sessions concernées et effacent les références aux clés BYOK.
- [backend/api.py:18](../backend/api.py#L18) : à chaque opération protégée, résolution de
  session et contrôle de l'existence, activation et propriétaire du compte en base.
  Les tests vérifient le rejet après expiration et révocation.
- [backend/account_api.py:60](../backend/account_api.py#L60) : invitations et reset aléatoires,
  digest en base, expiration, consommation atomique conditionnelle, invalidation des autres
  liens de reset après changement ; inscription uniquement si mode `invite`.
- [frontend/src/pages/Account.tsx:23](../frontend/src/pages/Account.tsx#L23) : lien de reset
  reçu en fragment puis retiré de l'adresse. Connexion/déconnexion déclenchent un rechargement
  complet, ce qui réinitialise le cache React Query du document courant.

Les sessions et limiteurs restent locaux au processus. Le Compose impose un worker API ;
une montée à plusieurs instances demande une architecture partagée. Une requête déjà admise
peut finir après une révocation : aucune promesse d'annulation rétroactive d'un appel externe
déjà envoyé n'est possible. Les workers IA recontrôlent le contexte avant les appels suivants.

### CSRF et confiance HTTPS

[frontend/server/app.mjs:137](../frontend/server/app.mjs#L137) reconnaît HTTPS via le socket
ou un proxy dont l'IP exacte est configurée ; un header `X-Forwarded-Proto` seul ne suffit pas.
Le mode de développement possède aussi un secret de passerelle ; le Compose de production
utilise l'IP Traefik, sans secret dans les labels. Les adresses configurées n'acceptent pas de CIDR.

[frontend/server/app.mjs:147](../frontend/server/app.mjs#L147) : double soumission CSRF signée
par HMAC, liée au token de session, avec cookie Secure/HttpOnly/Strict et header explicite.
Les méthodes mutatrices exigent la vérification ; les origines étrangères et `Sec-Fetch-Site:
cross-site` sont rejetés. Les routes comptes/BYOK requièrent une passerelle de service sécurisée
en backend. La frontière des autres routes est examinée dans SEC10-03.

## Autorisations : inventaire des surfaces HTTP

`Owner` est dérivé du token serveur ou, en mode historique explicitement activé, de la clé API.
L'utilisateur ne choisit pas son `owner_id` dans le corps de la requête. Le Compose de
production impose `LEGACY_API_ENABLED=false` et `API_KEYS={}`. La clé BFF de service ne vaut
pas identité utilisateur pour les documents.

| Surface FastAPI (préfixe `/api/v1`) | Contrôle côté serveur et accès indirect |
|---|---|
| `/health` ; `/auth/options` ; login/register/forgot/reset | Santé publique minimale ; options et cycle de compte via `secure_gateway` ; invitation/reset vérifiés |
| `/documents` GET/POST | Liste filtrée par propriétaire ; import attribué à l'identité résolue, quotas et admission |
| `/documents/{id}` GET/DELETE | `owned_document(id, owner)` ; suppression sous verrou, réservations et indexations actives protégées |
| `/{id}/analyze`, `/{id}/analysis` sous documents | Propriété vérifiée avant accès aux pages ou analyses ; absence et propriété étrangère donnent 404 |
| `/{id}/summarize`, `/ask`, `/summaries`, `/ai-history` | Propriété, consentement typé, historiques filtrés, références limitées aux passages autorisés |
| `/ai/status`, `/ai/usage` | `Owner`, usages filtrés par propriétaire ; les budgets OWNER_DEMO peuvent exposer des agrégats globaux prévus, sans contenu documentaire |
| `/ai/settings`, `/ai/key`, `/ai/key/validate` | Session personnelle et passerelle sécurisée ; clés en RAM et réponses limitées à leur état |
| `/account`, `/account/sessions`, `/account/sessions/{id}` | Compte actif ; révocation uniquement si la session cible appartient à ce compte |
| `/account/password`, `/account/deletion-request` | Mot de passe actuel, limitation de tentatives, révocation ; désactivation avant purge manuelle |
| `/{id}/ai-results`, `/{id}/embeddings` DELETE sous documents | Session personnelle, propriété, verrous et refus si travaux incompatibles actifs |
| `/{id}/index` GET/POST sous documents | Propriété avant admission ; statut filtré ; recontrôle compte/session et budget entre lots |
| `/search/status`, `/search/semantic`, `/search/ask` | Documents autorisés individuellement ; résultats lexicaux/vectoriels et caches filtrés par propriétaire |
| `/documents/compare`, `/comparisons/{id}`, `/{id}/summarize` sous comparisons | Autorisation des deux documents ; résultat filtré par propriétaire ; réautorisation des documents liés |
| `/documents/{id}/summary-plan`, `/summary-jobs` ; `/summary-jobs/{id}`, `/resume`, `/cancel` | Propriété du document et du job ; configuration enregistrée sans secret ; reprise liée au périmètre budgétaire du contexte |

Références centrales : [documents.py:16](../backend/services/documents.py#L16),
[rag/billing.py:35](../backend/rag/billing.py#L35),
[rag/retrieval.py:19](../backend/rag/retrieval.py#L19),
[rag/service.py:164](../backend/rag/service.py#L164),
[ai/long_summary.py:28](../backend/ai/long_summary.py#L28).
Les requêtes internes sans filtre direct `owner` sont précédées d'une autorisation de leur
parent ; elles ne constituent pas automatiquement une IDOR. Les données des workers
proviennent de jobs admis et non d'un identifiant arbitraire fourni directement à un worker.

Les workspaces sont actuellement personnels ; pas d'API de partage, d'ajout de membres ni
d'administration des comptes exposée par HTTP. Les CLI d'invitation, d'association d'email et
de purge sont locaux. Une future gestion partagée devra ajouter ses propres contrôles de rôle.
Le BFF possède sa liste explicite routes/méthodes, sans proxy générique.

Il n'existe pas d'endpoint de téléchargement du PDF original dans les routes examinées.
`Content-Disposition: attachment` n'est donc pas un mécanisme présent à valider. L'API rend
le texte par page en JSON et le frontend l'affiche comme texte React. Un téléchargement ou
aperçu PDF futur imposera une nouvelle revue d'autorisation, CSP et disposition de contenu.

## Fichiers, API, frontend et infrastructure : protections observées

### Import et extraction

[backend/services/documents.py:26](../backend/services/documents.py#L26) normalise le nom
fourni en basename, borne sa longueur, accepte PDF/TXT et génère un UUID de stockage.
Le nom original n'est pas employé pour construire le chemin disque. Création exclusive du
temporaire, suppression après échec et transaction base/fichier limitent les orphelins.

[backend/services/worker.py:11](../backend/services/worker.py#L11) combine signature et
véritable ouverture PyMuPDF, refuse PDF réparés/chiffrés nécessitant un mot de passe,
absence de texte, dépassement de 200 pages et 1 000 000 caractères. Le MIME annoncé ne sert
pas de preuve de format. TXT exige UTF-8 et refuse signatures binaires et caractères de contrôle.
Un PDF chiffré ouvrable sans mot de passe n'est pas explicitement distingué par un contrôle
général de toute encryption : le contrôle repose notamment sur `needs_pass`.

Worker jetable par `spawn`, durée 30 s et mémoire 512 Mio, deux workers maximum ; Linux ajoute
RLIMIT_AS et RLIMIT_CPU, le parent surveille RSS et termine le processus. La limite de texte
est vérifiée après `get_text` d'une page : l'allocation native intermédiaire dépend donc des
limites mémoire/temps, pas uniquement de `MAX_TEXT_CHARS`. Ce n'est pas un antivirus ni une
sandbox ; voir SEC10-01. Aucun document n'est exécuté volontairement.

Le stockage est hors du répertoire React, volume documentaire à `/app/var` et sous-répertoire
`/app/var/documents`. Le répertoire créé par l'API est demandé en 0700 ; les permissions
préexistantes ne sont pas corrigées automatiquement. Les fichiers prennent le mode de
création et l'umask du processus, sans chmod 0600 explicite. La confidentialité dépend donc
aussi des droits réels du répertoire ; aucun accès HTTP public aux fichiers n'a été trouvé.
Les UUID rendent les chemins imprévisibles mais ne sont pas une protection contre une
compromission du même UID ou une substitution locale de liens. Les accès disque ne sont
pas tous ouverts avec `O_NOFOLLOW` : à durcir lors du confinement, sans traversée de chemin
HTTP démontrée avec le nom fourni par l'utilisateur.

### API et navigateur

Schémas Pydantic bornés et `extra='forbid'` sur entrées sensibles ; UUIDs/pagination typés.
ORM et expressions paramétrées sur les routes ; pas de SQL utilisateur concaténé découvert.
Les SQL dynamiques d'outils administratifs ne sont pas des endpoints HTTP et ont un contexte
d'utilisation différent. Aucun mécanisme général d'URL externe fourni par l'utilisateur au
BFF ou au fournisseur IA ; origine backend issue de la configuration, chemins sur liste
autorisée, redirections upstream non suivies. Pas de SSRF démontrée par entrée documentaire.

Pas de `dangerouslySetInnerHTML`, `innerHTML` ou `eval` repéré dans les surfaces React/BFF
examinées. Les réponses documentaires/IA restent du texte React, sans rendu HTML/Markdown
arbitraire. Helmet configure CSP, `object-src 'none'`, `frame-ancestors 'none'`, scripts self ;
les styles inline sont autorisés pour l'interface. HSTS est fourni par les labels Traefik,
pas par le serveur HTTP interne. Aucun middleware CORS permissif n'est ajouté ; le navigateur
emploie le même origin via BFF et les vérifications Origin/CSRF restent nécessaires.

Erreurs SQL assainies, erreurs de validation sans réaffichage des entrées, pas de headers
upstream/cookies/redirections transmis aveuglément. La suppression reste autorisée et CSRF
protégée. Les routes Swagger/OpenAPI FastAPI existent dans l'API interne et ne sont pas
ajoutées à la liste de proxy BFF. Le mode debug FastAPI n'est pas activé.

### Docker et exploitation

[compose.production.yaml](../compose.production.yaml) : aucun port hôte pour API/PostgreSQL,
réseaux `data` et `application` internes, seul BFF attaché à `web`, réseau sortant distinct
pour API. Pas de socket Docker monté dans les conteneurs applicatifs. API/BFF non root,
rootfs lecture seule, no-new-privileges, plafonds mémoire/CPU/PIDs, tmpfs, healthchecks et
rotation Docker 10 Mo × 3. Un processus API et un BFF conservent la cohérence RAM actuelle.
PostgreSQL a son fonctionnement d'initialisation propre à l'image ; ne pas conclure de
l'absence de `USER` dans le Dockerfile à un serveur PostgreSQL root permanent.

Secrets fournis au runtime, pas copiés dans les images ; exclusions Docker/Git des `.env`.
Une recherche limitée de signatures de clés dans les fichiers suivis n'a trouvé aucune
correspondance ; seuls `.env.example` et `.env.production.example` sont suivis. Ce n'est
pas un audit exhaustif de l'historique Git, des anciens logs, artefacts et images.

Workflows : actions référencées par SHA, permissions explicites, tests avant publication,
images finales par digest, déploiement manuel avec environnement production et contrôle des
reviewers, SSH avec clé hôte vérifiée. Les protections réellement configurées dans GitHub
n'ont pas été interrogées. Les limites de la reproductibilité sont détaillées en SEC10-06.

Sprints 7–9 : validation de la release active et des montages `/app/var` et
`/var/lib/postgresql/data`, verrou commun, dump avec API/BFF arrêtés et reprise dans les
chemins d'erreur, confirmation Restic ID/tags/chemin, lecteur de secrets littéral sans shell,
TLS conservé, rapports assainis et notifications STARTTLS. Surveillance/rétention sans
socket Docker ; suppression réelle du Sprint 9 refusée avant toute opération.
Ces contrôles ont des tests locaux ; aucune restauration ou sauvegarde réelle n'a été faite
pendant l'audit. Les archives locales restent en clair sous permissions privées ; Restic
chiffre les copies distantes selon l'installation déclarée.

## Constats détaillés

### SEC10-01 — confinement du traitement PDF insuffisant face à une faille native

1. **Gravité : élevée conditionnelle.** Le PDF est une entrée hostile interprétée par du code
   natif. Une compromission du parseur aurait un impact intercompte important ; aucun PDF
   déclenchant une telle compromission ni CVE exploitable de cette version n'a été démontré.
2. **Localisation :** [worker.py:66–115](../backend/services/worker.py#L66),
   [documents.py:26–84](../backend/services/documents.py#L26),
   [Compose:28–48](../compose.production.yaml#L28), [Dockerfile:8–11](../Dockerfile#L8).
3. **Scénario :** un compte autorisé importe un PDF exploitant une vulnérabilité native.
   Le worker possède l'UID de l'API, hérite de son environnement, de sa vue du stockage et de
   sa connectivité. Il pourrait alors lire les autres fichiers et les secrets API/base, ou
   attaquer les données via les droits de la connexion applicative.
4. **Preuve :** `multiprocessing.Process` sans changement d'UID, environnement filtré,
   confinement réseau ou racine dédiée ; seuls mémoire/CPU/temps sont restreints. Le volume
   complet et le réseau API sont accessibles à ce processus. Rootfs read-only et les limites
   du conteneur ne retirent pas les accès nécessaires à l'API.
5. **Impact :** confidentialité/intégrité de plusieurs comptes si le parseur est compromis ;
   l'architecture n'offre pas une seconde frontière entre extraction et application.
6. **Correction recommandée :** worker d'extraction séparé, sans secrets, sans réseau, UID
   distinct, seul fichier d'entrée monté en lecture seule, sortie et ressources bornées,
   politique de syscalls/confinement adaptée. Maintenir MuPDF/PyMuPDF et scanner les images.
7. **Non-régression :** sur Linux, prouver que le worker ne lit ni un autre document, ni les
   secrets/volumes API, ne joint ni DB ni Internet, tout en traitant PDF/TXT valides et limites.
8. **Confiance :** absence de cette frontière **confirmée par code** ; exploitation native
   **à vérifier**, pas présentée comme une exécution distante confirmée.
9. **Décision :** blocage d'ouverture publique jusqu'à confinement ou acceptation formalisée
   de ce risque résiduel, appuyée par une revue des composants natifs et tests Linux.

### SEC10-02 — bufferisation des corps avant rejet d'une session invalide

1. **Gravité : moyenne.** Consommation de ressources par un client non authentifié, sous
   plafonds existants ; aucune saturation ni panne n'a été provoquée.
2. **Localisation :** [main.py:25–52](../backend/main.py#L25),
   [api.py:62–67](../backend/api.py#L62), [BFF:144–156](../frontend/server/app.mjs#L144),
   [BFF:175–190](../frontend/server/app.mjs#L175), [Compose:46–48](../compose.production.yaml#L46).
3. **Scénario :** un client HTTPS choisit un cookie au format plausible, obtient un CSRF
   lié à ce cookie et soumet un upload. Le BFF vérifie la présence/forme du token, l'API
   vérifie ensuite sa validité, après réception intégrale du corps et parsing multipart.
4. **Preuve locale :** POST multipart fictif avec Bearer inexistant : **1 048 692 octets
   consommés, HTTP 401, aucun document créé**. Le middleware spoule au-delà de 256 Kio avant
   d'appeler l'application. La barrière de deux workers se situe après cette étape.
5. **Impact :** bande passante, écriture tmpfs et travail de parsing sans session valide ;
   les 32 admissions Uvicorn et un tmpfs de 256 Mio doivent être dimensionnés ensemble pour
   des corps proches de 10 Mio. Le DoS Internet complet est un scénario, pas un résultat de test.
6. **Correction :** vérifier la session avant réception des uploads, sans retirer la borne
   en flux ; admission/concurrence des corps, délais de lecture et quotas temporaires
   explicites ; limites Traefik/BFF cohérentes. Ne pas confondre cookie présent et session valide.
7. **Non-régression :** token absent/invalide/expiré rejeté avant stockage du corps, flux
   chunked borné, multipart incomplet interrompu/nettoyé, protections CSRF intactes. Validation
   de capacité sur une stack jetable, jamais en production.
8. **Confiance :** ordre de traitement **confirmé** ; saturation **non testée**.
9. **Décision :** corriger et valider le budget d'upload avant ouverture publique.

### SEC10-03 — la provenance BFF n'est pas obligatoire sur toutes les routes privées

1. **Gravité : moyenne conditionnelle.** Ce n'est pas un accès sans identité : un token
   utilisateur valide et un accès au réseau API sont nécessaires.
2. **Localisation :** [api.py:18–40](../backend/api.py#L18),
   [gateway.py:14–16](../backend/gateway.py#L14), [Compose:26–48](../compose.production.yaml#L26).
3. **Scénario :** publication accidentelle du port API ou accès non prévu au réseau interne ;
   un porteur de token peut appeler documents/analyse/recherche sans contrôles Host/CSRF/TLS
   du BFF. Le mode Bearer protège encore l'identité et la propriété.
4. **Preuve locale :** application configurée avec clé de service indépendante, clés historiques
   désactivées et compte fictif : GET documents en HTTP avec **Bearer seul**, sans clé BFF
   ni header HTTPS, retourne **200** pour son espace vide.
5. **Impact :** dépendance au cloisonnement réseau pour imposer le passage par le BFF ;
   aucune exposition externe de ce port n'est constatée dans le Compose de production.
6. **Correction :** décider explicitement si le mode production exige la provenance BFF
   en plus de l'identité pour toutes les routes privées, ou autorise une API Bearer séparée
   avec ses propres garanties TLS. Conserver la santé interne minimale indépendante.
7. **Non-régression :** matrice réseau/provenance/session ; token valide sans service refusé
   si BFF obligatoire ; clé service seule toujours incapable d'ouvrir un espace documentaire.
8. **Confiance :** acceptation du Bearer seul **confirmée** ; accessibilité publique **à vérifier**.
9. **Décision :** ne pas publier l'API ; inspection réseau réelle et politique validée avant ouverture.

### SEC10-04 — journal de sécurité incomplet

1. **Gravité : moyenne.** Limitation de détection et d'investigation, pas une fuite confirmée.
2. **Localisation :** [settings_api.py:48–72](../backend/ai/settings_api.py#L48),
   [account_api.py:159–226](../backend/account_api.py#L159),
   [documents.py:87–118](../backend/services/documents.py#L87),
   [Compose:48](../compose.production.yaml#L48), [BFF index:6–10](../frontend/server/index.mjs#L6).
3. **Scénario :** compte compromis, tentatives répétées ou suppression documentaire ; les
   événements ne laissent pas de trace applicative structurée suffisante pour reconstituer
   l'acteur, le résultat et la chronologie. Un access log Traefik éventuel ne suffit pas à cela.
4. **Preuve :** absence de journal d'événements dans les branches login/logout/reset/révocation
   et suppression normale ; Uvicorn désactive les access logs. Des logs d'erreur assainis,
   quelques événements IA et une demande de suppression en base existent mais sont partiels.
5. **Impact :** détection tardive et difficultés à circonscrire une exposition ou une suppression.
6. **Correction :** événements structurés allowlistés, identifiants pseudonymes, action/résultat,
   horodatage et corrélation ; niveaux/rotation/accès et conservation définis. Aucun mot de
   passe, cookie, token CSRF/reset, clé BYOK, contenu PDF ou corps de requête dans ces traces.
7. **Non-régression :** capture de logs sur succès/échec/révocation/suppression ; recherche de
   secrets fictifs interdits, résistance aux sauts de ligne, attribution correcte entre comptes.
8. **Confiance :** insuffisance de traçabilité **confirmée dans le code** ; logs VPS non inspectés.
9. **Décision :** socle d'audit et procédure d'incident requis avant ouverture.

### SEC10-05 — alertes connues dans l'outillage Vitest/Tinypool

1. **Gravité : moyenne contextualisée**, à traiter dans la chaîne de développement ; le moteur
   npm classe deux paquets critiques et un modéré. Pas de RCE du BFF démontrée.
2. **Localisation :** [package-lock.json:2091](../frontend/package-lock.json#L2091),
   [ligne 4622](../frontend/package-lock.json#L4622),
   [ligne 4924](../frontend/package-lock.json#L4924), [Dockerfile frontend:4/14](../frontend/Dockerfile#L4).
3. **Scénario :** chaîne de pollution de prototype dans un processus utilisant Tinypool ou
   exposition d'un serveur de développement utilisant le plugin de mock concerné. Ces
   préconditions ne sont pas démontrées dans DocuMind ; les tests exécutent déjà du code du dépôt.
4. **Preuve :** npm audit complet retourne trois entrées : `@vitest/mocker` **3.2.7**, `vitest`
   **3.2.7**, `tinypool` **1.1.1** ; `npm audit --omit=dev` retourne **zéro** entrée.
5. **Impact :** risque développeur/CI conditionnel ; dépendances présentes dans l'étape de build,
   omises de l'installation runtime `npm ci --omit=dev`. Aucun chemin public équivalent trouvé.
6. **Correction :** migration contrôlée vers une branche Vitest maintenue/corrigée, avec
   Tinypool corrigé et vérification des prérequis Node/Vite. Ne pas lancer `npm audit fix --force`
   sans revue. Ajouter un contrôle de vulnérabilités exploitable et documenté à la CI.
7. **Non-régression :** tests React/BFF, TypeScript/build, nouveau scan complet et prod ; vérifier
   l'absence d'outils de développement dans l'image runtime et l'isolement des secrets CI.
8. **Confiance :** versions affectées et avis **confirmés** ; chaîne d'exploitation **non démontrée**.
9. **Décision :** résoudre/revoir avant publication publique ; ne pas présenter ces avis comme
   deux compromissions de production indépendantes.

Avis primaires consultés le 20/10/2026 :

- [Vitest GHSA-82fw-gwwq-j7x9](https://github.com/vitest-dev/vitest/security/advisories/GHSA-82fw-gwwq-j7x9) :
  lecture de fichiers via plugin de mock sous conditions d'exposition ; correctif 4.1.11 ou
  branche 5 corrigée. L'avis indique que les branches 2/3 ne reçoivent pas ce correctif.
- [Tinypool GHSA-5gmw-xhrv-c9v3](https://github.com/tinylibs/tinypool/security/advisories/GHSA-5gmw-xhrv-c9v3) :
  gadget de pollution de prototype des options de worker, corrigé en 2.1.1.
- [Tinypool GHSA-85c8-ppgw-ccpr](https://github.com/tinylibs/tinypool/security/advisories/GHSA-85c8-ppgw-ccpr) :
  gadget sur les options de `run`, corrigé en 2.1.2. Une source de pollution et le chemin
  d'appel concerné restent nécessaires ; la présence du paquet ne prouve pas cette chaîne.

### SEC10-06 — dépendances Python et entrées de build partiellement verrouillées

1. **Gravité : moyenne**, risque supply chain conditionnel ; aucune dépendance compromise
   n'a été identifiée par cet audit.
2. **Localisation :** [requirements.lock](../requirements.lock),
   [Dockerfile:1/8](../Dockerfile#L1), [Dockerfile.db:1–5](../Dockerfile.db#L1),
   [frontend/Dockerfile:1/10](../frontend/Dockerfile#L1),
   [ci.yml:30/66/74](../.github/workflows/ci.yml#L30).
3. **Scénario :** reconstruction d'un même commit avec tag de base déplacé ou dépendance
   transitive non contrainte ; une version différente non revue entre dans le build.
4. **Preuve :** 47 noms verrouillés, mais `argon2-cffi-bindings`, `cffi`, `pycparser` installés
   ne figurent pas dans le lock. Les bases Python/Node/PostgreSQL sont référencées par tags,
   pgvector par tag Git ; le lock Python n'a pas d'empreintes de distributions. La CI ne
   contient pas de gate de vulnérabilités. Les images **livrées**, elles, sont figées par digest.
5. **Impact :** moindre reproductibilité et couverture de validation variable, notamment pour
   les dépendances Linux non présentes sur Windows et les bibliothèques des images de base.
6. **Correction :** lock complet pour les cibles Linux, hashes, inventaire/SBOM des images,
   références sources/bases vérifiées et renouvelées selon procédure, scan CI régulier avec
   gestion explicite des exceptions. Conserver les releases finales par digest.
7. **Non-régression :** comparer inventaires de deux builds et dépendances runtime Linux,
   contrôler que toutes les transitives attendues sont couvertes et les images scannées.
8. **Confiance :** écarts de lock/build **confirmés** ; compromission **non démontrée**.
9. **Décision :** compléter le contrôle de supply chain avant publication publique.

## Informations et risques résiduels

**INFO10-01 — structures PDF actives.** Un PDF synthétique contenant une `OpenAction`
JavaScript et une pièce jointe bénigne est accepté et son texte extrait. Le code ne les
exécute pas et ne propose pas de téléchargement du PDF : ce résultat n'est pas une XSS ou
une exécution de script démontrée. Références : [worker.py:11–50](../backend/services/worker.py#L11),
[api.py:78–80](../backend/api.py#L78). Recommandation : formaliser « extraction de texte sans
certification d'innocuité », décider d'une politique antivirus/quarantaine selon les usages,
et refaire cette revue avant tout aperçu/téléchargement. Tests futurs : JS/actions/attachments
inoffensifs, polyglottes, liens, fichiers réparés et bombes de ressources dans une sandbox
locale bornée. Confiance confirmée pour l'acceptation, aucune exécution observée.

**INFO10-02 — garanties d'exploitation.** Le service de sauvegarde est non root mais rejoint
le groupe Docker ([unité:11](../ops/systemd/documind-backup.service#L11)) ; il faut le traiter
comme rôle d'administration du moteur Docker, pas comme isolement fort des autres projets.
Les helpers du bundle actif sont chargés comme code Python ; l'intégrité et les droits des
releases et scripts d'exploitation sont donc essentiels. Les moniteurs masquent le socket,
mais l'état réel et les droits du compte `debian` restent à inspecter. Recommandations : revue
locale des accès, moindre privilège, droits privés des archives, accès B2 à portée minimale,
contrôle des digests et versions réelles de Traefik/Node/PostgreSQL/MuPDF, permissions des
rapports et procédures de révocation. Aucun accès abusif à Docker n'a été testé.

Gravité **information** : le rôle Docker est nécessaire à l'orchestrateur actuel et n'est
pas une faille HTTP démontrée. Le scénario conditionnel est la compromission de ce compte
d'exploitation ou d'un helper qu'il charge, avec un impact potentiel sur les autres projets
du moteur Docker. La preuve disponible est la configuration versionnée et le chargement
explicite du helper, sans preuve des permissions effectives du VPS. Tests de non-régression
nécessaires après toute évolution : sauvegarde et reprise toujours fonctionnelles, scripts
non modifiables par des rôles applicatifs, services moniteur/rétention incapables de joindre
le socket Docker, et aucun effet sur un second projet Docker fictif. Confiance : rôle déclaré
**confirmé**, permissions et exploitabilité réelle **à vérifier**. Décision : revue administrative,
sans suppression ou changement de privilège pendant cette phase.

Une conservation réelle n'est pas activée : des documents supprimés peuvent rester dans les
sauvegardes sans échéance automatique. Cela demande une politique organisationnelle validée
avant collecte publique, sans autoriser une purge pendant cet audit. La restauration indépendante
de `51ac3259` et les derniers snapshots sont des déclarations antérieures de l'administratrice,
pas des restaurations répétées ou des objets interrogés ici.

## Dépendances : portée des résultats

`pip-audit` **2.10.1** dans un environnement d'outillage isolé : aucune vulnérabilité connue
signalée sur les **47 versions du lock**, puis les **50 distributions de dépendances installées**
hors projet local et pip. Cela n'inclut ni toutes les variantes Linux, ni le système Debian,
ni les bibliothèques embarquées MuPDF/libc/OpenSSL, ni les images VPS réelles. Le résultat
n'est pas une garantie d'absence de faille, et les bases d'avis évoluent.

Versions Node verrouillées examinées notamment : React/React DOM 19.3.1, React Router 7.18.4,
Express 5.3.0, Helmet 8.3.0, Vite 6.4.4 et Vitest 3.2.7. Ne pas appliquer les alertes de
React Server Components à ce frontend SPA en l'absence des paquets et de la surface serveur
concernés. Aucune fin de maintenance de l'ensemble des autres dépendances n'a été établie ;
leurs versions effectives de production et composants natifs restent à inventorier.

## Couverture de tests et décision de phase A

**455 tests Python, 25 BFF et 37 React réussis**, TypeScript et actionlint sans erreur ; trois
sondes locales complémentaires réussies. Les tests protègent notamment l'isolation de deux
comptes, erreurs de session, révocation, reset, quotas concurrents, uploads malformés/chiffrés,
sources RAG et jobs, headers/cookies/CSRF, sauvegardes et absence de suppressions en rétention.
Les tests BFF isolent leur upstream ; ils ne remplacent pas un parcours navigateur complet
avec TLS Traefik et PostgreSQL. Les sessions ne sont jamais imprimées dans les rapports.

Tests manquants prioritaires : admission d'upload avant authentification ; sandbox Linux et
absence d'accès latéral ; matrice BFF/API de production ; journal de sécurité ; fuzzing PDF
borné et sans réseau ; vérification native des permissions/liens ; enchaînement réel multi-
onglets/logout/retour arrière ; tests PostgreSQL des races d'invitation/reset/quotas ; revue
des IP transmises par la version réelle de Traefik et des contraintes de routage.

Le [plan de remédiation](sprint-10-remediation-plan.md) définit les critères de sortie et
l'ordre proposé. **Arrêt à la phase A : aucun correctif, déploiement ou ouverture n'est autorisé
par ce rapport. La phase B attend la validation explicite de l'administratrice.**
