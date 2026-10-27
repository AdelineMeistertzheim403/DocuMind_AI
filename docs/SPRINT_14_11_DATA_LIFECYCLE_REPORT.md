# DocuMind AI — Sprint 14.11 : cycle de vie des données et rétention sécurisée

27 octobre 2026. Travail local uniquement. Aucun déploiement, accès VPS/B2,
suppression réelle, restauration de production, modification du verrou SQL,
changement du mode d'inscription, changement IA ou changement de
`PUBLIC_LEGAL_READY` n'a été effectué.

## Décision de sécurité

| État | Conclusion |
| --- | --- |
| Fonctions implémentées | La simulation de rétention utilise maintenant par défaut 7 jours, 4 semaines et 3 mois, est configurable pour les recettes, inscrit la politique dans son plan et conserve les garde-fous existants. La purge explicite des comptes publics non vérifiés utilise maintenant sept jours par défaut. |
| Suppression effective | Toujours désactivée : `retention_production.py --execute` refuse inconditionnellement l'exécution. Aucun `restic forget`, `prune` ou nettoyage local n'est ajouté. |
| Validation opérationnelle | Non acquise : une activation destructive exige une conception/revue séparée, une approbation humaine et une recette isolée sur la stack réellement livrée. |
| Autorisation d'ouverture | Non acquise. `REGISTRATION_MODE=disabled`, IA désactivée et verrou SQL des cinq admissions cumulatives sont inchangés. |

## 1. Mécanisme de rétention préparé

`tools/retention_production.py` conserve son fonctionnement exclusivement en
simulation et applique désormais les valeurs par défaut suivantes :

| Niveau | Nombre de périodes occupées conservées | Règle de calendrier |
| --- | --- | --- |
| Quotidien | 7 | Jours Europe/Paris |
| Hebdomadaire | 4 | Semaines ISO Europe/Paris |
| Mensuel | 3 | Mois Europe/Paris |

Les paramètres de simulation `--daily-retention`,
`--weekly-retention` et `--monthly-retention` permettent une recette avec une
politique différente. Chaque valeur doit être un entier de 1 à 365 ; une valeur
invalide échoue fermée. Le rapport de plan contient `retention_policy` et la
raison de toute suppression théorique, par exemple `outside-7d-4w-3m`.

Le plan ne propose aucune suppression lorsque l'inventaire change pendant
l'analyse, qu'une archive locale ou distante est incohérente, qu'une vérification
échoue ou qu'un risque de disque/notification est détecté. Il conserve le
snapshot quotidien le plus récent seulement après vérification complète de ses
fichiers, conserve le dernier répertoire local nommé et ne propose jamais de
supprimer ensemble une archive locale et son snapshot distant associé.

Ces contrôles préservent au moins une copie distante confirmée, et une copie
locale appariée lorsqu'elle existe. En cas d'incertitude, le plan passe en
`attention-required` ou échoue ; l'exécution reste refusée. Cette preuve
technique de cohérence n'est pas encore un exercice de restauration
opérationnellement approuvé.

## 2. Simulations, audit et alertes

La simulation continue de produire un rapport privé, horodaté, atomiquement
persisté avec empreinte du plan, empreinte d'inventaire, inventaires exclus,
éventuelles suppressions théoriques, octets potentiellement récupérables et
fichiers vérifiés. Elle n'inclut ni secrets Restic/B2, ni contenu documentaire,
ni adresse utilisateur.

Les alertes de rétention réutilisent le mécanisme de notification minimalisé :
un échec réseau/lecture distant, une archive incohérente, un changement
d'inventaire, un verrou concurrent, la maintenance de sauvegarde ou un échec
de notification empêche une proposition exploitable et produit un événement
sanitisé. Les erreurs sont dédupliquées par l'état privé existant.

Les verrous de déploiement/rétention, le marqueur de maintenance des sauvegardes,
la validation du `current` et du schéma, les contrôles d'intégrité des archives
et la vérification Restic restent obligatoires. Le mécanisme ne contourne pas
la chaîne d'approbation de release ni l'ancre de confiance externe.

## 3. Purge des comptes non vérifiés

La commande locale `backend.account_admin purge-pending` conserve le dry-run par
défaut et requiert `--execute` pour toute mutation. Son seuil par défaut passe
de 48 heures à **168 heures (7 jours)** ; l'opératrice peut encore spécifier un
seuil explicitement compris entre 48 et 720 heures pour une intervention
exceptionnelle.

Avant une purge, le mécanisme exige un compte public non vérifié, non désactivé,
sans demande de suppression existante, sans lien de vérification encore valide,
sans document, ni réservation ou usage IA. En exécution il désactive le compte,
crée la demande de suppression puis réemploie le flux de purge contrôlé.
Le compteur SQL `issued_count` n'est jamais diminué : une admission non vérifiée
ou supprimée ne restitue pas de place.

## 4. Suppression de compte et résidus

1. La demande utilisateur désactive le compte et révoque ses sessions.
2. Une purge administrative explicite refuse de continuer si un worker,
   une réservation ou un travail d'indexation incompatible est en cours.
