# Docnelo Public Beta — Plan de réconciliation contrôlée de provenance API

Date : 1 novembre 2026. **Verdict actuel : NO-GO.**
Étude documentaire uniquement. Aucune commande VPS ni opération Docker
exécutée ; aucun code, garde, Compose, `.env`, label, clé, magasin ou témoin
lifecycle modifié. Ce plan n'autorise ni une intervention ni Lifecycle 10.

## 1. Faisabilité : créer une provenance prospective, pas réparer l'histoire

Selon le nouveau relevé communiqué par l'opératrice, r3 fonctionne sur VPS,
Web et PostgreSQL correspondent aux modèles actuels, l'API ne correspond
pas, et les familles 280/300/362 ne reproduisent pas son hash dans les
contextes testés. Les JSON VPS de ces essais ne sont pas présents localement
pour une vérification indépendante ; ils doivent entrer au dossier de preuve.

La stratégie étudiée est un **nouveau déploiement de référence fermé**,
avec entrées exactes et chaîne de création enregistrées. Il serait possible
techniquement de documenter la provenance d'un nouveau conteneur sans
retrouver celle de l'ancien. Ce n'est pas une autorisation de le faire.

Deux assertions resteront séparées dans tous les documents :

- **Historique H0 : non authentifié.** Conteneur annoncé créé le
  31 octobre 2026 à 01:11:06 UTC, label de configuration
  `e0559dddd889a8b0af4767c4d14668b32904ea547ac8865f8a2c691e5062aeaf`.
  Ne pas remplacer cette référence, effacer les essais négatifs ou
  déclarer sa préimage retrouvée après une recréation.
- **Référence prospective R1 : à qualifier, non créée.** Un identifiant de
  release neuf liera image, entrées, contexte, commande, événement et nouvel
  ID de conteneur. Son hash natif sera une nouvelle référence explicitement
  datée, pas une explication du hash H0.

### Verrou d'autorisation

Le garde parent exige l'égalité entre hash natif du modèle et label API
existant (`deliveries\docnelo-lifecycle-10-api\payload\check_closed_compose.py:61-64`). Le garde r1 exige aussi
les trois hashes historiques et le succès du garde parent
(`deliveries\docnelo-lifecycle10-compose-guard-r1\check_closed_compose.py:302-315`).
Les informations fournies ne satisfont pas cette condition API.

**Une approbation humaine de valeurs ou une nouvelle signature de manifeste
ne transforme pas ce refus en PASS.** Aucun `skip`, nouvel attendu substitué
au label, édition de garde, allowlist de hash ou invocation directe de
Compose à la place d'un garde bloquant n'est proposé.

Une éventuelle procédure dédiée de réconciliation devra être qualifiée
et faire l'objet d'une revue indépendante d'applicabilité des gardes :
chaque garde applicable doit passer sans modification. Un garde spécifique
au déploiement capacity10 n'est pas un contrôleur générique de cette étude ;
son éventuelle non-applicabilité à une autre opération doit être établie
par la politique autorisée, jamais déduite du fait qu'il refuse.
**Aucune voie de transition autorisée n'est établie par les artefacts lus.**
Si l'égalité historique reste un préalable de toute recréation, la
réconciliation demeure impossible sous cette politique tant qu'elle manque.
Le présent plan ne propose pas de lever ce préalable.

## 2. Périmètre futur recommandé et alternatives

La référence la moins risquée à étudier conserve la **même image API active
4aa850…**, le même code et les mêmes dépendances, avec des paramètres
effectifs équivalents. Son identité doit être recontrôlée sur VPS ; l'archive
locale n'atteste pas à elle seule l'image encore exécutée.

Conserver Web R2 et PostgreSQL, leurs IDs et images, réseaux et volumes.
Ne pas utiliser cette opération pour adopter la candidate capacity10,
changer de namespace, ajouter une garde applicative, corriger des
permissions, migrer les cinq magasins, faire une migration SQL, modifier
des valeurs publiques ou ouvrir les inscriptions. Toute correction
nécessaire de ce type constitue un autre lot, bloquant celui-ci.

