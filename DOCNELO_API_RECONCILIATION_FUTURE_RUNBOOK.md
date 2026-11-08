# Docnelo — Procédure future de réconciliation API et de retour arrière

Date : 1 novembre 2026. **NO-GO. Procédure non exécutée et non exécutable
en l'état.** Aucun bloc de commandes de création ou de migration n'est
fourni : les artefacts, contrôles d'autorisation, délais et entrées de repli
ne sont pas encore qualifiés.

Lire `DOCNELO_API_CONTROLLED_RECONCILIATION_PLAN.md` pour les risques,
la matrice de comparaison et la distinction des gardes. Chaque étape
ci-dessous est conditionnelle ; un refus interdit les étapes suivantes.
Il ne s'agit pas du runbook capacity10, même si certaines sources en
proviennent.

## A. Préparation documentaire, sans opération sur l'application

1. Définir un identifiant neuf d'intervention et un dossier d'artefacts
   prospectifs distinct de H0 et des releases scellées. Consigner
   `historical_provenance=unresolved`, `deployment_authorized=false`,
   `opening_authorized=false` dans le futur dossier de préparation.
2. Revoir avec l'autorité habilitée la voie autorisée et l'applicabilité
   de **chaque** garde existant. Ne pas ignorer un garde parce que le lot
   porte un autre nom. Si le hash H0 doit être reproduit avant toute
   recréation et ne l'est pas, arrêter ici. Aucune modification de garde
   ni procédure de contournement ne fait partie de ce runbook.
3. Définir la cible conservatrice : même image API, comportement et données
   identiques, aucun changement capacity10 ; dresser la liste exhaustive
   des deltas déclaratifs et des allocations Docker attendues.
4. Produire hors production les entrées immuables de cible et de repli,
   les références source propres, les manifestes, le mécanisme de
   collecte privée et le comparateur de réconciliation additionnel.
   Leur développement et qualification seraient un autre lot autorisé.
5. Qualifier sur Linux isolé création, startup, tests fonctionnels fermés,
   invariants lifecycle, capture/restauration et retour au repli. Aucun
   contact SMTP, utilisateur réel ou montage de volume actif.
6. Fixer numériquement la durée d'interruption, le délai healthy, le délai
   maximal de collecte/restauration, la fenêtre d'observation, le RPO
   et le RTO. Prévoir qui décide de l'arrêt et qui vérifie le résultat.
   Un champ « à renseigner » interdit de sceller le runbook exécutable.

Le dossier pourra prouver que la **cible** est reproductible. Il ne doit
pas s'appeler « configuration historique authentifiée ».

## B. Éléments à établir avant toute future interruption

Collecte opératrice séparément autorisée, uniquement en lecture compatible
avec les gardes et les restrictions de confidentialité :

1. Relever les preuves H0 dans un nouveau dossier privé : IDs complets,
   état et santé, labels, images, runtime intégral, entrées et contexte,
   rapport r3 complet, essais historiques négatifs et probes readonly
   compatibles. Recontrôler la stabilité pendant cette collecte.
2. Authentifier le manifeste H0, sa copie chiffrée hors VPS et les entrées
   cible/repli. Une copie d'inspect, un Dockerfile ou un tag seul ne sont
   pas une configuration de reprise.
3. Vérifier une sauvegarde antérieure récupérable dans le RPO, les outils
   installés, la destination indépendante et l'ID Restic existant. Ne
   pas inscrire un nouvel ID ou changer une configuration pour passer.
4. Vérifier la compatibilité **exacte** de l'orchestrateur de backup avec
   les chemins lifecycle effectifs, les overrides, les env-files et
   les clés. Aucun changement de root, omission d'override ou patch
   improvisé pour rendre la capture possible.
5. Revalider schémas, fermeture, quota et compteurs, namespace/HMAC, flags,
   latch, permissions et identité des magasins et clés. Ne pas utiliser
   un contrôle supposant dix admissions ou un namespace injecté.
6. Relier l'approbation de la fenêtre à H0, cible, repli, outils, liste de
   deltas et backup éprouvé. Une approbation vieillie ou une empreinte
   changée impose une nouvelle collecte et une nouvelle décision.

**Point d'arrêt B :** sans garde applicable passé, voie autorisée,
équivalence complète et repli qualifié, aucune interruption.

## C. Fenêtre future, uniquement après une autorisation distincte

### C1. Quiescence et sauvegarde fraîche