3. Les documents actifs et leurs données liées sont supprimés via les contrôles
   d'intégrité existants, puis les résultats RAG, jetons de compte et utilisateur
   sont supprimés.
4. L'identifiant de propriétaire et les données de comptabilité pseudonymisées
   peuvent demeurer afin d'empêcher un contournement de quota/budget.
5. Les archives de sauvegarde ne sont pas modifiées par la suppression active ;
   elles restent jusqu'à expiration de la politique lorsqu'elle sera activée.

Une erreur ou un état de fichier incertain doit arrêter la purge et faire l'objet
d'une réconciliation administrative. Aucun texte ne doit promettre un effacement
physique instantané dans toutes les copies.

## 5. Réconciliation après restauration

Avant de remettre en service une restauration :

1. Restaurer uniquement dans une cible isolée, identifier le snapshot par son
   identifiant complet et vérifier les empreintes, manifeste, inventaire,
   schéma, documents, compteur et verrou.
2. Garder les demandes de suppression et les décisions d'exécution dans un
   registre opérationnel minimal, distinct de la sauvegarde restaurée.
3. Comparer ce registre au contenu restauré ; pour chaque demande postérieure
   au snapshot, désactiver le compte, révoquer les sessions et rejouer le flux
   administratif de suppression après contrôle des workers/réservations.
4. Vérifier que le compteur d'admissions reste monotone, re-sceller le verrou
   public et ne jamais réinitialiser une admission depuis une copie ancienne.
5. Produire un relevé minimisé des identifiants internes, décisions et résultats,
   puis faire valider l'absence de résidu avant toute remise en service.

Le registre, ses durées de conservation, l'identité de son responsable et la
preuve d'une restauration complète restent à concevoir et à approuver. Une
restauration de production ne doit pas servir de test de cette procédure.

## 6. Activation progressive et retour au mode non destructif

L'activation n'est pas implémentée dans ce sprint : le refus de `--execute` est
volontaire. Lorsqu'une conception séparée sera approuvée, la progression minimale
est la suivante :

1. Exécuter uniquement des simulations quotidiennes dans le service existant et
   examiner les plans, alertes, snapshots confirmés et espace disque.
2. Réaliser une restauration complète dans un environnement isolé à partir d'un
   snapshot B2 identifié, puis valider la réconciliation des suppressions.
3. Faire revoir un mécanisme d'exécution distinct, à privilèges limités, qui
   exige une release attestée, un registre d'approbation humaine hors du plan,
   un plan frais dont l'inventaire est inchangé, les verrous exclusifs et une
   nouvelle vérification avant chaque suppression.
4. Séparer explicitement la suppression de snapshots de tout `restic prune`,
   imposer des limites de nombre/volume et arrêter au premier écart.
5. Activer au plus une opération supervisée après autorisation VPS/B2 explicite.
   Une alerte, un échec de réseau, une archive non vérifiée ou une limite
   dépassée doit arrêter l'opération.

Le retour au mode non destructif consiste à désactiver l'unité d'exécution
distincte et à laisser l'unité de simulation intacte. Il ne faut ni supprimer
les marqueurs de maintenance, ni contourner les verrous, ni relancer une
suppression par commande manuelle.

## 7. Tests réalisés

`pytest tests/test_retention.py tests/test_public_beta.py -q` : **84 réussis**.
La campagne couvre notamment les plans non destructifs, snapshots/archives
incohérents, inventaire distant modifié, erreurs de réseau et de notification,
verrous, marqueurs de maintenance, refus de `--execute`, conservation de copies
protégées, configuration 7/4/3 et limites invalides, ainsi que la purge
simulée/exécutée sur fixtures et la conservation du compteur cumulatif.

Les tests ont utilisé un répertoire temporaire isolé parce que le répertoire
temporaire partagé Windows n'était pas accessible. Aucun test n'a contacté B2
ni modifié une sauvegarde réelle.

## 8. Points nécessitant décision ou validation de l'exploitante

- [ ] Approuver les règles calendaires exactes et l'application de 7/4/3 aux
  sauvegardes locales et B2.
- [ ] Désigner le responsable des simulations, alertes, preuves de restauration
  et réconciliation des suppressions.
- [ ] Définir le registre minimal des suppressions postérieures aux sauvegardes,
  ses accès et sa durée de conservation.
- [ ] Vérifier les snapshots, service units, locks, accès B2/Restic et
  notifications sur le VPS, sans divulguer de secrets.
- [ ] Valider un exercice de restauration isolé et un test de reprise avant de
  proposer une unité destructive.
- [ ] Concevoir, faire attester et approuver séparément toute activation de
  suppression ; le plan de simulation ne vaut jamais autorisation.
- [ ] Mettre à jour les documents juridiques uniquement après mise en œuvre et
  validation opérationnelle des durées et procédures.

## Fichiers modifiés

- `tools/retention_production.py`
- `backend/account_admin.py`
- `tests/test_retention.py`
- `tests/test_public_beta.py`
- `docs/SPRINT_14_11_DATA_LIFECYCLE_REPORT.md`