| Option | Faisabilité et décision proposée |
|---|---|
| Maintien du conteneur actuel, collecte documentaire | Seule option immédiate sans mutation ; défaut de provenance inchangé, NO-GO maintenu |
| Même image, cible déclarative nouvelle préservant tout le runtime | Option prospective à qualifier en laboratoire ; exige autorisation applicable, sauvegarde et retour arrière éprouvés |
| Image capacity10 ou autre mise à jour fonctionnelle simultanée | Hors périmètre ; cumule les risques et nécessite une autre qualification |
| API parallèle sur les volumes ou la DB actifs | Exclue : risque de writers concurrents, sessions, connexions et verrous ; seuls des laboratoires isolés sont envisagés |
| Reconstruction d'un Compose depuis inspect pour le nommer « historique » | Exclue : la projection runtime ne retrouve pas les omissions, héritages ou entrées de création |

L'opération peut être reproductible au niveau **image + modèle de service +
contexte + valeurs effectives**. Elle ne produira pas à chaque essai les
mêmes IDs Docker, StartedAt, IP allouées ou métadonnées d'événement.
Ces allocations doivent être enregistrées, pas promises identiques.

## 3. Risques et mesures de maîtrise

| Risque | Mesure requise / arrêt |
|---|---|
| Contourner indirectement le garde historique | Cartographie écrite des gardes, voie autorisée qualifiée, aucun refus applicable ignoré ; sinon arrêt avant toute mutation |
| Perdre la seule instance Docker observable de H0 | Dossier préalable complet et décision consciente sur cette perte ; aucun retour « à l'identique » promis |
| Adopter les nouvelles valeurs du `.env` au lieu des valeurs servies | Comparaison privée complète et conservation explicite des valeurs approuvées ; aucune adoption automatique |
| Monter les anciens chemins plats ou de mauvaises clés | Vérification des cinq chemins, deux clés, identités des volumes et droits ; aucune réparation pendant le lot |
| Modifier Web/DB par la fusion ou les dépendances Compose | Cible API seule ; tous les overrides actifs conservés dans leur ordre ; modèles Web/DB et IDs invariants |
| Changer l'état durable au démarrage malgré l'absence de migration CLI | Qualification du startup de l'image exacte sur une restauration isolée ; inventaires avant/après et arrêt si mutation non autorisée |
| Sauvegarde fondée sur un modèle différent du runtime | Qualification de la chaîne de capture contre les chemins et valeurs effectifs ; pas de substitution de root ou d'override improvisée |
| Sauvegarde distante seulement « présente », non restaurable | Exercice de récupération de l'ID exact, vérification et restauration isolée ; présence Restic insuffisante |
| Perte d'accès/session ou interruption plus longue que prévu | Fenêtre fermée, information opératrice, durée maximale et point de décision écrits ; comptes/consentements persistants invariants |
| Fuite d'environnement ou de preuves contenant des clés | Dossiers privés, sorties expurgées, chiffrement hors VPS ; pas de logs shell bruts, `set -x`, secrets dans argv ou Git |
| Dérive entre approbation et création | Fenêtre exclusive, liaison d'approbation aux empreintes, contrôles frais ; toute dérive invalide la décision |
| Faux sentiment de rollback offert par la seule archive image | Modèle de repli complet, testé, compatible et autorisé ; sinon NO-GO avant destruction de l'ancienne instance |

## 4. Préserver l'état actuel et les preuves

Avant toute future fenêtre, constituer un dossier privé **H0** nouveau,
sans réécrire les dossiers r2/r3 ou les rapports historiques. Les collectes
complémentaires sont des opérations opératrices à autoriser séparément ;
elles ne sont pas exécutées dans cette étude.

