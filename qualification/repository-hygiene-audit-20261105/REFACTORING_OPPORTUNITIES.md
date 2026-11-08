# Opportunites de refactoring

Aucune transformation effectuee. Priorite avant beta : preservation, selection
d'une candidate et qualification des correctifs utiles, plutot qu'un grand
refactoring. Les copies scellees ne sont jamais la cible d'une mutualisation.

## Changements internes envisageables, sans comportement voulu nouveau

| Priorite / cible | Preuve et benefice | Taille / risque / dependances | Preuves et verification a exiger |
|---|---|---|---|
| P1 - Catalogue des candidates et materiaux | 4 056 entrees dans quatre familles; rendre explicite commit, hash, tests, statut NO-GO et emplacement prive | Petit a moyen, faible si documentaire expurge; apres sauvegarde | Ancres inchangees et liens resolvables; aucune reecriture de source scellee |
| P2 - `ops\testing\validate_beta_recipe.py:28-323` | main de 296 lignes melant controles et orchestration; extraire controles purs pour faciliter revue | Moyen, moyen; figer d'abord erreurs, sorties et codes retour | Tests recette positifs/negatifs, aucune commande operateur executee sur production |
| P2 - `tools\verify_snapshot.py:34-222` | verify_capture de 189 lignes; separer lecture/validation et orchestration seulement apres specification | Moyen, eleve pour un simple nettoyage; depend des formats v3/v5/v5.1 | Corpus versions historiques, negatif corruption/manquant/permissions, tests restaure/quarantaine; nouvel outillage versionne |
| P3 - `tools\backup_local.py:218-381` | create_backup de 164 lignes, responsabilites multiples | Moyen, eleve; fermeture offline des materiaux et politique de cles d'abord | Tests backup/integrite/keys/round-trip PG+lifecycle et echec; preuves d'avant non transferables |
| P3 - `backend\main.py:79-209` | create_app de 131 lignes, lifecycle/worker/middleware/routers | Moyen, eleve car ordre des controles sensible | Lifespan, auth, admissions, saturation, quarantaine et arret; aucune extraction qui change l'ordre |
| P3 - Figures desktop anciennes et nouvelles | `interface_helpers.py:430-530` reprend les memes concepts de graphiques dans deux chemins; ancien composite probablement non appele | Petit a moyen, moyen desktop; verifier consommateurs externes | Tests donnees/figures/export et deprecation; faible valeur pour la beta web |
| P3 - Tests de quarantaine | Fixtures/harness longs, dont `test_recovery_quarantine_inprocess.py:64-214` | Moyen, moyen; mutualiser seulement ce qui ne masque pas les differences de scenario | Conserver chaque negatif latch/restored/HTTP; eviter fixture generique tout-terrain |

Une comparaison AST des corps de fonctions d'au moins dix lignes n'a trouve
**aucun doublon strict** dans les 303 fichiers actifs analyses. La repetition de
concepts ou d'orchestration n'est donc pas presentee comme une duplication exacte
demontree. Les 1 803 occurrences source/tests identiques au-dela d'une premiere
copie sont surtout des instantanes : les dedupliquer en place detruirait la
portee de leurs manifestes.

La politique de cles est deja mutualisee dans `tools\lifecycle_key_policy.py:1-30`
et importee par backup_local, verify_snapshot et validate_restore. Ne pas proposer
sa recreation comme correction nouvelle. De meme, la fermeture du quota apres
restauration existe deja dans le worktree (`validate_restore.py:344-360`).

## Changements fonctionnels ou de securite : pas de simples refactorings

| Changement | Pourquoi distinct | Porte de validation |
|---|---|---|
| Reconciliation quota cinq / candidate dix | Schema, contraintes, witnesses et semantique cumulative; trois sources courantes propres a HEAD different aussi de la candidate | Tests concurrence, admission 11, echec/pending, PG/lifecycle round-trip et provenance candidate |
| Auth, sessions, inscription, suppression compte/documents | Regles d'acces et mutation, pas renommage interne | Matrice auth/E2E, tests negatifs, revue de duree de session et d'approbation |
| Backup/restauration, latch, pending, quarantaine | Garanties de recuperation, formats et fail-closed | Qualification dediee Linux/PG, preuves S2 pertinentes, rollback autorise |
| Correctif download BFF | Change une reponse HTTP de la release R2, avec contrat binaire et erreurs | Contrats BFF et E2E authentifie sur candidate nouvelle |
| Textes juridiques et versions de consentement | Changement documentaire a effet fonctionnel/legal | Approbation et conservation des versions historiques, pas remplacement silencieux sous meme identifiant |
| DocuMind vers Docnelo dans packages, volumes, cookies ou signatures | Peut casser imports, stockage et preuves | Inventaire des contrats et migration explicite; ne pas faire un remplacement global |
| Factorisation du parsing securise TAR/manifestes entre comparateurs P4 | v1, v2 et contents-only ont des contrats et portees differents | Nouvelle version, cas negatifs propres et nouvelle empreinte; versions historiques intactes |

Avant beta, seuls catalogue et clarification documentaire apportent un benefice
immediat sans perturber le runtime. Les correctifs fonctionnels utiles peuvent
etre retenus dans une future candidate avec leurs tests, mais les refactorings
touchant durabilite/securite sont a differer sauf justification et qualification
explicites. Aucun GO ne resulte d'une amelioration d'organisation.
