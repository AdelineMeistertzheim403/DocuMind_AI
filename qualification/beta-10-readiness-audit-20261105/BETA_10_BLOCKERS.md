# Blocages réels et priorités

**NO-GO.** Les références de contrôle renvoient à la matrice, qui donne
fichiers, lignes, dates et validité. Ne pas additionner les lignes d'agrégation
G/J aux problèmes dont elles découlent. Une absence de preuve dynamique
n'est pas qualifiée de vulnérabilité démontrée.

## Indispensables avant toute ouverture

| Priorité | Contrôles | Nature et justification | Minimum pour lever le blocage |
|---|---|---|---|
| P0-1 | A03/A04/C07/J01 | **Cible non attestée et transition non autorisée.** Le code capacity10 est qualifié localement, mais root/ancienne filière restent bornés cinq ; le hash H0 de création API n'a pas de provenance authentifiée. Une simple bascule public/10 ou un accord humain de valeurs ne fait pas passer le garde | Relevé frais privé/expurgé, release exacte et chaîne de création/configuration ; voie de transition qualifiée et autorisée où chaque garde applicable passe |
| P0-2 | D03/A05/B05 | **Confidentialité et frontière de confiance de l'assemblage non vérifiées.** Tests API d'isolation déjà présents ; ils ne prouvent pas les réseaux/ports/volumes/proxy effectivement servis | Deux comptes synthétiques via BFF exact, tests d'accès croisé sur liste/détail/download/delete, URLs directes et API ; aucun octet étranger ni contournement |
| P0-3 | E02/E03/E04/E06/F01 | **Reprise complète et fraîche non qualifiée.** Round-trip dix et composants restore déjà testés, mais pas la chaîne retenue entière, le témoin survivant indépendant ni le rollback après sixième admission | Capture/restauration isolée DB + documents + cinq SQLite + deux clés + latch ; intégrité, HMAC, compteurs, non-résurrection et fraîcheur ; quota fermé ; repli compatible dix ; revue S2 applicable |
| P1-1 | B04/C08/G02 | **Règle d'admission incohérente avec l'approbation annoncée.** En standard public, e-mail + mot de passe permettent l'activation sans accord administratif préalable identifié. Block/release n'est pas une file d'approbation obligatoire | Décision de cohorte explicite ; si approbation maintenue, état/verrou et tests d'absence d'accès avant accord. Toute modification de cette exigence exige une autorisation distincte |
| P1-2 | D04/C09 | **Téléchargement Web R2 défaillant et intégration dix non démontrée.** Les 50 tests BFF n'attestent pas le téléchargement : la recette des images R2 confirme 404. Le correctif et ses tests existent dans le workspace, pas dans R2 scellé | Petit delta Web versionné et qualifié avec streaming, session, propriété, headers et erreurs ; recette finale sur backend choisi |
| P1-3 | D05/D06/H03 | **Effacement/recours non opérationnels sous profil strict.** La garde refuse la suppression et la demande de compte, même dans la candidate admissions dix. Les purges durables sont explicitement refusées | Protocole opérationnel revu de demande/confirmation/effet/réconciliation, ou périmètre fonctionnel réduit explicitement approuvé avec traitement manuel des droits réellement qualifié ; aucune désactivation de durabilité ni activation synthétique |
| P1-4 | H01–H05 | **Information non approuvée et conservation non étayée.** Brouillons, plafond cinq, identifiant historique réutilisé dans le workspace, dates de bêta à revoir, promesses 7j/90j/3mois/3ans sans preuve d'application | Nouvelles versions immuables approuvées, URLs/API/UI/acceptations cohérentes, flux/prestataires vérifiés, politique de conservation et de droits applicable ; avis juridique sur les points requis |
| P1-5 | B03/C09/G01/I02–I04/J02/J03 | **Recette finale, exploitation et autorisation manquantes.** L'ancien E2E est BLOCKED, même si ses contrôles de refus passent ; l'état VPS, SMTP, marge machine et alertes ne sont pas observés ici | E2E isolé du même assemblage, délivrabilité et supervision qualifiées, responsable/suppléant, fermeture exercée, dossier signé et limité dix |

