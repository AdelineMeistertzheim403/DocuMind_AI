# Fiche de décision — bêta publique limitée à dix

**NON SIGNÉE — AUCUNE APPROBATION PRÉSUMÉE.**
Dossier de référence : 5 novembre 2026.

```text
DECISION=NO-GO
BETA_10_GO=false
REGISTRATION_OPENING_AUTHORIZED=false
P4_GO=false
P4_FORMAL_B1_CLOSED=false
formal_b1_contents_closed=false
```

Cette fiche constate les conditions manquantes. Elle ne modifie aucun NO-GO
antérieur, ne remplace aucune autorisation de migration/déploiement et ne
permet aucune ouverture. La mise à disposition de ce formulaire n'est pas
un acte du décideur.

## Identification du périmètre à décider

| Champ | Valeur |
|---|---|
| Décideur habilité, rôle et habilitation | **À renseigner** |
| Relecteur indépendant | **À renseigner** |
| Date/heure avec fuseau | **À renseigner** |
| Référence d'autorisation et signature vérifiable | **À renseigner** |
| Release, Git, images, architecture et manifeste définitifs | **À renseigner** ; HEAD local audité n'est pas la release complète |
| Filière : existante qualifiée distinctement / nouvelle P4 | **À décider explicitement** |
| Règle d'approbation administrative et cohorte existante/invitée | **À renseigner** |
| Fenêtre de validité et fraîcheur exigée des preuves | **À renseigner** |
| Responsable d'exploitation et suppléant | **À renseigner** |
| Référence du plan de fermeture et du repli compatible dix | **À renseigner** |

## Grille cumulative de GO

Chaque condition doit être satisfaite pour le **même assemblage définitif**,
avec la preuve citée et son approbation. Les statuts ci-dessous sont ceux
du contrôle de décision, pas une négation des acquis locaux.

| Gate | Condition exacte d'ouverture | État actuel | Référence / preuve encore requise |
|---|---|---|---|
| GO01 — Périmètre et infrastructure | Filière approuvée ; identités des images/outils et provenance/configuration effectives attestées ; tous gardes applicables passent sans exception | BLOQUANT | A01–A07/F05 ; H0 non authentifié, R1 non créée ; dossier frais et voie de transition autorisée |
| GO02 — Frontière sécurité | HTTPS vérifié, proxy de confiance exact, API/DB/volumes non accessibles publiquement, secrets privés, confinement d'extraction fail-closed effectif, aucun critique non vérifié | NON VÉRIFIÉ | A05/A06/B05/D01 ; recette réseau/TLS/image exacte |
| GO03 — Comptes | Authentification, expiration, logout/reset/révocation opérationnels ; approbation conforme à la règle autorisée ; pas d'accès avant les conditions requises | BLOQUANT | B01–B06/B04 ; API testée mais approbation préalable standard non démontrée et E2E incomplet |
| GO04 — Quota/cohorte | Dix admissions publiques cumulatives maximum, onzième sans attribution, courses/échecs/pending sûrs ; compteur non recyclé ; total de personnes autorisées compatible dix ; close/reopen maîtrisés | PARTIEL | C01–C09 ; candidate testée 8b11, non assimilée à la production ; cohorte et fermeture borne dix à compléter |
| GO05 — Confidentialité/données | Aucun accès intercompte, aucune fuite de fichiers/erreurs ; stockages et droits maîtrisés ; download et parcours documentaires promis fonctionnels | BLOQUANT | D01–D07 ; isolation API testée, assemblage non qualifié ; Web R2 download 404 |
| GO06 — Droits/effacement | Demandes et effets d'effacement traitables, confirmés et traçables ; holds/incertitudes et non-résurrection maîtrisés ; recours approuvé et réalisable | BLOQUANT | D05/D06/H03 ; garde strict non synthétique refuse les parcours concernés |
| GO07 — Sauvegarde/reprise/rollback | Capture cohérente complète, récupérable hors VPS, restaurée et vérifiée isolément ; fraîcheur indépendante, HMAC/receipts, quota fermé non diminué ; repli compatible dix | BLOQUANT | E01–E07/F01 ; round-trip synthétique réussi, chaîne complète effective et revue S2 manquantes |
| GO08 — Parcours | Navigateur/BFF/API/PG/lifecycle/SMTP qualifiés ensemble ; UI/API dix cohérents ; erreurs contrôlées ; fonctions IA exclues effectivement désactivées | BLOQUANT | G01–G10 ; P04 BLOCKED ; delta téléchargement/effacement et recette finale nécessaires |
| GO09 — Information/conformité | Nouvelles versions légales approuvées, anciennes inchangées, URLs/versions/acceptations cohérentes ; prestataires/flux/droits/conservation applicables et preuves disponibles | BLOQUANT | H01–H05 ; brouillons et promesses non étayées ; avis juridique à obtenir selon sujets |
| GO10 — Exploitation | Ressources/marge capture suffisantes, disponibilité/API/PG/disque/backup observables, alertes reçues, responsables et incident/fermeture exercés | NON VÉRIFIÉ | I01–I04 ; scripts/tests présents ≠ installation effective |
| GO11 — P4 si retenu/imposé | B1/C5 décidés par personnes habilitées, B2–B7 qualifiés et autorisations d'exécution/déploiement séparées | BLOQUANT | F02–F04 ; A identique seulement, B=ERROR/20, C non accordé |
| GO12 — Acte final | Tous critères applicables satisfaits, preuves fraîches liées aux hashes, revue indépendante et décision explicite limitée dix, puis autorisation d'ouverture distincte | BLOQUANT | J01–J03 ; décideur/date/signature non renseignés |

