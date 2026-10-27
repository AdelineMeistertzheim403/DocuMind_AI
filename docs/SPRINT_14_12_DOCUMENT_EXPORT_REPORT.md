# DocuMind AI — Sprint 14.12 : récupération et export sécurisé des documents

27 octobre 2026. Implémentation locale, sans déploiement, accès VPS/B2,
suppression de données réelles, changement du verrou SQL, activation des
inscriptions publiques ou activation IA.

## Décision

| Sujet | État |
| --- | --- |
| Téléchargement individuel | Implémenté et testé pour les documents originaux PDF et TXT accessibles au propriétaire authentifié. |
| Archive ZIP globale | Non implémentée volontairement. Le téléchargement individuel borné utilise les limites déjà appliquées à l'import et ne crée aucun fichier persistant. |
| Ouverture de la bêta | Non autorisée par ce sprint. `REGISTRATION_MODE=disabled`, IA désactivée et quota cumulatif restent inchangés. |

## 1. Audit et comportement réel

Avant ce sprint, l'API permettait de lister, consulter, analyser et supprimer un
document, mais ne proposait pas de route de téléchargement du fichier original.
Les rapports/exportations du client desktop ne démontraient pas une récupération
du fichier source par l'application web.

Une route authentifiée est maintenant disponible :

```text
GET /api/v1/documents/{document_id}/download
GET /bff/documents/{document_id}/download
```

Le BFF requiert la session personnelle HTTPS habituelle, n'accepte que cet
itinéraire GET précis et transmet le jeton de session uniquement vers l'API.
Une session absente ou expirée renvoie une erreur contrôlée ; une réponse 401
amont supprime le cookie de session, comme les autres routes privées.

## 2. Contrôles de sécurité

Avant tout envoi, l'API :

1. recherche le document avec `owned_document`, qui retourne 404 tant pour un
   identifiant inconnu que pour un document d'un autre propriétaire ;
2. accepte exclusivement le nom de stockage opaque généré par le serveur ;
3. refuse un répertoire de stockage non sûr, un lien symbolique, un fichier
   absent, un type non régulier, une taille divergente ou une empreinte SHA-256
   divergente ;
4. ouvre le fichier avec les protections anti-suivi de lien disponibles, vérifie
   son contenu sur le descripteur déjà ouvert, puis le diffuse par blocs ;
5. renvoie un `Content-Disposition` avec nom de secours généré et nom original
   encodé, sans divulguer le chemin interne ;
6. ferme le descripteur à la fin de la diffusion, y compris si le client
   interrompt le téléchargement.

Le BFF ne relaie pas arbitrairement les en-têtes amont : il valide type, taille,
Content-Disposition et borne la taille à `maxUploadBytes`, puis diffuse le flux
sans buffer applicatif complet. Les en-têtes imposent `Cache-Control: no-store`.

L'interface comporte un lien **Télécharger** dans la bibliothèque et la fiche
document. Le navigateur traite la réponse comme une pièce jointe : aucune archive
ou copie temporaire applicative n'est créée.

## 3. Limites et export global

Le fichier individuel est limité par la taille maximale d'import existante
(10 Mio par défaut, configurable côté serveur). Sa vérification complète avant
envoi ajoute une lecture du fichier, choix proportionné à cette limite et à la
garantie d'intégrité.

Une archive ZIP globale n'est pas livrée : créer un ZIP en mémoire ou sur le
disque, gérer les annulations, les quotas cumulés, la cohérence entre base et
fichiers, l'espace temporaire VPS et le nettoyage post-interruption exigerait un
design distinct. Un ZIP ne doit pas être ajouté comme simple boucle de fichiers
ou archive persistante.

Pour une évolution future, exiger au minimum : limite du nombre de documents et
du total non compressé/compressé, réservation d'espace et délai, streaming sans
chemin interne, contrôle d'accès pour chaque document, descripteurs fermés à
l'annulation, nettoyage prouvé d'un répertoire temporaire privé et tests de
pression mémoire/espace. Tant que ces garanties ne sont pas démontrées,
le téléchargement individuel constitue le parcours de récupération approuvé.

## 4. Fermeture de bêta

Avant d'annoncer un préavis de fermeture de 30 jours, vérifier sur la stack
effectivement livrée :

- le téléchargement individuel des PDF et TXT pour chaque compte concerné ;
- les limites, délais, interruption réseau, erreurs de stockage et support
  utilisateur ;
- la persistance des routes, sessions et capacité de téléchargement pendant tout
  le préavis ;
- l'information exacte sur les délais de suppression active et l'expiration
  distincte des sauvegardes ;
- une solution d'assistance contrôlée pour les personnes qui ne peuvent pas
  récupérer un fichier elles-mêmes.

Le téléchargement ne couvre pas automatiquement les données dérivées, analyses,
historique de compte ou copies de sauvegarde. Toute promesse d'export global ou
de portabilité élargie nécessite une fonctionnalité et une recette propres.

## 5. Tests et validations restantes

Les tests automatisés couvrent :

- téléchargement fidèle du contenu original, type, longueur et nom encodé ;
- absence de session, clé invalide et accès inter-compte ;
- fichier absent, contenu corrompu et identité de stockage hostile ;
- BFF : session obligatoire, diffusion contrôlée, en-têtes amont invalides
  refusés et session expirée supprimée ;
- contrôle de type TypeScript et build frontend.

Restent à valider avant toute autorisation de production :

- [ ] recette navigateur HTTPS avec les tailles, PDF et TXT réellement admis ;
- [ ] comportement réseau lent/interrompu, limites reverse proxy et timeout sur
  le VPS ;
- [ ] dimensionnement des téléchargements simultanés et journalisation minimisée ;
- [ ] décision séparée sur un éventuel ZIP global ;
- [ ] procédure de support/communication de fermeture et cohérence avec la
  politique de rétention approuvée.

## Fichiers modifiés

- `backend/api.py`
- `backend/services/documents.py`
- `frontend/server/app.mjs`
- `frontend/server/app.test.mjs`
- `frontend/src/components/DocumentTable.tsx`
- `frontend/src/pages/DocumentDetail.tsx`
- `tests/test_documents.py`
- `docs/SPRINT_14_12_DOCUMENT_EXPORT_REPORT.md`