| Objet | Conservation et contrôle attendus |
|---|---|
| Conteneurs API/Web/DB | ID complet, Created, StartedAt, état/santé, image ID/référence, Config, HostConfig, Mounts complets avec doublons, réseaux et labels ; relevés avant/après collection |
| Configuration courante | Octets originaux des Compose/overrides, chemins physiques, ordre complet `-f`, empreintes, données de labels conservées comme observations et non comme anciens octets |
| Environnement | Copies privées des fichiers actuels et relevé privé des valeurs effectives nécessaires à la conservation ; sources d'interpolation, ordre CLI/service, valeurs héritées d'image et absences distingués |
| Contexte d'exécution | Version et identité de Compose, Python d'outillage, plateforme, daemon/socket/contexte Docker, project-directory, nom de projet, profils et options ; variables shell pertinentes conservées en privé |
| Image active | Archive sauvegardée, SHA-256, ID du config blob, référence textuelle et plateforme ; ni retag écrasant un tag existant, ni substitution par un build « équivalent » |
| Lifecycle et données | Probes existants compatibles et réellement readonly, quota/fermeture, schémas, namespace signé, latch, permissions/identités des clés et magasins ; rattachement à une capture cohérente |
| Recherche négative | Rapports r3, refus, contextes et résultats 280/300/362 ; portée exacte des essais, absence de provenance explicite |
| Provenance humaine | Identifiant d'intervention, opérateur habilité, date UTC et état d'horloge, motif, revue, approbation liée au dossier, événements et résultat |

Un inspect brut peut contenir des secrets. S'il doit être conservé pour
une comparaison intégrale, ce sera dans le dossier privé chiffré, jamais
dans le terminal ou le dépôt. Le rapport partageable contient seulement
les noms de champs, chemins non sensibles et empreintes approuvées.
Les coordonnées privées des opérateurs ne sont pas à publier.

Chaque fichier de preuve est créé sans écrasement. Un manifeste SHA-256
couvre les octets ; son empreinte est authentifiée hors bande et liée à
une approbation humaine. Prévoir une copie chiffrée hors VPS et une politique
de conservation approuvée ; aucune nouvelle durée de rétention ni purge
automatique n'est inventée. Les preuves contenant des clés suivent la
politique de sauvegarde des secrets, pas celle des rapports publics.

## 5. Matrice effective → cible : aucun delta global n'est déjà approuvé

Il manque ici l'inspect privé complet et le modèle cible revu. Le hash
API différent n'indique pas les champs responsables. Les anciens rapports
mentionnent deux champs publics différents ; ce constat doit être
revalidé, pas reconduit comme une liste exhaustive.

| Domaine | Observation disponible / inconnue | Politique de cible minimale |
|---|---|---|
| Image API | Référence historique 4aa850… ; présence actuelle à vérifier | Même ID, même configuration d'image, même plateforme et référence textuelle approuvée ; aucun build |
| Environnement API complet | Écart antérieur `PUBLIC_CONTACT_EMAIL` / `PUBLIC_OPERATOR_NAME` ; reste du relevé actuel non fourni | Égalité intégrale des valeurs effectives et de la présence/absence, y compris héritages ; pas seulement les deux noms publics |
| Sept chemins lifecycle | Historique des déclarations identifié ; runtime actuel à certifier | Cinq chemins et deux clés identiques au runtime approuvé, sans déplacement ou ajout de déclaration non revu |
| Namespace, fermeture et flags | États annoncés dans les anciens dossiers, fraîcheur à établir | Identiques au relevé frais ; aucune injection de namespace « pour passer » un probe |
| User/UID/GID, entrypoint, commande, workdir | Image/user historiques connus partiellement | Héritages et explicites distingués ; effectifs inchangés, startup qualifié |
| Mounts | r3 normalise uniquement l'ordre des enregistrements complets | Toutes les propriétés et multiplicités conservées ; mêmes sources/destinations/types/modes/propagations/identités |
| Réseaux | Web/DB hashes conformes selon l'opératrice | Mêmes réseaux physiques et IDs, alias déclarés, IPAM, options ; allocations dynamiques enregistrées séparément |
| Sécurité et ressources | Pas de projection exhaustive VPS disponible ici | Rootfs, capacités, security_opt, tmpfs, limites, stop_grace_period, restart, healthcheck et logging inchangés |
| Labels | Label API H0 inconcilié ; labels utilisateur à inventorier | Labels utilisateur conservés ; métadonnées Compose nouvelles uniquement celles normalement générées lors d'une future création autorisée |
| Web/DB | Hashes conformes annoncés | Modèles, environnement, IDs, images, volumes et sécurité inchangés ; DB sans redémarrage |
| Fichiers `.env` / ordre | Deux fichiers CLI dans les runbooks, un service env_file interpolé | Originaux jamais édités ; toute entrée privée nouvelle et tout ordre explicitement documentés et qualifiés |

