# Sprint 14.9 — Pages légales en préparation

26 octobre 2026. Travail local sur `preparation/sprint-14-review`, sans commit,
push ou déploiement. Les trois rapports non suivis du Sprint 14.8 sont préservés.
Référence : [audit juridique technique](SPRINT_14_8_LEGAL_READINESS_REVIEW.md).

## Résultat

Les routes `/mentions-legales`, `/confidentialite`, `/cgu` sont publiques,
déclarées hors `RequireAccount`. Elles rendent des textes statiques sans session
et sans requête API. Elles réutilisent les composants de navigation et classes
visuelles existantes, avec titres et sections sémantiques.

**Les trois documents sont des brouillons non approuvés.** Cette mention figure
sur chaque page et les liens. Les informations absentes sont explicitement à
compléter, sans identité, adresse, durée ou garantie inventée. La page ne prétend
pas vérifier les conditions juridiques d'ouverture. Les textes sources, lisibles
et modifiables en revue, résident dans `frontend/src/legal/documents.ts`.

## Fichiers du lot

| Fichier | Modification |
| --- | --- |
| `frontend/src/App.tsx` | Trois routes publiques et route de version des CGU, hors garde de session. |
| `frontend/src/pages/Legal.tsx` | Page documentaire commune, avertissement permanent, navigation et liste des versions ; refus d'une version inconnue. |
| `frontend/src/legal/documents.ts` | Brouillons mentions/confidentialité/CGU et registre de versions explicites. |
| `frontend/src/legal/README.md` | Procédure de révision, archivage et correspondance future des paramètres. |
| `frontend/src/pages/Account.tsx` | Liens locaux sur les formulaires et `/legal`, erreur API explicite sur le portail ; corrections suppression/sauvegardes/IA. |
| `frontend/src/components/Layout.tsx` | Liens permanents dans le footer ; stockage serveur privé et IA indisponible pour la bêta, plutôt que promesse de stockage sur l'appareil. |
| `frontend/src/components/Workspace.tsx` | Confirmation de suppression distinguant données actives, nettoyage et sauvegardes. |
| `frontend/src/pages/Legal.test.tsx` | Onze cas supplémentaires : accès sans session/API, navigation, version, refus des versions absentes/spéciales, footer et formulaire fermé sur panne. |
| Ce rapport | Résultats, limites et décisions restantes. |

Aucun changement backend, BFF, migration, workflow, dépendance ou configuration.
L'apparition d'un CRLF introduit par l'écriture Windows a été corrigée dans les
quatre fichiers édités pour conserver les fins LF du dépôt et un diff ciblé.

## Version des CGU et séparation des brouillons

Version locale : **`beta-2026-10-26-draft-1`**. Lien stable :
`/cgu/versions/beta-2026-10-26-draft-1`. `/cgu` désigne la version courante.
Les versions inconnues, y compris les propriétés héritées JavaScript, affichent
une page « Version des CGU introuvable », sans substitution silencieuse.

Pour toute modification ultérieure, ajouter une nouvelle entrée et conserver
l'ancienne avec son texte intégral. Git et le registre donnent une traçabilité,
pas une garantie de stockage immuable. Une future version approuvée devra porter
un statut explicite revu ; les anciens brouillons ne doivent pas devenir approuvés
par changement global d'un libellé. Archiver version, texte, empreinte, date et
preuve de décision selon la procédure décrite dans le README.

Les liens locaux sont distingués des **documents configurés par l'exploitant**
retournés par `/auth/options`. Les liens et `terms_version` utilisés par le
formulaire d'acceptation restent ceux de l'API, sans remplacement par le brouillon.
Le test historique vérifie toujours l'envoi de la version configurée. La panne
API laisse les brouillons lisibles, mais n'autorise pas une inscription.

Après approbation seulement, préparer une URL HTTPS absolue pointant sur la
version approuvée avec `PUBLIC_TERMS_VERSION` identique ; les mentions et la
confidentialité doivent également pointer sur leurs textes réellement validés.
`PUBLIC_LEGAL_READY` n'est ni lu pour certifier ces pages ni modifié ici : sa valeur
future doit résulter d'une décision humaine, pas de la réussite des tests.

## Contenu et décisions restantes

Les brouillons décrivent les faits techniques : cinq admissions cumulatives,
vérification email, stockage serveur de fichiers/texte/analyses, sessions,
désactivation du compte avant purge administrative, sauvegardes distinctes,
possibles erreurs de nettoyage, fonctions IA indisponibles pour la bêta initiale.
Ils ne promettent pas une purge automatique, un effacement instantané de toutes
les copies, un envoi d'email garanti ou une localisation exclusive en France.

