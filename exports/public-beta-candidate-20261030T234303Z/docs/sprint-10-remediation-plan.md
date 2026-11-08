# Sprint 10 — plan de remédiation proposé

Date : 20 octobre 2026. Ce plan accompagne [l'audit de phase A](sprint-10-security-audit.md).
Il **n'autorise aucune correction, mise à jour, modification du VPS ou ouverture publique**.
La phase B ne commence qu'après validation explicite de l'administratrice, sur un périmètre
convenu. Les inscriptions publiques et l'IA doivent rester désactivées.

## Ordre proposé et critères d'acceptation

Les priorités représentent l'ordre de travail proposé, pas une affirmation de compromission.
P0 = décision préalable à l'ouverture ; P1 = durcissement nécessaire dans la préparation ;
P2 = amélioration et validation complémentaire. Aucune durée ferme n'est estimée sans conception.

| Priorité | Constat | Travail à proposer en phase B | Critère de sortie vérifiable |
|---|---|---|---|
| P0 | SEC10-01 | Concevoir une frontière d'extraction sans secrets ni réseau, distincte de l'API | Tests Linux : accès aux autres documents, DB et secrets impossible ; ressources bornées ; PDF/TXT toujours compatibles |
| P0 | SEC10-02 | Authentifier/admettre l'upload avant sa réception et borner les corps simultanés | Token absent/invalide/expiré rejeté avant spool ; chunked borné ; capacité tmpfs/concurrence vérifiée localement |
| P0 | SEC10-03 / INFO10-02 | Valider la frontière BFF/API et l'état réseau réel | Aucune exposition API/DB publique ; provenance obligatoire ou exception API explicitement conçue ; headers non usurpables |
| P1 | SEC10-04 | Ajouter une piste d'audit sécurité minimale, sans données sensibles | Succès/échecs sensibles traçables et corrélés ; tests d'absence de mots de passe/tokens/documents dans les logs |
| P1 | SEC10-05 | Migrer l'outillage de tests vers des versions corrigées maintenues | Nouvel audit complet/prod, tests React/BFF, TypeScript et build ; aucun outil de dev dans l'image runtime |
| P1 | SEC10-06 | Compléter les locks Linux, inventaires de build et contrôles de vulnérabilités | Transitifs couverts, images scannées, entrées vérifiées et digests finaux conservés ; exceptions motivées |
| P1 | INFO10-02 | Revoir droits d'exploitation, secrets et procédures d'incident/restauration | Revue administrative documentée, sans afficher les secrets ; permissions des volumes/archives contrôlées |
| P2 | INFO10-01 | Formaliser la politique PDF et les évolutions de restitution | Extraction distincte de certification d'innocuité ; revue obligatoire avant aperçu/téléchargement original |
| P2 | Tests manquants | Étendre tests navigateur, PostgreSQL et cas concurrents | Matrice de sécurité automatisée avec données fictives et parcours bout en bout sur stack jetable |

## Lot 1 — conception du confinement et de l'admission

Définir le protocole entre API et extracteur : référence d'entrée contrôlée, lecture seule,
aucun nom utilisateur comme chemin d'exécution, format de sortie JSON borné, timeout et
codes d'erreur. Le processus d'extraction ne doit recevoir ni environnement applicatif,
clé BFF, identifiants DB, secrets SMTP, clé IA ni vue du volume documentaire complet.
La compatibilité du moteur de bureau et de l'analyse classique reste un critère explicite.

Choisir une isolation Linux adaptée : UID/service séparé et permissions, réseau interdit,
montages minimaux, restrictions de syscalls et plafonds CPU/mémoire/processus/sortie. La simple
création d'un subprocess ou l'ajout d'un antivirus ne satisfait pas ce critère.
Évaluer séparément la permission requise pour administrer un worker : ne pas monter le socket
Docker dans l'API pour lui permettre de créer arbitrairement des conteneurs.

Placer le contrôle de session avant le coût de réception/parsing multipart. Garder une limite
sur le flux reçu même lorsque Content-Length manque ou ment, avec concurrence/temporaire
bornées avant cette réception. Vérifier le comportement en cas de client déconnecté et de
requête interrompue ; ne pas laisser de fichiers temporaires ou de réservations incohérentes.

Les tests de capacité devront viser une stack locale jetable avec limites conservatrices.
Pas de PDF d'exploitation réel, de bombe non bornée ni de test de charge sur le VPS.

## Lot 2 — frontières d'accès et non-régression d'isolation

Décider explicitement si toutes les routes privées doivent exiger identité utilisateur **et**
preuve de provenance BFF en production. Si une API Bearer directe est souhaitée plus tard,
elle doit avoir son propre contrat réseau/TLS et ne pas hériter implicitement de la sécurité
du navigateur. La clé de service ne doit jamais donner accès au propriétaire partagé.

Établir une matrice paramétrée pour chaque route privée : Alice, Bob, aucune session, jeton
invalide, expiré, révoqué, compte désactivé, clé service seule, token sans provenance, identifiant
inexistant et ressource étrangère. Vérifier statut, absence de texte/nom privé, absence de
modification, absence d'appel fournisseur et absence de réservation de coût injustifiée.

Inclure les accès indirects : comparaison de deux comptes, caches et historiques, sources,
embeddings, statuts d'indexation, étapes intermédiaires de résumé, reprise/annulation de jobs.
Répéter sur une base PostgreSQL/pgvector **neuve, dédiée et jetable**, jamais en réutilisant
une URL de production. Les tests de concurrence doivent vérifier les contraintes réelles
PostgreSQL pour invitations, reset, quotas et budgets.

Conserver les cookies `__Host-`, Secure/HttpOnly/Strict et la signature CSRF liée à la session.
Tester HTTPS terminé par un Traefik de test : IP de proxy exacte, faux X-Forwarded refusés,
Host et Origin adverses, CSRF absent/invalide/d'une autre session, methods et chemins non autorisés.
Un parcours Playwright local devra aussi couvrir logout/ancien cookie/retour arrière/multi-
onglets et disparition du contenu mis en cache après expiration. Les redirections UI actuelles
réinitialisent l'instance du document ; la rétention de données dans un autre onglet reste à tester.

## Lot 3 — journal de sécurité et supply chain

Proposer un schéma minimal : date UTC, type d'action, succès/refus, identité pseudonymisée
si connue, ressource opaque si utile, identifiant de corrélation et catégorie d'erreur bornée.
Définir qui peut lire les journaux et leur durée de conservation avant implémentation.
Les données de trafic et l'IP peuvent être utiles mais doivent être minimisées selon le besoin.
Ne pas réactiver une journalisation brute des corps ou headers pour compenser le manque d'audit.

Planifier la mise à jour Vitest en vérifiant les exigences de Node/Vite/TypeScript ; ne pas
appliquer un `audit fix --force` global. Les avis Tinypool exigent une chaîne de pollution de
prototype et ne prouvent pas une RCE publique : vérifier les chemins pertinents et les nouvelles
versions effectives. Conserver les jobs PR sans secrets de publication et l'approbation manuelle
du déploiement. Aucun push ne doit déclencher une mise en production.

Produire un lock complet adapté aux plateformes Linux construites, inventorier les transitifs
et bibliothèques des images, conserver des empreintes vérifiées et établir un calendrier de
renouvellement des bases. Ajouter des scans Python, npm et images avec règles d'échec et
exceptions revues. Un score de scanner seul ne décide pas de l'exploitabilité ; documenter
l'exposition, les préconditions et les mesures compensatoires de chaque exception.

## Revue administrative à programmer séparément

Cette revue distante n'a pas été effectuée et ne fait pas partie d'une action autorisée par
la remise du présent plan. L'administratrice devra valider son périmètre avant exécution.

- Identifier la release active et les digests réels ; comparer au code audité et aux inventaires.
- Vérifier localement sur le VPS l'absence de publication API/DB, les seuls réseaux nécessaires,
  l'adresse réelle Traefik approuvée, les règles X-Forwarded et la chaîne HTTPS/cookies/HSTS.
- Confirmer `REGISTRATION_MODE=disabled` et `AI_ENABLED=false` sans imprimer de secrets ;
  ne pas changer ces valeurs pendant une inspection.
- Examiner les modes et propriétaires des répertoires documentaires, releases, scripts,
  archives et configurations privées ; ne pas élargir les permissions pour faire passer un test.
- Revoir le rôle Docker du compte de sauvegarde, ses accès B2 et l'intégrité des helpers.
  Ne pas supprimer ce rôle au hasard : la reprise et les sauvegardes doivent continuer à fonctionner.
- Vérifier les journaux réels et leur rotation, les timers et les incidents non résolus.
  Le Sprint 9 doit rester en simulation, exécution réelle refusée.
- Revoir la restauration indépendante et la politique de conservation des données supprimées.
  Aucune purge ni restauration sur les volumes de production ne découle de cette liste.

## Critères de fermeture et passage éventuel à l'ouverture

Chaque constat doit obtenir un correctif revu et ses tests, ou une acceptation de risque explicite
précisant responsable, justification, mesures compensatoires, durée et échéance de réévaluation.
Les incertitudes d'exposition de SEC10-03 et INFO10-02 doivent être levées par des preuves
d'exploitation ; un simple test unitaire ne peut pas les fermer.

Avant décision d'ouverture : relecture des correctifs, tests de sécurité complets, comparaison
des images validées et de la release cible, sauvegarde/restauration indépendante revue,
procédure d'incident/révocation, politique documentaire et de conservation approuvée.
Tout déploiement suivra ensuite son approbation propre. L'ouverture des inscriptions ou de
l'IA reste une décision distincte, jamais une conséquence automatique d'un audit réussi.

**Statut de livraison : plan proposé, phase B non commencée.**
