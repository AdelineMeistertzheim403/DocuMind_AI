# Sprint 12 — SEC10-04 : journalisation et surveillance de sécurité

## Périmètre et référence de travail

Travail local du 22 octobre 2026. `git status --short --branch` était propre sur
`security/sec10-03-gateway-auth`. Le `main` local, `e3c50d8`, ne contient pas SEC10-03 :
son `trusted_gateway()` conserve encore l'ancien repli. Le commit local `6963958`
contient la correction, ses fixtures, ses tests et son rapport ; `main` est son ancêtre.
La branche locale `security/sec10-04-audit-logging` a été créée depuis ce commit vérifié.
Ce constat ne remet pas en cause le déploiement signalé par l'administratrice, mais
aucun fetch n'a été effectué pour prétendre connaître le `main` distant actuel.

Objectif : produire des événements de sécurité utiles sans nouveau stockage métier,
identité personnelle dans les logs, télémétrie distante ou service supplémentaire.
Les producteurs sont implémentés localement ; **aucune surveillance applicative nouvelle
n'est active en production**. Les Sprints 7–9 et leurs alertes d'exploitation ne changent pas.

## Audit préalable des mécanismes existants

| Composant | Événement existant | Niveau / format | Informations exposées | Lacune ou décision |
| --- | --- | --- | --- | --- |
| API `main.py` | erreur SQL, échec SMTP | ERROR/WARNING, texte | nom de classe d'exception SQL, texte SMTP fixe | aucun identifiant de corrélation ; convertir en événements fixes |
| Auth / gateway | refus HTTP et login/logout | pas de journal applicatif dédié | réponses contrôlées ; pas de preuve structurée | instrumenter les décisions, sans recopier credentials ni distinguer les comptes inconnus |
| Admission upload | limites, délais, déconnexions | réponses HTTP uniquement | aucun contenu journalisé dans ce module | ajouter une observation ASGI sans appeler `receive` prématurément |
| Service documents | suppression physique différée | `logger.exception` | nom interne de tombstone, traceback pouvant contenir chemins/erreurs | remplacer par un événement fixe sans nom de fichier |
| IA | règlement de réservation, schéma invalide | INFO/WARNING texte | UUID de réservation, statut, noms de schéma/catégories | conserver le signal sans identifiant ni champs dynamiques |
| Worker résumé long | exception de worker | ERROR texte | UUID de job | supprimer le job ID du journal et conserver l'échec fiable |
| Worker portable | exception inattendue du processus enfant | traceback multiprocessing possible | détails d'exception et chemins | réponse interne fixe, sans traceback brut ; politique de ressources inchangée |
| BFF | démarrage, mauvaise configuration | `console.log/error` | adresse/port configurés ou message fixe | événements JSON ; pas de logs d'authentification ou de corrélation auparavant |
| Erreurs BFF | réponses contrôlées ; fallback Express | JSON métier ; stack possible pour une erreur non traitée | risque de détails dans le fallback | handler final générique, sans objet d'erreur dans les logs |
| Traefik | configuration serveur externe | inconnu sur le VPS | accès/URI/IP potentiels non vérifiés | le dépôt ne permet pas de certifier les access logs réels ; aucune modification |
| PostgreSQL serveur | paramètres de logs hérités de l'image | hors schéma applicatif | erreurs/détails SQL potentiels ; non garantis par l'expurgation API | revue distincte des réglages serveur avant ouverture publique ; aucun réglage modifié |
| Docker production | rotation `json-file` | enveloppe JSON du driver | stdout/stderr des services | `max-size=10m`, `max-file=3`, réutilisés par les services |
| Backups / monitoring / rétention | rapports JSON et messages fixes | fichiers privés / journald | états, catégories, quelques chemins techniques | mécanismes déjà testés ; ne pas les transformer en collecteur de logs applicatifs |
| Administration CLI | compte créé, inventaire propriétaires, invitation | sortie interactive | UUID propriétaires ; token d'invitation nécessaire à sa remise | sortie d'administration à accès restreint, pas un flux de logs à collecter |

La recherche a couvert `print`, `logging`, `logger`, `console.log/error`, tracebacks,
handlers d'erreur et les fournisseurs IA. Les logs fournisseurs ne sont pas alimentés
avec leurs réponses/prompts par les nouveaux producteurs ; le SDK OpenAI est déjà
abaissé à WARNING. Une garantie universelle sur le logging de bibliothèques tierces,
le démon Docker ou Traefik externe ne découle pas de ce contrôle applicatif.

Les CLI d'invitation doivent continuer à remettre le token à l'opérateur : ne pas
rediriger leur sortie vers un collecteur. De même, les exports, dumps et rapports de
sauvegarde ne doivent pas être ingérés comme des événements applicatifs. Les scripts
de sauvegarde, restauration, Gmail, surveillance et conservation n'ont pas été modifiés.

