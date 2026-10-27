# DocuMind AI — Sprint 14.10 : conformité opérationnelle et finalisation juridique

27 octobre 2026. Audit local documentaire et de code, sans accès au VPS, aux
paramètres de production, à B2, au fournisseur SMTP ou aux données réelles.
Aucune purge, restauration, modification de configuration, ouverture
d'inscription ou activation IA n'a été effectuée.

## Décision de préparation

| État | Conclusion |
| --- | --- |
| Développement terminé | Partiel : les routes publiques de brouillons juridiques, le verrou SQL à cinq admissions cumulatives, la désactivation IA et les contrôles de sauvegarde/restauration de recette existent. |
| Politique approuvée | Non : les durées proposées restent des choix à valider ; la rétention effective est volontairement non activée. Les textes affichés sont des brouillons. |
| Autorisation d'ouverture | Non acquise : `REGISTRATION_MODE=disabled`, `PUBLIC_LEGAL_READY` reste inchangé et aucune décision distincte d'ouverture n'est justifiée. |

Cette conclusion ne constitue pas un avis juridique. Les qualifications, bases
légales, obligations sectorielles et obligations de médiation doivent être
validées pour les usages et les personnes réellement visés.

## 1. Audit technique et écart avec la politique proposée

| Sujet | État observé | Écart / décision à prendre |
| --- | --- | --- |
| Logs techniques | Rotation Docker `json-file` de 10 Mo, trois fichiers par service ; API sans access log. | Rotation par taille, pas conservation calendaire de 90 jours. Les logs Traefik, OS, alertes et prestataires n'ont pas été vérifiés. Définir les sources, la finalité, le responsable et une suppression vérifiable à 90 jours avant de l'annoncer. |
| Sauvegardes | Création quotidienne locale et Restic/B2, contrôles d'intégrité et rapport d'échec. `retention_production.py` est en simulation. | Aucun `forget`, `prune`, nettoyage local ou suppression de snapshot n'est activé. La stratégie documentée conserve 7 jours, 4 semaines et **6 mois**, alors que la proposition demande 3 mois pour les mensuelles. Ne pas présenter les 7 j / 4 sem. / 3 mois comme opérationnels. |
| Restauration | La recette isolée sauvegarde, vérifie les empreintes, restaure dans une base de test et vérifie documents, quota et verrou. | La procédure est testable sans toucher aux données réelles, mais aucun exercice périodique de restauration ni vérification B2 de production n'est prouvé. Prévoir un test approuvé sur cible isolée et une procédure de réapplication des suppressions après restauration. |
| Comptes non vérifiés | `public-registration purge-pending` simule par défaut ; exécution explicite disponible. | Le seuil actuel est configurable de 48 à 720 h, avec défaut de 48 h. Une purge à 7 jours est possible en paramétrage, mais aucun planificateur ni preuve d'exécution périodique n'existe. Une purge ne rend jamais une place du quota. |
| Documents et comptes | La suppression active supprime les objets liés après confirmation SQL ; la fermeture désactive et révoque avant purge administrative. Un nettoyage de fichier peut être différé si l'état est incertain. | Pas de conservation automatique pendant la vie du compte suivie d'une suppression selon une procédure vérifiée ; pas de réconciliation documentée des copies de sauvegarde. Ne pas garantir un effacement instantané ou complet de toutes les copies. |
| Demandes RGPD | Canal de contact et brouillon de politique présents ; conservation minimale de preuves seulement évoquée. | Aucun registre de dossiers, critère de justification, échéance de trois ans, purge ni contrôle d'accès spécifiques n'est démontré. |
| Inactivité | Aucun mécanisme de revue à 12 mois identifié. | Définir la notion d'inactivité, l'information éventuelle, le workflow de revue et l'absence de suppression automatique sans décision validée. |
| Cinq inscriptions | Le compteur SQL est cumulatif, le seuil public est cinq, les admissions non vérifiées et supprimées consomment une place ; la restauration de recette re-scelle le verrou. | Conforme à la contrainte. Ne pas modifier le verrou, le compteur, ni utiliser une purge pour recycler une admission. |
| IA et ouverture | `REGISTRATION_MODE=disabled` par défaut, IA désactivée et contrôlée côté API. | À conserver. Aucun changement de `PUBLIC_LEGAL_READY`, de l'IA ou du mode d'inscription ne relève de ce sprint. |

## 2. Modifications nécessaires, sans exécution destructive

Avant une approbation de politique, concevoir puis faire revoir séparément :

1. un inventaire de toutes les sources de logs et de sauvegardes, avec un
   planificateur, une journalisation d'exécution, des alertes d'échec et une
   conservation calendaire réellement contrôlée ;
2. un workflow idempotent de purge des comptes non vérifiés à sept jours, de
   revue des comptes inactifs à douze mois, et de traitement des demandes de
   suppression, chacun avec simulation, approbation explicite et preuves
   minimisées ;