Le registre de différences devra, pour chaque champ, consigner :
`source actuelle → valeur effective → déclaration cible → effet attendu →
justification → test → approbation`, avec valeurs sensibles seulement en privé.
Un champ inconnu ou un delta comportemental non autorisé bloque la cible.

La cible peut nécessiter un **nouvel override privé de conservation** ou
une nouvelle entrée d'environnement immuable ; leur forme reste à choisir
après inventaire et qualification. Ils sont des entrées futures, jamais
« l'historique reconstitué ». Les fichiers `.env` existants ne sont pas
modifiés. Le déplacement ou changement de chemin d'env_file peut changer
le hash et la résolution relative : il doit être traité comme un delta
déclaratif, même si les valeurs effectives sont identiques.

Le contrôle utilisera la résolution réelle de Compose et les héritages de
l'image. Dollars littéraux, valeurs nulles/non résolues, doublons et ordre
des env-files seront testés. Aucun filtrage des variables, dédoublonnage de
montages ou hash « maison » ne remplace `config --hash` natif.

## 6. Sauvegarde et restauration : préalables opérationnels distincts

Une sauvegarde doit couvrir PostgreSQL, documents, les cinq magasins
lifecycle et leur cohérence S2, les deux clés, le latch et les entrées privées
de configuration/provenance nécessaires. Elle ne certifie pas l'ancienne
commande Docker.

L'orchestrateur lu (`tools\public_beta_backup.py:139-177`) utilise :
un root physique, **un seul Compose de base**, deux env-files, un contexte
shell restreint et un latch explicite. Il stoppe API/Web, démarre le
conteneur DB existant et ne redémarre pas API/Web automatiquement.
Il n'accepte pas arbitrairement la chaîne d'overrides de cette nouvelle
étude. Son helper prend des chemins lifecycle dans la configuration
résolue, pas une preuve implicite de l'environnement API de H0.

**Conséquence :** ne pas supposer que cet outil capture les bons chemins
parce que ses validations de volumes passent. Il faut qualifier la release
effectivement installée et sa chaîne contre le runtime approuvé, les
overrides et les clés root:app. Si elle ne sait pas traiter les entrées
nécessaires sans modification ni omission, c'est un prérequis bloquant ;
aucun patch ou chemin alternatif de capture n'est livré ici.

La release V5.1 conservée annonce un format de backup V5, mais aussi
l'absence de qualification runtime Linux dans ses métadonnées
(`deliveries\docnelo-public-beta-backup-v5.1-20261031\RELEASE.json`).
Ce n'est pas une preuve de déploiement ou de restauration réelle du VPS.
Le schéma actuel doit déterminer l'outillage compatible ; aucune migration
capacity10 ou adoption de V5.2 n'est incluse dans ce plan.

Deux barrières temporelles :

1. **Avant la première interruption :** une sauvegarde existante assez
   récente selon RPO approuvé, complète, chiffrée hors VPS, avec restauration
   isolée réussie et repli testé. Sinon pas de fenêtre. La capture fraîche
   ne peut pas être présentée comme déjà acquise avant son propre arrêt.
2. **Après quiescence autorisée, avant remplacement API :** capture fraîche
   cohérente, intégrité/S2, ID Restic complet, tags/chemins/destination et
   repo ID vérifiés, récupération et validation de cette capture exacte.
   Pas de « dernier backup » choisi par date.