Les trois P0 sont des critères de sécurité/données critiques. Ils ne peuvent
être transformés en réserve « après ouverture ». Les P1 restent nécessaires
pour la bêta décrite, mais plusieurs se résolvent par **preuve/recette ou
publication maîtrisée**, pas par une refonte.

## Conditions dépendant du périmètre d'architecture

### Filière P4

F03/F04 : B1 non clôturé, anomalie OCI entière non approuvée, métadonnées
incomplètes, provenance et B2–B7 ouverts. La mesure A des 9 771 contenus
et les 35/46 tests sont des acquis, pas une autorisation. **Si la bêta déploie
P4 ou si la politique impose cette base, toutes ces barrières restent
préalables.** Aucun build ni essai d'exécution n'est autorisé par cet audit.

### Filière existante/capacity10 distincte

F05/A03 : les artefacts prouvent qu'une filière héritant de l'API Python 3.13
est étudiée indépendamment de P4 Python 3.11. Cela peut éviter d'attendre P4,
mais **pas** de qualifier sa propre sécurité et sa reprise. Il manque une
décision habilitée d'applicabilité et une transition autorisée. Le plan
H0/R1 dit explicitement qu'aucune voie autorisée n'est établie ; ne pas le
transformer en permission prospective. Ne pas passer directement à Compose,
renommer un hash attendu ou fabriquer une nouvelle signature pour écarter
un refus.

La sélection de candidate capacity10 exige son protocole/témoins/outillage
compatible, pas seulement la variable `PUBLIC_REGISTRATION_LIMIT=10`.
Le profil Beta Lite à cinq n'est pas un substitut qualifié pour dix.

## Améliorations pouvant attendre, sous conditions

| Amélioration | Pourquoi hors chemin minimal | Limite à respecter |
|---|---|---|
| Recherche globale, dossiers, tags, renommage | Non démontrés comme fonctions promises nécessaires ; recherche locale paginée déjà explicite | Ne pas annoncer une recherche sur toute la bibliothèque |
| IA, RAG et clés personnelles fournisseur | Explicitement exclus de la phase initiale | IA/demo/legacy effectivement false ; refus propre, aucun appel payant |
| Supervision centralisée élaborée ou haute disponibilité | Dix personnes n'imposent pas en soi cluster/observabilité complexe | Healthchecks, alertes utiles reçues, métriques machine/PG et opérateur disponibles restent indispensables |
| Limiteurs distribués/sessions multi-workers | Le Compose décrit un worker et des sessions RAM assumées | Ne pas augmenter workers/réplicas sans qualification ; limites IP et resets restent à éprouver |
| Automatisation complète des tâches de conformité | Une procédure manuelle bornée peut être acceptable si réellement exécutable et approuvée | Aucun report des droits, de la sécurité de l'effacement ou de la conservation effective |
| Reprise de tout le rebranding | R2 dispose déjà de tests, vues et preuves locales | Corriger uniquement les nouveaux textes/écarts nécessaires, sans réécrire les versions historiques |

## Ne pas refaire par défaut

- Capacity10, migration additive, concurrence, onzième refusée, pending et
  restauration synthétique : réutiliser la candidate 8b11 et ses preuves.
- `0007` : contrôler sa présence, ne pas la rejouer ou réduire le compteur.
- Sealer et durcissement restore : déjà corrigés en développement ; qualifier
  la bonne release sur Linux plutôt que corriger un diagnostic devenu ancien.
- Comparateurs et identité régulière P3 : preuves locales B1 vérifiées ;
  conserver ERROR/20 et les différences de métadonnées.
- Tests UI/API déjà réussis : ne les rejouer que pour les deltas, le nouvel
  assemblage ou une limite d'applicabilité explicite.

Le « chemin court » n'est donc ni une reconstruction P4 précipitée, ni une
réouverture immédiate. C'est la sélection d'un périmètre autorisable, la
réutilisation des acquis, puis la clôture ciblée des écarts de parcours,
de données, d'information et de preuve effective.