À fournir et valider par l'exploitante, avec conseil juridique adapté :

- identité et statut complets, coordonnées, directeur de publication, mentions
  d'immatriculation pertinentes et hébergeur contractuel exact ;
- responsable de traitement, rôles pour les contenus clients, finalités/bases,
  droits et canal d'exercice, catégories de documents admises et public éligible ;
- entités, régions, accès, contrats et transferts pour hébergement, SMTP,
  sauvegardes et alertes ; OVH/B2 restent des indications du projet à confirmer ;
- durées effectives par catégorie, purge et suivi des demandes, traces de quotas,
  comptes non vérifiés, archives locales/B2, logs et réapplication des suppressions
  après restauration ; aucune modification de la conservation dans ce lot ;
- gratuité/prix, durée et fin de bêta, propriété des documents, usages interdits,
  suspension, assistance, responsabilités et droit applicable ;
- validation et archivage de la version approuvée, communication des changements,
  correspondance entre texte présenté et version acceptée.

Les conditions d'ouverture du runbook et les risques SQL-01, SQL-03, RF10-03 et
RF10-04 ne sont pas clos par ces pages. L'acceptation des CGU ne vaut ni consentement
général aux traitements ni autorisation d'une future fonction IA.

## Tests exécutés

| Commande / contrôle | Résultat |
| --- | --- |
| `npm.cmd run test:ui -- --reporter=dot` (version finale) | **63 réussis**, 11 fichiers, 0 échec/ignoré ; 4,79 s. |
| `npm.cmd run test:bff` | **50 réussis**, 0 échec/ignoré/annulé ; 861 ms. |
| `npm.cmd run build` | TypeScript et Vite réussis sur la version finale. |
| `git diff --check` | Réussi après maintien des fins de ligne LF. |

Le premier lancement Vitest dans le sandbox Windows a échoué avant les tests
sur une permission de lecture esbuild. Exécution locale avec permissions adaptées
réussie ; aucune désactivation de test ou protection applicative. La première
suite à 61 succès a été suivie de la version finale à 63 après ajout des deux
cas de propriétés héritées. Ne pas additionner ces campagnes.

Les tests de routes utilisent `AppRoutes` et MemoryRouter sans compte. Ils vérifient
l'absence d'appel `account.me` et `account.options` depuis les trois documents.
Les tests historiques d'inscription restent inchangés et réussissent, notamment
liens configurés HTTPS, acceptation, version transmise et indisponibilité.
Pas de nouvelle campagne Python (backend inchangé), test navigateur E2E, recette
Docker ou visite de production revendiqués. Le rendu mobile/clavier réel et le
chargement direct HTTPS sur la future stack restent à contrôler avant livraison.

## Checklist : deux décisions distinctes

### Développement local

- [x] Trois routes anonymes avec contenu statique et avertissement de brouillon.
- [x] Liens permanents dans footer, portail et formulaires.
- [x] Textes de stockage/suppression/IA corrigés sans changer leur implémentation.
- [x] Version explicite, registre d'archives, refus des versions inconnues.
- [x] Panne API : textes locaux lisibles, inscription fermée.
- [x] Tests frontend/BFF et build réussis ; modifications existantes préservées.
- [ ] Revue humaine du diff, validation visuelle/navigateur et autorisation de publication Git.

### Autorisation d'ouverture — non acquise

- [ ] Toutes les informations obligatoires complétées et vérifiées.
- [ ] Trois textes approuvés par l'exploitante avec validation juridique adaptée.
- [ ] Versions archivées, URL finales et version API cohérentes ; aucun brouillon
  présenté comme conditions approuvées à accepter.
- [ ] Politiques de conservation/suppression réelles validées et opérationnelles.
- [ ] Prestataires, transferts, contacts et exercice des droits validés.
- [ ] Recette des pages publiques en HTTPS, sans session et après fermeture.
- [ ] Prérequis techniques/opérationnels du runbook et risques résiduels traités.
- [ ] Autorisations distinctes de livraison et d'ouverture, IA toujours désactivée.

**Développement local prêt pour revue ; documents non approuvés et ouverture
publique non autorisée.** Aucun changement de `.env.production`,
`REGISTRATION_MODE`, quota, verrou SQL, IA ou politique effective de rétention.