GO11 ne devient **NON APPLICABLE** à une filière distincte qu'après décision
écrite de périmètre et de politique. Cela ne change ni `P4_GO=false`, ni le
refus B1, ni les gardes applicables à cette autre filière.

## Résultats acquis à annexer, pas à refaire

- Candidate fermée 8b11 : 227 tests API/PostgreSQL/lifecycle, 50 BFF et
  11 opérateur ; round-trip synthétique dix et stale zéro refusé, P01/P02.
- Sources candidates 15/15 et payload 37/37 conformes aux manifestes locaux,
  vérifiés dans cet audit ; ces sommes ne sont pas une signature humaine.
- Web R2 : qualification graphique/UI/BFF locale, P03 ; **download 404 reste
  un résultat défaillant**, pas une réserve effacée par 134 autres tests.
- B1 : archive et fiche indépendantes conformes aux deux ancres opératrice,
  quatre sous-manifestes/18 entrées vérifiés ; A=9 771 contenus identiques,
  B=20, C non accordé. Fiche non signée.
- Durcissement restore et quarantaine : acquis de développement/in-process,
  scopes Windows/synthétiques distincts d'une qualification globale Linux/S2.

## Réserves et risques résiduels

Les dix comptes ne suppriment pas les risques de fuite intercompte, perte de
données, compte compromis ou impossibilité de traitement des droits.
Les sessions/limiteurs RAM mono-processus, l'interruption d'exploitation,
les délais SMTP, les quotas logiques et les limites fonctionnelles doivent
être expliqués et acceptés dans le périmètre approuvé.

Les risques critiques non vérifiés ne peuvent être acceptés tacitement.
Une limite méthodologique telle que l'absence de source indépendante après
perte simultanée des preuves impose une reprise fermée, pas un GO par
égalité de copies anciennes. Les conditions applicables de sortie de
quarantaine doivent rester distinctes de la validation des copies.

## Bornes d'un éventuel acte futur

L'autorisation, si les gates sont ensuite satisfaites, devra préciser :
maximum dix admissions cumulatives sans recyclage ; traitement des personnes
historiques/invitées ; règle d'approbation ; images/configuration exactes ;
IA/demo/legacy désactivés ; responsables, fenêtre, critères d'arrêt et
fermeture ; pas de promotion P4/C5 implicite ; pas d'extension de population
ou de fonctions sans nouvelle décision.

**Critères d'arrêt immédiat à définir dans la procédure autorisée** :
fuite/accès étranger, garde en refus, compteur incohérent/pending, erreur
d'intégrité ou de fraîcheur, backup invalide, impossibilité de fermeture,
défaillance de droits, ressources critiques ou alerte non traitable.
Fermer les nouvelles admissions ne signifie ni supprimer les comptes,
ni restaurer un ancien dump, ni diminuer `issued_count`.

## Décision actuelle, non signée

**NO-GO — ouverture non autorisée.**

Avis du décideur : **À renseigner après levée documentée des conditions**.
Réserves levées / preuves finales / dates : **À renseigner**.
Nom, rôle, date, référence et signature : **Non renseignés**.

La seule décision exprimée par ce dossier reste conservatoire ; aucune
case d'acceptation n'est précochée.
