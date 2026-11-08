# Chemin minimal vers une décision limitée à dix

**Plan non exécutoire. Aucun déploiement, accès distant ou test mutateur
n'est autorisé par ce document.** Les actions futures nécessitent leurs
autorisations propres. Toute dérive d'image, de configuration ou de preuve
invalide les étapes dépendantes. Aucune durée artificielle de roadmap n'est
assignée.

## Dépendances et étapes

| Étape | Objectif | Prérequis | Actions futures soumises à autorisation | Acceptation | Preuve attendue | Risque | Dépendances |
|---|---|---|---|---|---|---|---|
| M1 | Choisir une filière et une politique de cohorte admissibles | Présent audit et décideur habilité | Décider P4 ou qualification distincte de l'existant ; préciser dix personnes/admissions, comptes historiques/invités, approbation préalable, fonctions promises ; cartographier les gardes H0/S2/Lifecycle | Périmètre écrit ; aucune garde refusée contournée ; voie de transition réellement autorisable, sinon arrêt | Décision de périmètre et politique d'applicabilité signées | Choisir l'existant pour masquer un NO-GO | Aucun |
| M2 | Établir les faits effectifs sans changer les services | Autorisation distincte de collecte et règle de confidentialité | Collecter IDs/images/versions, chaîne ordonnée Compose/overrides/env-files et empreintes, paramètres allowlist, montages/réseaux/droits, schéma/quota et agrégats de comptes, latch et témoins avec outil relu | Release/runtime identifiés ; pas d'énigme transformée en PASS ; disabled/closed et compteur préservés | Dossier frais privé, sorties expurgées, commandes/RC et manifeste avec ancre indépendante | Fuite de secrets, probe faussement readonly, effet de sidecar/lock | M1 pour portée ; la collecte limitée peut préparer la décision sans mutation |
| M3 | Réutiliser capacity10 et clore les seuls deltas fonctionnels | M1, sources candidates vérifiées | Conserver 8b11 scellée ; qualifier delta BFF download déjà écrit ; traiter effacement strict et approbation si exigée ; textes UI dix ; aucune fusion massive du workspace | Parcours promis sûrs ; profils synthétiques jamais utilisés comme solution ; tests négatifs sur chaque delta | Diff minimal, révision, inventaires, tests ciblés et lien avec acquis 227/50/11 | Refaire capacity10 ou embarquer changements étrangers | M1 ; M2 pour liaison à la cible finale |
| M4 | Qualifier reprise et retour fermé compatibles avec la cible | Release/outillage sélectionnés, autorisation laboratoire neuf | Exercer capture cohérente, récupération du snapshot exact, restore PostgreSQL/documents/cinq SQLite/deux clés/latch, fermeture quota et refus d'échecs ; rapprochement HMAC/fraîcheur/non-résurrection ; repli fermé à dix | Tous inventaires conformes, compteur jamais diminué, pending non rejoué, aucun attachement avant autorisation ; repli compatible après sixième admission | Manifestes, RC/logs, rapports DB/fichiers/stores, preuve de fraîcheur indépendante, revue S2 applicable | Détruire l'ancien état, croire qu'un hash prouve la fraîcheur, rollback vers cinq | M1 ; M3 pour tester les deltas de données ; préparation parallèle possible |
| M5 | Rendre l'information et les droits réellement applicables | Règles M1, flux effectifs identifiables | Préparer nouvelles versions CGU/notice/confidentialité et dates de bêta ; conserver archives ; vérifier entités/régions/transferts, canal support/droits, durées et moyens de traitement ; revue juridique | Documents approuvés et cohérents avec capacités réelles ; promesses prouvées ; API/UI/version/URL/empreintes concordent | Avis d'exploitante et juridique si nécessaire, hashes/URLs permanentes, preuve de conservation et traitement des demandes | Publication d'un brouillon, réécriture rétroactive d'une version acceptée | M1 ; M2/M3/M4 pour validation finale ; rédaction parallèle |
| M6 | Valider l'assemblage exact et son exploitation | M2–M5, release unique figée, autorisation de recette isolée | Recette navigateur/BFF/API/PG/lifecycle dix, SMTP captif puis délivrabilité autorisée, isolement deux comptes, download/delete/recours, fermeture et incidents ; contrôler HTTPS, ressources, backup/alertes et responsables | Aucun critique non vérifié ; scénarios TG du document de lacunes satisfaits ou exclusion explicitement justifiée ; pas de faux comptes sur VPS | Dossier E2E et exploitation daté, commandes/paramètres expurgés/RC, logs, images et manifeste | Appeler 26 refus PASS un E2E réussi ; éprouver la onzième en production | M2, M3, M4, M5 |
| M7 | Décider, sans ouvrir dans cet audit | M1–M6 complets et revue indépendante | Compléter la grille GO/NO-GO, identité/date/signature, bornes dix, critères d'arrêt et autorisation d'une éventuelle intervention ultérieure | Aucune approbation implicite ; décision reliée aux hashes et à une fenêtre de validité | Acte humain distinct ; présent document reste NO-GO | Confondre GO local fermé, permission de déploiement et permission d'inscription | M6 ; P4 B1–B7 en plus si M1 choisit/impose P4 |

## Collecte et recette : frontières à préserver

M2 n'autorise ni connexion VPS pendant cet audit, ni exécution aveugle des
commandes anciennes. Certaines CLI dites de statut peuvent ouvrir SQLite,
créer un lock ou déclencher des imports : les relire sur la **release exacte**
et vérifier leurs effets avant une future autorisation. Les secrets ne
doivent pas entrer dans un rapport public, argv, inspect brut publié ou Git.

M4 implique des écritures de laboratoire et éventuellement un accès distant :
**NON VÉRIFIÉ — CONTRÔLE DYNAMIQUE REQUIS**. M6 également. Ni les fixtures du
dépôt ni leur cleanup ne doivent pointer vers la base active, les données
historiques ou les volumes de la bêta.

Le plan ne propose aucune commande d'ouverture ou de changement de quota.
Une éventuelle procédure de déploiement sera un autre lot autorisé. Une
permission de préparation fermée ne suffit pas pour l'acte d'ouverture.

## Organisation parallèle minimale

Après M1, quatre pistes sont indépendantes : collecte de preuves M2,
revue des deltas M3, préparation de laboratoire M4 et rédaction/revue M5.
Leurs conclusions doivent converger sur les mêmes images/outils/configurations
avant M6. La collecte ne doit pas provoquer une maintenance concurrente
avec une capture. Les tests de source sans mutation historique et la revue
juridique peuvent rester parallèles.

Si une filière distincte de P4 est approuvée, poursuivre P4 séparément sans
retarder artificiellement la preuve de cette filière, mais sans aucun GO P4.
Si P4 est obligatoire, ses barrières sont des prérequis de M6, pas une piste
qu'on peut laisser ouverte au moment du GO.

## Arrêts explicites

Arrêt si : voie de transition non autorisée ; image/configuration inconnue ;
garde en refus ; compteur régressif ou témoins pending/contradictoires ;
preuve externe de fraîcheur absente ; accès intercompte ; suppression non
confirmée présentée comme réussie ; restauration incomplète ; rollback cinq
incompatible ; textes non approuvés ; SMTP/alertes indisponibles ; marge
machine insuffisante ; décideur non identifié.

Ne pas résoudre ces arrêts par changement de permissions, reset de quota,
désactivation de durabilité, flag synthétique, réécriture de preuve ou
nouveau hash attendu. Conserver les dossiers d'échec et demander une
qualification/autorisation distincte.