Ne pas réenregistrer un ID Restic, changer bucket/préfixe, ajouter une
planification ou lancer une purge. Le mode `--record-repo-id` écrit une
configuration : il n'est pas une précommande neutre de ce lot.
Un arrêt de Web peut être nécessaire à la sauvegarde cohérente ; même
temporaire, il doit être inclus dans le périmètre futur autorisé. Si
l'autorisation interdit aussi cet arrêt, la procédure existante ne convient
pas et la fenêtre reste NO-GO.

La restauration de contrôle est hors production, avec DB, volumes et
réseaux propres, sans SMTP, workers externes ou inscriptions réelles.
Le latch du laboratoire est quarantiné selon la politique de restore,
sans modifier le latch original. Aucun montage des volumes actifs, aucune
restauration sur ceux-ci pour démontrer la récupérabilité.

## 7. Tests à qualifier avant et après une éventuelle intervention

Tous les tests ci-dessous sont **à réaliser ultérieurement**, pas des
résultats de cette étude. RPO, RTO, délais de santé et fenêtre d'observation
doivent être chiffrés et approuvés avant d'écrire le runbook exécutable.

| Phase | Tests / preuve attendue | Refus |
|---|---|---|
| Avant, statique | Release source propre et bornée, manifeste authentifié, images exactes ; références, options, fichiers et contexte exhaustifs | Artefact mutable, version inconnue, secret dans bundle |
| Avant, modèles | Hashes natifs API/Web/DB, rejeu `defer_paths` fidèle, résolution et environnement complets ; aucun delta Web/DB ou comportement API | Rejeu infidèle, dollar/null mal traité, entrée ou héritage inconnu |
| Avant, Linux isolé | Création de la cible depuis les entrées exactes sur restore privé ; santé, login/session de test, lectures API/BFF, fermeture ; aucun effet startup durable inattendu | Mutation non autorisée, incompatibilité de lecteur, clé/namespace/chemin incorrect |
| Avant, reprise | Repli construit depuis ses entrées exactes sur la même copie de laboratoire ; tests identiques, reprise dans RTO et état durable conservé | « Rollback » réduit à un tag d'image ou à un inspect |
| Avant, frais VPS | Collecte r3 stable, égalité des invariants, sécurité, schémas, quota, latch, preuves HMAC, droits et gardes applicables | Toute dérive réelle, garde failed ou preuve vieillie |
| Après capture | Vérification et restauration de l'ID exact ; quiescence, données et preuves reliées à la fenêtre | Capture partielle, distante ambiguë, droits/clé absents |
| Après création | Nouvel ID API relié à l'événement et aux entrées ; hash label API égal au hash natif R1 ; image exacte et santé dans le délai | Hash/image non conformes, création non tracée, healthcheck insuffisant |
| Après, invariants | Environnement et runtime équivalents ; clés, stores, namespace, latch, quota, schémas, flags et données conservés ; Web/DB invariants | Delta non listé, redémarrage DB, nouvelle admission, divergence de témoin |
| Après, service fermé | Endpoints existants readonly et clients de test autorisés ; métriques/erreurs durant la fenêtre approuvée | Ouverture involontaire, SMTP réel, E2E créant des comptes ou données |

Les timestamps Created/StartedAt et l'ID API devront naturellement changer
si une recréation a lieu. Les allocations automatiques seront documentées
avec leur règle et leur valeur avant/après. Aucun masque général de
NetworkSettings, HostConfig, labels utilisateur, environnement ou Mounts.
Les sous-listes de propriétés restent sensibles sauf sémantique qualifiée.

Le helper parent `operator_runtime.py` est un contrôle complémentaire,
pas le comparateur intégral de réconciliation : il projette certains champs
de Mounts et son CLI traite spécialement le namespace
`documind-public-beta`. Sa méthode reste inchangée ; ses exemptions ne
deviennent pas des autorisations de delta pour cette cible à image identique.
Tout lecteur/probe doit être compatible avec l'image et l'état signés ;
une erreur de lecteur ne justifie ni injection de variable ni correction de clé.

## 8. Prérequis et critères GO/NO-GO