## Architecture minimale retenue

### API

`backend/security_audit.py` fournit une liste blanche d'événements, opérations et raisons,
un contexte `ContextVar` et un writer stdout dédié. Les producteurs ne transmettent
jamais l'objet request, une exception, des paramètres SQL ou une donnée utilisateur au
writer. Les champs supplémentaires sont ignorés ; les valeurs non autorisées sont rejetées.

`SecurityAudit`, middleware ASGI pur, est placé avant IPAdmission, UploadAdmission,
RequestSizeLimit et le routage. Il enveloppe `receive` pour observer un éventuel abandon,
sans jamais le solliciter de lui-même. Il produit une décision finale par requête,
à partir d'une raison fixe marquée au point de contrôle ou du résultat HTTP. Les événements
de workers/règlement IA représentent des étapes distinctes, pas un access log systématique.
Les accès documentaires valides et sondes de santé valides ne sont pas journalisés.

Les erreurs SQL utilisent le handler contrôlé existant. Les exceptions applicatives
inattendues sont interceptées avec HTTP 500 générique avant toute réponse commencée,
sans remonter leur message au logger Uvicorn. Une réponse déjà commencée ne peut pas
être remplacée : un événement d'erreur est conservé et la fin de transport dépend du serveur.
Si l'envoi de la réponse 500 échoue lui-même, cette erreur est aussi contenue pour ne
pas transmettre au serveur la chaîne d'exceptions avec le message sensible initial.
La configuration globale invalide et le confinement indisponible produisent un message
de démarrage fixe, sans afficher les entrées de validation/DSN. Le démarrage reste refusé.

### BFF

`security-audit.mjs` produit le même noyau JSON pour les refus locaux, limites de transfert,
erreurs de liaison API, démarrage et mauvaise configuration. Le middleware de corrélation
précède Host/Origin/session/CSRF. L'événement est émis une seule fois sur finish/close.
Le BFF ne duplique pas les refus explicitement reçus de l'API. Il journalise son propre
abandon de transport lorsque le client disparaît ; cela n'affirme pas que l'API a interrompu
une transaction déjà autorisée. Les payloads et erreurs upstream ne sont jamais copiés.

### Disponibilité et bornes

- API : file de 1024 lignes, tentative d'insertion non bloquante ; au plus 100 événements/s
  par processus. Un thread daemon effectue seul l'écriture locale `os.write`, hors chemin
  critique. Les lignes sont bornées par les types, constantes et identifiant de 32 caractères.
- BFF : au plus 100 événements/s par instance d'application ; respect de
  `stdout.writableNeedDrain`, aucune file applicative non bornée. Docker stdout est un pipe ;
  les autres types de destinations ne constituent pas une preuve de latence identique.
- Échec d'écriture/saturation : pas de nouvel échec d'authentification, compteur interne de
  pertes/erreurs, résumé `system.audit.dropped` lorsque la sortie fonctionne à nouveau et
  qu'un événement peut être écrit, au plus un résumé par seconde. Aucun fallback avec exception.
- Contention du verrou du writer Python : l'événement est refusé immédiatement ; le
  compteur de pertes n'est pas exhaustif pour cette contention. La capture est best effort.
- Le budget n'est pas une file prioritaire par sévérité : une saturation peut également
  faire perdre des événements critiques. Une réserve de capacité/collecte durable pour
  ces événements doit être étudiée avant un besoin d'audit exhaustif ou une ouverture publique.
- Aucun `flush` bloquant dans une requête. `flush(timeout)` est réservé aux tests/observations.
  Un arrêt brutal peut perdre la file. Pas de garantie exactly-once, durable ou forensique.
- Si stdout reste bloqué, les compteurs ne sont pas un système d'alerte externe accessible :
  surveiller le driver/collecte et les lacunes de flux avant toute ouverture publique.

## Schéma et confidentialité

Champs communs : `timestamp` UTC ISO 8601 avec suffixe Z, `level`, `service`, `event`,
`operation`, `outcome`. Champs optionnels : `request_id` (32 hex minuscules),
`http_status` (entier 100–599), `reason_code` (enum). Seul le résumé de pertes ajoute
`dropped_count`, un entier plafonné. `499` est une convention interne d'abandon, pas une
réponse effectivement envoyée à un client disparu.

Services : `documind-api`, `documind-bff`. Niveaux : INFO pour une action observée,
WARNING pour refus/anomalies, ERROR pour indisponibilité/worker/erreur interne,
CRITICAL pour configuration de sécurité empêchant le démarrage. `outcome=success`
sur une révocation administrative HTTP 200 ne signifie pas qu'une session invalide a
été acceptée ; `outcome=denied/error/aborted` décrit les autres décisions.

