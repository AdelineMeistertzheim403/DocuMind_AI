# Synthese - diagnostic et plan uniquement

**REVIEW_ONLY_BLOCKED. Aucun nettoyage reel.**
Les dix livrables sont non indexes; la proposition `.gitignore` n'est pas appliquee.

```text
BETA_10_GO=false
REGISTRATION_OPENING_AUTHORIZED=false
P4_GO=false
formal_b1_contents_closed=false
```

## Reponses aux douze questions

1. **Pourquoi plus de 4 000 ?** 44 fichiers suivis modifies et 4 192 entrees non
   suivies, soit 4 236 entrees initiales. 4 056 sont dans deliveries/exports/
   candidates/qualification : accumulation d'instantanes et preuves, pas 4 000
   modifications du runtime. Deux entrees sont des racines de worktrees, donc
   4 234 fichiers ordinaires en attente au sens strict.
2. **Combien de sources ?** 1 730 fichiers classes code, plus 538 tests, copies
   historiques incluses. Hors des quatre familles : 54 code et 25 tests.
   Les 2 268 code/tests en attente n'ont que 465 contenus SHA-256 distincts;
   les copies scellees ne sont pas pour autant supprimables.
3. **Combien de generes/temporaires ?** 623 generes identifies : 596 cache npm,
   27 distributions a conserver comme preuves possibles. Cinq scripts de patch
   temporaires candidats sont encore classes code; aucun nombre exhaustif de
   fichiers jetables n'est etabli.
4. **Qu'ajouter aux exclusions ?** Caches Python/couverture racine manquants,
   venv alternatif, caches/frontend coverage locaux, variantes `.env.*` racine
   avec exceptions de modeles, cache npm R1 et cle TLS candidate par chemin exact.
   Effet principal : 597 entrees cache/cle, pas disparition des milliers de preuves.
5. **Quels sensibles suivis a tort ?** Aucun secret actuel suivi n'est demontre;
   modeles suivis non attestes surs. Un ancien PDF au nom personnel reste
   atteignable dans l'historique local; son nom est expurge. Cle TLS non suivie
   visible, dumps et archives prives sont a proteger. Pas d'assurance d'absence
   de secrets et pas de purge d'historique.
6. **Quels historiques conserver ?** Sources candidates, exports horodates,
   branding R1/R2, backup v5/v5.1, revisions recovery, P4/B1-B7 accessibles,
   comparateurs distincts, preuves, manifestes, recus et decisions NO-GO.
   Les images/dumps/archives opaques relevent d'une conservation privee controlee,
   pas d'un ajout massif a Git.
7. **Quel code supprimer a faible risque apres validation ?** Aucun module
   demontre supprimable. Ancienne fonction `creer_figure_analyse` probablement
   inutilisee, a verifier pour le desktop et les consommateurs externes.
   Scripts `.tmp_*.py` a sauvegarder/examiner, pas effacer d'office.
8. **Quels refactorings utiles avant beta ?** Catalogue des candidates, des
   materiaux et des lots; clarification de configuration/provenance.
   Differer les grandes extractions backup/durabilite. Un correctif BFF, un
   changement de quota ou d'auth n'est pas un simple refactoring.
9. **Comment tout sauvegarder ?** Historique/refs/metadonnees Git d'une part,
   travail courant avec non suivis et ignores utiles d'autre part, preuves
   scellees independantes enfin; copies privees chiffrees, manifestes SHA-256,
   controles de stabilite et restauration verifiee dans un emplacement neuf.
   Bundle/clone/diff seuls insuffisants.
10. **Comment retrouver un statut lisible sans perte ?** Vue compacte et
    consultation par perimetre maintenant; exclusions precises apres accord;
    conservation cataloguee et commits cibles apres sauvegarde. Aucun objectif
    artificiel de statut vide, ni exclusion globale des familles de preuves.
11. **Quels lots sans invalider les qualifications ?** Sauvegarde, catalogue
    expurge, documentation et regles Git ciblees peuvent laisser les bytes
    qualifies intacts. Pas de retrait automatique d'index. Toute relocalisation
    de preuve impose verification et chaine de conservation.
12. **Quels changements attendre ?** Integration dix admissions, auth/session,
    effacement, witnesses/pending/latch/quarantaine, backup/restore, dependencies,
    BFF/E2E et contrats legaux doivent appartenir a une future candidate qualifiee.
    Les 227+50+11 tests historiques ne qualifient pas le worktree actuel.

## Limites determinantes

Le statut parent est compte exactement par sorties NUL. L'inventaire physique
ignore n'est **pas exhaustif** : 115 refus de permission et deux avertissements
de fonctionnalite; aucun contournement. Les tailles des fichiers ordinaires
enumeres sont 834 314 589 octets en attente et 10 937 900 600 octets au total
hors `.git`, chemins inaccessibles et contenu interne des worktrees imbriques.
Pas de lecture privee de dumps/cles/documents ou d'archives opaques.

Le worktree a des travaux utiles absents de la candidate, tandis que six fichiers
propres a la candidate dix n'existent ni dans HEAD ni dans le worktree principal.
Ne fusionner aucun de ces objets automatiquement. Commencer la suite par une
autorisation de sauvegarde verifiable, jamais par un effacement.