| Barrière | Condition requise pour une décision future | État aujourd'hui |
|---|---|---|
| Autorisation | Voie de réconciliation explicitement autorisée, cartographie des gardes et absence de contournement | **Non établie : bloquant** |
| Historique | H0 et essais négatifs conservés ; aucune conclusion historique nouvelle sans preuve | Historique non authentifié |
| Observations | Rapport r3 VPS complet et frais, inspect privé, image et contexte recontrôlés | Résumé opérateur seulement ici |
| Cible | Inventaire exhaustif, aucun delta effectif non approuvé, mêmes code/image/état | Non définie ni qualifiée |
| Sauvegarde | Chaîne de capture compatible, backup antérieur récupérable, puis capture fraîche cohérente | Preuves opérationnelles non fournies |
| Repli | Entrées de repli immuables, reprise testée, garanties et limites explicites | **Non qualifié : bloquant** |
| Sécurité/lifecycle | Tous les contrôles applicables inchangés et passés ; état fermé frais | Succès exhaustif non établi |
| Fenêtre | Opérateur habilité, exclusivité, RPO/RTO/délais chiffrés, approbation liée aux empreintes | À définir |
| Preuve prospective | Journal fiable, événement, hashes et stockage privé hors VPS prêts | À préparer hors production |

Un éventuel **GO d'intervention limité** signifierait seulement que ces
barrières sont toutes satisfaites pour une opération précise, pas un GO
Lifecycle 10 ni une ouverture. Le succès documentaire ou du diagnostic
r3 n'est pas une autorisation. Un `diagnostic_complete=true` avec retour
2 et `status=NO-GO` conserve cette signification.

## 9. Nouveaux contrôles versus gardes existants

| Contrôle | Fonction et portée |
|---|---|
| Gardes lifecycle existants | Sécurité et cohérence des stores, HMAC/namespace, quotas, durabilité, latch, flags, permissions et politiques d'admission ; restent inchangés et obligatoires |
| Gardes de déploiement scellés | Conditions de leur transition spécifique, images/modèles/hashes et état initial ; refus conservé, aucun attendu substitué |
| Diagnostic r3 existant | Observation stable et matrices de rejeu ; aucune autorisation de déploiement ou preuve automatique de provenance |
| Réconciliation prospective, à développer/qualifier dans un autre lot autorisé | Liaison entrées-contexte-commande-événement-ID, delta explicite, équivalence complète et repli ; **addition**, pas remplacement des gardes |
| Manifeste et approbation humaine | Authenticité/inventaire des nouveaux artefacts et décision bornée ; pas une preuve HMAC lifecycle, historique ou un PASS de garde |

L'étude ne crée ni ce nouveau contrôleur, ni un JSON d'approbation,
ni un override, ni une nouvelle baseline de hash. Le détail de la
séquence future et du retour arrière se trouve dans
`DOCNELO_API_RECONCILIATION_FUTURE_RUNBOOK.md`.

## Sources principales et verdict

Sources consultées : `DOCNELO_API_DEPLOYMENT_PROVENANCE_20261031_REPORT.md`,
`DOCNELO_LIFECYCLE10_RESIDUAL_HASH_ANALYSIS.md:7-12,49-56`,
`deliveries\docnelo-lifecycle-10-api\payload\check_closed_compose.py:19-69`,
`deliveries\docnelo-lifecycle10-compose-guard-r1\check_closed_compose.py:243-340`,
`deliveries\docnelo-lifecycle-10-api\payload\operator_runtime.py`,
`deliveries\docnelo-lifecycle-10-api\payload\probe_status.py`,
`tools\public_beta_backup.py:59-96,139-198`,
`ops\public_beta\BACKUP_ENCRYPTED_OFF_VPS.md`,
`ops\public_beta\VPS_BACKUP_RESTORE_RUNBOOK.md`,
et les runbooks Lifecycle 10 existants. Ceux-ci sont des sources de
conditions et de limites, **pas des commandes à reprendre pour cette étude**.

**NO-GO actuel.** La nouvelle provenance prospective est une possibilité
technique sous conditions ; aucune transition autorisée, cible exacte,
sauvegarde fraîche ou réversibilité complète n'est démontrée. L'historique
de H0 demeure non résolu. Aucune mutation pendant cette étude.