Relever une dernière fois IDs, versions, entrées et état, puis appliquer
la quiescence de l'orchestrateur déjà qualifié. Dans la procédure existante,
cela signifie arrêt API/Web et DB existante seule ; cet arrêt de Web doit
être autorisé expressément, même si seul l'API sera ensuite recréé.
Aucun redémarrage DB, `lifecycle-init`, migration, reset ou réparation.

Exiger la capture fraîche exacte, sa vérification intégrale, les deux clés,
S2, latch, données et empreintes, puis l'ID complet distant et la
récupération/validation selon l'exercice approuvé. Les lecteurs de capture
doivent préserver les stores et permissions. L'orchestrateur ne doit pas
redémarrer automatiquement API/Web.

En cas d'échec : conserver fermé et toutes les preuves ; l'opératrice
contrôle l'état réel. Une reprise éventuelle du **conteneur existant**
relève du chemin de reprise préqualifié, pas d'un `up` improvisé.

### C2. Décision irréversible sur l'ancienne instance

Avant tout remplacement, vérifier à nouveau que les inputs scellés
correspondent à la décision, que les données n'ont pas dérivé et que le
repli peut être appliqué dans le délai. Émettre un point de décision
documenté avec l'identifiant complet de l'API H0.

La destruction/remplacement de H0 ferait perdre son instance et son ID.
L'archive image ne sauvegarde pas ce conteneur. Aucun renommage,
clone, checkpoint Docker ou mécanisme de conservation d'instance n'est
supposé disponible ou proposé sans qualification dédiée.

**Si la réversibilité exigée inclut le retour à l'ID, Created, StartedAt
et label H0 exacts, le remplacement est NO-GO : ce plan ne sait pas la
garantir.** Si une reprise fonctionnelle depuis une nouvelle baseline
équivalente est la garantie choisie, ses limites doivent être approuvées
avant cette décision, sans relâcher les gardes applicables.

### C3. Création future tracée de l'API seule

Cette étape reste interdite tant que les barrières précédentes manquent.
Le futur runbook scellé devra spécifier la commande et ses arguments
exacts, pas des valeurs choisies pendant l'incident :

| Paramètre | Exigence |
|---|---|
| Moteur | Version Compose qualifiée et daemon/socket Public Beta explicite ; pas de mise à jour dans la fenêtre |
| Contexte | Project-directory physique, nom de projet et plateforme exacts ; profils/options fixés |
| Entrées | Liste ordonnée complète des `-f` et `--env-file`, chemins physiques, empreintes, contexte shell privé lié au manifeste |
| Image | Même ID API approuvé, référence textuelle documentée ; image déjà disponible, aucun build/pull ou retag écrasant |
| Action | Uniquement le service API, dépendances non démarrées ; aucune commande visant Web/DB/init ou migration |
| Journal | argv non sensible et références privées, date UTC, code retour, événement Docker si disponible, nouvel ID et label immédiatement collectés |

Les options limitant dépendances, build et pull ne remplacent aucun garde.
Enregistrer le résultat de l'action et l'inspect du nouveau conteneur pour
relier commande, image, modèle, entrées et nouvel ID. Une date ou un événement
Docker seuls ne suffisent pas. Aucun label existant n'est édité ; les nouveaux
labels normalement produits par Compose sont vérifiés contre le modèle R1.

### C4. Vérifications avant retour du service fermé

Attendre healthy dans le délai approuvé et vérifier la disponibilité réelle,
puis :

- Hash natif API R1 égal au nouveau label ; image et provenance de création
  conformes, collecte stable avec la méthode r3.
- Comparaison intégrale du runtime au registre de deltas approuvé ; mêmes
  valeurs effectives, propriétés/multiplicités des montages, réseaux et
  sécurité. IDs et valeurs allouées API documentés séparément.
- Identités/images/configurations Web et DB conservées, DB sans redémarrage.
  Si Web a été stoppé pour le backup, reprise uniquement du conteneur Web
  existant par le chemin autorisé, sans recréation.
- Données, schémas, quota et fermeture, compteurs/consentements, namespace,
  HMAC, latch, empreintes/modes/identités des clés et stores conformes à la
  capture cohérente. Aucun changement startup non autorisé.
- Tests fermés readonly préqualifiés et observation durant la fenêtre
  définie ; pas d'inscription, email réel, upload destructif ni dry-run
  capacity10 comme étape de cette opération.

Les invariants durables doivent être comparés dans des conditions cohérentes :
aucun writer applicatif/concurrent non prévu pendant la vérification.
Si cette quiescence ne peut être assurée, une égalité des stores ou des
compteurs n'est pas certifiée ; arrêter plutôt que normaliser une divergence.