Sont absents par construction : Authorization, clés API/BFF/IA, cookies, sessions,
CSRF, invitations, mots de passe, reset tokens, corps/prompts/réponses IA, embeddings,
fichiers, chemins, identifiants de document/compte/workspace, e-mail, IP et user agent.
Aucun hachage d'IP/e-mail/identifiant personnel n'est présenté comme une anonymisation.
Les request IDs sont des données techniques de corrélation ; ils doivent aussi être
soumis à la minimisation et aux contrôles d'accès, sans prétendre à un anonymat universel.

## Catalogue des événements

Tous les événements partagent la liste blanche ci-dessus et les bornes 100/s. Aucun
champ interdit n'est admis pour une famille particulière. L'API est propriétaire des
décisions métier ; le BFF est propriétaire de ses seuls refus/échecs locaux.

| Événement | Déclencheur exact / propriétaire | Niveau | Champs utiles / test |
| --- | --- | --- | --- |
| `auth.login.success` | API login HTTP 2xx | INFO | request_id, login, statut ; test login success/failure/logout |
| `auth.login.failure` | API login 400/401/422 hors refus gateway/rate | WARNING | raison générique invalid_identity ; même test |
| `auth.logout` | API logout réussi | INFO | aucun token ; même test |
| `auth.session.invalid` | API route privée 401 ; BFF refuse une session manquante en local | WARNING | invalid_session/missing_session ; tests sessions absente/inventée/révoquée |
| `auth.session.revoked` | API utilisateur désactivé/propriétaire modifié, ou suppression d'une session valide | WARNING | session_revoked ou completed ; tests admission et cycle de vie |
| `auth.password_reset.requested` | API forgot-password 202, compte connu ou inconnu | INFO | même événement sans e-mail ; test reset_genericity |
| `auth.password_reset.completed` | API reset réussi | INFO | sans token ; test reset_genericity |
| `auth.password.changed` | API changement réussi, sessions révoquées | INFO | sans password/user ID ; test password_change_deletion |
| `access.denied` | refus privé 403/404, échec de confirmation password ; BFF Host/Origin/CSRF/query | WARNING | raison fixe ; tests BFF et exceptions |
| `access.cross_owner.denied` | document absent du scope propriétaire mais UUID existant | WARNING | not_owner, sans UUID ; test cross_owner_denial |
| `gateway.authentication.failed` | clé BFF invalide ou marqueur HTTPS incorrect | WARNING | invalid_service_credential/secure_transport_required ; tests gateway/spoofing |
| `rate_limit.exceeded` | quota de fréquence ou capacité du limiteur dépassé | WARNING | rate_limit sans bucket/IP ; test rate_limit_and_document_quota |
| `quota.exceeded` | quota documentaire/stockage ou HTTP 402 budget | WARNING | quota ; même test et régressions IA |
| `upload.admission.denied` | refus d'identité/autorisation upload | WARNING | statut + raison fixe ; tests early_admission sans receive |
| `upload.capacity.exceeded` | admission/réception ou prévalidation GET 503 hors erreur SQL/worker identifiée | WARNING | capacity ; tests SEC10-02 et slot d'auth épuisé dans le test quotas |
| `upload.size.exceeded` | upload 413 hors quota métier identifié | WARNING | size ; régressions taille exacte/+1 |
| `upload.rejected` | upload multipart/format/contenu 400/415/422 | WARNING | invalid_request ; régressions uploads |
| `upload.timeout` | réception upload 408 | WARNING | timeout ; tests délais SEC10-02 |
| `upload.aborted` | déconnexion observée par receive/annulation API ou close BFF | INFO | disconnected/499 ; tests SEC10-02 de déconnexion |
| `upload.completed` | API upload 2xx | INFO | aucun nom/taille/contenu ; test cross_owner et recette HTTPS |
| `account.created` | API inscription sur invitation réussie | INFO | sans e-mail/invitation ; test reset_genericity |
| `account.deletion.requested` | API désactive le compte après confirmation | INFO | sans compte ; test password_change_deletion |
| `account.deletion.completed` | purge administrative réellement commitée | INFO | hors HTTP, sans compte/path ; même test |
| `system.database.unavailable` | exception SQL observée par health/handler/admission | ERROR | database, sans SQL/DSN ; test sql_and_unexpected_exceptions |
| `system.security_config.invalid` | configuration globale/credentials requis/confinement indisponibles | CRITICAL | security_unavailable ; tests démarrage fail-closed existants |
| `system.worker.failed` | erreur inattendue API/BFF, worker de résumé, erreur de protocole/sandbox identifiée | ERROR | raison fixe sans job ID ; tests exception/protocole |
| `system.file_cleanup.failed` | unlink différé échoue après suppression logique | ERROR | cleanup_failed, sans tombstone/exception ; audit du service documentaire |
| `system.mail.failed` | livraison SMTP observée en échec | ERROR | mail_failed, aucun destinataire ; audit du worker mail |
| `system.ai.settled` | règlement de réservation appliqué | INFO | settled ; ne promet pas le succès fournisseur ; régressions IA |
| `system.ai.output_rejected` | validation du schéma IA refuse la sortie | WARNING | invalid_output sans schéma/payload ; régressions IA |
| `system.api.unavailable` | BFF observe une liaison API défaillante ou réponse inattendue | ERROR | upstream_unavailable ; tests preflight offline/timeout |
| `system.started` | BFF écoute effectivement | INFO | started, aucune adresse ; démarrage de recette |
| `system.audit.dropped` | reprise de sortie après pertes comptées | WARNING | compteur, aucun request ID ; tests writer borné |