3. une procédure de suppression post-restauration : enregistrer les demandes
   en attente, réconcilier la copie restaurée avant remise en service et
   documenter le délai de disparition des sauvegardes ;
4. un registre à accès restreint des demandes RGPD, avec motif de conservation,
   date de clôture et expiration paramétrable jusqu'à trois ans seulement
   lorsqu'elle est justifiée ;
5. des tests sur fixtures et bases/volumes isolés : dry-run de chaque purge,
   calcul de chaque échéance, échec de suppression, tentative de restauration,
   réconciliation et non-régression du quota cumulatif.

Les contrôles existants permettent ces tests sans supprimer de données réelles :
simulation de `purge-pending`, tests de recette avec base indépendante, contrôle
d'empreintes et restauration isolée. Toute exécution réelle sur VPS, B2 ou
sauvegarde exige une autorisation séparée.

## 3. Fondements RGPD et rôles à valider

| Finalité effective | Données principales | Base à faire valider | Rôle attendu |
| --- | --- | --- | --- |
| Création, authentification, session, vérification email et récupération | Email, identifiant, secret dérivé, statut, jetons hachés, session | Exécution du contrat/mesures précontractuelles ; sécurité à documenter si distincte | DocuMind est responsable de traitement. |
| Hébergement, consultation et analyse classique demandés par l'utilisateur | Fichiers, noms, métadonnées, texte extrait, résultats | Exécution du service ; qualification à confirmer pour les contenus professionnels | Pour un particulier utilisant son propre compte, DocuMind détermine en principe les moyens et finalités du service. Pour un client professionnel important ses données métier pour son propre compte, DocuMind peut être sous-traitant pour ces contenus : contrat art. 28, instructions, sécurité, sous-traitants ultérieurs et assistance à prévoir. |
| Sécurité, anti-abus, journalisation et prévention de fraude | Événements techniques, tentatives, données de session limitées | Intérêt légitime, après mise en balance et information | DocuMind responsable de traitement ; les prestataires techniques sont à qualifier et encadrer. |
| Sauvegarde, reprise et intégrité | Copie des données applicatives et documentaires | Nécessaire à la fourniture/sécurité ; durées proportionnées à documenter | Même rôle que les données source ; prestataires de backup à encadrer. |
| Exercice des droits et réclamations | Identité, demande, décision, preuve minimale | Obligation légale ou intérêt légitime selon la demande et le droit applicable | DocuMind responsable de traitement. |

L'acceptation des CGU ne vaut pas consentement général. Aucun consentement n'est
à déduire pour une future IA ; elle est désactivée. Confirmer les entités
contractantes, régions, accès, sous-traitants SMTP/sauvegarde/hébergement,
transferts éventuels et catégories de documents réellement autorisées avant de
finaliser la politique.

## 4. Téléchargement, export, fermeture et durée de bêta

Les rapports/exportations du client desktop sont documentés, mais aucun endpoint
authentifié clairement identifié ne démontre le téléchargement individuel du
fichier source ou un export exhaustif des documents pour l'application web.
La suppression de résultats IA/embeddings ne prouve pas cette capacité.

**Un préavis de fermeture de 30 jours ne doit donc pas être approuvé** avant une
recette sur compte de test qui vérifie, pour chaque document, le téléchargement
du fichier original et l'export des données utiles, les autorisations, les
erreurs, les volumes limites, le maintien des liens pendant le préavis et
l'information des utilisateurs. Prévoir une alternative d'assistance si une
exportation autonome échoue.

Une bêta initiale de six mois est techniquement envisageable seulement comme
décision de calendrier : aucun mécanisme ne l'implémente ou ne la vérifie.
Les CGU actuelles contiennent des dates de brouillon incompatibles avec une
promesse ferme de six mois et indiquent que les modalités de récupération et de
préavis restent à définir. Définir date de début, date/condition de fin,
préavis, canal de notification, disponibilité de l'export et traitement après
fermeture avant toute publication.

## 5. Réclamations et consommateurs

Les brouillons prévoient un contact, la CNIL pour les droits relatifs aux données
et signalent que les modalités de réclamation doivent être précisées. Ils ne
désignent pas de médiateur de la consommation. Si le service est proposé à des
consommateurs et que la réglementation française applicable l'exige, identifier
un médiateur compétent, adhérer si nécessaire et publier ses coordonnées ainsi
que les modalités de saisine après tentative de réclamation directe. Cette
qualification doit être validée avant approbation des CGU ; ne pas inventer un
médiateur.

## 6. Cookies, stockages navigateur et traceurs