### C5. Conservation et décision de clôture

Créer un dossier **R1-created** distinct de H0, contenant :

| Ensemble | Contenu minimal |
|---|---|
| Entrées | Release/source, images, Compose/overrides, contexte et env-files privés, ordre et SHA-256 |
| Action | Décision liée aux empreintes, commande, début/fin UTC, code retour, événements disponibles, nouvel ID API |
| Comparaisons | Rapports avant/après, deltas approuvés et allocations, hash natif/label R1, invariant Web/DB et preuves lifecycle |
| Récupération | Identifiant backup exact, résultats de restauration, référence du repli testé et éventuel retour arrière |
| Conservation | Manifeste authentifié, copie privée chiffrée hors VPS, emplacement et politique de rétention approuvés |
| Conclusions | Provenance prospective établie ou incomplète ; historique H0 toujours non authentifié ; ouverture non autorisée |

Un échec de conservation empêche de déclarer la nouvelle provenance complète,
même si l'API sert. Le sort opérationnel de ce cas doit être prévu avant
intervention : garder fermé, conserver les preuves disponibles, appliquer
le chemin qualifié de récupération si nécessaire, jamais refaire une
création « pour obtenir un journal propre ».

Le NO-GO Lifecycle 10 reste indépendant. Une nouvelle baseline ne retire
pas la dette de provenance H0 et n'autorise ni migration ni ouverture.

## D. Conditions d'arrêt et retour arrière

| Instant / échec | Réponse prévue, à qualifier et autoriser |
|---|---|
| Avant première mutation | Arrêter le projet de fenêtre ; application actuelle conservée, NO-GO et preuves maintenus |
| Après arrêt, avant remplacement API | Ne pas lancer de création ; conserver la capture/erreur ; reprise éventuelle des conteneurs existants seulement par le chemin testé et après contrôle d'intégrité, de latch et des gardes |
| Après remplacement, API non saine ou delta runtime | Maintenir l'accès applicatif fermé selon la quiescence autorisée ; appliquer uniquement la configuration de repli scellée avec l'image compatible et les mêmes données, après décision |
| Hash R1 ou provenance de création non conformes | Ne pas modifier le label/attendu ni adopter le hash observé ; conserver l'ID et l'incident ; retour au repli qualifié si les conditions de sécurité le permettent |
| Clé, magasin, HMAC, schéma, compteur ou latch divergent | Arrêt incident ; aucune restauration ou réparation automatique, pas de chmod/chown, reset, downgrade ou settle ; analyse indépendante |
| Repli échoue, délai dépassé ou état durable incertain | Rester fermé ; escalade opératrice selon le plan incident préapprouvé, sans improviser un autre modèle |

### Garantie et limites du repli

Le repli n'est ni l'une des familles 280/300/362 rebaptisée H0, ni un hash
ancien obtenu artificiellement. Il est une configuration **prospective
de récupération fonctionnelle**, avec origine et valeurs explicitement
attestées à partir du relevé approuvé, même image et mêmes données.
Sa création et sa compatibilité doivent avoir été éprouvées en laboratoire.
Sans cette configuration ou son autorisation applicable : NO-GO avant C2.

Un retour au repli créerait lui aussi un nouvel ID et une nouvelle date,
avec sa propre provenance. Il ne restitue pas la création historique H0.
Les inscriptions restent disabled/fermées, plafond et compteurs conservés.

Aucune restauration de données sur les volumes actifs n'est une étape
ordinaire de rollback. Une capture n'est pas une permission de revenir
à un état antérieur effaçant admissions, comptes ou témoins. Une divergence
durable ouvre un incident distinct ; elle ne doit pas être masquée en
recopiant les magasins ou les clés.

### Opérations toujours exclues de cette procédure

Pas de migration Alembic ou lifecycle/capacity10, init, ouverture, modification
des `.env` existants, clés, droits, latch, magasins, labels ou empreintes
existantes ; pas de restauration active, suppression de volume, nettoyage
Docker/Restic, changement de réseau/Traefik, API parallèle sur données
actives ou passage outre un garde.
La future création normalement tracée de nouveaux artefacts Docker relève
uniquement d'une autorisation séparée ; elle n'est pas permise aujourd'hui.

## Verdict

**NO-GO actuel.** Ce document définit une séquence de qualification et
les arrêts attendus, pas une commande de déploiement utilisable.
La voie autorisée, les comparateurs, entrées exactes, preuves de sauvegarde,
délais et repli restent à établir hors production. Aucune opération effectuée.
