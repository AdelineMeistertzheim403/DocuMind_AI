# Docnelo — préparation de la bêta publique à dix utilisateurs

**Dossier de référence : 5 novembre 2026. Décision : NO-GO.**
Audit documentaire et statique, sans intervention sur l'application ou le VPS.
Révision de départ : `1bc1a4a5bb49395acabdce5e7604d1a6b97dea61`,
**avec modifications locales et livraisons hors de cet arbre Git**.
Le dépôt courant, la candidate qualifiée et la production sont trois objets distincts.

```text
BETA_10_GO=false
REGISTRATION_OPENING_AUTHORIZED=false
P4_GO=false
P4_FORMAL_B1_CLOSED=false
```

## Diagnostic

Le chantier n'est pas à reprendre de zéro. **La capacité durable dix existe déjà
dans une candidate isolée**, commit
`8b11d4daf47bd7c3c6766b9f5231ea8a84fdbf71`, image déclarée
`sha256:32a1516206d9e648e3741b54dc0543c0b455f22cdf676e7d69d9a971e1f4213d`.
Ses traces locales donnent **227 tests API/PostgreSQL/lifecycle, 50 BFF et
11 contrôles opérateur réussis**, ainsi qu'un round-trip PostgreSQL/lifecycle
réel sur données synthétiques. Les quinze sources du manifeste candidat et
les 37 fichiers du payload ont été vérifiés par SHA-256 pendant cet audit.
Ce n'est ni un nouveau passage des tests, ni une qualification de l'état VPS.

Le passage cinq → dix, la migration additive des témoins, le refus de la
onzième admission, la concurrence sur la dernière place, les commits incertains
et le rapprochement avec un ancien dump ont donc des preuves spécifiques :
**ne pas redévelopper ces mécanismes ni demander une nouvelle recette complète
sans changement de leur périmètre**. En revanche, la branche principale locale
conserve des bornes à cinq et des gardes synthétiques : changer seulement une
variable d'environnement ne permet pas de promouvoir cette candidate.

Les obstacles utiles à traiter sont maintenant :

| Priorité | Écart réel | Travail minimal restant |
|---|---|---|
| 1 | Cible effective et voie de transition non qualifiées : provenance de création API H0 non authentifiée, dérive Compose non résolue | Collecte fraîche autorisée et décision sur les gardes applicables ; aucune exception à un garde refusant |
| 2 | Exigence d'approbation administrative non démontrée dans le profil public standard | Fixer la règle de cohorte ; si approbation préalable obligatoire, implémenter et tester ce verrou, sans assimiler vérification e-mail et approbation |
| 3 | Web R2 renvoie 404 au téléchargement ; suppression document/compte refusée sous durabilité stricte non synthétique | Qualifier le correctif BFF déjà présent en développement ; traiter séparément le protocole opérationnel d'effacement et ses recours |
| 4 | Reprise complète, fraîcheur indépendante et rollback compatibles dix non qualifiés sur la chaîne réellement retenue | Un exercice ciblé complet, isolé et autorisé ; conserver les acquis des round-trips et du durcissement |
| 5 | Textes encore brouillons/cinq, promesses de conservation non étayées ; recette finale et exploitation effective inconnues | Nouvelles versions approuvées, rétention démontrée, E2E et contrôles opératoires ciblés |

Références détaillées, criticités et actions : `BETA_10_READINESS_MATRIX.md`
et `BETA_10_BLOCKERS.md`. Aucun pourcentage d'avancement n'est attribué :
les preuves n'ont pas toutes le même périmètre, la même version ou le même poids.

## Réponses aux dix questions de décision

### 1. Qu'est-ce qui fonctionne et est suffisamment validé pour dix ?

**Sur la candidate fermée uniquement** : admissions cumulatives 1 à 10,
onzième refusée, course de deux APIs/connexions PostgreSQL, fermeture sans
remise à zéro, migration des témoins, refus en état pending, restauration
des copies à dix et détection d'un ancien compteur contradictoire.
Les sessions, reset et protections documentaires ont des tests locaux réussis
dans ce dossier. Le Web R2 dispose aussi de tests UI/BFF et de vues navigateur
sur API simulée. **Aucun parcours global n'est déclaré prêt en production**
pour dix personnes sur cette seule base.

### 2. Quels sont les véritables blocages ?

La liaison release/configuration/VPS et la voie autorisée de transition ;
l'approbation préalable si elle est obligatoire ; les parcours téléchargement
et effacement dans le profil retenu ; la reprise complète et fraîche ;
l'information légale approuvée ; la recette de bout en bout et les conditions
d'exploitation effectivement vérifiées. L'isolation intercomptes reste un
critère critique à confirmer sur l'assemblage exact, même si ses tests API
existent et passent dans les traces candidates.

### 3. Quels travaux ne pas recommencer ?