| Élément constaté | Finalité | Consentement |
| --- | --- | --- |
| Cookie de session `__Host-…`, `Secure`, `HttpOnly`, `SameSite=Strict` | Authentification et sécurité d'accès | A priori exempté lorsqu'il reste strictement nécessaire ; informer dans la politique. |
| Protection CSRF associée aux écritures | Sécurité de session | A priori exemptée lorsqu'elle reste strictement nécessaire. |
| `localStorage` / `sessionStorage` applicatifs | Aucun usage identifié dans le code ou les recettes consultés | Aucun consentement à recueillir sur cette base ; confirmer en recette navigateur. |
| Analytics, publicité, pixels ou SDK tiers | Aucun traceur identifié dans le code consulté | Aucun bandeau de consentement n'est justifié par les preuves actuelles. Tout ajout ultérieur non nécessaire exige une analyse préalable et, le cas échéant, un consentement avant dépôt/lecture. |

L'inventaire doit être rejoué dans un navigateur sur la stack réellement
livrée, y compris les ressources tierces, le BFF, les pages publiques et les
flux d'erreur. L'absence de code applicatif ne prouve pas l'absence de traceur
ajouté par l'hébergeur, un CDN ou un outil de support.

## 7. Corrections des documents juridiques

Les documents de `frontend/src/legal/documents.ts` sont des brouillons et
doivent le rester jusqu'à validation. Les corrections à préparer, sans transformer
une hypothèse en garantie, sont :

- remplacer le tableau de sauvegardes uniforme de trois mois par la politique
  approuvée, seulement lorsqu'elle est effectivement mise en œuvre ; à défaut,
  décrire le critère de conservation sans durée ferme ;
- ne présenter les sept jours pour comptes non vérifiés, 90 jours de logs, trois
  ans de dossiers RGPD et douze mois d'inactivité qu'après décision, mécanisme
  et responsable opérationnel identifiés ;
- conserver la distinction entre désactivation, purge administrative, suppression
  de fichiers et expiration des sauvegardes ; ne pas promettre d'effacement
  physique instantané ;
- compléter les rôles, finalités, bases, destinataires, régions/transferts,
  sous-traitants, droit applicable, réclamations et médiation uniquement avec
  des faits contractuellement vérifiés ;
- remplacer les dates de bêta brouillon par des dates/modalités approuvées, et
  n'ajouter le préavis de 30 jours qu'après recette d'export ;
- archiver chaque texte approuvé, son identifiant, son empreinte, sa date et la
  décision de validation ; faire correspondre l'URL HTTPS et
  `PUBLIC_TERMS_VERSION`, sans modifier `PUBLIC_LEGAL_READY` dans ce lot.

## 8. Blocages et validations restantes

### Blocages avant approbation de la politique

- [ ] Décider les durées proposées et le périmètre exact des logs, sauvegardes,
  demandes, documents et comptes ; faire approuver l'écart de six à trois mois
  pour les mensuelles.
- [ ] Implémenter et tester les mécanismes de rétention, purge, traçabilité et
  réconciliation, sans toucher au verrou SQL.
- [ ] Prouver sur environnement isolé une restauration complète et la gestion
  des suppressions post-restauration.
- [ ] Confirmer l'export/téléchargement individuel avant tout préavis de 30 jours.
- [ ] Qualifier les rôles RGPD, prestataires, contrats, régions et transferts.
- [ ] Identifier le cadre de réclamations et, si applicable, le médiateur
  compétent.
- [ ] Réaliser l'inventaire navigateur de production des cookies et traceurs.

### Validations restantes avant toute autorisation d'ouverture

- [ ] Faire approuver les textes finalisés et leur archivage ; les brouillons ne
  suffisent pas.
- [ ] Vérifier les URLs publiques, HTTPS, l'accès anonyme, l'acceptation de la
  version exacte et les informations de contact réelles.
- [ ] Vérifier avec autorisation les timers, B2/Restic, SMTP, logs et restauration
  sur la stack effective sans afficher de secrets ni de données utilisateur.
- [ ] Obtenir une décision d'ouverture distincte du développement et de
  l'approbation de politique.

Jusqu'à ces validations, conserver `REGISTRATION_MODE=disabled`, l'IA
désactivée, `PUBLIC_LEGAL_READY` inchangé, les mécanismes existants de sécurité
et de sauvegarde, ainsi que le verrou SQL de cinq inscriptions cumulatives.

## Sources examinées

- `docs/SPRINT_14_8_LEGAL_READINESS_REVIEW.md`
- `docs/SPRINT_14_9_LEGAL_PAGES_IMPLEMENTATION_REPORT.md`
- `docs/SPRINT_14_7_PUBLIC_BETA_OPENING_RUNBOOK.md`
- `docs/sprint-9-retention.md` et `docs/sprint-7-backups.md`
- `tools/backup_production.py`, `ops/testing/validate_beta_recipe.py`,
  `backend/account_admin.py`, `backend/config.py` et `compose.production.yaml`
- `frontend/src/legal/documents.ts` et `frontend/src/legal/README.md`