Non émis séparément : gateway success à chaque requête (trop bruyant), account.disabled
(déjà impliqué par deletion.requested), account.sessions.revoked à chaque reset/change
(déjà impliqué par leur événement), invalid/revoked/expired distingués après disparition
du token (le vault ne garde pas d'historique supplémentaire), system.backup.failed dans
l'API (aucun signal fiable local à cette API). Le catalogue n'invente pas ces observations.

`owned_document` effectue une existence minimale supplémentaire sur UUID après un refus
pour distinguer missing/cross-owner uniquement dans le journal interne. La réponse reste
404 identique, sans query métier supplémentaire sur les accès autorisés et sans UUID loggé.

## Corrélation et frontières de confiance

1. Le navigateur ne choisit pas l'ID : le BFF génère un UUIDv4 aléatoire pour chaque
   requête, remplace tout X-Request-ID client et le retourne dans la réponse.
2. Le BFF transmet ce même ID à la prévalidation GET, à l'upload POST et aux autres appels API.
3. L'API n'accepte qu'un seul en-tête de 32 hex minuscules et une clé BFF authentifiée
   par `trusted_gateway()` SEC10-03. Une clé historique, même autorisée comme utilisateur,
   ne peut pas imposer cet identifiant. Sinon l'API génère son propre ID.
4. Les ContextVar isolent les requêtes ; les appels threadpool/to_thread héritent du contexte.
   Les workers asynchrones indépendants peuvent n'avoir aucun request ID : aucun job/account
   ID n'est ajouté pour compenser. La corrélation des jobs persistants n'est pas implémentée.
5. L'en-tête de réponse est fixé côté serveur. Aucune nouvelle origine CORS, permission,
   route publique, clé ou cookie n'est ajouté. Les logs ne réutilisent pas l'IP client.

Traefik précède la génération de l'ID BFF : **la corrélation des trois composants n'est
pas active** par cette seule modification. Une future configuration approuvée pourrait
ne conserver que l'en-tête de réponse X-Request-ID dans un access log minimal de ce routeur,
après validation des champs réellement supportés par la version de Traefik. Ne pas faire
confiance à l'en-tête de requête transmis par un navigateur ; ne pas activer globalement
des access logs qui enregistreraient query strings, chemins privés, IP, headers ou cookies.

## Détection et alertes proposées — non installées

Le monitor Sprint 8 observe infrastructure/sauvegardes, pas ces événements applicatifs.
Ne pas modifier silencieusement son hook Gmail ni ses arguments. Une solution minimale
future consiste en un lecteur local en lecture seule des seuls stdout API/BFF Docker,
avec curseur borné par conteneur/flux/position, déduplication des seules relectures de lignes,
corrélation par request ID et agrégats temporels
sans IP/compte, rapport local privé et alerte externe seulement après consentement.
Les doublons métier/API sont déjà limités à la production ; des événements transport
distincts peuvent partager un ID et doivent rester distinguables.

| Règle initiale | Fenêtre / seuil | Sévérité | Action et faux positifs | Validation locale |
| --- | --- | --- | --- | --- |
| Échecs login | 20 / 5 min, agrégat service | WARNING | vérifier tendance ; pas d'accusation ciblée ; relever le seuil à partir d'une référence locale | fixtures événements synthétiques autour de la borne |
| Rejets gateway | 3 / 1 min | ERROR | vérifier configuration BFF/chemin réseau ; un redémarrage coordonné peut expliquer un pic | séquence ancienne clé / clé valide |
| Cross-owner / refus privés | 10 / 10 min | WARNING | corréler opérations ; exclure anciennes routes UI connues après revue | requêtes de deux propriétaires fictifs |
| Admission upload | 20 refus / 5 min | WARNING | comparer motif capacité/identité et trafic légitime | cas invalides et saturation bornée de tests |
| Capacité temporaire | 10 / 5 min, 30 / 5 min persistant | WARNING puis ERROR | vérifier santé/marges ; pas de purge automatique de .part | budgets fictifs insuffisants |
| PostgreSQL indisponible | 1, escalade 3 / 1 min | ERROR puis CRITICAL | contrôler health et maintenance planifiée ; pas de redémarrage automatique | SQLAlchemyError simulée |
| Configuration de sécurité invalide | 1 | CRITICAL | livraison arrêtée ; vérifier sandbox/config sans l'assouplir | check_available simulé en échec |
| Pertes de journal / worker répété | 1 perte, ou 3 workers / 5 min | WARNING / ERROR | rétablir collecte, vérifier ressources ; ne pas conclure à absence d'incident pendant une lacune | sink bloqué/brisée, protocole invalide |

Ces seuils sont des hypothèses de départ, pas une mesure de trafic de production ni un
moteur installé. Fenêtres glissantes, rappel au plus toutes les 30 min par incident,
retour à la normale après deux fenêtres saines, maintenance explicitement bornée et
déduplication doivent être validés avant activation. Des événements distincts portant le
même request ID ne doivent pas être fusionnés, notamment les tentatives IA multiples ;
un request ID n'est pas un ID d'événement. Aucun e-mail, Slack ou service tiers
n'a été contacté par la journalisation ou les tests.

## Rotation, conservation et exploitation

- Application : stdout JSON (une ligne par événement), aucun fichier documentaire de logs.
  Le driver json-file prévu par le Compose de production ajoute son enveloppe ; son chemin réel n'est pas supposé
  sur le VPS. `docker logs` est la lecture administrative normale, avec portée par service.
- Compose production déjà présent : `max-size=10m`, trois fichiers par service,
  donc une enveloppe nominale de trois fois cette taille, pas une durée garantie. Un pic peut couvrir
  peu de temps malgré la limitation des producteurs. Le daemon et Traefik n'ont pas été changés.
- systemd/rapports Sprints 7–9 : journald et répertoires privés existants, formats conservés.
  Ils ne sont pas fusionnés dans ce schéma ; aucun backup.failed fictif n'est créé par l'API.
- Proposition à faire approuver : objectif initial de 7 jours pour les événements courants
  si la capacité le permet, prolongation d'un extrait d'incident jusqu'à 30 jours lorsque
  justifiée et documentée. Ce ne sont ni des règles activées ni des durées légales universelles.
- Limiter l'accès aux administrateurs autorisés ; l'accès au socket/groupe Docker confère
  des pouvoirs larges et ne doit pas être donné à un lecteur de logs non privilégié sans étude.
  Les extraits doivent rester locaux, privés, sans secrets ajoutés manuellement.
- En incident : relever UTC/service/event/request ID, conserver le strict extrait nécessaire,
  constater les lacunes/pertes, examiner le code/configuration sans copier de .env, puis
  suivre les procédures approuvées de révocation/restauration. Aucun automatisme de purge,
  suppression de document, rotation de secret ou blocage de compte n'est introduit.
- Purge : laisser la rotation Docker bornée existante fonctionner. Pour de futurs exports
  privés, définir expiration, revue des pièces gelées pour incident puis suppression explicite
  de l'export concerné. Ne pas supprimer les fichiers actifs du daemon ou modifier globalement
  journald/Traefik pour appliquer cette proposition.

## Modifications et compatibilité

Nouveaux modules : `backend/security_audit.py`, `backend/audit_middleware.py`,
`frontend/server/security-audit.mjs`. Nouveaux tests : `tests/test_security_audit.py` et
`frontend/server/security-audit.test.mjs`, ce dernier ajouté aux commandes npm existantes.

Instrumentation : main, gateway, authentication, resource_limits, api health, upload_admission,
services documents/worker/extraction, account_admin, ai service/long_summary, BFF app/index.
Les schémas métier, tables, clés, vault, budgets, CSRF, contrôles de propriétaire et politique
Landlock/seccomp ne sont pas modifiés. Le test de démarrage confinement vérifie désormais
le message fixe expurgé, toujours avec refus avant démarrage du worker.

Aucune dépendance, migration, configuration de production, unité systemd, outil Sprints 7–9,
inscription publique, fonction IA ou nouveau workflow n'est ajouté/activé. Les workflows
existants récupèrent les nouveaux tests via pytest et la commande `test:bff`.

## Scénarios et preuves de tests

Les sentinelles incluent faux password, texte documentaire, e-mail, clé de service,
session, invitation, reset token, caractères de contrôle et en-tête de 10 000 caractères.
Les tests vérifient les événements attendus et l'absence de ces valeurs dans les JSON,
sorties capturées, erreurs HTTP contrôlées et logs capturés. Le Bearer backend de login
reste retourné à son consommateur BFF légitime ; il n'est jamais journalisé et le BFF
continue de le retirer de la réponse navigateur.

Sont exercés : login succès/échec/logout ; sessions absentes/inventées/expirées/révoquées/
désactivées ; rejets gateway ; anti-spoof request ID ; cross-owner 404 ; quotas ; SQL et
exception inattendue sentinelles ; contexte séparé ; sink cassé ; queue saturée avec
synchronisation Event et délais de sécurité ; reset générique, inscription sur invitation,
changement de password, désactivation/purge fictives. Les tests SEC10-02 vérifient toujours
zéro lecture avant admission et nettoyage/libération des capacités.

## Résultats observés et décision

| Environnement / commande | Réussis | Ignorés | Échoués | Observations |
| --- | ---: | ---: | ---: | --- |
| Windows : pytest security_audit + gateway_security + upload_admission | 92 | 0 | 0 | première sélection, avant les deux derniers cas de cycle de vie |
| Windows : pytest security_audit + extraction_protocol | 53 | 0 | 0 | 21 cas audit + 32 protocole, refus au démarrage contrôlé |
| Windows Python 3.13.7 : suite complète | 583 | 40 | 0 | 480,14 s ; les 40 cas natifs Linux sont ignorés sur cette plateforme |
| WSL Ubuntu Python 3.12.3 : première suite complète | 622 | 0 | 1 | 502,70 s ; un HTTP 503 SQL dans le scénario de reprise de résumé long |
| WSL : scénario résumé long isolé, nouvelle base SQLite | 1 | 0 | 0 | 11,35 s ; aucune modification des assertions/timeouts |
| Docker isolation-tests Python 3.13, sans réseau/volume | 181 | 0 | 0 | 52,79 s ; 72 confinement/protocole + gateway/comptes/BYOK/uploads/audit |
| Docker / PostgreSQL 17 + pgvector : suite complète | 623 | 0 | 0 | 494,83 s ; TEST_DATABASE_URL dédié à une base neuve |
| Node : `npm.cmd --prefix frontend run test:bff` | 48 | 0 | 0 | dont 6 nouveaux tests audit ; inclut les déconnexions d'upload |
| React : `npm.cmd --prefix frontend run test:ui` | 37 | 0 | 0 | 7 fichiers ; aucun appel IA |
| TypeScript/Vite : `npm.cmd --prefix frontend run build` | — | — | 0 | build réussi, également lors du build de l'image frontend |
| Recette HTTPS locale / contrôles API directs | 21 + 7 | 0 | 0 | auth, mauvais password, CSRF, TXT/analyse, isolation et révocation |
| Logs réels de recette | 19 événements contrôlés | — | 0 | 7 types requis présents, aucune sentinelle, corrélation et absence de doublon |
| WSL : confirmation complète avant dernière garde d'envoi 500 | 623 | 0 | 0 | 431,62 s ; le premier HTTP 503 n'est pas reproduit |
| Windows : suite complète avec garde d'envoi 500 | 584 | 40 | 0 | 561,68 s |
| WSL : suite complète avec garde d'envoi 500 | 624 | 0 | 0 | 579,30 s |
| Windows : audit + gateway + uploads, derniers ajustements | 95 | 0 | 0 | 158,17 s ; prévalidation 503 et exception de send couvertes |
| WSL : derniers 22 tests audit | 22 | 0 | 0 | 33,06 s ; sources finales recopiées, nouvelle base temporaire |
| Docker final sans réseau ni volume | 182 | 0 | 0 | 54,12 s ; inclut les 22 cas audit finaux |
| Docker final / PostgreSQL : suite complète | 624 | 0 | 0 | 505,55 s ; nouveau projet et nouvelle base vide |

Les sélections se recoupent : ne pas additionner leurs nombres. L'avertissement de
dépréciation Starlette/httpx est connu et distinct d'un échec métier. Le premier lancement
React/esbuild était bloqué par les restrictions de lecture des répertoires parents ;
la relance avec permissions d'exécution locales a réussi sans modifier Vite ou les protections.

La première campagne WSL a échoué dans
`test_truncated_response_preserves_checkpoint_and_counts_real_attempts_on_resume` :
le suivi de reprise a reçu HTTP 503 « Base de données indisponible ». L'événement
`system.database.unavailable` était présent, sans SQL, texte d'exception, identifiant
de job ou contenu documentaire. Le scénario isolé passe. La cause DBAPI précise du
premier échec n'est pas connue : une contention SQLite est une hypothèse, pas une cause
confirmée. La confirmation complète à 623 cas puis la campagne à 624 cas ont réussi
sans reproduire cet incident. Cet échec initial reste dans le bilan ; il n'est pas
reclassé en erreur d'environnement démontrée ni déclaré corrigé par une modification SQL.
Un premier essai de diagnostic n'atteignait pas pytest à cause d'un environnement JSON
API_KEYS mal formé ; le démarrage a été refusé avec un message expurgé, puis l'environnement
du diagnostic a été corrigé. Aucun délai SQL ou contrôle de sécurité n'a été assoupli.

Les suites complètes Windows/WSL à 584/624 cas ont été lancées après la garde empêchant
la fuite de chaîne d'exception. Le dernier classement explicite du 503 de prévalidation
a été ajouté pendant ces exécutions : il est couvert ensuite sur les sources finales
par Windows 95 cas, WSL 22 cas, Docker 182 cas et la suite PostgreSQL 624 cas. Aucun
statut HTTP ni contrôle d'identité n'a changé avec ce dernier classement.

### Commandes et ressources de validation

Les campagnes ont réutilisé les mécanismes des rapports SEC10-02/03 et de la CI :

```powershell
$testBase = Join-Path (Get-Location) ('var/pytest-sec1004-' + [guid]::NewGuid().ToString('N'))
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --tb=short --basetemp $testBase
npm.cmd --prefix frontend run test:bff
npm.cmd --prefix frontend run test:ui
npm.cmd --prefix frontend run build
wsl -d Ubuntu --exec bash /mnt/c/Users/Adeline/Documents/DocuMind_AI/var/sec1004-8c2cec37b8/linux-test.sh
wsl -d Ubuntu --exec bash /mnt/c/Users/Adeline/Documents/DocuMind_AI/var/sec1004-8c2cec37b8/linux-confirm.sh
```

Les commandes Python utilisent un environnement de processus neutre (`DATABASE_URL=sqlite://`,
API_KEYS vide au sens JSON `{}`, clés BFF/IA vides, IA désactivée), puis les fixtures injectent
leurs seules identités fictives. Aucun fichier .env n'est copié dans la recette Linux/Docker.
Les scripts et copies sont sous `var/sec1004-8c2cec37b8/` (ignoré) et
`/var/tmp/documind-sec1004-8c2cec37b8/` (sources/venv Linux dédiés). La préparation du
venv réutilise pip local, sans installation système ; la résolution des dépendances et
des images de base utilise seulement les dépôts publics habituels, pas le registre privé.

Images neuves construites avec les Dockerfiles existants :

```powershell
$project = 'sec1004-8c2cec37b8'
$dockerConfig = Join-Path (Get-Location) 'var/sec10-03-docker-client'
docker --config $dockerConfig build --target isolation-tests --tag "${project}-isolation:local" .
docker --config $dockerConfig build --target production --tag "${project}-api:local" .
docker --config $dockerConfig build --tag "${project}-web:local" frontend
docker --config $dockerConfig run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges --memory 1536m --cpus 2 --pids-limit 64 --tmpfs /tmp:rw,noexec,nosuid,size=256m,mode=1777 --env DATABASE_URL=sqlite:// --env AI_ENABLED=false "${project}-isolation:local" python -m pytest -q -p no:cacheprovider --tb=short tests/test_extraction_linux.py tests/test_extraction_protocol.py tests/test_gateway_security.py tests/test_byok.py tests/test_accounts_saas.py tests/test_upload_admission.py tests/test_security_audit.py
```

La suite PostgreSQL utilise cette même image, un montage read-only de la copie de sources
assainie sur `/suite`, les mêmes restrictions et le seul réseau interne `${project}_data`.
La commande est `python -m pytest -q -p no:cacheprovider --tb=short` avec
`TEST_DATABASE_URL` désignant la seule base fictive `gateway_tests`, créée vide dans le
PostgreSQL tmpfs de ce projet. L'application de recette utilise une autre base neuve,
`upload_test`, migrée explicitement à `0006`. Certains tests autonomes utilisent leur
propre SQLite par conception, comme dans la CI.

Le Compose de recette existant et sa surcharge Windows ignorée sont réutilisés, sans
modification, avec une surcharge temporaire du nouveau projet : noms d'images uniques,
sous-réseau distinct `172.30.253.0/24`, ports éphémères et certificats fictifs neufs.
Les commandes `compose up --wait db`, `exec db createdb`, `run --rm --no-deps api alembic
upgrade head` et `up --wait api web traefik` sont limitées à ce projet avec `--env-file`
fictif explicite. Traefik est non privilégié, UID/GID 1000. La particularité Windows du
réseau proxy non interne est conservée ; les réseaux application/données restent internes.
Cela n'est pas une preuve d'absence d'egress du BFF ; le parseur sans réseau est prouvé
par la campagne Docker `--network none` et les tests natifs.

La recette a utilisé `https://documind.test:55380`, résolution explicite vers 127.0.0.1,
SNI et certificat autosigné chargé comme ancre de confiance locale, sans désactivation TLS
ni installation dans le magasin système. Deux comptes fictifs, un TXT sentinelle et
des cookies conservés uniquement en mémoire ont été utilisés. Aucun `.part` résiduel.
Le script `recipe_checks.py` ne publie que les comptes de contrôles et une corrélation
technique. `check_logs.py` inspecte stdout/stderr sans les imprimer, vérifie le schéma,
les sept types requis, l'absence de credentials/password/document/user sentinelles, puis
la concordance du request ID HTTP upload/API et l'absence de doublon BFF.

Le noyau local est Linux 6.18.54.1 WSL, Landlock ABI 7 ; aucune attestation de la version
réellement déployée sur Linux 6.12/ABI 6 n'est inventée. Les conteneurs API/BFF/DB étaient
healthy et Traefik répondait en HTTPS. Après vérification des labels/noms et de l'absence
de volumes persistants, les quatre conteneurs et trois réseaux **nouveaux** ont été retirés
avec `compose down`, sans `-v` ni prune. Les ressources préexistantes sont conservées.
Les images de test et traces privées ignorées restent locales pour revue.
Le driver observé sur cette recette Docker Desktop est `local`, et non `json-file` :
les événements applicatifs restent JSON dans `docker logs`, mais cela ne certifie ni
le stockage physique ni la rotation effectivement appliqués sur le VPS. Les options
`json-file` décrites plus haut sont celles du Compose de production examiné.

La garde d'envoi 500 et le classement de prévalidation ont donné lieu à une seconde
recette entièrement neuve : `sec1004-final-ea5afba1`, sous-réseau `172.30.254.0/24`,
traces sous `var/sec1004-final-ea5afba1/`, HTTPS local sur le port éphémère 60682.
La préparation est la même, avec de nouvelles bases, de nouveaux noms d'images et
de nouveaux certificats. Elle confirme à nouveau les 21 contrôles HTTPS et 7 contrôles
API, les 19 événements contrôlés dont sept types requis, et l'absence de sentinelles/doublons ; pas de `.part` résiduel.
PostgreSQL 17.11 / pgvector 0.8.7 / Alembic 0006 ont été relevés sur cette recette.
L'API est non-root (`app`), read-only, cap-drop ALL, `NoNewPrivs=1`, `Seccomp=2`.
Les journaux de ce PostgreSQL fictif ont aussi été examinés sans les imprimer : aucun
e-mail/password sentinelle, aucune ligne STATEMENT/DETAIL dans cette campagne ; cela
ne prouve pas une absence générale de données SQL dans les logs serveur d'autres erreurs.
Le second projet a été retiré après les mêmes vérifications, sans toucher aux ressources
préexistantes ni supprimer de volume. Aucun script de recette n'a été relancé sur une base
non vide ou un projet existant.

Pour cette seconde campagne, utiliser les commandes ci-dessus avec ce nouvel identifiant
et `var/sec1004-final-ea5afba1/` ; le script WSL `linux-final.sh` réutilise le seul venv
de tests et crée un nouveau basetemp, tandis que `linux-audit-final.sh` vérifie les derniers
cas ciblés. Ces chemins sont un historique de tests, pas des commandes de déploiement.

### Décision finale

**Prêt pour revue Git des producteurs de sécurité applicatifs.** Les événements critiques
retenus, l'expurgation, la corrélation BFF/API, les refus avant lecture et l'isolation
d'identité sont vérifiés par les tests et la recette locale. Le premier incident SQLite
non reproduit reste une réserve à suivre, sans cause affirmée. La garde d'erreur d'envoi
500 possède un test sentinelle spécifique. Les six nouveaux fichiers et le diff suivi
ont été contrôlés sans erreur de formatage ; aucun fichier privé, certificat ou artefact
`var/` n'entre dans les candidats Git.

Ce verdict n'est ni une autorisation de publication ni une validation d'ouverture publique :
alertes et collecte restent proposées, la corrélation Traefik réelle n'est pas installée,
les pertes best effort et la réserve transport demeurent. Avant une future PR, actualiser
les références Git distantes seulement avec autorisation et vérifier la base `main`, dont
la référence locale était en retard au début du travail. Aucun commit/push/PR/merge,
accès VPS/Registry privée, workflow distant, déploiement ou envoi d'alertes n'a été effectué.

## Limites et conditions avant ouverture publique

Le logging best effort ne remplace pas une collecte durable ni une alerte active. Absence
de signature/chaînage des événements, d'horloge de confiance externe, de corrélation des jobs
indépendants ou d'identification de la source d'une attaque par IP : limites intentionnelles
ou restant à traiter selon besoin. Des logs locaux peuvent être altérés par un administrateur.

La réserve SEC10-03 sur `Expect: 100-continue`, corps annoncé mais non envoyé et connexion
persistante devant Traefik reste ouverte. SEC10-04 ne la corrige pas et ne prouve pas un
rejet immédiat à cette frontière ; la sonde avec Connection: close est un scénario distinct.
Les buffers du réseau/proxy ne sont pas supprimés par une journalisation ASGI.

Avant ouverture publique : revue Git de la minimisation et du coût des événements, CI complète,
validation des ressources/volume, stratégie de collecte et perte de logs, propriétaire des
alertes et exercice local du futur lecteur, politique de conservation approuvée, vérification
du Traefik réel et de ses champs sans collecte excessive, décision explicite sur la réserve
transport, puis autorisations de publication et de livraison distinctes. Aucune opération
manuelle de production n'est exécutée ici. Les adaptations de collecte/Traefik/alertes
nécessiteraient leur propre accord et une recette avant activation.