L'implémentation capacity10 et sa recette locale, la migration SQL `0007`
déjà présente selon l'opératrice, le rebranding R2 qualifié localement, les
composants de durcissement restore déjà corrigés en développement, les
contrôleurs OCI et la mesure des 9 771 contenus P3. Ne pas réinitialiser
`issued_count`, recréer les magasins ou reconstruire P3 pour cet audit.
Une adaptation de release doit réutiliser les preuves applicables, puis
tester seulement ses deltas et leur intégration.

### 4. Quels contrôles demandent surtout une preuve ciblée ?

État VPS frais, images et chaîne complète des overrides, schéma/compteurs/
témoins/latch, SMTP réel et délivrabilité, HTTPS et réseau effectifs,
ressources disponibles, réception des alertes, restauration distante de
l'ID exact, isolation de deux comptes via le BFF cible et rollback fermé
compatible dix. Ils ne justifient pas de réécrire leurs mécanismes par défaut.
**NON VÉRIFIÉ — CONTRÔLE DYNAMIQUE REQUIS**, hors de cet audit.

### 5. Quels problèmes nécessitent réellement du code ?

Le verrou d'approbation par compte **si la règle demandée est maintenue** ;
le parcours opérationnel d'effacement aujourd'hui refusé ; la publication
cohérente de nouveaux textes et du plafond dix dans l'UI. Le correctif BFF
de téléchargement et ses tests existent déjà dans le workspace : il faut
en faire un delta revu et qualifié, pas le réinventer. Le sealer du restore
est également déjà appelé dans le code de développement : sa qualification
Linux/intégrée reste à établir, pas son absence à corriger à nouveau.

### 6. P4 est-il obligatoirement sur le chemin critique ?

**Aucune dépendance technique obligatoire à la nouvelle base P4 n'est établie
par les pièces examinées.** La filière bêta existante/capacity10 hérite d'une
image Python 3.13 ; le chantier P4 porte une nouvelle base Python 3.11.
Le dossier candidate et les runbooks bêta ne subordonnent pas leur code à
l'exécution de P4. En revanche, seule une décision de périmètre habilitée peut
confirmer qu'une qualification distincte de l'infrastructure actuelle est
admise. Si P4 est choisi ou imposé par la politique de sécurité, B1 à B7
deviennent des prérequis, sans exception.

### 7. Peut-on ouvrir sur l'infrastructure actuelle ?

**Voie techniquement envisageable, pas actuellement autorisée ni suffisamment
qualifiée.** Elle doit avoir ses propres identités, preuves de sécurité,
sauvegarde, reprise, tests et décision. Le seul changement public/10 sur
l'API historique ne suffit pas. Le plan de réconciliation H0/R1 n'autorise
aucune transition et interdit de contourner les gardes.
Ni le NO-GO P4 ni les NO-GO Lifecycle/S2 existants ne sont levés ici.

### 8. Quelles sont les cinq prochaines actions les plus utiles ?

1. Choisir et faire approuver le périmètre de qualification, la règle
   d'approbation des personnes et la voie autorisée malgré le blocage H0.
2. Obtenir un relevé opérateur frais, expurgé et ancré des identités,
   configurations, compteurs, témoins, latch et ressources, sans ouvrir.
3. Clore les deltas de parcours : BFF téléchargement, effacement strict,
   éventuelle approbation préalable ; conserver capacity10 scellée.
4. Réunir la preuve de reprise complète/fraîche et de rollback fermé à dix,
   en laboratoire isolé, avec les outils de la release choisie.
5. Finaliser les nouvelles informations utilisateurs, puis la recette E2E,
   SMTP/alertes et le dossier de décision humaine limité à dix.

### 9. Quels travaux paralléliser ?

Après choix du périmètre : collecte opérateur, revue juridique/conservation,
revue des deltas UI/BFF/effacement et préparation du laboratoire de reprise.
Leurs résultats convergent vers **une seule release figée** avant recette
finale. P4 peut continuer en parallèle si une filière indépendante est
formellement retenue ; sinon ses barrières restent sur le chemin critique.

### 10. Quelles conditions exactes pour un GO limité ?

Tous les critères du document `BETA_10_GO_NO_GO.md` doivent être satisfaits,
reliés à la même release et signés par un décideur habilité : absence de
critère critique non vérifié, dix admissions cumulatives sans recyclage et
cohorte totale maîtrisée, approbation conforme à la règle retenue, confidentialité,
parcours promis fonctionnels, reprise/rollback sûrs, information approuvée,
exploitation disponible et autorisation d'ouverture distincte. Un GO futur
ne serait ni un GO IA, ni un GO P4, ni une clôture B1/C5.

## Limites décisives

Le contrôle des ancres B1 et des preuves locales est direct ; les exécutions
Debian et les états de production restent des faits historiques rapportés.
L'archive B1 prouve A, conserve **B=ERROR/20**, et n'accorde pas C.
La fiche indépendante est un formulaire non signé. La cause du blob reste
`ROOT_CAUSE_NOT_ESTABLISHED`. Aucun dossier inaccessible n'a été rendu lisible,
aucune recherche exhaustive des sources externes n'est revendiquée.
